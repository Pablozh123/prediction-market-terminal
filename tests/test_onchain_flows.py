import unittest

import pandas as pd

from app import onchain_flows as ocf

WALLET = "0x204f72f35326db932158cba6adff0b9a1da95e14"
OUTSIDER = "0x1111111111111111111111111111111111111111"
PROTOCOL = "0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e"


def log(sender: str, recipient: str, usdc: float, block: int = 1000, tx: str = "0xtx") -> dict:
    return {
        "address": ocf.USDC_CONTRACTS[0],
        "blockNumber": hex(block),
        "transactionHash": tx,
        "data": hex(int(round(usdc * 10 ** ocf.USDC_DECIMALS))),
        "topics": [ocf.TRANSFER_TOPIC, ocf.topic_address(sender), ocf.topic_address(recipient)],
    }


class TopicTests(unittest.TestCase):
    def test_address_round_trip(self) -> None:
        topic = ocf.topic_address(WALLET)
        self.assertEqual(len(topic), 66)
        self.assertEqual(ocf.address_from_topic(topic), WALLET.lower())

    def test_malformed_topic(self) -> None:
        self.assertEqual(ocf.address_from_topic(""), "")
        self.assertEqual(ocf.address_from_topic(None), "")


class DecodeTests(unittest.TestCase):
    def test_decodes_amount_with_six_decimals(self) -> None:
        decoded = ocf.decode_transfer_log(log(OUTSIDER, WALLET, 1234.56))
        self.assertAlmostEqual(decoded["amount"], 1234.56, places=6)
        self.assertEqual(decoded["recipient"], WALLET.lower())

    def test_rejects_non_transfer_and_short_logs(self) -> None:
        """A malformed entry must drop out, not poison a sum."""
        bad_topic = log(OUTSIDER, WALLET, 1.0)
        bad_topic["topics"][0] = "0xdead"
        self.assertIsNone(ocf.decode_transfer_log(bad_topic))
        short = log(OUTSIDER, WALLET, 1.0)
        short["topics"] = short["topics"][:2]
        self.assertIsNone(ocf.decode_transfer_log(short))

    def test_unparseable_data_is_skipped(self) -> None:
        broken = log(OUTSIDER, WALLET, 1.0)
        broken["data"] = "not hex"
        self.assertIsNone(ocf.decode_transfer_log(broken))

    def test_frame_deduplicates(self) -> None:
        entry = log(OUTSIDER, WALLET, 5.0)
        frame = ocf.decode_transfer_logs([entry, dict(entry)])
        self.assertEqual(len(frame), 1)

    def test_empty_input(self) -> None:
        self.assertTrue(ocf.decode_transfer_logs([]).empty)


class ClassifyTests(unittest.TestCase):
    def _flows(self) -> pd.DataFrame:
        entries = [
            log(OUTSIDER, WALLET, 100_000.0, block=1),   # deposit
            log(WALLET, OUTSIDER, 40_000.0, block=5, tx="0xb"),  # withdrawal
            log(PROTOCOL, WALLET, 5_000_000.0, block=3, tx="0xc"),  # settlement in
            log(WALLET, PROTOCOL, 4_900_000.0, block=4, tx="0xd"),  # trading out
        ]
        return ocf.classify_flows(ocf.decode_transfer_logs(entries), WALLET)

    def test_direction_and_protocol_flags(self) -> None:
        flows = self._flows()
        self.assertEqual(set(flows["direction"]), {"in", "out"})
        self.assertEqual(int(flows["is_protocol"].sum()), 2)

    def test_summary_separates_funding_from_trading(self) -> None:
        """Counting settlement inflows as deposits would inflate funding by the volume."""
        summary = ocf.flow_summary(self._flows())
        self.assertAlmostEqual(summary["deposits_external"], 100_000.0)
        self.assertAlmostEqual(summary["withdrawals_external"], 40_000.0)
        self.assertAlmostEqual(summary["net_external"], 60_000.0)
        self.assertAlmostEqual(summary["deposits_protocol"], 5_000_000.0)

    def test_transfers_not_involving_the_wallet_are_dropped(self) -> None:
        other = ocf.decode_transfer_logs([log(OUTSIDER, PROTOCOL, 7.0)])
        self.assertTrue(ocf.classify_flows(other, WALLET).empty)

    def test_empty_inputs(self) -> None:
        self.assertTrue(ocf.classify_flows(pd.DataFrame(), WALLET).empty)
        self.assertEqual(ocf.flow_summary(pd.DataFrame())["net_external"], 0.0)


class PeakExposureTests(unittest.TestCase):
    def test_high_water_mark_not_total_deposits(self) -> None:
        """Recycled dollars must not be counted twice as committed capital."""
        entries = [
            log(OUTSIDER, WALLET, 100.0, block=1, tx="0x1"),
            log(WALLET, OUTSIDER, 100.0, block=2, tx="0x2"),
            log(OUTSIDER, WALLET, 100.0, block=3, tx="0x3"),
        ]
        flows = ocf.classify_flows(ocf.decode_transfer_logs(entries), WALLET)
        self.assertAlmostEqual(ocf.flow_summary(flows)["deposits_external"], 200.0)
        self.assertAlmostEqual(ocf.peak_external_exposure(flows), 100.0)

    def test_protocol_transfers_are_excluded(self) -> None:
        entries = [
            log(OUTSIDER, WALLET, 50.0, block=1, tx="0x1"),
            log(PROTOCOL, WALLET, 9_000.0, block=2, tx="0x2"),
        ]
        flows = ocf.classify_flows(ocf.decode_transfer_logs(entries), WALLET)
        self.assertAlmostEqual(ocf.peak_external_exposure(flows), 50.0)

    def test_empty(self) -> None:
        self.assertEqual(ocf.peak_external_exposure(pd.DataFrame()), 0.0)


if __name__ == "__main__":
    unittest.main()
