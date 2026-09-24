"""Public source-wallet research and durable overlap notices, separate from paper PnL.

No orders are placed here. One bounded background read every five minutes;
SQLite keeps source links, snapshots and notices across API/daemon restarts.
"""
from __future__ import annotations

import json
import logging
import math
import re
import sqlite3
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

import pandas as pd

from app.scorecard import wallet_scorecard
from src import copy_trading as ct
from src import prediction_markets as md

REFRESH_SECONDS = 300
SOURCE_RE = re.compile(r'https://(?:x\.com|twitter\.com)/[A-Za-z0-9_]+/status/[0-9]+(?:\?[^\s]*)?\Z')
GEOPOLITICS = re.compile(r'\b(geopolitics|ceasefire|invasion|iran|israel|ukraine|russia|nato|gaza|hamas|hezbollah|nuclear|war)\b', re.I)
LOG = logging.getLogger(__name__)
_NEXT_CHECK: dict[str, float] = {}
_CHECK_LOCK = threading.Lock()


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _connect(db_path):
    # Public research must not contend with paper-book transactions that can
    # stay open while the daemon seeds remote positions.
    path = Path(db_path).with_suffix('.intelligence.sqlite')
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS copy_watchlist (
            wallet TEXT PRIMARY KEY, sources TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS copy_intelligence (
            id INTEGER PRIMARY KEY CHECK(id=1), attempted REAL NOT NULL, payload TEXT NOT NULL);
    ''')
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _number(value, default=0.0):
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _stamp(value):
    value = pd.to_datetime(value, utc=True, errors='coerce')
    return None if pd.isna(value) else value


def _records(frame):
    # pandas' serializer converts timestamps and NaN to ISO/null, never NaN JSON.
    return json.loads(frame.to_json(orient='records', date_format='iso')) if not frame.empty else []


def import_watchlist(entries, db_path=ct.DEFAULT_DB_PATH):
    """Idempotent import. Existing pause states, labels, cash and notes survive."""
    validated = []
    for entry in entries:
        wallet = str(entry.get('wallet', '')).strip().lower()
        sources = list(dict.fromkeys(entry.get('sources') or []))
        if not md.is_polymarket_wallet(wallet) or any(not isinstance(s, str) or not SOURCE_RE.fullmatch(s) for s in sources):
            raise ValueError('A valid wallet and HTTPS X/Twitter post URLs are required')
        validated.append((wallet, sources))
    conn = ct.connect(db_path)
    try:
        existing = {row[0] for row in conn.execute('SELECT wallet FROM traders')}
        for wallet, _ in validated:
            if wallet not in existing:
                ct.follow_trader(wallet, conn=conn)
                existing.add(wallet)
    finally:
        conn.close()
    with _connect(db_path) as conn:
        for wallet, sources in validated:
            old = conn.execute('SELECT sources FROM copy_watchlist WHERE wallet=?', (wallet,)).fetchone()
            merged = list(dict.fromkeys((json.loads(old[0]) if old else []) + sources))
            conn.execute('INSERT INTO copy_watchlist VALUES (?,?) ON CONFLICT(wallet) DO UPDATE SET sources=excluded.sources',
                         (wallet, json.dumps(merged)))
            conn.commit()
        # Make new wallets eligible immediately, without deleting previous observations.
        conn.execute('UPDATE copy_intelligence SET attempted=0 WHERE id=1')
    return read_state(db_path)


def trading_style(activity, metadata):
    buys = [r for r in activity if r.get('type') == 'TRADE' and r.get('side') == 'BUY'
            and 0 < _number(r.get('price')) < 1 and _number(r.get('notional')) > 0]
    categories = defaultdict(lambda: {'notional': 0., 'markets': set()})
    hours, early, late = [], 0, 0
    for row in buys:
        key = row.get('market_key', '')
        meta = metadata.get(key, {})
        events = meta.get('events') or []
        event = events[0] if events else {}
        context = ' '.join(str(v or '') for v in [row.get('title'), row.get('event_slug'), meta.get('category'), event.get('title')])
        category = 'Geopolitics' if GEOPOLITICS.search(context) else md.market_filter_category(meta.get('category') or event.get('category'), context)
        categories[category]['notional'] += _number(row.get('notional'))
        categories[category]['markets'].add(key)
        end, entry = _stamp(meta.get('endDate')), _stamp(row.get('time'))
        if end is not None and entry is not None and end >= entry:
            h = (end - entry).total_seconds() / 3600
            hours.append(h)
            early += h >= 168
            late += h <= 24
    total = sum(_number(r.get('notional')) for r in buys)
    def weighted(predicate):
        return sum(_number(r.get('notional')) for r in buys if predicate(r)) / total if total else None
    return {
        'buy_count': len(buys), 'buy_notional': total,
        'categories': sorted([{'category': c, 'share': v['notional'] / total,
                               'notional': v['notional'], 'markets': len(v['markets'])}
                              for c, v in categories.items()], key=lambda x: -x['share']),
        'longshot_share': weighted(lambda r: _number(r.get('price')) <= .2),
        'favorite_share': weighted(lambda r: _number(r.get('price')) >= .8),
        'avg_entry': sum(_number(r.get('price')) * _number(r.get('notional')) for r in buys) / total if total else None,
        'timing_n': len(hours), 'median_hours_to_end': median(hours) if hours else None,
        'early_share': early / len(hours) if hours else None, 'late_share': late / len(hours) if hours else None,
        'timing_basis': 'Scheduled market end, not the actual resolution timestamp. Early >=7d; late <=24h.',
        'basis': 'Heuristic categories and buy-notional weighted entry prices in the loaded activity window. Longshot <=20%; favorite >=80%.',
    }


def market_overlaps(activity, now=None):
    """Net positive purchases per wallet/outcome within 24h, not current holdings.

    A source with both outcomes is explicitly mixed; multiple fills by one
    source never count as multiple wallets. Sells offset shares, not dollars.
    """
    now = _stamp(now or datetime.now(timezone.utc))
    legs = {}
    seen = set()
    for r in activity:
        stamp = _stamp(r.get('time'))
        if stamp is None or not 0 <= (now - stamp).total_seconds() <= 86400:
            continue
        if r.get('type') != 'TRADE' or r.get('side') not in ('BUY', 'SELL'):
            continue
        wallet, market, outcome = r.get('wallet'), r.get('market_key'), r.get('outcome')
        if not wallet or not market or not outcome:
            continue
        # Only deduplicate when upstream supplies a transaction identity.
        tx = r.get('transaction_hash') or r.get('transactionHash')
        identity = (wallet, tx, r.get('asset'), outcome, r.get('side'), r.get('size'), r.get('price'))
        if tx and identity in seen:
            continue
        seen.add(identity)
        key = (str(wallet).lower(), market, str(outcome).casefold())
        leg = legs.setdefault(key, {'wallet': str(wallet).lower(), 'market_key': market,
                                   'title': r.get('title') or market, 'url': r.get('url'),
                                   'outcome': outcome, 'net_shares': 0., 'buy_notional': 0., 'last_buy_at': None})
        size = max(0., _number(r.get('size')))
        leg['net_shares'] += size if r['side'] == 'BUY' else -size
        if r['side'] == 'BUY' and size:
            leg['buy_notional'] += max(0., _number(r.get('notional')))
            iso = stamp.isoformat()
            leg['last_buy_at'] = max(iso, leg['last_buy_at'] or iso)
    groups = defaultdict(list)
    for leg in legs.values():
        if leg['net_shares'] > 1e-6 and leg['last_buy_at']:
            groups[leg['market_key']].append(leg)
    result = []
    for market, participants in groups.items():
        wallets = {p['wallet'] for p in participants}
        if len(wallets) < 2:
            continue
        sides = {p['outcome'].casefold() for p in participants}
        signature = json.dumps([market, sorted((p['wallet'], p['outcome'].casefold()) for p in participants)])
        result.append({'key': signature, 'market_key': market, 'title': participants[0]['title'],
                       'url': participants[0]['url'], 'wallet_count': len(wallets),
                       'direction': 'same_outcome' if len(sides) == 1 else 'different_outcomes',
                       'participants': participants, 'last_buy_at': max(p['last_buy_at'] for p in participants)})
    return sorted(result, key=lambda r: r['last_buy_at'], reverse=True)


def merge_alerts(previous, overlaps, now):
    old = {r['key'] for r in previous.get('overlaps', [])}
    new = [{**r, 'detected_at': now, 'initial': not previous.get('snapshot_at')} for r in overlaps if r['key'] not in old]
    return (new + previous.get('alerts', []))[:100]


def fetch_wallet(wallet):
    errors = {}
    def attempt(key, fn, default):
        try:
            return fn()
        except Exception as exc:
            errors[key] = str(exc)[:250]
            return default
    profile = attempt('profile', lambda: md._get_json(f'{md.POLY_GAMMA}/public-profile', {'address': wallet}), {})
    activity = attempt('activity', lambda: _records(md.get_polymarket_activity(wallet, limit=500)), [])
    positions = attempt('positions', lambda: _records(md.get_polymarket_positions(wallet, limit=500)), [])
    keys = list(dict.fromkeys(r['market_key'] for r in activity if r.get('market_key')))
    markets = attempt('metadata', lambda: md.get_polymarket_markets_by_condition_ids(keys), []) if keys else []
    metadata = {m.get('conditionId'): m for m in markets}
    # Gamma omits some sports submarkets from condition-id lookup. The existing
    # event-slug fallback recovers their end dates; league slugs also classify them.
    missing_slugs = list(dict.fromkeys(r['event_slug'] for r in activity
                                      if r.get('event_slug') and r.get('market_key') not in metadata))
    if missing_slugs:
        fallback = attempt('metadata_fallback', lambda: md.get_polymarket_markets_by_event_slugs(missing_slugs[:100]), [])
        metadata.update({m.get('conditionId'): m for m in fallback})
    card = wallet_scorecard(wallet, refresh=True, ttl_seconds=0, fetchers={
        'smart_row': lambda _: None, 'risk_row': lambda _: None,
    })
    errors.update(card.get('errors', {}))
    # Only the canonical scalar summaries are needed on this desk. Calibration
    # buckets/attribution tables belong to the full wallet page, not this cache.
    card = {key: card.get(key) for key in ('track', 'sample', 'snapshot_at', 'calibration')}
    if card['calibration']:
        card['calibration'] = {key: value for key, value in card['calibration'].items() if key != 'buckets'}
    # Resolved/lost rows left unredeemed are not active positions.
    open_rows = [r for r in positions if _number(r.get('size')) > 0
                 and 0 < _number(r.get('current_price')) < 1]
    return {'wallet': wallet, 'name': profile.get('name') or profile.get('pseudonym') or None,
            'profile_url': md.polymarket_profile_url(wallet), 'snapshot_at': _utc_now(),
            'style': trading_style(activity, metadata), 'scorecard': card,
            'positions': open_rows, 'activity': activity, 'errors': errors,
            'activity_count': len(activity), 'activity_capped': len(activity) >= 500,
            'activity_from': min((r['time'] for r in activity if r.get('time')), default=None),
            'positions_capped': len(positions) >= 500,
            'sharpe': None, 'sharpe_reason': 'Unavailable: no complete, cash-flow-adjusted daily source-equity return series. Trade PnL is not a portfolio Sharpe.'}


def read_state(db_path=ct.DEFAULT_DB_PATH):
    with _connect(db_path) as conn:
        row = conn.execute('SELECT attempted,payload FROM copy_intelligence WHERE id=1').fetchone()
        state = json.loads(row['payload']) if row else {}
        state['watchlist'] = {r['wallet']: json.loads(r['sources']) for r in conn.execute('SELECT * FROM copy_watchlist')}
    state['refresh_seconds'] = REFRESH_SECONDS
    stamp = _stamp(state.get('snapshot_at'))
    state['stale'] = stamp is None or (pd.Timestamp.now(tz='UTC') - stamp).total_seconds() > REFRESH_SECONDS * 2
    return state


def refresh(db_path=ct.DEFAULT_DB_PATH):
    previous = read_state(db_path)
    wallets = list(previous['watchlist'])
    profiles, errors, activity = {}, {}, []
    failed_activity = set()
    def fetch(wallet):
        try:
            return wallet, fetch_wallet(wallet), None
        except Exception as exc:
            return wallet, None, str(exc)[:250]
    with ThreadPoolExecutor(max_workers=3) as pool:
        for wallet, profile, error in pool.map(fetch, wallets):
            if profile is None:
                errors[wallet] = error
                failed_activity.add(wallet)
                if wallet in previous.get('profiles', {}):
                    profiles[wallet] = {**previous['profiles'][wallet], 'stale': True}
                continue
            profiles[wallet] = profile
            if profile.get('errors'):
                errors[wallet] = profile['errors']
            if 'activity' not in profile.get('errors', {}):
                activity.extend(profile.get('activity', []))
            else:
                failed_activity.add(wallet)
            profile['recent_trades'] = [r for r in profile.get('activity', []) if r.get('type') == 'TRADE'][:10]
            profile.pop('activity', None)
    now = _utc_now()
    overlaps = market_overlaps(activity, now)
    incomplete_markets = {r['market_key'] for r in previous.get('overlaps', [])
                          if any(p['wallet'] in failed_activity for p in r['participants'])}
    for row in overlaps:
        row['partial'] = row['market_key'] in incomplete_markets
    state = {'snapshot_at': now, 'profiles': profiles, 'errors': errors, 'overlaps': overlaps,
             'alerts': merge_alerts(previous, [r for r in overlaps if not r['partial']], now), 'window_hours': 24}
    # Keep membership through failed reads, so recovery is not a new event.
    if failed_activity:
        missing = [r for r in previous.get('overlaps', []) if any(p['wallet'] in failed_activity for p in r['participants'])]
        state['overlaps'] += [{**r, 'stale': True} for r in missing if r['key'] not in {o['key'] for o in overlaps}]
    with _connect(db_path) as conn:
        conn.execute('INSERT INTO copy_intelligence VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, attempted=excluded.attempted',
                     (time.time(), json.dumps(state, allow_nan=False)))
    return state


def refresh_async(db_path=ct.DEFAULT_DB_PATH):
    """SQLite lease prevents overlapping API and daemon fetches; no request waits."""
    db_path = str(Path(db_path).resolve())
    with _CHECK_LOCK:
        if _NEXT_CHECK.get(db_path, 0) > time.monotonic():
            return
        _NEXT_CHECK[db_path] = time.monotonic() + 30
    with _connect(db_path) as conn:
        if not conn.execute('SELECT 1 FROM copy_watchlist LIMIT 1').fetchone():
            return
        changed = conn.execute('''INSERT INTO copy_intelligence VALUES(1,?,'{}')
            ON CONFLICT(id) DO UPDATE SET attempted=excluded.attempted
            WHERE copy_intelligence.attempted < ?''', (time.time() + 600, time.time() - REFRESH_SECONDS)).rowcount
    if not changed:
        return
    def work():
        try:
            refresh(db_path)
        except Exception:
            LOG.exception('Copy wallet intelligence refresh failed')
    threading.Thread(target=work, name='copy-intelligence', daemon=True).start()


def start_monitor(db_path, stop_file):
    """Keep research running even while a paper sync waits on remote services."""
    def monitor():
        while not Path(stop_file).exists():
            try:
                refresh_async(db_path)
            except Exception:
                LOG.exception('Copy research monitor could not schedule a read')
            time.sleep(30)
    thread = threading.Thread(target=monitor, name='copy-research-monitor', daemon=True)
    thread.start()
    return thread
