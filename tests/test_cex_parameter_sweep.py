"""Verdichtung darf Signale, Frische, Tiefe und Paper-Ergebnisse nicht ändern."""
import unittest
import itertools
import random
from dataclasses import replace

from scripts.cex_parameter_sweep import HOLDS, LATENCIES, LOOKBACKS, compact_events, query_times, trade_result
from src.cex_leadlag import Config, replay
from tests.test_cex_leadlag import book, event, market, price, stream


class CompactionTests(unittest.TestCase):
    def compare(self, rows, config=None, latency=100):
        rows = sorted(rows, key=lambda row: row['t_ns'])
        config = config or Config(hold_ms=1000)
        queries = query_times(rows, [config.lookback_ms], [config.hold_ms], [latency], config.threshold_bps)
        reduced = compact_events(rows, queries, config.shares)
        self.assertEqual(trade_result(replay(rows, config, latency, presorted=True)),
                         trade_result(replay(reduced, config, latency, presorted=True)))
        return reduced

    def test_entry_exit_and_full_signal_features(self):
        self.compare(stream())

    def test_freshness_of_unchanged_book_is_preserved(self):
        rows = [market(), book(0), price(0, 100), book(900), price(1000, 100.1),
                book(1099), book(2099, .79, .80), event(2300, 'clock')]
        self.compare(rows, Config(hold_ms=1000, stale_ms=200))

    def test_true_stale_exit_is_not_refreshed(self):
        self.compare(stream()[:5] + [event(2300, 'clock')], Config(hold_ms=1000, stale_ms=200))

    def test_same_timestamp_book_order_around_price(self):
        self.compare([market(), book(0), price(0, 100), book(1000), price(1000, 100.1),
                      book(1000, .59, .60), book(2000, .79, .80), event(2300, 'clock')])

    def test_disconnect_and_orphan_delta_do_not_restore_book(self):
        self.compare(stream()[:5] + [event(1050, 'status', source='polymarket', state='disconnected'),
                                    event(1100, 'book', token='u', snapshot=False, changes=[[.6, 100, 'SELL']]),
                                    event(2300, 'clock')])

    def test_multiple_depth_levels_and_fees(self):
        rows = stream()
        rows[1]['asks'] = [[.5, 3], [.51, 4], [.52, 20], [.6, 100]]
        rows[3]['asks'] = rows[1]['asks']
        self.compare(rows)

    def test_insufficient_depth_and_zero_size_deletion(self):
        rows = [market(), book(0, size=5), price(0, 100),
                event(900, 'book', token='u', snapshot=False, changes=[[.50, 0, 'SELL']]),
                price(1000, 100.1), book(1100), event(2300, 'clock')]
        self.compare(rows)

    def test_parameter_combinations(self):
        base = Config(hold_ms=1000)
        for hold in (100, 500, 1000):
            for latency in (0, 100, 250, 1000):
                with self.subTest(hold=hold, latency=latency):
                    self.compare(stream(), replace(base, hold_ms=hold), latency)

    def test_capital_floor_penalizes_unresolved_positions(self):
        result = replay(stream()[:6], Config(hold_ms=1000), 100)
        summary = trade_result(result)['summary']
        self.assertAlmostEqual(summary['floor_pnl'], summary['cash'] - 100)
        self.assertLess(summary['floor_pnl'], summary['realized_pnl'])

    def test_shared_compaction_across_grid_with_gaps_fees_and_close(self):
        rng = random.Random(17)
        start = market()
        start['market']['end_s'] = 1011
        rows = [start]
        value = 100
        for ms in range(0, 10001, 125):
            value += rng.choice((-.02, -.01, .005, .01, .02))
            rows.append(price(ms, value))
        for ms in range(0, 10001, 37):
            if 4000 < ms < 6500:
                continue
            ask = rng.choice((.48, .49, .50, .51, .52))
            up = book(ms, ask-.01, ask, size=rng.choice((4, 9, 12, 100)))
            up['asks'].append([ask+.01, 20])
            down = {**up, 'token': 'd'}
            rows.extend((up, down))
        changed = market()
        changed.update(t_ns=3_000_000_000, wall_ns=1_003_000_000_000)
        changed['market'].update(fee_rate=.1, end_s=1011)
        rows.extend((changed, event(5000, 'status', source='polymarket', state='disconnected'),
                     event(10001, 'clock')))
        rows.sort(key=lambda row: row['t_ns'])
        queries = query_times(rows, LOOKBACKS, HOLDS, LATENCIES)
        reduced = compact_events(rows, queries)
        for threshold, window, hold, latency in itertools.product((.5, 2), LOOKBACKS, HOLDS, LATENCIES):
            config = Config(threshold_bps=threshold, lookback_ms=window, hold_ms=hold)
            with self.subTest(threshold=threshold, window=window, hold=hold, latency=latency):
                self.assertEqual(trade_result(replay(rows, config, latency, presorted=True)),
                                 trade_result(replay(reduced, config, latency, presorted=True)))


if __name__ == '__main__':
    unittest.main()
