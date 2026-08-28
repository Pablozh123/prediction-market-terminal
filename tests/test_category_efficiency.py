"""app/category_efficiency.py: classification, sampling, scoring, payload shape.

Network-free. Gamma events and CLOB series are small fixtures; the module
must score them exactly and must never produce a figure without its n.
"""

from __future__ import annotations

import json
import unittest

import pandas as pd

from app import category_efficiency as ce


def _event(slug: str, tags: list[str], markets: list[dict]) -> dict:
    return {
        "slug": slug,
        "title": slug.replace("-", " "),
        "tags": [{"label": t, "slug": t.lower()} for t in tags],
        "markets": markets,
    }


def _market(question: str, yes_won: bool | None, *, token: str = "tok", volume: float = 5000.0,
            end: str = "2026-06-30T00:00:00Z", closed_time: str = "2026-07-01 12:00:00+00",
            created: str = "2026-05-01T00:00:00Z", outcomes: tuple[str, str] = ("Yes", "No")) -> dict:
    if yes_won is None:
        prices = ["0.5", "0.5"]
    else:
        prices = ["1", "0"] if yes_won else ["0", "1"]
    return {
        "conditionId": "0x" + question.replace(" ", "")[:20].lower(),
        "question": question,
        "outcomes": json.dumps(list(outcomes)),
        "outcomePrices": json.dumps(prices),
        "clobTokenIds": json.dumps([token, token + "no"]) if token else "[]",
        "closed": True,
        "closedTime": closed_time,
        "endDate": end,
        "createdAt": created,
        "volumeNum": volume,
        "umaResolutionStatus": "resolved",
    }


def _series(points: list[tuple[str, float]]) -> pd.DataFrame:
    return pd.DataFrame({"time": pd.to_datetime([p[0] for p in points], utc=True), "price": [p[1] for p in points]})


class ClassifyTests(unittest.TestCase):
    def test_specific_tag_beats_generic_section(self) -> None:
        # FOMC decision: tagged Politics (generic) and Fed Rates (specific).
        self.assertEqual(ce.classify_category("Fed decreases rates by 25 bps?", ["Politics", "Fed Rates", "Economy"]), "Business/Finance")
        # Fed chair nomination: Trump (specific politics) sits ahead of Fed Rates.
        self.assertEqual(ce.classify_category("Will Trump nominate Warsh?", ["Jerome Powell", "Politics", "Trump", "Fed Rates"]), "Politics")

    def test_generic_tags_and_sports(self) -> None:
        self.assertEqual(ce.classify_category("Will Spain win?", ["Sports", "Soccer", "FIFA World Cup"]), "Sports")
        self.assertEqual(ce.classify_category("Best Picture?", ["Culture", "Awards", "Oscars"]), "Pop culture")
        self.assertEqual(ce.classify_category("Best AI model?", ["Tech", "AI"]), "Science/Tech")
        self.assertEqual(ce.classify_category("Bitcoin above 100k?", ["Crypto", "Bitcoin"]), "Crypto")

    def test_up_or_down_is_not_crypto_by_itself(self) -> None:
        self.assertEqual(ce.classify_category("S&P 500 opens up or down?", ["SPX", "Up or Down", "Daily"]), "Business/Finance")

    def test_mentions_by_title_wins_over_tags(self) -> None:
        self.assertEqual(ce.classify_category('Will Trump say "tariff" during the address?', ["Politics", "Trump"]), "Mentions")
        self.assertEqual(ce.classify_category("How many times will Musk mention Mars?", ["Tech"]), "Mentions")

    def test_falls_back_to_live_classifier_then_other(self) -> None:
        self.assertEqual(ce.classify_category("Will Bitcoin hit $100k?", []), "Crypto")
        self.assertEqual(ce.classify_category("Will Scotland win the 2026 FIFA World Cup?", []), "Sports")
        self.assertEqual(ce.classify_category("Will it be a leap year?", ["Recurring", "Featured"]), "Other")

    def test_elections_split_from_politics(self) -> None:
        # Direct tag, and Gamma's many spellings via word match on the label.
        self.assertEqual(ce.classify_category("Will Mamdani win?", ["nyc mayor", "world elections", "politics"]), "Elections")
        self.assertEqual(ce.classify_category("AfD above 10%?", ["Politics", "deprec German Election", "World"]), "Elections")
        # Elections beats Geopolitics: an election in a conflict country is still an election.
        self.assertEqual(ce.classify_category("Who wins?", ["Ukraine", "Elections"]), "Elections")

    def test_geopolitics_split_from_politics(self) -> None:
        self.assertEqual(ce.classify_category("US x Iran deal?", ["Geopolitics", "Iran", "Trump"]), "Geopolitics")
        self.assertEqual(ce.classify_category("Ceasefire holds?", ["Middle East", "Politics"]), "Geopolitics")
        # Generic "world" without anything more specific is geopolitics now.
        self.assertEqual(ce.classify_category("First leader out in 2026?", ["World"]), "Geopolitics")
        # Domestic politics stays politics.
        self.assertEqual(ce.classify_category("Shutdown by Friday?", ["Politics", "Government Shutdown"]), "Politics")

    def test_tweet_count_markets_by_tag_and_title(self) -> None:
        self.assertEqual(ce.classify_category("Elon posts 100-119 times?", ["Tweet Markets", "Elon Musk"]), "Tweets/Social")
        self.assertEqual(ce.classify_category("Will Elon Musk tweet 500+ times this week?", ["Elon Musk"]), "Tweets/Social")


