import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app import analysis_views as av


class LoadPayloadTests(unittest.TestCase):
    def test_loads_valid_json(self):
        with TemporaryDirectory() as tmp:
            (Path(tmp) / "meta.json").write_text('{"backend": "mock"}', encoding="utf-8")
            self.assertEqual(av.load_publish_payload(Path(tmp), "meta.json"), {"backend": "mock"})

    def test_missing_or_broken_returns_none(self):
        with TemporaryDirectory() as tmp:
            self.assertIsNone(av.load_publish_payload(Path(tmp), "queue.json"))
            (Path(tmp) / "queue.json").write_text("{broken", encoding="utf-8")
            self.assertIsNone(av.load_publish_payload(Path(tmp), "queue.json"))
            (Path(tmp) / "list.json").write_text("[1, 2]", encoding="utf-8")
            self.assertIsNone(av.load_publish_payload(Path(tmp), "list.json"))


class QueueFilterTests(unittest.TestCase):
    CARDS = [
        {"id": "a", "score_band": "high"},
        {"id": "b", "score_band": "medium"},
        {"id": "c", "score_band": "low"},
    ]

    def test_filters_by_band(self):
        self.assertEqual([c["id"] for c in av.filter_queue_cards(self.CARDS, "medium")], ["b"])

    def test_unknown_band_returns_all(self):
        self.assertEqual(len(av.filter_queue_cards(self.CARDS, "Alle")), 3)


class KategoriePointsTests(unittest.TestCase):
    def test_joins_and_marks_censored(self):
        karte = {
            "kategorien": [
                {"kategorie": "Politik", "brier_t7": 0.35, "n_maerkte": 73},
                {"kategorie": "Sport", "brier_t7": 0.04, "n_maerkte": 60},
                {"kategorie": "Krypto", "brier_t7": None, "n_maerkte": 81},
            ],
            "beispiele": [
                {"kategorie": "Politik", "minuten_bis_konvergenz": 60.0, "praezisions_hinweis": "Median"},
                {"kategorie": "Sport", "minuten_bis_konvergenz": 210.0, "praezisions_hinweis": "enthaelt Spieldauer"},
                {"kategorie": "Krypto", "minuten_bis_konvergenz": 2.0, "praezisions_hinweis": ""},
            ],
        }
        points = av.kategorie_points(karte)
        self.assertEqual([p["kategorie"] for p in points], ["Politik", "Sport"])
        self.assertFalse(points[0]["censored"])
        self.assertTrue(points[1]["censored"])
        self.assertEqual(points[1]["minuten"], 210.0)

    def test_negative_konvergenz_floored_to_one_minute(self):
        # Vor dem Ereignis eingepreist (negative Minuten) darf auf der
        # log-Achse nicht still verschwinden -> Untergrenze 1 Minute.
        karte = {
            "kategorien": [{"kategorie": "Krypto", "brier_t7": 0.11, "n_maerkte": 81}],
            "beispiele": [{"kategorie": "Krypto", "minuten_bis_konvergenz": -44.0, "praezisions_hinweis": "Untergrenze 1 Minute"}],
        }
        points = av.kategorie_points(karte)
        self.assertEqual(len(points), 1)
        self.assertEqual(points[0]["minuten"], 1.0)
        self.assertEqual(points[0]["minuten_roh"], -44.0)

    def test_empty_karte_safe(self):
        self.assertEqual(av.kategorie_points({}), [])


class MentionsBarsTests(unittest.TestCase):
    def test_sorted_by_tradeable_window_desc(self):
        payload = {
            "faelle": [
                {"event": "kurz", "minuten_bis_erste_reaktion": 1.0, "minuten_bis_konvergenz": 30.0, "stunden_im_handelbaren_fenster": 0.5, "korrekt_aufgeloestes_outcome": "YES"},
                {"event": "lang", "minuten_bis_erste_reaktion": 2.0, "minuten_bis_konvergenz": 5.0, "stunden_im_handelbaren_fenster": 12.0, "korrekt_aufgeloestes_outcome": "NO"},
                {"event": "leer", "minuten_bis_erste_reaktion": None, "minuten_bis_konvergenz": None},
            ]
        }
        rows = av.mentions_bars(payload)
        self.assertEqual([r["event"] for r in rows], ["lang", "kurz"])
        self.assertEqual(rows[0]["outcome"], "NO")


