import unittest

from app import claims
from app import report_card as rcd


def make_card(
    *,
    quality="adequate",
    verdict_allowed=True,
    n_events=40,
    ci=(0.01, 0.06),
    edge=0.03,
    capped=False,
    verdict="positive",
    farmer=False,
    one_hit=False,
    risk_level=None,
    top_share=0.2,
    brier=(0.18, 0.22),
    score=71.0,
    resolved_markets=42,
):
    ci_low, ci_high = ci if ci is not None else (None, None)
    return {
        "wallet": "0xtest",
        "snapshot_at": "2026-07-16T18:00:00+00:00",
        "data_window": {"trades": resolved_markets, "source": "polymarket_closed_positions"},
        "track": {
            "score": score,
            "grade": "B",
            "farmer_flag": farmer,
            "one_hit_flag": one_hit,
            "top_market_share": top_share,
            "resolved_markets": resolved_markets,
            "resolved_events": n_events,
            "headline_win_rate": 0.58,
            "pnl_per_volume": 0.04,
            "risk_adjusted": 0.6,
        },
        "calibration": {"n": n_events, "brier_entry": brier[0], "brier_baseline": brier[1]},
        "realized_edge": {
            "n_positions": n_events + 5,
            "n_events": n_events,
            "edge": edge,
            "ci_low": ci_low,
            "ci_high": ci_high,
            "verdict": verdict,
            "headline": "Sample headline.",
            "capped": capped,
        },
        "attribution": None,
        "smart": None,
        "risk": (
            {"wallet_insider_score": 80.0, "risk_level": risk_level, "flags": []}
            if risk_level
            else None
        ),
        "sample": {"n_resolved": n_events, "quality": quality, "verdict_allowed": verdict_allowed},
        "errors": {},
    }


class VerdictStateTests(unittest.TestCase):
    def test_skilled_read_on_positive_ci(self):
        state = rcd.verdict_state(make_card(ci=(0.011, 0.062)))
        self.assertEqual(state["state"], rcd.STATE_SKILLED_READ)
        self.assertIn("RECORD BEYOND CHANCE", state["status"])
        self.assertIn("40 events", state["status"])
        self.assertTrue(state["status_de"])
        self.assertTrue(state["evidence"])

    def test_luck_range_when_ci_includes_zero(self):
        state = rcd.verdict_state(make_card(ci=(-0.02, 0.04), verdict="chance"))
        self.assertEqual(state["state"], rcd.STATE_LUCK_RANGE)
        self.assertIn("NOT SEPARABLE FROM CHANCE", state["status"])

    def test_negative_read_when_ci_below_zero(self):
        state = rcd.verdict_state(make_card(ci=(-0.06, -0.01), edge=-0.03, verdict="negative"))
        self.assertEqual(state["state"], rcd.STATE_NEGATIVE_READ)
        self.assertIn("NEGATIVE RECORD", state["status"])

    def test_insufficient_sample(self):
        state = rcd.verdict_state(make_card(quality="insufficient", verdict_allowed=False, n_events=7, verdict="thin"))
        self.assertEqual(state["state"], rcd.STATE_INSUFFICIENT)
        self.assertIn("NO VERDICT YET", state["status"])
        self.assertIn("7 resolved events", state["status"])

    def test_developing_sample_gets_no_verdict(self):
        state = rcd.verdict_state(make_card(quality="developing", verdict_allowed=False, n_events=25, verdict="thin"))
        self.assertEqual(state["state"], rcd.STATE_INSUFFICIENT)

    def test_capped_feed_blocks_verdict_even_with_adequate_n(self):
        state = rcd.verdict_state(make_card(capped=True, verdict="capped"))
        self.assertEqual(state["state"], rcd.STATE_INSUFFICIENT)
        self.assertIn("extremes", state["status"])

    def test_no_resolved_positions(self):
        state = rcd.verdict_state(
            make_card(quality="insufficient", verdict_allowed=False, n_events=0, ci=None, edge=None, verdict="none", resolved_markets=0)
        )
        self.assertEqual(state["state"], rcd.STATE_INSUFFICIENT)
        self.assertIn("no resolved positions", state["status"].lower())

    def test_flagged_beats_skilled_read(self):
        state = rcd.verdict_state(make_card(farmer=True, ci=(0.02, 0.08)))
        self.assertEqual(state["state"], rcd.STATE_FLAGGED)
        self.assertIn("FLAGGED", state["status"])
        self.assertNotIn("BEYOND CHANCE", state["status"])

    def test_flagged_on_high_risk_level(self):
        state = rcd.verdict_state(make_card(risk_level="High"))
        self.assertEqual(state["state"], rcd.STATE_FLAGGED)
        self.assertIn("insider screen", state["status"].lower())

    def test_empty_scorecard_is_insufficient(self):
        state = rcd.verdict_state({})
        self.assertEqual(state["state"], rcd.STATE_INSUFFICIENT)