class EinpreisungstypTests(unittest.TestCase):
    def test_schwelle_zaehler_und_defaults(self) -> None:
        self.assertEqual(ce.einpreisungstyp("Will Bitcoin hit $100k in 2026?", "Crypto"), "schwelle")
        self.assertEqual(ce.einpreisungstyp("S&P 500 up or down on Friday?", "Business/Finance"), "schwelle")
        self.assertEqual(ce.einpreisungstyp("Will the SEC approve a Solana ETF?", "Crypto"), "nachrichten")
        self.assertEqual(ce.einpreisungstyp('Will Trump say "tariff"?', "Mentions"), "zaehler")
        self.assertEqual(ce.einpreisungstyp("Elon posts 260-279 tweets?", "Tweets/Social"), "zaehler")
        self.assertEqual(ce.einpreisungstyp("How many times will Musk mention Mars?", "Science/Tech"), "zaehler")
        self.assertEqual(ce.einpreisungstyp("Highest temperature in NYC above 90F?", "Weather"), "schwelle")
        self.assertEqual(ce.einpreisungstyp("Anything", "Other"), "unklar")

    def test_sports_fixture_vs_future(self) -> None:
        # A "vs" title or a short life = one game, in play; long-lived futures are a series.
        self.assertEqual(ce.einpreisungstyp("Spain vs. Belgium: extra time?", "Sports", 20.0), "spielverlauf")
        self.assertEqual(ce.einpreisungstyp("Will Egypt win on 2026-06-15?", "Sports", 40.0), "spielverlauf")
        self.assertEqual(ce.einpreisungstyp("Game prop created days out", "Sports", 2.0), "spielverlauf")
        self.assertEqual(ce.einpreisungstyp("Will the Lakers win the 2026 NBA Finals?", "Sports", 200.0), "serie")
        # An in-game total is in play, not a price threshold.
        self.assertEqual(ce.einpreisungstyp("Lakers score above 110 points?", "Sports", 3.0), "spielverlauf")

    def test_stichtag_reveals(self) -> None:
        self.assertEqual(ce.einpreisungstyp("Will Connolly win the Irish Presidential Election?", "Elections"), "stichtag")
        self.assertEqual(ce.einpreisungstyp("Will Colin Farrell win Best Actor at the 98th Academy Awards?", "Pop culture"), "stichtag")
        self.assertEqual(ce.einpreisungstyp("Fed rate cut in September?", "Business/Finance"), "stichtag")
        self.assertEqual(ce.einpreisungstyp("Will TikTok's sale be announced by June?", "Pop culture"), "nachrichten")

    def test_messlogik_covers_every_category(self) -> None:
        # The published messlogik must speak for every bucket the table can show.
        for name in ce.CATEGORIES:
            self.assertIn(name, ce.MESSLOGIK)
        for name, block in ce.MESSLOGIK.items():
            for key in ("anker", "einpreisung", "nicht_gemessen", "latenz_t0"):
                self.assertTrue(str(block.get(key) or "").strip(), f"{name}.{key} empty")