class PipelineTimelineTests(unittest.TestCase):
    def test_log_order_and_whitelisted(self):
        payload = {
            "eintraege": [
                {"action": "NONE", "reason": "kein_yes_ask", "limit_price": None, "bestes_angebot": 0.9, "bestes_gebot": 0.8, "size_usd": None},
                {"action": "YES", "reason": "count", "limit_price": 0.82, "bestes_angebot": 0.82, "bestes_gebot": 0.8, "size_usd": 12.3},
            ]
        }
        rows = av.pipeline_timeline(payload)
        self.assertEqual([r["action"] for r in rows], ["NONE", "YES"])
        self.assertEqual(
            set(rows[0].keys()),
            {"action", "reason", "limit_price", "bestes_angebot", "bestes_gebot", "size_usd"},
        )

    def test_action_counts(self):
        payload = {"eintraege": [{"action": "NONE"}] * 34 + [{"action": "YES"}]}
        self.assertEqual(av.pipeline_action_counts(payload), {"NONE": 34, "YES": 1})


class PipelineLaeufeTests(unittest.TestCase):
    def test_laeufe_in_quellreihenfolge(self):
        payload = {
            "eintraege": [{"action": "YES"}],
            "wortzaehler_endstaende": {"a": 1},
            "laeufe": [
                {
                    "profil": "allin_july17",
                    "n_eintraege": 31,
                    "n_kaeufe": 6,
                    "eintraege": [{"action": "YES"}],
                    "wortzaehler_endstaende": {"a": 1},
                },
                {
                    "profil": "allin_july3",
                    "n_eintraege": 35,
                    "n_kaeufe": 1,
                    "eintraege": [{"action": "NONE"}],
                    "wortzaehler_endstaende": {},
                },
            ],
        }
        laeufe = av.pipeline_laeufe(payload)
        self.assertEqual([l["profil"] for l in laeufe], ["allin_july17", "allin_july3"])
        self.assertEqual(laeufe[0]["n_eintraege"], 31)
        self.assertEqual(laeufe[0]["n_kaeufe"], 6)
        self.assertEqual(laeufe[0]["wortzaehler_endstaende"], {"a": 1})

    def test_altes_artefakt_ohne_laeufe_ergibt_einen_lauf(self):
        payload = {
            "eintraege": [{"action": "NONE"}, {"action": "YES"}],
            "wortzaehler_endstaende": {"a": 2},
        }
        laeufe = av.pipeline_laeufe(payload)
        self.assertEqual(len(laeufe), 1)
        self.assertEqual(laeufe[0]["n_eintraege"], 2)
        self.assertEqual(laeufe[0]["n_kaeufe"], 1)
        self.assertEqual(laeufe[0]["wortzaehler_endstaende"], {"a": 2})

    def test_leeres_artefakt_ergibt_keine_laeufe(self):
        self.assertEqual(av.pipeline_laeufe({"eintraege": []}), [])
        self.assertEqual(av.pipeline_laeufe({}), [])

    def test_default_lauf_ist_juengster_mit_kaeufen(self):
        laeufe = [
            {"profil": "jre_july20", "n_kaeufe": 0},
            {"profil": "allin_july17", "n_kaeufe": 6},
            {"profil": "allin_july3", "n_kaeufe": 1},
        ]
        self.assertEqual(av.pipeline_default_lauf(laeufe), 1)

    def test_default_lauf_ohne_kaeufe_ist_juengster(self):
        laeufe = [{"profil": "a", "n_kaeufe": 0}, {"profil": "b", "n_kaeufe": 0}]
        self.assertEqual(av.pipeline_default_lauf(laeufe), 0)
        self.assertEqual(av.pipeline_default_lauf([]), 0)

    def test_timeline_arbeitet_auf_einem_lauf(self):
        lauf = av.pipeline_laeufe(
            {
                "laeufe": [
                    {
                        "profil": "p",
                        "eintraege": [
                            {"action": "YES", "reason": "r", "limit_price": 0.5,
                             "bestes_angebot": 0.6, "bestes_gebot": 0.4, "size_usd": 1.0},
                        ],
                        "wortzaehler_endstaende": {},
                    }
                ]
            }
        )[0]
        rows = av.pipeline_timeline(lauf)
        self.assertEqual([r["action"] for r in rows], ["YES"])
        self.assertEqual(av.pipeline_action_counts(lauf), {"YES": 1})


class AuditHashTests(unittest.TestCase):
    def test_pairs_and_caps(self):
        audit = {"prompt_hashes": ["p1", "p2", "p3"], "output_hashes": ["o1", "o2", "o3"]}
        rows = av.audit_hash_rows(audit, limit=2)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0], {"call": "1", "prompt_hash": "p1", "output_hash": "o1"})


