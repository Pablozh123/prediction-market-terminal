"""Die Thesis-Nutzlast: hermetisch ueber synthetische Tabellen, und gegen das
echte Thesis-Repo, wenn es neben diesem liegt.

Der hermetische Teil baut einen Mini-Ergebnisordner mit denselben Spalten
wie die echten Tabellen und prueft, dass jede Zahl im Verdikt und im
Klartext aus diesen Tabellen kommt. Der zweite Teil laeuft nur lokal, wenn
das Schwester-Repo da ist, und prueft die Redaktion: keine Wallet-Adresse
in der Nutzlast, obwohl h3_wallet_tiers.csv welche fuehrt.
"""

from __future__ import annotations

import csv
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from app import research_payload as rp
from app import thesis_results as tr

PROJEKT = Path(__file__).resolve().parents[1]


def _csv(pfad: Path, spalten: list[str], zeilen: list[list]) -> None:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    with pfad.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(spalten)
        w.writerows(zeilen)


def _json(pfad: Path, daten) -> None:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(daten), encoding="utf-8")


def mini_thesis(ziel: Path) -> Path:
    """Ein Ergebnisordner mit allen erwarteten Dateien, klein aber vollstaendig."""
    r = ziel / tr.RESULTS_DIR
    # H1: zehn Tage, Polymarket immer besser als 538.
    _csv(r / "h1_brier_scores.csv",
         ["date", "bs_polymarket", "bs_fivethirtyeight", "bs_always_50", "bs_prior_day"],
         [[f"2024-03-{d:02d}", 0.2, 0.3, 0.25, 0.2] for d in range(1, 11)])
    _json(r / "h1_diebold_mariano.json", [
        {"source_1": "Polymarket", "source_2": "FiveThirtyEight", "dm_statistic": -20.0, "p_value": 1e-30, "n_obs": 10},
        {"source_1": "Polymarket", "source_2": "immer_50%", "dm_statistic": -4.0, "p_value": 0.001, "n_obs": 10},
        {"source_1": "Polymarket", "source_2": "Vortag_Polymarket", "dm_statistic": 0.0, "p_value": 0.98, "n_obs": 10},
    ])
    _csv(r / "h1_calibration_diagnostic_bins.csv",
         ["forecast_source_id", "forecast_source_label", "bin_label", "case_count", "mean_forecast_probability", "observed_frequency"],
         [["polymarket_state_final_50", "Polymarket state final", "0.0-0.2", 19, 0.04, 0.0],
          ["polymarket_state_final_50", "Polymarket state final", "0.8-1.0", 27, 0.95, 1.0],
          ["rieke_state_final_50", "Rieke", "0.8-1.0", 27, 0.9, 1.0]])
    _csv(r / "h1_calibration_diagnostic_summary.csv",
         ["forecast_source_label", "case_count", "mean_brier_loss", "expected_calibration_error", "brier_skill_vs_50_percent"],
         [["Polymarket state final", 50, 0.026, 0.084, 0.895], ["Rieke", 50, 0.03, 0.077, 0.88]])
    _csv(r / "h1_poll_claim_readiness_summary.csv",
         ["summary_id", "value", "unit", "description"],
         [["primary_polymarket_support_count", 262, "rows", ""], ["primary_comparison_count", 285, "rows", ""],
          ["primary_polymarket_support_share", 0.9192982456140351, "share", ""], ["counterexample_row_count", 5, "rows", ""],
          ["broad_claim_proven", 0, "binary", ""]])
    _csv(r / "h1_forecast_quality_synthesis.csv",
         ["evidence_label", "comparator_label", "case_count", "polymarket_lower_loss_count", "polymarket_lower_loss_share",
          "mean_polymarket_brier", "mean_comparator_brier", "aggregate_mean_supports_polymarket", "majority_cases_supports_polymarket"],
         [["Daily 538 overlap", "FiveThirtyEight", 10, 10, 1.0, 0.2, 0.3, "True", "True"],
          ["Rieke 50-state model", "Rieke", 50, 12, 0.24, 0.026, 0.03, "True", "False"],
          ["270toWin", "270toWin", 50, 9, 0.18, 0.026, 0.031, "True", "False"]])
    # H2: zwei Ereignisse, eines gerichtet, eines neutral.
    _csv(r / "h2_event_window_summary.csv",
         ["event_id", "event_date", "title", "event_type", "source_url", "expected_direction", "relevance_score",
          "window_label", "observed_days", "final_cumulative_abnormal_change", "estimation_observations"],
         [["evt_a", "2024-07-13", "Rally shooting", "major_news", "https://x", "trump_up", 0.95, "primary_0d_to_1d", 2, 0.0719, 13],
          ["evt_a", "2024-07-13", "Rally shooting", "major_news", "https://x", "trump_up", 0.95, "secondary_minus_1d_to_3d", 5, 0.0723, 13],
          ["evt_b", "2024-06-28", "Debate", "debate", "https://y", "neutral", 0.9, "primary_0d_to_1d", 2, 0.0254, 13],
          ["evt_b", "2024-06-28", "Debate", "debate", "https://y", "neutral", 0.9, "secondary_minus_1d_to_3d", 5, 0.0085, 13]])
    _csv(r / "h2_event_window_rows.csv",
         ["event_id", "window_label", "event_date", "date", "relative_day", "cumulative_abnormal_change"],
         [["evt_a", "secondary_minus_1d_to_3d", "2024-07-13", "2024-07-12", -1, 0.001],
          ["evt_a", "secondary_minus_1d_to_3d", "2024-07-13", "2024-07-13", 0, 0.03],
          ["evt_a", "secondary_minus_1d_to_3d", "2024-07-13", "2024-07-14", 1, 0.07]])
    # H3: zwei Tiers, eines mit Signal bei Lag 1. Adressen im Inventar
    # bleiben absichtlich drin: die Nutzlast darf sie nicht uebernehmen.
    _csv(r / "thesis_h3_summary.csv",
         ["summary_id", "hypothesis", "summary_type", "label", "metric", "value"],
         [["h3_model_row_count", "H3", "coverage", "rows", "aligned_model_rows", 1216],
          ["h3_wallet_count_tier_1_top_1pct", "H3", "wallet_tier", "tier_1_top_1pct", "wallet_count", 32],
          ["h3_wallet_count_tier_4_observed_baseline", "H3", "wallet_tier", "tier_4_observed_baseline", "wallet_count", 2704]])
    _csv(r / "h3_lead_lag_correlations.csv",
         ["tier", "lag_days", "observation_count", "correlation"],
         [["tier_1_top_1pct", 0, 304, -0.07], ["tier_1_top_1pct", 1, 303, 0.1858], ["tier_1_top_1pct", 2, 302, -0.01],
          ["tier_4_observed_baseline", 0, 304, 0.0], ["tier_4_observed_baseline", 1, 303, -0.02], ["tier_4_observed_baseline", 2, 302, -0.057]])
    _csv(r / "h3_granger_results.csv",
         ["tier", "lag_days", "observation_count", "f_statistic", "p_value"],
         [["tier_1_top_1pct", 1, 304, 10.7, 0.0012], ["tier_1_top_1pct", 2, 304, 5.0, 0.007],
          ["tier_4_observed_baseline", 1, 304, 0.1, 0.9], ["tier_4_observed_baseline", 2, 304, 0.5, 0.78]])
    _json(r / "h3_wallet_distribution_inventory.json", {
        "diagnostics": {"concentration": {"top_1_wallet_share": 0.679, "top_10_wallet_share": 0.724},
                        "cumulative_amount_usd_quantiles": {"min": 10000.0}},
        "input": {"date_range_start": "2024-01-01T04:24:22Z", "date_range_end": "2024-11-04T23:56:30Z"},
        "beispiel_adresse": "0xc5d563a36ae78145c45a50134d48a1215220f80a",
    })
    # Schweiz: ein Fall, zwei Umfragen, drei Preise, eine Antwortzeile.
    _csv(r / "swiss_referendum_10mio_final_case_study.csv",
         ["official_title", "vote_date", "official_outcome", "official_yes_share", "latest_live_polymarket_yes_probability",
          "latest_live_polymarket_vote_share_abs_error", "live_observation_rows", "history_observation_rows",
          "live_polymarket_beats_raw_vote_share_count", "live_polymarket_beats_raw_binary_proxy_count",
          "history_polymarket_beats_raw_vote_share_count", "official_dashboard_url"],
         [["Initiative", "2026-06-14", "rejected", 0.4521, 0.215, 0.2371, 74, 504, 0, 74, 36, "https://admin.ch"]])
    _csv(r / "swiss_referendum_10mio_poll_accuracy.csv",
         ["poll_id", "source_name", "published_at_utc", "final_poll_for_source", "yes_share", "no_share", "undecided_share",
          "raw_yes_signed_error", "raw_yes_abs_error", "poll_direction_against_50pct"],
         [["p1", "SRG/gfs.bern", "2026-05-08T03:56:00Z", "False", 0.47, 0.47, 0.06, 0.0179, 0.0179, "raw_yes_below_50pct_rejection_direction"],
          ["p2", "SRG/gfs.bern", "2026-06-03T03:55:00Z", "True", 0.45, 0.52, 0.03, -0.0021, 0.0021, "raw_yes_below_50pct_rejection_direction"]])
    _csv(r / "swiss_referendum_10mio_polymarket_price_history.csv",
         ["observed_at_utc", "yes_probability"],
         [["2026-04-28T00:00:11Z", 0.345], ["2026-04-28T05:00:11Z", 0.35], ["2026-06-13T13:04:20Z", 0.315]])
    _csv(r / "swiss_referendum_10mio_information_response.csv",
         ["poll_id", "poll_source", "poll_published_at_utc", "poll_signal_direction", "polymarket_change_1h", "polymarket_change_6h",
          "polymarket_change_24h", "polymarket_change_48h", "alignment_48h", "information_processing_label"],
         [["p2", "SRG/gfs.bern", "2026-06-03T03:55:00Z", "down", 0.0, -0.01, -0.04, -0.05, "same_direction", "delayed_same_direction_6h"]])
    _csv(r / "swiss_referendum_10mio_live_accuracy_windows.csv", ["observation_id"], [["a"], ["b"]])
    return ziel


class MiniThesisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.root = mini_thesis(Path(self.tmp.name))
        self.p = tr.build_payload(self.root, jetzt=datetime(2026, 9, 4, tzinfo=timezone.utc))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_vier_abschnitte_ohne_fehlende(self) -> None:
        self.assertEqual(self.p["fehlend"], [])
        self.assertEqual([s["id"] for s in self.p["sektionen"]], ["h1", "h2", "h3", "swiss"])
        self.assertEqual(self.p["zaehler"]["gesamt"], 4)
        self.assertEqual(self.p["stand_utc"], "2026-09-04T00:00:00+00:00")

    def test_jeder_abschnitt_hat_pflichtfelder(self) -> None:
        for s in self.p["sektionen"]:
            with self.subTest(abschnitt=s["id"]):
                for feld in ("frage", "verdikt", "verdikt_art", "einfach", "analyse", "interpretation", "zahlen", "diagramme", "quellen"):
                    self.assertTrue(s.get(feld), f"{feld} fehlt")
                self.assertIn(s["verdikt_art"], rp.VERDIKT_ARTEN)
                self.assertEqual([i["art"] for i in s["interpretation"]], [rp.LESART, rp.GEGENLESART, rp.GRENZE])

    def test_h1_zahlen_kommen_aus_den_tabellen(self) -> None:
        h1 = self.p["sektionen"][0]
        self.assertIn("10 overlap days", h1["verdikt"])
        self.assertIn("0.200 vs 0.300", h1["verdikt"])
        self.assertIn("262 of 285", h1["verdikt"])
        self.assertIn("2 of 3 scopes", h1["verdikt"])
        self.assertEqual(h1["verdikt_art"], rp.VERDIKT_GEMISCHT)
        self.assertFalse(h1["breite_behauptung_bewiesen"])
        self.assertEqual(h1["diagramme"]["brier_quellen"]["punkte"][0], {"label": "Polymarket", "wert": 0.2})
        # Zehn Tage im Maerz 2024 fallen in zwei ISO-Wochen.
        self.assertEqual(len(h1["diagramme"]["brier_wochen"]["x"]), 2)
        self.assertEqual(set(h1["diagramme"]["kalibrierung"]), {"polymarket_state_final_50", "rieke_state_final_50"})

    def test_h2_richtung_und_groesster_ausschlag(self) -> None:
        h2 = self.p["sektionen"][1]
        self.assertIn("1 of 1 directional events", h2["verdikt"])
        self.assertIn("+7.2 pp", h2["verdikt"])
        self.assertEqual(h2["verdikt_art"], rp.VERDIKT_JA)
        ereignisse = {e["id"]: e for e in h2["ereignisse"]}
        self.assertTrue(ereignisse["evt_a"]["treffer"])
        self.assertIsNone(ereignisse["evt_b"]["treffer"])
        pfad = h2["diagramme"]["pfade"]["serien"][0]["werte"]
        self.assertEqual(pfad, [0.1, 3.0, 7.0, None, None])

    def test_h3_bonferroni_und_top_tier(self) -> None:
        h3 = self.p["sektionen"][2]
        self.assertIn("32 wallets", h3["verdikt"])
        self.assertIn("r +0.186", h3["verdikt"])
        self.assertIn("Granger p 0.0012", h3["verdikt"])
        # Vier Tests, Bonferroni 0.0125: beide Top-Tier-p-Werte drunter.
        self.assertIn("2 fall below 0.05 and 2 survive a Bonferroni correction (0.0125)", h3["einfach"])
        self.assertIn("67.9%", h3["einfach"])
        self.assertEqual(h3["diagramme"]["tiers"]["punkte"], [{"label": "Top 1%", "wert": 32}, {"label": "Everyone else", "wert": 2704}])

    def test_schweiz_richtige_seite_falsche_zahl(self) -> None:
        sw = self.p["sektionen"][3]
        self.assertIn("21.5% against an official 45.21%", sw["verdikt"])
        self.assertIn("all 74 live windows", sw["verdikt"])
        self.assertEqual(sw["verdikt_art"], rp.VERDIKT_GEMISCHT)
        # Drei Stundenwerte an zwei Tagen ergeben zwei Tagespunkte, der
        # letzte je Tag gewinnt.
        self.assertEqual(sw["diagramme"]["preis"]["punkte"], [{"t": "2026-04-28", "wert": 0.35}, {"t": "2026-06-13", "wert": 0.315}])
        self.assertIn("1 of 1", [z["wert"] for z in sw["zahlen"] if z["label"].startswith("Poll releases")][0])

    def test_keine_wallet_adresse_in_der_nutzlast(self) -> None:
        # Das Inventar traegt eine Adresse; sie darf nicht durchrutschen.
        self.assertEqual(rp.wallet_adressen_in(self.p), [])

    def test_fehlende_tabelle_laesst_abschnitt_weg(self) -> None:
        (self.root / tr.RESULTS_DIR / "h2_event_window_rows.csv").unlink()
        p = tr.build_payload(self.root)
        self.assertEqual([s["id"] for s in p["sektionen"]], ["h1", "h3", "swiss"])
        self.assertEqual(p["fehlend"], ["h2_event_window_rows.csv"])
        self.assertEqual(tr.fehlende_dateien(self.root), ["h2_event_window_rows.csv"])

    def test_thesis_root_aus_umgebung(self) -> None:
        import os
        alt = os.environ.get("THESIS_ROOT")
        try:
            os.environ["THESIS_ROOT"] = str(self.root)
            self.assertEqual(tr.thesis_root(), self.root)
            self.assertEqual(tr.thesis_root("/x"), Path("/x"))
        finally:
            if alt is None:
                os.environ.pop("THESIS_ROOT", None)
            else:
                os.environ["THESIS_ROOT"] = alt


class EchtesThesisRepoTests(unittest.TestCase):
    """Nur lokal: das Schwester-Repo liegt neben diesem."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = tr.thesis_root(repo_root=PROJEKT)
        if tr.fehlende_dateien(cls.root):
            raise unittest.SkipTest("Thesis-Repo nicht vorhanden oder unvollstaendig")
        cls.p = tr.build_payload(cls.root)

    def test_vollstaendig_und_redigiert(self) -> None:
        self.assertEqual(self.p["fehlend"], [])
        self.assertEqual(self.p["zaehler"]["gesamt"], 4)
        self.assertEqual(rp.wallet_adressen_in(self.p), [])

    def test_kopfzahlen_der_thesis(self) -> None:
        h1, h2, h3, sw = self.p["sektionen"]
        self.assertIn("194 overlap days", h1["verdikt"])
        self.assertIn("262 of 285", h1["verdikt"])
        self.assertIn("+7.2 pp", h2["verdikt"])
        self.assertIn("Granger p 0.0012", h3["verdikt"])
        self.assertIn("45.21%", sw["verdikt"])


if __name__ == "__main__":
    unittest.main()