class EventRowsTests(unittest.TestCase):
    def test_decision_time_is_the_earlier_stamp(self) -> None:
        early = ce.decision_time("2026-07-20T00:00:00Z", "2026-07-07 21:30:01+00")
        self.assertEqual(early.isoformat(), "2026-07-07T21:30:01+00:00")
        late = ce.decision_time("2026-06-15T00:00:00Z", "2026-06-18T00:32:19Z")
        self.assertEqual(late.isoformat(), "2026-06-15T00:00:00+00:00")
        self.assertIsNone(ce.decision_time(None, ""))

    def test_rows_keep_only_settled_binary_markets_with_a_token(self) -> None:
        event = _event("world-cup", ["Sports"], [
            _market("Will Spain win?", True, token="a"),
            _market("Will Egypt win?", False, token="b"),
            _market("Refunded line", None, token="c"),                       # 0.5/0.5 -> not settled
            _market("Multi outcome", True, token="d", outcomes=("Spain", "Egypt")),
            _market("No token", True, token=""),
        ])
        rows = ce.market_rows_from_event(event)
        self.assertEqual([r["question"] for r in rows], ["Will Spain win?", "Will Egypt win?"])
        self.assertEqual([r["won"] for r in rows], [True, False])
        self.assertTrue(all(r["category"] == "Sports" for r in rows))
        self.assertEqual(rows[0]["yes_token_id"], "a")
        self.assertEqual(rows[0]["decision_time"].isoformat(), "2026-06-30T00:00:00+00:00")
        self.assertEqual(rows[0]["tags"], ["Sports"])

    def test_lifetime_and_sample_bucket(self) -> None:
        row = ce.market_rows_from_event(_event("e", ["Crypto"], [_market("Bitcoin above 100k?", True, created="2026-06-28T00:00:00Z")]))[0]
        self.assertAlmostEqual(ce.lifetime_days(row), 2.0)
        self.assertEqual(ce.sample_bucket(row, 7.0), "Crypto|short")
        long_row = ce.market_rows_from_event(_event("e", ["Crypto"], [_market("Bitcoin above 100k?", True)]))[0]
        self.assertEqual(ce.sample_bucket(long_row, 7.0), "Crypto")


class SelectTests(unittest.TestCase):
    def _rows(self) -> list[dict]:
        markets = [
            _market("Will Spain win?", True, token="a", volume=100),
            _market("Will France win?", False, token="b", volume=90),
            _market("Will Egypt win?", False, token="c", volume=80),
            _market("Tiny line", False, token="d", volume=10),
            _market("Game tomorrow?", True, token="e", volume=70, created="2026-06-29T00:00:00Z"),
            _market("Fifteen minutes", True, token="f", volume=60, created="2026-06-29T23:00:00Z"),
        ]
        return ce.market_rows_from_event(_event("world-cup", ["Sports"], markets))

    def test_caps_per_event_and_category_and_volume(self) -> None:
        picked = ce.select_markets(self._rows(), max_per_category=2, max_per_event=10, min_volume=50, taken={})
        # Two long-lived (cap 2), one short (half cap = 1); the tiny line and the 1-hour market are out.
        self.assertEqual([p["question"] for p in picked], ["Will Spain win?", "Will France win?", "Game tomorrow?"])
        picked = ce.select_markets(self._rows(), max_per_category=10, max_per_event=2, min_volume=0, taken={})
        self.assertEqual(len(picked), 2)

    def test_taken_counts_carry_across_events(self) -> None:
        picked = ce.select_markets(self._rows(), max_per_category=2, max_per_event=10, min_volume=0, taken={"Sports": 2})
        self.assertEqual([p["question"] for p in picked], ["Game tomorrow?"])

    def test_caps_reached(self) -> None:
        full = {c: 5 for c in ce.CATEGORIES if c != ce.OTHER}
        self.assertTrue(ce.caps_reached(full, 5))
        full["Mentions"] = 4
        self.assertFalse(ce.caps_reached(full, 5))


