import unittest

import pandas as pd

from app import signals as sig


def market(title, volume_1h, volume_24h, **extra):
    row = {
        "platform": "Polymarket",
        "title": title,
        "market_key": title,
        "category": "",
        "yes_price": 0.5,
        "volume_1h": volume_1h,
        "volume_24h": volume_24h,
        "activity_volume": volume_24h,
        "liquidity": 50_000.0,
        "spread": 0.05,
        "change_1h": 0.0,
        "url": "https://example.com",
    }
    row.update(extra)
    return row


class VolumeAnomalyTests(unittest.TestCase):
    def _signals(self, markets):
        return sig.build_monitor_signals(
            pd.DataFrame(markets),
            pd.DataFrame(),
            min_volume=0.0,
            min_liquidity=0.0,
            min_move=0.05,
            max_spread=0.01,
            min_whale_notional=1e12,
            ending_days=0,
            holder_threshold=1.0,
            holder_checks=0,
            tracked_keys=set(),
        )

    def test_hot_hour_flags_anomaly(self):
        signals = self._signals(
            [
                market("Hot market", volume_1h=5_000.0, volume_24h=24_000.0),
                market("Calm market", volume_1h=1_000.0, volume_24h=24_000.0),
            ]
        )
        anomalies = signals[signals["signal_type"] == "Volume anomaly"]
        self.assertEqual(list(anomalies["title"]), ["Hot market"])
        self.assertAlmostEqual(float(anomalies.iloc[0]["value"]), 5.0, places=6)
        self.assertIn("5.0x the 24h baseline", anomalies.iloc[0]["reason"])

    def test_thin_markets_are_ignored(self):
        signals = self._signals([market("Tiny market", volume_1h=900.0, volume_24h=2_000.0)])
        if signals.empty:
            return
        self.assertTrue((signals["signal_type"] != "Volume anomaly").all())


if __name__ == "__main__":
    unittest.main()
