"""Geschluckte Fehler in den Wallet- und Copy-Pfaden.

Dritte Folge nach ``tests/test_venue_feed_integrity.py`` (umbenanntes Feld)
und ``tests/test_swallowed_errors.py`` (ausgefallener Teil-Request). Hier
geht es um Stellen, an denen ein gefangener Fehler nicht zu weniger Daten
fuehrt, sondern zu anderen: ein Vorgabewert nimmt den Platz einer Messung
ein, und nichts an der Oberflaeche sagt, dass gemessen gar nicht wurde.

Nach Schadenshoehe:

* ``copy_trading._apply_redeem`` rechnete eine verlierende Papier-Position
  mit einem Dollar je Anteil ab, sobald ein einzelner HTTP-Aufruf in der
  Gewinner-Auskunft fehlschlug. Aus einem Totalverlust wurde eine volle
  Auszahlung, und das Papierbuch, der Copy-Desk und jede daraus abgeleitete
  Kennzahl trugen den Fehler weiter, ohne dass etwas fehlschlug.
* ``track_record.reconcile_resolved_with_activity`` hat die Verkaufsseite
  ungeprueft mit null angesetzt und die so gerechnete Zeile als
  ``pnl_source="cash_flow"``, also als die vertrauenswuerdigere Zahl,
  ausgewiesen.
* ``prediction_terminal.load_wallet_account_stats`` machte aus einem
  Netz-Aussetzer drei falsche Aussagen: ein junges Konto, ein Insider-Bonus
  darauf und ein Kassenstand von null.
* ``load_wallet_win_rates`` las den Gewinner-Rand des gedeckelten Feeds und
  meldete dessen Trefferquote als die der Wallet.
* ``api/server.build_wallet_detail`` behauptete ``activity_truncated=False``
  ueber einem Abruf, der gar nicht angekommen war.

Alles gegen ``tests/market_api_fixtures.py``, also ohne Netz.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from app import track_record as trec
from src import copy_trading as ct
from tests.market_api_fixtures import (
    WALLETS,
    failing_requests,
    offline_market_apis,
)

#: Der Markt, um den es in den Copy-Tests geht. Der Name ist zugleich das
#: Ende des CLOB-Pfads ``/markets/<condition>``, weshalb ``failing_requests``
#: genau diesen einen Aufruf scheitern lassen kann und sonst keinen.
MARKT = "market-1"


def quellen_trade(
    *,
    tx: str = "0xno",
    asset: str = "no-token",
    outcome: str = "No",
    price: float = 0.6,
    size: float = 1000.0,
) -> dict:
    return {
        "transaction_hash": tx,
        "asset": asset,
        "side": "BUY",
        "price": price,
        "size": size,
        "timestamp": 1779900000,
        "market_key": MARKT,
        "title": "Example market",
        "outcome": outcome,
        "time": "2026-05-27T18:00:00Z",
    }


def redeem_aktivitaet(size: float = 1000.0, usdc: float = 1000.0) -> pd.DataFrame:
    """Die Quelle loest ihre Gewinnerseite ein: 1000 Anteile fuer 1000 Dollar."""

    return pd.DataFrame(
        [
            {
                "type": "REDEEM",
                "conditionId": MARKT,
                "transactionHash": "0xredeem-loss",
                "timestamp": 1779900100,
                "size": size,
                "usdcSize": usdc,
                "title": "Example market",
            }
        ]
    )


class GewinnerAuskunftTests(unittest.TestCase):
    """Die Auskunft trennt "kein Gewinner" von "keine Antwort"."""

    def test_a_market_that_did_not_answer_is_not_an_answer(self) -> None:
        with failing_requests(MARKT):
            auskunft = ct.fetch_closed_market_winner_assets([MARKT])
        self.assertEqual(dict(auskunft), {})
        self.assertIn(MARKT, auskunft.unanswered)
        self.assertFalse(auskunft.outcome_known(MARKT))
        self.assertTrue(auskunft.errors)

    def test_markets_above_the_cap_are_never_asked_and_say_so(self) -> None:
        # Ungefragt ist nicht beantwortet: ueber der Schranke wurde die Frage
        # nie gestellt, und frueher sah das aus wie "kein Gewinner".
        conditions = [f"c-{index}" for index in range(5)]
        with offline_market_apis():
            auskunft = ct.fetch_closed_market_winner_assets(conditions, max_conditions=2)
        self.assertEqual(len(auskunft.unanswered), 3)
        self.assertTrue(auskunft.outcome_known("c-0"))
        self.assertFalse(auskunft.outcome_known("c-4"))

    def test_a_plain_mapping_still_counts_as_answered(self) -> None:
        # Aufrufer, die eine gewoehnliche Zuordnung uebergeben, sagen damit
        # nichts ueber Ausfaelle aus; ihr Verhalten bleibt, wie es war.
        auskunft = ct._als_winner_lookup({MARKT: {"yes-token"}})
        self.assertTrue(auskunft.outcome_known(MARKT))
        self.assertTrue(auskunft.outcome_known("market-2"))


class EinloesungOhneAusgangTests(unittest.TestCase):
    """Eine Aufloesung ohne gelesenen Ausgang wird nicht gebucht.

    Das Zahlenbeispiel, in dem der Fehler steckte: die Quelle kauft 1000
    Anteile "No" zu 60 Cent, der Copier spiegelt ein Prozent davon, also 10
    Anteile fuer 6 Dollar. Die Kasse steht danach bei 994. Der Markt geht
    gegen "No" aus, die Quelle loest ihre Gewinnerseite fuer 1000 Dollar
    ein.

    * Auskunft vorhanden: 10 Anteile mal 0 Dollar, realisiert -6.00, Kasse
      bleibt 994.00.
    * Auskunft ausgefallen, alter Stand: 10 Anteile mal 1.00 Dollar,
      realisiert +4.00, Kasse 1004.00. Ein Verlust von 6 Dollar wird als
      Gewinn von 4 Dollar gebucht, ein Ausschlag von 10 Dollar auf einer
      Position von 6.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "copy.sqlite"
        self.settings = ct.CopySettings(trade_limit=20)
        ct.reset_paper_portfolio(db_path=self.db_path)
        conn = ct.connect(self.db_path)
        try:
            ct.apply_paper_trade(conn, quellen_trade(), self.settings)
            conn.commit()
        finally:
            conn.close()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _sync(self):
        with patch("src.copy_trading.fetch_source_activity", return_value=redeem_aktivitaet()), patch(
            "src.copy_trading.fetch_position_metadata", return_value={}
        ), failing_requests(MARKT):
            return ct.sync_settlement_activity(ct.COPY_TARGET_WALLET, settings=self.settings, db_path=self.db_path)

    def test_the_paper_book_starts_at_ten_shares_for_six_dollars(self) -> None:
        snapshot = ct.value_paper_portfolio(db_path=self.db_path)
        self.assertAlmostEqual(snapshot.cash, 994.0)
        self.assertAlmostEqual(float(snapshot.positions.iloc[0]["shares"]), 10.0)
        self.assertAlmostEqual(float(snapshot.positions.iloc[0]["cost_basis"]), 6.0)

    def test_a_failed_winner_lookup_no_longer_pays_a_dollar_a_share(self) -> None:
        result = self._sync()
        snapshot = ct.value_paper_portfolio(db_path=self.db_path)
        # Die Zahl, die frueher hier stand: 1004.00 Kasse und +4.00 realisiert.
        self.assertAlmostEqual(snapshot.cash, 994.0)
        self.assertAlmostEqual(snapshot.realized_pnl, 0.0)
        self.assertEqual(result.undecided, 1)
        self.assertEqual(result.copied, 0)

    def test_the_undecided_position_stays_open_and_is_named(self) -> None:
        result = self._sync()
        snapshot = ct.value_paper_portfolio(db_path=self.db_path)
        self.assertFalse(snapshot.positions.empty)
        self.assertAlmostEqual(float(snapshot.positions.iloc[0]["shares"]), 10.0)
        self.assertTrue(any("did not answer" in err for err in result.errors))

    def test_no_order_is_written_so_the_next_pass_tries_again(self) -> None:
        # Eine geschriebene Order gaelte beim naechsten Lauf als Duplikat:
        # die Position bliebe fuer immer offen, und das waere die zweite
        # stille Falschaussage.
        self._sync()
        self.assertTrue(ct.get_paper_orders(db_path=self.db_path).query("status == 'undecided'").empty)
        with patch("src.copy_trading.fetch_source_activity", return_value=redeem_aktivitaet()), patch(
            "src.copy_trading.fetch_position_metadata", return_value={}
        ), patch("src.copy_trading.fetch_closed_position_assets", return_value={MARKT: {"yes-token"}}):
            zweiter = ct.sync_settlement_activity(ct.COPY_TARGET_WALLET, settings=self.settings, db_path=self.db_path)
        snapshot = ct.value_paper_portfolio(db_path=self.db_path)
        self.assertEqual(zweiter.undecided, 0)
        self.assertTrue(snapshot.positions.empty)
        self.assertAlmostEqual(snapshot.cash, 994.0)
        self.assertAlmostEqual(snapshot.realized_pnl, -6.0)

    def test_a_readable_lookup_still_settles_the_loser_at_zero(self) -> None:
        # Die Gegenprobe: nichts faellt aus, also wird abgerechnet wie bisher.
        with patch("src.copy_trading.fetch_source_activity", return_value=redeem_aktivitaet()), patch(
            "src.copy_trading.fetch_position_metadata", return_value={}
        ), patch("src.copy_trading.fetch_closed_position_assets", return_value={MARKT: {"yes-token"}}):
            result = ct.sync_settlement_activity(ct.COPY_TARGET_WALLET, settings=self.settings, db_path=self.db_path)
        snapshot = ct.value_paper_portfolio(db_path=self.db_path)
        self.assertEqual(result.undecided, 0)
        self.assertAlmostEqual(snapshot.cash, 994.0)
        self.assertAlmostEqual(snapshot.realized_pnl, -6.0)


