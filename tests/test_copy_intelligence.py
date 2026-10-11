import tempfile
import unittest
import json
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from app import copy_intelligence as ci
from src import copy_trading as ct

A, B = '0x' + 'a' * 40, '0x' + 'b' * 40
NOW = '2026-09-16T12:00:00+00:00'


def trade(wallet=A, outcome='Yes', side='BUY', **extra):
    return dict(wallet=wallet, market_key='m1', title='Ukraine ceasefire?',
                outcome=outcome, side=side, type='TRADE', price=.1, size=100,
                notional=10, time=NOW, **extra)


class IntelligenceTests(unittest.TestCase):
    def test_sports_event_slug_classifies_missing_gamma_market(self):
        row = {**trade(), 'title': 'Arizona vs. San Francisco', 'event_slug': 'mlb-ari-sf-2026-08-27'}
        style = ci.trading_style([row], {})
        self.assertEqual(style['categories'][0]['category'], 'Sports')
        self.assertIsNone(style['late_share'])

    def test_fetch_serializes_canonical_scorecard_without_inventing_sharpe(self):
        card = {'track': {'settled_pnl': 42}, 'sample': {'quality': 'insufficient'},
                'calibration': {'n': 1, 'buckets': pd.DataFrame([{'x': 1}])}}
        with patch.object(ci.md, '_get_json', return_value={'name': 'Trader'}), \
             patch.object(ci.md, 'get_polymarket_activity', return_value=pd.DataFrame()), \
             patch.object(ci.md, 'get_polymarket_positions', return_value=pd.DataFrame()), \
             patch.object(ci, 'wallet_scorecard', return_value=card):
            result = ci.fetch_wallet(A)
        json.dumps(result, allow_nan=False)
        self.assertEqual(result['scorecard']['track']['settled_pnl'], 42)
        self.assertIsNone(result['sharpe'])

    def test_multiple_process_schedulers_share_a_lease(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'copy.sqlite'
            ci.import_watchlist([{'wallet': A}], db)
            with patch.object(ci.threading, 'Thread') as thread:
                ci.refresh_async(db)
                ci._NEXT_CHECK.clear()  # a second process has no in-memory throttle
                ci.refresh_async(db)
                self.assertEqual(thread.call_count, 1)

    def test_research_read_does_not_wait_for_paper_write_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'copy.sqlite'
            ci.import_watchlist([{'wallet': A}], db)
            with closing(ct.connect(db)) as conn:
                conn.execute('BEGIN EXCLUSIVE')
                self.assertIn(A, ci.read_state(db)['watchlist'])
                conn.rollback()

    def test_style_uses_buys_and_keeps_timing_denominator(self):
        rows = [trade(), {**trade(), 'market_key': 'm2', 'price': .9, 'notional': 90},
                {**trade(side='SELL'), 'notional': 9000}]
        profile = ci.trading_style(rows, {'m1': {'endDate': '2026-09-17T12:00:00Z'}})
        self.assertEqual(profile['buy_count'], 2)
        self.assertAlmostEqual(profile['longshot_share'], .1)
        self.assertAlmostEqual(profile['favorite_share'], .9)
        self.assertEqual(profile['timing_n'], 1)
        self.assertEqual(profile['late_share'], 1)
        self.assertEqual(profile['categories'][0]['category'], 'Geopolitics')

    def test_overlap_deduplicates_wallets_and_distinguishes_outcomes(self):
        self.assertEqual(ci.market_overlaps([trade(), trade()], NOW), [])
        same = ci.market_overlaps([trade(), trade(B)], NOW)[0]
        self.assertEqual(same['direction'], 'same_outcome')
        opposite = ci.market_overlaps([trade(), trade(B, 'No')], NOW)[0]
        self.assertEqual(opposite['direction'], 'different_outcomes')
        self.assertEqual(opposite['wallet_count'], 2)

    def test_sells_old_and_future_trades_do_not_create_overlap(self):
        for other in [trade(B, side='SELL'), {**trade(B), 'time': '2026-09-10T12:00:00Z'},
                      {**trade(B), 'time': '2026-09-17T12:00:00Z'}]:
            self.assertEqual(ci.market_overlaps([trade(), other], NOW), [])
        self.assertEqual(ci.market_overlaps([trade(), trade(B), trade(B, side='SELL')], NOW), [])

    def test_import_is_idempotent_preserves_notes_and_rejects_unsafe_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'copy.sqlite'
            entries = [{'wallet': A, 'sources': ['https://x.com/Example/status/123']}]
            ci.import_watchlist(entries, db)
            ct.update_trader(A, note='my existing note', active=False, db_path=db)
            ci.import_watchlist(entries, db)
            with closing(ct.connect(db)) as conn:
                row = dict(conn.execute('SELECT * FROM traders WHERE wallet=?', (A,)).fetchone())
            self.assertEqual(row['active'], 0)
            self.assertEqual(row['note'], 'my existing note')
            self.assertEqual(len(ci.read_state(db)['watchlist']), 1)
            with self.assertRaises(ValueError):
                ci.import_watchlist([{'wallet': B, 'sources': ['javascript:alert(1)']}], db)

    def test_alerts_only_on_new_membership_and_return_after_disappearance(self):
        overlaps = ci.market_overlaps([trade(), trade(B)], NOW)
        first = ci.merge_alerts({}, overlaps, NOW)
        self.assertEqual(len(first), 1)
        previous = {'overlaps': overlaps, 'alerts': first}
        self.assertEqual(ci.merge_alerts(previous, overlaps, NOW), first)
        previous['overlaps'] = []
        self.assertEqual(len(ci.merge_alerts(previous, overlaps, '2026-09-16T13:00:00Z')), 2)

    def test_partial_failure_does_not_reuse_stale_trades_for_alerts(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'copy.sqlite'
            ci.import_watchlist([{'wallet': A}, {'wallet': B}], db)
            def fetch(wallet):
                if wallet == B:
                    raise RuntimeError('upstream unavailable')
                return {'wallet': wallet, 'snapshot_at': NOW, 'activity': [trade()], 'errors': {}}
            with patch.object(ci, 'fetch_wallet', side_effect=fetch):
                state = ci.refresh(db)
            self.assertEqual(state['overlaps'], [])
            self.assertIn(B, state['errors'])

    def test_notice_survives_restart_and_failed_member_does_not_notify(self):
        third = '0x' + 'c' * 40
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'copy.sqlite'
            ci.import_watchlist([{'wallet': w} for w in [A, B, third]], db)
            failed = set()
            def fetch(wallet):
                if wallet in failed:
                    raise RuntimeError('temporary outage')
                return {'wallet': wallet, 'snapshot_at': NOW, 'activity': [trade(wallet)], 'errors': {}}
            with patch.object(ci, 'fetch_wallet', side_effect=fetch), patch.object(ci, '_utc_now', return_value=NOW):
                self.assertEqual(len(ci.refresh(db)['alerts']), 1)
                self.assertEqual(len(ci.refresh(db)['alerts']), 1)
                failed.add(third)
                partial = ci.refresh(db)
                self.assertEqual(len(partial['alerts']), 1)
                self.assertTrue(any(r.get('stale') for r in partial['overlaps']))
                failed.clear()
                self.assertEqual(len(ci.refresh(db)['alerts']), 1)


if __name__ == '__main__':
    unittest.main()
