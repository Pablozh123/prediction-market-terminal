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


class ReconcileTests(unittest.TestCase):
    def test_a_complete_ledger_reconciles(self) -> None:
        out = ocf.reconcile_ledger(total_in=1_000_000, total_out=400_000,
                                   ending_balance=800_000, reported_profit=200_000)
        self.assertAlmostEqual(out["net_flow"], 600_000)
        self.assertAlmostEqual(out["residual"], 0.0)
        self.assertTrue(out["reconciles"])

    def test_missing_outflows_show_up_as_a_negative_residual(self) -> None:
        """If withdrawals were not captured, the ledger implies too much money left."""
        out = ocf.reconcile_ledger(total_in=1_000_000, total_out=0,
                                   ending_balance=200_000, reported_profit=100_000)
        self.assertLess(out["residual"], 0)
        self.assertFalse(out["reconciles"])

    def test_residual_is_scaled_against_profit(self) -> None:
        out = ocf.reconcile_ledger(total_in=100, total_out=0,
                                   ending_balance=1_100, reported_profit=1_000)
        self.assertAlmostEqual(out["residual"], 0.0)
        self.assertTrue(out["reconciles"])

    def test_tolerance_absorbs_rounding(self) -> None:
        out = ocf.reconcile_ledger(total_in=1_000_000, total_out=0,
                                   ending_balance=1_100_000 + 5, reported_profit=100_000)
        self.assertTrue(out["reconciles"])

    def test_zero_profit_leaves_percentage_undefined(self) -> None:
        out = ocf.reconcile_ledger(1_000, 500, 500, 0)
        self.assertIsNone(out["residual_pct_of_profit"])


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


AMBIGUOUS = "0xc417fd8e9661c0d2120b64a04bb3278c17e99db1"
FOREIGN_TOKEN = "0x7ceb23fd6bc0add59e62ac25578270cff1b9f619"  # WETH on Polygon, 18 decimals


class AmbiguousCounterpartyTests(unittest.TestCase):
    """A counterparty both address lists claim must not be silently resolved."""

    def test_address_is_in_both_lists(self) -> None:
        self.assertIn(AMBIGUOUS, ocf.AMBIGUOUS_ADDRESSES)
        self.assertEqual(ocf.AMBIGUOUS_ADDRESSES,
                         ocf.PROTOCOL_ADDRESSES & ocf.BRIDGE_ADDRESSES)

    def test_deposit_through_ambiguous_route_is_not_booked_as_protocol(self) -> None:
        """$50k in through the documented deposit proxy used to report $0 funding."""
        flows = ocf.classify_flows(
            ocf.decode_transfer_logs([log(AMBIGUOUS, WALLET, 50_000.0)]), WALLET)
        self.assertEqual(list(flows["classification"]), ["ambiguous"])
        summary = ocf.flow_summary(flows)
        self.assertAlmostEqual(summary["deposits_protocol"], 0.0)
        self.assertAlmostEqual(summary["deposits_ambiguous"], 50_000.0)
        self.assertAlmostEqual(summary["net_external_low"], 0.0)
        self.assertAlmostEqual(summary["net_external_high"], 50_000.0)
        self.assertAlmostEqual(ocf.peak_external_exposure(flows), 0.0)
        self.assertAlmostEqual(
            ocf.peak_external_exposure(flows, include_ambiguous=True), 50_000.0)

    def test_range_ends_are_the_two_consistent_readings(self) -> None:
        entries = [log(AMBIGUOUS, WALLET, 800.0, block=1, tx="0x1"),
                   log(WALLET, AMBIGUOUS, 300.0, block=2, tx="0x2"),
                   log(OUTSIDER, WALLET, 100.0, block=3, tx="0x3")]
        summary = ocf.flow_summary(
            ocf.classify_flows(ocf.decode_transfer_logs(entries), WALLET))
        self.assertAlmostEqual(summary["net_external_low"], 100.0)
        self.assertAlmostEqual(summary["net_external_high"], 600.0)


class TransferIdentityTests(unittest.TestCase):
    """Two equal transfers inside one batched payout are two, not one."""

    def test_same_amount_twice_in_one_tx_survives(self) -> None:
        entries = [log(PROTOCOL, WALLET, 10.0, tx="0xbatch") | {"logIndex": "0x4"},
                   log(PROTOCOL, WALLET, 10.0, tx="0xbatch") | {"logIndex": "0x9"}]
        frame = ocf.decode_transfer_logs(entries)
        self.assertEqual(len(frame), 2)
        self.assertAlmostEqual(float(frame["amount"].sum()), 20.0)

    def test_the_identical_log_repeated_is_still_one(self) -> None:
        entry = log(PROTOCOL, WALLET, 10.0, tx="0xbatch") | {"logIndex": "0x4"}
        self.assertEqual(len(ocf.decode_transfer_logs([entry, dict(entry)])), 1)

    def test_logs_without_an_index_fall_back_to_the_payload_key(self) -> None:
        entry = log(PROTOCOL, WALLET, 10.0, tx="0xbatch")
        frame = ocf.decode_transfer_logs([entry, dict(entry)])
        self.assertEqual(len(frame), 1)
        self.assertEqual(int(frame["log_index"].iloc[0]), -1)


class TokenUnitTests(unittest.TestCase):
    """Only collateral is money; a foreign token is not a dollar."""

    def _foreign(self, raw_units: int) -> dict:
        entry = log(OUTSIDER, WALLET, 0.0)
        entry["address"] = FOREIGN_TOKEN
        entry["data"] = hex(raw_units)
        return entry

    def test_foreign_token_is_dropped_by_the_contract_filter(self) -> None:
        """1 WETH read with USDC decimals was a $1,000,000,000,000 deposit."""
        flows = ocf.classify_flows(
            ocf.decode_transfer_logs([self._foreign(10 ** 18)]), WALLET)
        self.assertTrue(flows.empty)
        self.assertAlmostEqual(ocf.flow_summary(flows)["deposits_external"], 0.0)

    def test_decimals_mapping_drops_unknown_contracts_before_scaling(self) -> None:
        frame = ocf.decode_transfer_logs([self._foreign(10 ** 18)], ocf.TOKEN_DECIMALS)
        self.assertTrue(frame.empty)

    def test_collateral_keeps_its_own_decimals(self) -> None:
        frame = ocf.decode_transfer_logs([log(OUTSIDER, WALLET, 12.5)], ocf.TOKEN_DECIMALS)
        self.assertAlmostEqual(float(frame["amount"].iloc[0]), 12.5)
        self.assertFalse(bool(frame["decimals_assumed"].iloc[0]))

    def test_pusd_is_carried_but_flagged_as_assumed(self) -> None:
        """Its decimals are not pinned in this repo, so the row says so."""
        entry = log(OUTSIDER, WALLET, 1.0)
        entry["address"] = ocf.PUSD_CONTRACT
        frame = ocf.decode_transfer_logs([entry], ocf.TOKEN_DECIMALS)
        self.assertEqual(len(frame), 1)
        self.assertTrue(bool(frame["decimals_assumed"].iloc[0]))

    def test_contract_filter_can_be_switched_off(self) -> None:
        flows = ocf.classify_flows(
            ocf.decode_transfer_logs([self._foreign(10 ** 6)]), WALLET, contracts=None)
        self.assertEqual(len(flows), 1)


if __name__ == "__main__":
    unittest.main()