class VerkaufsSeiteTests(unittest.TestCase):
    """Die Korrektur aus dem Zahlungsstrom braucht auch die Verkaufsseite.

    Zahlenbeispiel: 100 Anteile zu 50 Cent gekauft (50 Dollar), 60 davon zu
    80 Cent verkauft (48 Dollar), die restlichen 40 zu einem Dollar
    eingeloest (40 Dollar). Der eigene Zahlungsstrom ist also +38.00. Faellt
    der Verkauf aus dem gelesenen Fenster, rechnet die Korrektur 0 + 40 - 50
    = -10.00 und weist die Zeile als ``cash_flow`` aus, also als die
    verlaesslichere Zahl. Der Fehler betraegt 48 Dollar und hat das Vorzeichen
    gewechselt.
    """

    def setUp(self) -> None:
        self.resolved = pd.DataFrame(
            [
                {
                    "market_key": "0xmarkt",
                    "outcome": "Yes",
                    "title": "Example market",
                    "current_price": 1.0,
                    "realized_pnl": -50.0,
                }
            ]
        )

    @staticmethod
    def _aktivitaet(mit_verkauf: bool) -> pd.DataFrame:
        rows = [
            {"market_key": "0xmarkt", "outcome": "Yes", "type": "TRADE", "side": "BUY", "notional": 50.0},
            {"market_key": "0xmarkt", "outcome": "Yes", "type": "REDEEM", "side": "", "notional": 40.0},
        ]
        if mit_verkauf:
            rows.insert(1, {"market_key": "0xmarkt", "outcome": "Yes", "type": "TRADE", "side": "SELL", "notional": 48.0})
        return pd.DataFrame(rows)

    def test_a_complete_window_still_corrects_the_row(self) -> None:
        out, korrigiert = trec.reconcile_resolved_with_activity(self.resolved, self._aktivitaet(True))
        self.assertEqual(korrigiert, 1)
        self.assertAlmostEqual(float(out.iloc[0]["realized_pnl"]), 38.0)
        self.assertEqual(str(out.iloc[0]["pnl_source"]), "cash_flow")

    def test_a_truncated_window_no_longer_invents_a_correction(self) -> None:
        # Die Zahl, die frueher hier stand: -10.00, ausgewiesen als cash_flow.
        aktivitaet = self._aktivitaet(False)
        aktivitaet.attrs["window_truncated"] = True
        out, korrigiert = trec.reconcile_resolved_with_activity(self.resolved, aktivitaet)
        self.assertEqual(korrigiert, 0)
        self.assertAlmostEqual(float(out.iloc[0]["realized_pnl"]), -50.0)
        self.assertEqual(str(out.iloc[0]["pnl_source"]), "unverified")
        self.assertEqual(out.attrs["pnl_reconciliation"]["withheld"], 1)

    def test_the_flag_can_also_be_passed_explicitly(self) -> None:
        out, korrigiert = trec.reconcile_resolved_with_activity(
            self.resolved, self._aktivitaet(False), window_truncated=True
        )
        self.assertEqual(korrigiert, 0)
        self.assertEqual(str(out.iloc[0]["pnl_source"]), "unverified")

    def test_an_unreadable_window_withholds_the_correction_too(self) -> None:
        aktivitaet = self._aktivitaet(True)
        aktivitaet.attrs["read_error"] = "connection reset by peer"
        out, korrigiert = trec.reconcile_resolved_with_activity(self.resolved, aktivitaet)
        self.assertEqual(korrigiert, 0)
        self.assertEqual(str(out.iloc[0]["pnl_source"]), "unverified")