class PricingTests(unittest.TestCase):
    def test_hourly_first_then_daily_fallback(self) -> None:
        decision = "2026-07-01T00:00:00Z"
        hourly = _series([("2026-06-29T12:00:00Z", 0.60), ("2026-06-30T23:00:00Z", 0.80)])
        daily = _series([("2026-06-01T00:00:00Z", 0.20), ("2026-06-23T00:00:00Z", 0.40)])
        prices = ce.horizon_prices(hourly, daily, decision, (30, 7, 1))
        self.assertEqual(prices, {30: 0.20, 7: 0.40, 1: 0.60})
        # No series at all: every horizon is None, never a default.
        self.assertEqual(ce.horizon_prices(None, None, decision, (7, 1)), {7: None, 1: None})

    def test_price_must_predate_the_horizon(self) -> None:
        decision = "2026-07-01T00:00:00Z"
        hourly = _series([("2026-06-30T00:00:01Z", 0.9)])  # one second inside T-1
        self.assertIsNone(ce.price_at_horizon(hourly, decision, 1))


class TableTests(unittest.TestCase):
    def _obs(self) -> list[dict]:
        return [
            {"category": "Sports", "won": True, "volume": 100, "prices": {7: 0.9, 1: 0.95}},
            {"category": "Sports", "won": False, "prices": {7: 0.2, 1: 0.10}, "volume": 300},
            {"category": "Sports", "won": True, "prices": {7: None, 1: 0.60}, "volume": 200},
            {"category": "Politics", "won": False, "prices": {7: 0.4, 1: 0.30}, "volume": 50},
            {"category": "Politics", "won": True, "prices": {7: None, 1: None}, "volume": 999},  # unpriced -> not counted
        ]

    def test_scores_and_sample_sizes(self) -> None:
        rows = ce.category_table(self._obs(), horizons=(7, 1))
        by = {r["kategorie"]: r for r in rows}
        self.assertEqual(list(by), ["Politics", "Sports"])
        sports = by["Sports"]
        self.assertEqual(sports["n_maerkte"], 3)
        self.assertEqual(sports["n_t7"], 2)
        self.assertEqual(sports["n_t1"], 3)
        self.assertAlmostEqual(sports["brier_t7"], ((0.9 - 1) ** 2 + (0.2 - 0) ** 2) / 2, places=4)
        self.assertEqual(sports["trefferquote_t7"], 1.0)
        self.assertAlmostEqual(sports["brier_t1"], ((0.95 - 1) ** 2 + 0.1 ** 2 + 0.4 ** 2) / 3, places=4)
        self.assertEqual(sports["median_volumen_usd"], 200.0)
        self.assertEqual([h["horizont_tage"] for h in sports["horizonte"]], [7, 1])
        self.assertEqual(sports["horizonte"][0]["n"], 2)
        self.assertEqual(sports["horizonte"][0]["anteil_entschieden"], 0.0)
        # Politics has one priced market: T-7 0.4 -> hit is False (0.4 < 0.5, outcome No -> hit).
        politics = by["Politics"]
        self.assertEqual(politics["n_maerkte"], 1)
        self.assertEqual(politics["trefferquote_t7"], 1.0)
        self.assertEqual(politics["horizonte"][0]["trefferquote_ci95"][0] <= 1.0, True)

    def test_missing_horizon_is_none_not_zero(self) -> None:
        rows = ce.category_table([{"category": "Sports", "won": True, "volume": 1, "prices": {1: 0.9}}], horizons=(7, 1))
        self.assertIsNone(rows[0]["brier_t7"])
        self.assertEqual(rows[0]["n_t7"], 0)
        self.assertEqual(rows[0]["horizonte"][0], {
            "horizont_tage": 7, "brier": None, "brier_ci95": [None, None], "trefferquote": None,
            "n": 0, "anteil_entschieden": None, "brier_offen": None,
            "brier_offen_ci95": [None, None], "trefferquote_offen": None, "n_offen": 0,
        })

    def test_open_subset_excludes_settled_prices(self) -> None:
        # Two effectively settled prices score near-perfect and drag the
        # headline Brier down; brier_offen must ignore them.
        obs = [
            {"category": "S", "won": True, "volume": 1, "prices": {7: 0.99}},
            {"category": "S", "won": False, "volume": 1, "prices": {7: 0.01}},
            {"category": "S", "won": True, "volume": 1, "prices": {7: 0.6}},
            {"category": "S", "won": False, "volume": 1, "prices": {7: 0.4}},
        ]
        row = ce.category_table(obs, horizons=(7,))[0]
        h7 = row["horizonte"][0]
        self.assertEqual(h7["n"], 4)
        self.assertEqual(h7["n_offen"], 2)
        self.assertAlmostEqual(h7["brier_offen"], (0.4 ** 2 + 0.4 ** 2) / 2, places=4)
        self.assertEqual(h7["anteil_entschieden"], 0.5)
        self.assertEqual(row["brier_t7_offen"], h7["brier_offen"])
        self.assertEqual(row["n_t7_offen"], 2)

    def test_typen_breakdown_and_vorzeitig_share(self) -> None:
        obs = [
            {"category": "S", "won": True, "volume": 1, "prices": {1: 0.9}, "einpreisungstyp": "spielverlauf", "vorzeitig": False},
            {"category": "S", "won": False, "volume": 1, "prices": {1: 0.2}, "einpreisungstyp": "spielverlauf", "vorzeitig": True},
            {"category": "S", "won": True, "volume": 1, "prices": {1: 0.8}, "einpreisungstyp": "serie", "vorzeitig": None},
        ]
        row = ce.category_table(obs, horizons=(1,))[0]
        typen = {t["typ"]: t for t in row["typen"]}
        self.assertEqual(set(typen), {"spielverlauf", "serie"})
        self.assertEqual(typen["spielverlauf"]["n"], 2)
        self.assertAlmostEqual(typen["spielverlauf"]["brier_t1"], (0.01 + 0.04) / 2, places=4)
        self.assertEqual(typen["serie"]["n_t1"], 1)
        # Share of early closes counts only rows where the stamp pair existed.
        self.assertEqual(row["anteil_vorzeitig"], 0.5)
        # Observations scored before the typology existed: no typen, no guess.
        ohne = ce.category_table([{"category": "S", "won": True, "volume": 1, "prices": {1: 0.9}}], horizons=(1,))[0]
        self.assertEqual(ohne["typen"], [])
        self.assertIsNone(ohne["anteil_vorzeitig"])

    def test_rescore_joins_tags_and_retypes(self) -> None:
        candidates = [
            {"market_key": "m1", "question": "Will Mamdani win?", "tags": ["world elections", "politics"]},
            {"market_key": "m2", "question": "Spain vs. Belgium: extra time?", "tags": ["Sports", "Soccer"]},
        ]
        observations = [
            {"market_key": "m1", "question": "Will Mamdani win?", "category": "Politics", "won": True,
             "volume": 10.0, "lifetime_days": 90.0, "prices": {"7": 0.7, "1": 0.9}},
            {"market_key": "m2", "question": "Spain vs. Belgium: extra time?", "category": "Sports", "won": False,
             "volume": 5.0, "lifetime_days": 3.0, "prices": {"1": 0.2}},
            {"market_key": "m3", "question": "Orphan without candidate", "category": "Crypto", "won": True,
             "volume": 1.0, "lifetime_days": 10.0, "prices": {"1": 0.6}},
        ]
        neu = ce.rescore_observations(candidates, observations)
        by = {o["market_key"]: o for o in neu}
        self.assertEqual(by["m1"]["category"], "Elections")
        self.assertEqual(by["m1"]["einpreisungstyp"], "stichtag")
        self.assertEqual(by["m2"]["einpreisungstyp"], "spielverlauf")
        # Prices and outcomes stay exactly as cached.
        self.assertEqual(by["m1"]["prices"], {"7": 0.7, "1": 0.9})
        # No candidate: category kept, typed from title alone.
        self.assertEqual(by["m3"]["category"], "Crypto")
        self.assertEqual(by["m3"]["einpreisungstyp"], "nachrichten")

    def test_thin_categories_fold_into_other(self) -> None:
        rows = ce.category_table(self._obs(), horizons=(7, 1), min_markets=2)
        self.assertEqual([r["kategorie"] for r in rows], ["Sports", "Other"])
        self.assertEqual(rows[1]["n_maerkte"], 1)

    def test_calibration_bins_carry_n_and_skip_empty(self) -> None:
        obs = [
            {"category": "S", "won": True, "prices": {7: 0.95}},
            {"category": "S", "won": True, "prices": {7: 0.92}},
            {"category": "S", "won": False, "prices": {7: 0.05}},
            {"category": "S", "won": False, "prices": {7: 1.0}},  # closed last bin
        ]
        bins = ce.calibration_bins(obs, days=7)
        self.assertEqual([(b["von"], b["bis"], b["n"]) for b in bins], [(0.0, 0.1, 1), (0.9, 1.0, 3)])
        top = bins[1]
        self.assertAlmostEqual(top["vorhergesagt"], (0.95 + 0.92 + 1.0) / 3, places=4)
        self.assertAlmostEqual(top["realisiert"], 2 / 3, places=4)
        self.assertEqual(len(top["realisiert_ci95"]), 2)

    def test_string_keys_from_json_roundtrip(self) -> None:
        obs = json.loads(json.dumps([{"category": "S", "won": True, "volume": 1, "prices": {7: 0.9, 1: 0.8}}]))
        rows = ce.category_table(obs, horizons=(7, 1))
        self.assertEqual(rows[0]["n_t7"], 1)
        self.assertEqual(rows[0]["n_t1"], 1)