RUNS_PAYLOAD = {
    "hinweis": "Deskriptive Nachauswertung",
    "stand_utc": "2026-07-10T12:00:00+00:00",
    "kennzeichnung": "live/deskriptiv",
    "aggregat": {
        "n_runs": 3, "n_wetten": 2, "gewonnen": 1, "verloren": 0, "offen": 1,
        "einsatz_usd": 108.36, "aufgeloester_einsatz_usd": 5.97,
        "realisierter_payout_usd": 7.02, "realisierter_pnl_usd": 1.05,
        "roi_realisiert_pct": 17.6, "offener_einsatz_usd": 102.39,
    },
    "runs": [
        {
            "profil": "allin_july3", "event_slug": "s", "episode_titel": "Ep 1",
            "modus": "LIVE", "drop_quelle": "libsyn_rss",
            "pubdate_utc": "2026-07-03T22:12:00Z",
            "drop_erkannt_utc": "2026-07-03T23:21:22Z",
            "erkennungslatenz_s": 4162.0, "erste_entscheidung_s": 70.0,
            "erster_fill_s": 75.0, "n_maerkte": 20, "n_entscheidungen": 35,
            "zaehler": {"no_action": 34, "live_partial": 1}, "eingepreist": 19,
            "einsatz_usd": 5.97, "realisierter_pnl_usd": 1.05,
            "wetten": [{
                "frage": "Will Tourism be said?", "seite": "YES",
                "entscheidungs_preis": 0.13, "avg_fill_preis": 0.8504,
                "shares": 7.02, "einsatz_usd": 5.97, "sweep_clips": 1,
                "fill_status": "live_partial",
                "fill_ts_utc": "2026-07-03T23:22:37Z", "aufgeloest": True,
                "gewonnen": True, "payout_usd": 7.02, "pnl_usd": 1.05,
                "roi_pct": 17.6, "aktueller_yes_preis": None,
            }],
            "verpasste_chancen": [],
        },
        {
            "profil": "allin_july10", "event_slug": "s2",
            "episode_titel": "Ep 2", "modus": "LIVE", "drop_quelle": "youtube",
            "pubdate_utc": "2026-07-10T01:15:25+00:00",
            "drop_erkannt_utc": "2026-07-10T01:17:27Z",
            "erkennungslatenz_s": 122.0, "erste_entscheidung_s": 52.0,
            "erster_fill_s": 64.0, "n_maerkte": 19, "n_entscheidungen": 22,
            "zaehler": {"no_action": 7, "live_fill": 1, "skipped_budget": 14},
            "eingepreist": 3, "einsatz_usd": 102.39,
            "realisierter_pnl_usd": None,
            "wetten": [{
                "frage": "Will IPO be said?", "seite": "YES",
                "entscheidungs_preis": 0.63, "avg_fill_preis": 0.9001,
                "shares": 113.76, "einsatz_usd": 102.39, "sweep_clips": 5,
                "fill_status": "live_fill",
                "fill_ts_utc": "2026-07-10T01:18:31Z", "aufgeloest": False,
                "gewonnen": None, "payout_usd": None, "pnl_usd": None,
                "roi_pct": None, "aktueller_yes_preis": 0.67,
            }],
            "verpasste_chancen": [{
                "frage": "Will Musk be said?", "seite": "YES",
                "limit_preis": 0.83, "grund": "budget_erschoepft",
            }],
        },
    ],
}


class RunDashboardViewTests(unittest.TestCase):
    def test_format_sekunden(self):
        self.assertEqual(av.format_sekunden(None), "--")
        self.assertEqual(av.format_sekunden(64.0), "64 s")
        self.assertEqual(av.format_sekunden(4162.0), "69 min")

    def test_run_kpis_defaults_and_values(self):
        kpis = av.run_kpis(RUNS_PAYLOAD)
        self.assertEqual(kpis["n_runs"], 3)
        self.assertEqual(kpis["realisierter_pnl_usd"], 1.05)
        self.assertEqual(kpis["roi_realisiert_pct"], 17.6)
        leer = av.run_kpis({})
        self.assertEqual(leer["n_wetten"], 0)
        self.assertIsNone(leer["roi_realisiert_pct"])

    def test_run_latenz_rows(self):
        rows = av.run_latenz_rows(RUNS_PAYLOAD)
        self.assertEqual([r["profil"] for r in rows],
                         ["allin_july3", "allin_july10"])
        self.assertEqual(rows[1]["erster_fill_s"], 64.0)
        self.assertEqual(rows[0]["n_wetten"], 1)
        self.assertEqual(av.run_latenz_rows({}), [])

    def test_wette_status(self):
        self.assertEqual(av.wette_status({"aufgeloest": True, "gewonnen": True}),
                         ("WON", "win"))
        self.assertEqual(av.wette_status({"aufgeloest": True, "gewonnen": False}),
                         ("LOST", "loss"))
        self.assertEqual(av.wette_status({"aufgeloest": False}), ("OPEN", "open"))

    def test_run_wetten_rows(self):
        rows = av.run_wetten_rows(RUNS_PAYLOAD["runs"][1])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status_label"], "OPEN")
        self.assertEqual(rows[0]["sweep_clips"], 5)
        self.assertEqual(rows[0]["aktueller_yes_preis"], 0.67)

    def test_run_verpasste_rows(self):
        rows = av.run_verpasste_rows(RUNS_PAYLOAD["runs"][1])
        self.assertEqual(rows[0]["limit_preis"], 0.83)
        self.assertEqual(av.run_verpasste_rows({}), [])


