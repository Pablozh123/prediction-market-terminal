"""Reproduzierbare Parametersuche mit unverändertem CEX-Paper-Replay.

Aufruf: python -m scripts.cex_parameter_sweep
540 Kombinationen bei 250 ms, danach eingefrorene Auswahl bei vier Latenzen.
"""
from __future__ import annotations

import csv
import hashlib
import itertools
import json
import math
import pickle
import sqlite3
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from src.book_stream import BookState
from src.cex_leadlag import Config, replay

OUT = Path('outputs/cex_parameter_sweep/20261011')
TRAIN = Path('data/cex_leadlag/20261009T173058Z-fb372f')
LATENCIES = (100, 250, 500, 1000)
LOOKBACKS = (500, 1000, 2000)
HOLDS = (1000, 2000, 5000, 10000, 20000)


def trade_result(arm):
    """Nur die durch Verdichtung exakt erhaltenen Handelsgrössen übernehmen."""
    summary = {k: v for k, v in arm['summary'].items()
               if k not in {'quote_responses', 'censored_responses', 'median_response_ms'}}
    summary['floor_pnl'] = summary['cash'] - arm['config']['cash']
    assert math.isclose(summary['cash'] + summary['entry_cost_open'],
                        arm['config']['cash'] + summary['realized_pnl'], abs_tol=1e-7)
    for trade in arm['trades']:
        if trade['net_pnl'] is not None:
            assert math.isclose(trade['net_pnl'], trade['exit_vwap'] * trade['shares']
                                - trade['exit_fee'] - trade['entry_gross'] - trade['entry_fee'], abs_tol=1e-7)
    return {**{k: arm[k] for k in ('config', 'latency_ms', 'signals', 'trades', 'skips', 'diagnostics')},
            'summary': summary}


def query_times(rows, lookbacks, holds, latencies, minimum_threshold=.5):
    """Superset aller möglichen Signal-, Einstiegs- und Ausstiegszeitpunkte."""
    queries = set()
    history = {window: deque() for window in lookbacks}
    offsets = {int(delay * 1e6) for delay in latencies}
    offsets.update(int((delay + hold) * 1e6) for delay in latencies for hold in holds)
    for row in rows:
        if row['kind'] != 'price' or row['source'] != 'binance':
            continue
        tick = row['t_ns']
        queries.add(tick)
        candidate = False
        for window, ticks in history.items():
            ticks.append((tick, row['price']))
            target = tick - window * 1e6
            while len(ticks) > 1 and ticks[1][0] <= target:
                ticks.popleft()
            if ticks[0][0] <= target and target - ticks[0][0] <= 2000 * 1e6:
                move = (row['price'] / ticks[0][1] - 1) * 10000
                candidate |= abs(move) >= minimum_threshold
        if candidate:
            queries.update(tick + offset for offset in offsets)
    return sorted(queries)


def compact_events(rows, queries, shares=10):
    """Exakte Bücher an allen Handelsprüfzeitpunkten, mit Originalzeitstempel.

Keine zeitlichen Bins: Frische und Reihenfolge bleiben erhalten. Auf die
Tiefe für die feste Stückzahl begrenzt. Kursreaktionsstatistiken entfallen.
"""
    books, latest, selected, kept = {}, {}, {}, []
    query_index = 0

    def cap(levels, reverse):
        remaining, result = shares, []
        for price in sorted(levels, reverse=reverse):
            size = min(remaining, levels[price])
            result.append([price, size])
            remaining -= size
            if remaining < 1e-9:
                break
        return result

    def flush():
        for token, book in books.items():
            sequence, row = latest[token]
            if sequence not in selected:
                selected[sequence] = {'kind': 'book', 'token': token, 'snapshot': True,
                                      't_ns': row['t_ns'], 'wall_ns': row['wall_ns'],
                                      'bids': cap(book.bids, True), 'asks': cap(book.asks, False)}

    for sequence, row in enumerate(rows):
        while query_index < len(queries) and queries[query_index] < row['t_ns']:
            flush()
            query_index += 1
        kind = row['kind']
        if kind == 'book':
            token = row['token']
            if row['snapshot']:
                book = BookState()
                book.apply_snapshot(row['bids'], row['asks'])
                books[token] = book
            elif token in books:
                for price, size, side in row['changes']:
                    books[token].apply_change(price, size, side)
            else:
                continue
            latest[token] = sequence, row
        else:
            if kind == 'price':
                flush()  # Auch die Reihenfolge innerhalb gleicher Zeitstempel bewahren.
            if kind == 'status' and row['source'] == 'polymarket' and row['state'] in {'connected', 'disconnected'}:
                books.clear()
                latest.clear()
            kept.append((sequence, row))
    flush()
    kept.extend(selected.items())
    kept.sort(key=lambda item: (item[1]['t_ns'], item[0]))
    return [row for _, row in kept]