class PayloadTests(unittest.TestCase):
    OLD = {
        "hinweis": "thesis note",
        "stand_utc": "2026-08-07T04:30:03+00:00",
        "kategorien": [{"kategorie": "Politik", "brier_t7": 0.35, "n_maerkte": 73}],
        "beispiele": [{"kategorie": "Sport", "minuten_bis_konvergenz": 180.4}],
    }

    def test_snapshot_and_examples_are_preserved(self) -> None:
        payload = ce.compose_payload([{"kategorie": "Politics", "n_maerkte": 5}], self.OLD, stand_utc="2026-08-17T00:00:00+00:00",
                                     horizons=(7, 1), quelle={"methode": "m"}, hinweis="new note")
        self.assertEqual(payload["provenienz"], "terminal/category_efficiency")
        self.assertEqual(payload["beispiele"], self.OLD["beispiele"])
        self.assertEqual(payload["thesis_snapshot"]["kategorien"], self.OLD["kategorien"])
        self.assertEqual(payload["thesis_snapshot"]["hinweis"], "thesis note")
        self.assertEqual(payload["horizonte_tage"], [7, 1])
        self.assertEqual(payload["kategorien"][0]["kategorie"], "Politics")
        # A second run keeps the thesis snapshot instead of snapshotting itself.
        again = ce.compose_payload([], payload, stand_utc="x", horizons=(7,), quelle={}, hinweis="")
        self.assertEqual(again["thesis_snapshot"]["kategorien"], self.OLD["kategorien"])
        self.assertEqual(again["beispiele"], self.OLD["beispiele"])

    def test_sample_summary(self) -> None:
        rows = [{"n_maerkte": 3, "horizonte": [{"horizont_tage": 7, "n": 2}, {"horizont_tage": 1, "n": 3}]},
                {"n_maerkte": 1, "horizonte": [{"horizont_tage": 7, "n": 1}, {"horizont_tage": 1, "n": 0}]}]
        self.assertEqual(
            ce.sample_summary(rows),
            # Drei besetzte Zellen: die leere T-1-Zelle zaehlt nicht als Vergleich.
            {"n_maerkte": 4, "n_kategorien": 2, "n_je_horizont": {"T-7": 3, "T-1": 3}, "n_vergleiche": 3},
        )