if __name__ == "__main__":
    unittest.main()


class ShowcaseViewTests(unittest.TestCase):
    RUNS = {
        "aggregat": {"sichtbare_tiefe_usd": 929.87,
                     "einsatz_zu_sichtbarer_tiefe_pct": 67.4},
        "runs": [{
            "profil": "allin_july17", "episode_titel": "E281",
            "drop_quelle": "mp3_url_prober", "erkennungslatenz_s": None,
            "erster_fill_s": 70.0, "einsatz_usd": 250.0,
            "realisierter_pnl_usd": 15.01,
            "sichtbare_tiefe_usd": 318.35,
            "einsatz_zu_sichtbarer_tiefe_pct": 113.1,
            "wallet_netto_usd": 119.84,
            "wallet_kaeufe_usd": 288.09,
            "race": {"first_on": 6, "wetten_mit_tape": 6},
            "wetten": [
                {"aufgeloest": True, "gewonnen": True},
                {"aufgeloest": True, "gewonnen": False},
                {"aufgeloest": False, "gewonnen": None},
            ],
        }],
    }

    def test_track_record_rows(self):
        [row] = av.track_record_rows(self.RUNS)
        self.assertEqual(row["profil"], "allin_july17")
        self.assertEqual(row["n_wetten"], 3)
        self.assertEqual(row["gewonnen"], 1)
        self.assertEqual(row["verloren"], 1)
        self.assertEqual(row["race_first"], "6/6")
        self.assertEqual(row["sichtbare_tiefe_usd"], 318.35)
        # Cash wallet-first: Stake/PnL kommen aus dem Wallet-Abgleich.
        self.assertEqual(row["einsatz_usd"], 288.09)
        self.assertEqual(row["pnl_usd"], 119.84)
        self.assertEqual(row["cash_basis"], "wallet")

    def test_track_record_ohne_race(self):
        runs = {"runs": [{"profil": "x", "wetten": [], "race": None,
                          "einsatz_usd": 5.0,
                          "realisierter_pnl_usd": 1.0}]}
        [row] = av.track_record_rows(runs)
        self.assertIsNone(row["race_first"])
        self.assertEqual(row["n_wetten"], 0)
        # Ohne Wallet-Overlay: Log-Werte mit Basis-Flag "log".
        self.assertEqual(row["einsatz_usd"], 5.0)
        self.assertEqual(row["pnl_usd"], 1.0)
        self.assertEqual(row["cash_basis"], "log")

    def test_postmortem_rows_neueste_zuerst(self):
        payload = {"eintraege": [
            {"datum": "2026-07-10", "titel": "alt"},
            {"datum": "2026-07-18", "titel": "neu"},
        ]}
        rows = av.postmortem_rows(payload)
        self.assertEqual(rows[0]["titel"], "neu")

    def test_pilot_overview_und_signale(self):
        payload = {
            "protokoll": {
                "budget_usdc": 100.0, "einsatz_je_trade_usdc": 10.0,
                "regel_freeze_datum": "2026-07-18",
                "handelsfenster_bis": "2026-08-01",
                "quelle": "docs/x.md", "arm1_kurz": "a1", "arm2_kurz": "a2",
            },
            "watcher_lauf_ts_utc": "2026-07-18T10:19:52Z",
            "signal_zaehler": {"arm2:signal": 92,
                               "arm1:kandidat_referenz_pruefen": 1},
            "signale_neueste": [{"ts_utc": "t", "arm": "arm2"}],
            "trades": [],
        }
        ov = av.pilot_overview(payload)
        self.assertEqual(ov["n_signale"], 93)
        self.assertEqual(ov["n_trades"], 0)
        self.assertEqual(ov["budget_usdc"], 100.0)
        self.assertEqual(len(av.pilot_signal_rows(payload)), 1)

    def test_pilot_overview_leer_faellt_weich(self):
        ov = av.pilot_overview({})
        self.assertEqual(ov["n_signale"], 0)
        self.assertIsNone(ov["budget_usdc"])