def prepare(run, verify_original=False):
    """Archiv oder festen vollständigen Präfix lesen, unverändert lassen."""
    name = run.name
    manifest = json.loads((run / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('data_loss') or manifest['status'] not in {'complete', 'recording'}:
        raise ValueError('Verlustbehaftetes oder fehlgeschlagenes Archiv')
    archive = run / 'events.jsonl'
    limit = archive.stat().st_size
    digest = hashlib.sha256()
    metadata = {'run': str(run), 'source_status': manifest['status'], 'manifest': manifest}
    db = sqlite3.connect('')
    db.execute('PRAGMA journal_mode=OFF')
    db.execute('CREATE TABLE events (ts INTEGER, kind TEXT, payload TEXT)')
    byte_count, first_wall, last_wall, last_tick = 0, None, None, None

    def ingest():
        nonlocal byte_count, first_wall, last_wall, last_tick
        with archive.open('rb') as file:
            while file.tell() < limit:
                line = file.readline()
                if file.tell() > limit or not line.endswith(b'\n'):
                    break
                row = json.loads(line)
                digest.update(line)
                byte_count = file.tell()
                wall = row['wall_ns']
                first_wall = min(first_wall, wall) if first_wall is not None else wall
                last_wall = max(last_wall, wall) if last_wall is not None else wall
                last_tick = max(last_tick, row['t_ns']) if last_tick is not None else row['t_ns']
                yield row['t_ns'], row['kind'], line.decode('utf-8')

    print(f'Archiv vorbereiten: {name}', flush=True)
    try:
        db.executemany('INSERT INTO events VALUES (?, ?, ?)', ingest())
        if manifest['status'] == 'complete' and digest.hexdigest() != manifest['events_sha256']:
            raise ValueError('Archivprüfsumme stimmt nicht')
        if manifest['status'] == 'recording':
            clock = {'kind': 'clock', 't_ns': last_tick, 'wall_ns': last_wall}
            db.execute('INSERT INTO events VALUES (?, ?, ?)', (last_tick, 'clock', json.dumps(clock)))
        db.execute('CREATE INDEX event_time ON events(ts)')

        def rows():
            return (json.loads(row[0]) for row in db.execute('SELECT payload FROM events ORDER BY ts, rowid'))

        prices = (json.loads(row[0]) for row in db.execute("SELECT payload FROM events WHERE kind='price' ORDER BY ts, rowid"))
        queries = query_times(prices, LOOKBACKS, HOLDS, LATENCIES)
        compact = compact_events(rows(), queries)
        original_count = db.execute('SELECT COUNT(*) FROM events').fetchone()[0]
        parity = []
        if verify_original:
            original = json.loads((run / 'report.json').read_text(encoding='utf-8'))
            assert original['code_sha256']['cex_leadlag.py'] == hashlib.sha256(Path('src/cex_leadlag.py').read_bytes()).hexdigest()
            for arm in original['arms']:
                actual = trade_result(replay(compact, Config(**arm['config']), arm['latency_ms'], presorted=True))
                assert actual == trade_result(arm), f'Baseline-Parität {arm["latency_ms"]} ms'
                parity.append({'config': arm['config'], 'latency_ms': arm['latency_ms'], 'passed': True})
            config = Config(threshold_bps=1, lookback_ms=500, hold_ms=10000, max_ask=.95, max_price_jump=.05)
            full = trade_result(replay(rows(), config, 250, presorted=True))
            reduced = trade_result(replay(compact, config, 250, presorted=True))
            assert full == reduced, 'Parität alternativer Parameter gegen frisches vollständiges Replay'
            parity.append({'config': asdict(config), 'latency_ms': 250, 'passed': True, 'fresh_full_replay': True})
    finally:
        db.close()
    path = OUT / f'{name}.pickle'
    with path.open('wb') as file:
        pickle.dump(compact, file, protocol=pickle.HIGHEST_PROTOCOL)
    metadata.update(archive_prefix_bytes=byte_count, archive_prefix_sha256=digest.hexdigest(),
                    observed_duration_s=(last_wall - first_wall) / 1e9,
                    first_event_utc=datetime.fromtimestamp(first_wall / 1e9, timezone.utc).isoformat(),
                    last_event_utc=datetime.fromtimestamp(last_wall / 1e9, timezone.utc).isoformat(),
                    original_events=original_count, compact_events=len(compact), parity=parity)
    (OUT / f'{name}.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    print(f'Verdichtet: {original_count:,} auf {len(compact):,} Ereignisse; Parität: {len(parity)} Prüfungen', flush=True)
    return path, metadata


def init_worker(path):
    global _events
    # Nur unseren eigenen, lokal erzeugten Cache öffnen, nie externe Pickle-Dateien.
    with Path(path).open('rb') as file:
        _events = pickle.load(file)


def evaluate(task):
    index, config, latency = task
    result = trade_result(replay(_events, Config(**config), latency, presorted=True))
    return {'id': index, 'config': config, 'latency_ms': latency,
            'summary': result['summary'], 'skips': result['skips']}


def batch(path, tasks):
    with ProcessPoolExecutor(max_workers=4, initializer=init_worker, initargs=(str(path),)) as pool:
        results = []
        for result in pool.map(evaluate, tasks, chunksize=4):
            results.append(result)
            if len(results) % 40 == 0:
                print(f'Varianten berechnet: {len(results)}/{len(tasks)}', flush=True)
    return results


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    grid = [asdict(Config(threshold_bps=threshold, lookback_ms=window, hold_ms=hold,
                          max_ask=limit, max_price_jump=jump))
            for threshold, window, hold, limit, jump in itertools.product(
                (.5, 1, 2, 3), LOOKBACKS, HOLDS, (.65, .85, .95), (.01, .02, .05))]
    assert len(grid) == 540
    (OUT / 'grid_spec.json').write_text(json.dumps({'configs': grid, 'selection_latency_ms': 250,
        'minimum_closed_trades': 10, 'ranking': 'cash minus starting cash; open positions valued at zero',
        'created_utc': datetime.now(timezone.utc).isoformat()}, indent=2), encoding='utf-8')
    train_path, train_meta = prepare(TRAIN, verify_original=True)
    results = batch(train_path, [(i, config, 250) for i, config in enumerate(grid)])
    results.sort(key=lambda r: (r['summary']['floor_pnl'], r['summary']['closed_trades']), reverse=True)
    (OUT / 'grid_results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    with (OUT / 'grid_results.csv').open('w', newline='', encoding='utf-8') as file:
        flattened = [{**r['config'], 'latency_ms': r['latency_ms'], **r['summary']} for r in results]
        writer = csv.DictWriter(file, fieldnames=list(flattened[0]))
        writer.writeheader()
        writer.writerows(flattened)
    selected = [r for r in results if r['summary']['closed_trades'] >= 10][:10]
    baseline = asdict(Config())
    if not any(r['config'] == baseline for r in selected):
        selected.append({'id': 'baseline', 'config': baseline})
    (OUT / 'selected.json').write_text(json.dumps({'frozen_utc': datetime.now(timezone.utc).isoformat(),
                                                 'selected': selected}, indent=2), encoding='utf-8')
    print('Auswahl eingefroren; spätere Daten werden erst jetzt ausgewertet.', flush=True)
    tasks = [(r['id'], r['config'], latency) for r in selected for latency in LATENCIES]
    comparisons = [{'dataset': 'Auswahlfenster', 'metadata': train_meta, 'results': batch(train_path, tasks)}]
    for name in ('20261011T094806Z-e564fd', '20261011T095642Z-2c8689'):
        path, metadata = prepare(Path('data/cex_leadlag') / name)
        comparisons.append({'dataset': 'Zeitlich spätere Prüfung', 'metadata': metadata, 'results': batch(path, tasks)})
    report = {'completed_utc': datetime.now(timezone.utc).isoformat(), 'grid_count': len(grid),
              'selected': selected, 'comparisons': comparisons,
              'code_sha256': {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                              for path in (Path(__file__), Path('src/cex_leadlag.py'), Path('src/book_stream.py'))}}
    (OUT / 'comparison.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(f'Fertig: {OUT / "comparison.json"}', flush=True)


if __name__ == '__main__':
    main()