class BrierIntervalTests(unittest.TestCase):
    """Eine Rangfolge ueber zwoelf Kategorien und fuenf Horizonte ist ohne
    Intervall keine Aussage: 60 Zellen laufen von sich aus auseinander."""

    def _obs(self, prices_and_outcomes):
        return [
            {"category": "S", "won": won, "volume": 1, "prices": {7: preis}}
            for preis, won in prices_and_outcomes
        ]

    def test_interval_brackets_the_brier(self) -> None:
        obs = self._obs([(0.6, True), (0.4, False), (0.7, True), (0.3, False), (0.55, False)])
        h7 = ce.category_table(obs, horizons=(7,))[0]["horizonte"][0]
        low, high = h7["brier_ci95"]
        self.assertIsNotNone(low)
        self.assertLessEqual(low, h7["brier"])
        self.assertGreaterEqual(high, h7["brier"])

    def test_a_perfectly_uniform_bucket_has_a_zero_width_interval(self) -> None:
        # Jeder Einzelfehler identisch (0.25) -> keine Streuung, kein Band.
        obs = self._obs([(0.5, True), (0.5, False), (0.5, True), (0.5, False)])
        h7 = ce.category_table(obs, horizons=(7,))[0]["horizonte"][0]
        self.assertAlmostEqual(h7["brier"], 0.25, places=9)
        self.assertEqual(h7["brier_ci95"], [0.25, 0.25])

    def test_a_noisier_bucket_gets_a_wider_band(self) -> None:
        ruhig = self._obs([(0.5, True), (0.5, False), (0.5, True), (0.5, False)])
        unruhig = self._obs([(0.99, False), (0.01, True), (0.5, True), (0.5, False)])
        breite = lambda rows: (lambda ci: ci[1] - ci[0])(  # noqa: E731 - nur hier gebraucht
            ce.category_table(rows, horizons=(7,))[0]["horizonte"][0]["brier_ci95"]
        )
        self.assertGreater(breite(unruhig), breite(ruhig))

    def test_single_observation_has_no_interval(self) -> None:
        h7 = ce.category_table(self._obs([(0.6, True)]), horizons=(7,))[0]["horizonte"][0]
        self.assertEqual(h7["brier_ci95"], [None, None])

    def test_open_subset_carries_its_own_interval(self) -> None:
        obs = self._obs([(0.99, True), (0.01, False), (0.6, True), (0.4, False), (0.55, True)])
        h7 = ce.category_table(obs, horizons=(7,))[0]["horizonte"][0]
        self.assertEqual(h7["n_offen"], 3)
        self.assertIsNotNone(h7["brier_offen_ci95"][0])
        self.assertLessEqual(h7["brier_offen_ci95"][0], h7["brier_offen"])


if __name__ == "__main__":
    unittest.main()