class DiagnosisTests(unittest.TestCase):
    def test_concentration_and_small_sample(self):
        card = make_card(quality="developing", verdict_allowed=False, n_events=22, top_share=0.7)
        sentence = rcd.diagnosis_sentence(card)
        self.assertIn("70% of gross profit", sentence)
        self.assertIn("22 resolved events", sentence)
        self.assertTrue(sentence.endswith("."))

    def test_strong_and_weak_calibration(self):
        strong = rcd.diagnosis_sentence(make_card(brier=(0.15, 0.24)))
        weak = rcd.diagnosis_sentence(make_card(brier=(0.26, 0.24)))
        self.assertIn("beat the base-rate benchmark", strong)
        self.assertIn("no edge over the base rate", weak)

    def test_farmer_driver_leads(self):
        sentence = rcd.diagnosis_sentence(make_card(farmer=True, top_share=0.8))
        self.assertIn("near-zero edge per dollar", sentence)

    def test_never_empty_even_on_empty_card(self):
        self.assertTrue(rcd.diagnosis_sentence({}))
        self.assertTrue(rcd.diagnosis_sentence({}, lang="de"))

    def test_fallback_breadth_sentence(self):
        card = make_card(top_share=0.1, brier=(None, None))
        card["calibration"] = {"n": 40, "brier_entry": None, "brier_baseline": None}
        sentence = rcd.diagnosis_sentence(card)
        self.assertIn("breadth across 42 resolved markets", sentence)

    def test_german_variant(self):
        sentence = rcd.diagnosis_sentence(make_card(top_share=0.7), lang="de")
        self.assertIn("Bruttogewinns", sentence)


class CopySummaryTests(unittest.TestCase):
    def test_available_summary(self):
        summary = rcd.copy_summary({"roi": 0.123, "copied_trades": 17, "fees_paid": 12.5}, days=90)
        self.assertTrue(summary["available"])
        self.assertIn("+12.3%", summary["text"])
        self.assertIn("17 copied trades", summary["text"])
        self.assertIn("modeled", summary["text"])

    def test_placeholder_without_trades(self):
        for stats in (None, {}, {"copied_trades": 0, "roi": 0.5}):
            summary = rcd.copy_summary(stats)
            self.assertFalse(summary["available"])
            self.assertIsNone(summary["roi"])
            self.assertIn("no copy number", summary["text"].lower())

    def test_german_placeholder(self):
        summary = rcd.copy_summary(None, lang="de")
        self.assertIn("keine Copy-Zahl", summary["text"])


class ClaimsConformanceTests(unittest.TestCase):
    def test_all_templates_pass_the_claims_register(self):
        cards = [
            make_card(),
            make_card(ci=(-0.02, 0.04), verdict="chance"),
            make_card(ci=(-0.06, -0.01), edge=-0.03, verdict="negative"),
            make_card(quality="insufficient", verdict_allowed=False, n_events=5, verdict="thin"),
            make_card(capped=True, verdict="capped"),
            make_card(farmer=True),
            make_card(risk_level="High"),
            {},
        ]
        texts: list[str] = []
        for card in cards:
            state = rcd.verdict_state(card)
            texts.extend([state["status"], state["status_de"], *state["evidence"]])
            texts.append(rcd.diagnosis_sentence(card))
            texts.append(rcd.diagnosis_sentence(card, lang="de"))
        texts.append(rcd.copy_summary({"roi": 0.1, "copied_trades": 5, "fees_paid": 1.0})["text"])
        texts.append(rcd.copy_summary(None)["text"])
        texts.append(rcd.copy_summary({"roi": 0.1, "copied_trades": 5, "fees_paid": 1.0}, lang="de")["text"])
        texts.append(rcd.copy_summary(None, lang="de")["text"])
        for text in texts:
            self.assertEqual(claims.find_forbidden(text), [], msg=f"forbidden phrase in: {text}")


if __name__ == "__main__":
    unittest.main()