class KontoStatistikTests(unittest.TestCase):
    """Ein abgebrochenes Fenster ist kein junges Konto, ein toter RPC keine leere Kasse."""

    WALLET = WALLETS[0]

    def setUp(self) -> None:
        import prediction_terminal as pt

        self.pt = pt
        pt.load_wallet_account_stats.clear()

    @staticmethod
    def _volle_seite(alter_tage: float) -> pd.DataFrame:
        """500 Zeilen, die juengste jetzt, die aelteste ``alter_tage`` alt."""

        jetzt = pd.Timestamp.now(tz="UTC")
        return pd.DataFrame(
            {
                "time": [jetzt - pd.Timedelta(days=alter_tage * index / 499) for index in range(500)],
                "notional": [10.0] * 500,
            }
        )

    def test_an_intact_window_measures_the_account_age(self) -> None:
        with offline_market_apis(), patch("src.copy_trading.fetch_polygon_usdc_balance", return_value=4_200.0):
            frame = self.pt.load_wallet_account_stats((self.WALLET,))
        row = frame.iloc[0]
        self.assertEqual(row["account_age_state"], self.pt.ACCOUNT_AGE_MEASURED)
        self.assertIsNotNone(row["account_age_days"])
        self.assertAlmostEqual(float(row["cash_balance"]), 4_200.0)
        self.assertTrue(bool(row["cash_balance_read"]))

    def test_a_broken_page_loop_no_longer_reports_a_young_account(self) -> None:
        # Der Fall, aus dem "new account (3d)" wurde: Seite 1 kommt voll
        # zurueck und reicht drei Tage zurueck, Seite 2 kommt nicht an. Der
        # aelteste gelesene Eintrag ist dann drei Tage alt, das Konto nicht.
        seiten = [self._volle_seite(3.0), ConnectionError("connection reset by peer")]

        def hole(_wallet, limit=500, offset=0, **_kwargs):
            eintrag = seiten[min(offset // 500, len(seiten) - 1)]
            if isinstance(eintrag, Exception):
                raise eintrag
            return eintrag

        with patch("src.prediction_markets.get_polymarket_activity", side_effect=hole), patch(
            "src.copy_trading.fetch_polygon_usdc_balance", return_value=1.0
        ):
            frame = self.pt.load_wallet_account_stats((self.WALLET,))
        row = frame.iloc[0]
        self.assertEqual(row["account_age_state"], self.pt.ACCOUNT_AGE_UNKNOWN)
        self.assertIsNone(row["account_age_days"])
        self.assertTrue(pd.isna(row["oldest_activity_time"]))
        self.assertIn("connection reset", str(row["activity_error"]))

    def test_a_window_that_hit_the_page_cap_is_a_lower_bound_not_an_age(self) -> None:
        with patch("src.prediction_markets.get_polymarket_activity", return_value=self._volle_seite(4.0)), patch(
            "src.copy_trading.fetch_polygon_usdc_balance", return_value=1.0
        ):
            frame = self.pt.load_wallet_account_stats((self.WALLET,))
        row = frame.iloc[0]
        self.assertEqual(row["account_age_state"], self.pt.ACCOUNT_AGE_WINDOW_CAPPED)
        self.assertIsNone(row["account_age_days"])
        self.assertGreater(float(row["activity_window_days"]), 3.0)

    def test_a_failed_balance_call_is_not_a_balance_of_zero(self) -> None:
        with offline_market_apis(), patch(
            "src.copy_trading.fetch_polygon_usdc_balance", side_effect=RuntimeError("rpc unavailable")
        ):
            frame = self.pt.load_wallet_account_stats((self.WALLET,))
        row = frame.iloc[0]
        self.assertTrue(pd.isna(row["cash_balance"]))
        self.assertFalse(bool(row["cash_balance_read"]))
        self.assertIn("rpc unavailable", str(row["cash_balance_error"]))

    def test_an_unmeasured_age_earns_no_insider_points_and_no_flag(self) -> None:
        from app import suspicion as susp

        risk = pd.DataFrame(
            [{"wallet": self.WALLET, "wallet_insider_score": 40.0, "wallet_insider_flags": ""}]
        )
        stats = pd.DataFrame(
            [{"wallet": self.WALLET, "account_age_days": 3.0, "account_age_state": self.pt.ACCOUNT_AGE_UNKNOWN}]
        )
        out = susp.apply_account_age_bonus(risk, stats)
        # Die Zahlen, die frueher hier standen: 50 Punkte und "new account (3d)".
        self.assertAlmostEqual(float(out.iloc[0]["wallet_insider_score"]), 40.0)
        self.assertNotIn("new account", str(out.iloc[0]["wallet_insider_flags"]))

    def test_a_measured_young_account_still_earns_them(self) -> None:
        from app import suspicion as susp

        risk = pd.DataFrame(
            [{"wallet": self.WALLET, "wallet_insider_score": 40.0, "wallet_insider_flags": ""}]
        )
        stats = pd.DataFrame(
            [{"wallet": self.WALLET, "account_age_days": 3.0, "account_age_state": self.pt.ACCOUNT_AGE_MEASURED}]
        )
        out = susp.apply_account_age_bonus(risk, stats)
        self.assertAlmostEqual(float(out.iloc[0]["wallet_insider_score"]), 50.0)
        self.assertIn("new account (3d)", str(out.iloc[0]["wallet_insider_flags"]))

    def test_an_unknown_balance_no_longer_reads_as_fully_exposed(self) -> None:
        from src import prediction_markets as md

        offen = pd.DataFrame([{"value": 5_000.0, "unrealized_pnl": 0.0, "initial_value": 5_000.0}])
        leer = pd.DataFrame()
        gemessen = md.trader_insight_metrics(offen, leer, leer, cash_balance=5_000.0)
        unbekannt = md.trader_insight_metrics(offen, leer, leer, cash_balance=float("nan"))
        self.assertAlmostEqual(float(gemessen["exposure"]), 0.5)
        # Frueher: 1.0, also "100% exposed" aus einer nicht gelesenen Kasse.
        self.assertIsNone(unbekannt["exposure"])


class GewinnerRandTests(unittest.TestCase):
    """Die Trefferquote der Bestenliste liest beide Enden, nicht nur eines.

    Der Feed deckelt bei rund 50 Zeilen und sortiert ohne Zutun nach dem
    groessten Gewinn. Hier antwortet er wie das Original: absteigend drei
    Gewinner, aufsteigend drei Verlierer. Der Gewinner-Rand allein ergibt
    3 von 3, also 100%; beide Enden ergeben 3 von 6, also 50%.
    """

    WALLET = WALLETS[0]

    def setUp(self) -> None:
        import prediction_terminal as pt

        self.pt = pt
        pt.load_wallet_win_rates.clear()

    @staticmethod
    def _zeile(index: int, pnl: float) -> dict:
        return {
            "proxyWallet": GewinnerRandTests.WALLET,
            "conditionId": f"0x{index:064x}",
            "title": f"Market {index}",
            "outcome": "Yes",
            "asset": str(index),
            "avgPrice": 0.4,
            "curPrice": 1.0 if pnl > 0 else 0.0,
            "totalBought": 100.0,
            "realizedPnl": pnl,
            "timestamp": 1779900000 + index,
            "slug": f"market-{index}",
            "eventSlug": f"market-{index}",
        }

    def _sortierter_feed(self):
        gewinner = [self._zeile(index, 500.0 - index * 100) for index in range(3)]
        verlierer = [self._zeile(10 + index, -200.0 - index * 100) for index in range(3)]

        def hole(url: str, params=None, **kwargs):
            from tests.market_api_fixtures import FixtureResponse, fixture_get

            if str(url).rstrip("/").endswith("/closed-positions"):
                richtung = str((params or {}).get("sortDirection", "DESC")).upper()
                return FixtureResponse(verlierer if richtung == "ASC" else gewinner)
            return fixture_get(url, params=params, **kwargs)

        return patch("requests.get", side_effect=hole)

    def test_both_tails_are_read_so_the_rate_is_not_the_winner_tail(self) -> None:
        with self._sortierter_feed():
            frame = self.pt.load_wallet_win_rates((self.WALLET,))
        row = frame.iloc[0]
        # Die Zahlen, die frueher hier standen: Trefferquote 1.0 ueber 3
        # Positionen und $1,200.00 realisiert, weil nur die absteigende Seite
        # gelesen wurde. Beide Enden: 3 von 6 und $300.00.
        self.assertAlmostEqual(float(row["win_rate"]), 0.5)
        self.assertEqual(int(row["closed_positions"]), 6)
        self.assertEqual(int(row["winning_positions"]), 3)
        self.assertAlmostEqual(float(row["closed_realized_pnl"]), 300.0)
        self.assertFalse(bool(row["win_rate_capped"]))


class AktivitaetsFensterTests(unittest.TestCase):
    """Ein gescheiterter Abruf behauptet keine Vollstaendigkeit mehr."""

    WALLET = WALLETS[0]

    def _payload(self):
        from api import server

        with patch.object(server, "load_ranked", return_value=pd.DataFrame()), patch.object(
            server, "risk_screen_basis", return_value=(pd.DataFrame(), pd.DataFrame(), 2500.0)
        ), patch.object(server, "load_leaderboard", return_value=pd.DataFrame()), failing_requests("/activity"):
            return server.build_wallet_detail(self.WALLET)

    def test_a_failed_activity_fetch_is_named_instead_of_claimed_complete(self) -> None:
        payload = self._payload()
        activity = payload["activity"]
        # Frueher: window_truncated False, n_rows 0, kein Feld dazwischen --
        # nicht zu unterscheiden von einer Wallet, die nichts getan hat.
        self.assertEqual(activity["window_state"], "unreadable")
        self.assertTrue(activity["error"])
        self.assertEqual(activity["n_rows"], 0)
        self.assertTrue(payload["identity"]["activity_error"])

    def test_the_intact_window_still_says_read(self) -> None:
        from api import server

        with patch.object(server, "load_ranked", return_value=pd.DataFrame()), patch.object(
            server, "risk_screen_basis", return_value=(pd.DataFrame(), pd.DataFrame(), 2500.0)
        ), patch.object(server, "load_leaderboard", return_value=pd.DataFrame()), offline_market_apis():
            payload = server.build_wallet_detail(self.WALLET)
        self.assertEqual(payload["activity"]["window_state"], "read")
        self.assertEqual(payload["activity"]["error"], "")
        self.assertEqual(payload["identity"]["activity_error"], "")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
