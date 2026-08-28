import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

from app import claims

REPO_ROOT = Path(__file__).resolve().parents[1]

FIXTURE_YAML = """
version: 1
disclaimers:
  thin_sample:
    de: "Stichprobe zu klein fuer ein Urteil."
    en: "Sample too small for a verdict."
    surfaces:
      - web/js/pages/beispiel.js
  past_not_forecast:
    de: "Keine Prognose."
allowed_claims:
  - id: fresh
    text: "Fresh claim."
    evidence: "tests/test_claims.py"
    last_verified: 2026-07-01
  - id: old
    text: "Old claim."
    evidence: "tests/test_claims.py"
    last_verified: 2026-05-01
  - id: broken-date
    text: "No usable date."
    evidence: "tests/test_claims.py"
    last_verified: "unknown"
forbidden_phrases:
  - phrase: "predicts future returns"
    reason: "Prediction promise."
  - phrase: "Kaufempfehlung"
    reason: "Beratungs-Sprache."

caveat_markers:
  - marker: "not investment advice"
  - marker: "not proof"
    allow:
      - "not proof the market heard anything"
"""


class ClaimsFixtureTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "claims.yaml"
        self.path.write_text(FIXTURE_YAML, encoding="utf-8")

    def test_find_forbidden_is_case_insensitive_same_line(self):
        hits = claims.find_forbidden("This score PREDICTS FUTURE RETURNS for sure.", path=self.path)
        self.assertEqual(hits, [("predicts future returns", "Prediction promise.")])

    def test_find_forbidden_does_not_match_across_line_breaks(self):
        hits = claims.find_forbidden("predicts future\nreturns", path=self.path)
        self.assertEqual(hits, [])

    def test_find_forbidden_reports_each_line(self):
        text = "Kaufempfehlung hier.\nUnd noch eine kaufempfehlung dort."
        hits = claims.find_forbidden(text, path=self.path)
        self.assertEqual(len(hits), 2)

    def test_disclaimer_language_and_fallback(self):
        self.assertEqual(claims.disclaimer("thin_sample", "de", path=self.path), "Stichprobe zu klein fuer ein Urteil.")
        self.assertEqual(claims.disclaimer("thin_sample", "en", path=self.path), "Sample too small for a verdict.")
        self.assertEqual(claims.disclaimer("past_not_forecast", "en", path=self.path), "Keine Prognose.")
        self.assertEqual(claims.disclaimer("missing", "de", path=self.path), "")

    def test_stale_claims_boundary(self):
        today = date(2026, 7, 31)  # fresh claim is exactly 30 days old -> not stale
        stale = claims.stale_claims(max_age_days=30, today=today, path=self.path)
        stale_ids = {entry["id"] for entry in stale}
        self.assertEqual(stale_ids, {"old", "broken-date"})
        one_day_later = date(2026, 8, 1)  # now 31 days -> stale
        stale_ids = {entry["id"] for entry in claims.stale_claims(max_age_days=30, today=one_day_later, path=self.path)}
        self.assertIn("fresh", stale_ids)

    def test_scoreline_view_quality_states(self):
        for quality in ("insufficient", "developing", "adequate", None):
            view = claims.scoreline_view(
                n=25,
                ci="[+0.4, +5.2] pp",
                quality=quality,
                verdict="Edge beyond chance on this sample.",
                snapshot_at="2026-07-16T18:00:00+00:00",
                path=self.path,
            )
            self.assertIn("n=25", view["meta"])
            self.assertIn("95% CI [+0.4, +5.2] pp", view["meta"])
            self.assertIn("snapshot 2026-07-16 18:00 UTC", view["meta"])
        insufficient = claims.scoreline_view(quality="insufficient", verdict="Edge beyond chance.", path=self.path)
        self.assertNotIn("Edge beyond chance.", insufficient["note"])
        self.assertIn("Sample too small", insufficient["note"])
        self.assertEqual(insufficient["badge"], "INSUFFICIENT SAMPLE")
        adequate = claims.scoreline_view(quality="adequate", verdict="Edge beyond chance.", path=self.path)
        self.assertIn("Edge beyond chance.", adequate["note"])
        self.assertEqual(adequate["badge"], "ADEQUATE SAMPLE")
        self.assertEqual(claims.scoreline_view(path=self.path)["badge"], "")


class RealRegisterTests(unittest.TestCase):
    def test_register_loads_with_required_blocks(self):
        data = claims.load_claims(REPO_ROOT / "data" / "claims.yaml")
        self.assertIn("disclaimers", data)
        self.assertIn("allowed_claims", data)
        self.assertIn("forbidden_phrases", data)
        for key in ("score_generic", "diagnostic_not_advice", "past_not_forecast", "thin_sample"):
            entry = data["disclaimers"][key]
            self.assertTrue(entry.get("de"))
            self.assertTrue(entry.get("en"))
        for claim in data["allowed_claims"]:
            self.assertTrue(claim.get("id"))
            self.assertTrue(claim.get("evidence"))
            self.assertTrue(claim.get("last_verified"))

    def test_register_contains_brief_minimum_phrases(self):
        phrases = {phrase.lower() for phrase, _ in claims.forbidden_phrases(REPO_ROOT / "data" / "claims.yaml")}
        for required in (
            "sagt zukuenftige performance voraus",
            "predicts future returns",
            "garantiert",
            "sicherer gewinn",
            "risk-free",
            "wir empfehlen zu kaufen",
            "kaufempfehlung",
            "you should buy",
            "you should copy",
        ):
            self.assertIn(required, phrases)


class RegisterForTheUiTests(unittest.TestCase):
    """Die Haelfte des Registers, die es speist statt nur zu verbieten."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "claims.yaml"
        self.path.write_text(FIXTURE_YAML, encoding="utf-8")

    def test_surfaces_and_surface_map(self):
        self.assertEqual(claims.surfaces("thin_sample", path=self.path), ("web/js/pages/beispiel.js",))
        self.assertEqual(claims.surfaces("past_not_forecast", path=self.path), ())
        self.assertEqual(claims.surface_map(path=self.path),
                         {"web/js/pages/beispiel.js": ["thin_sample"]})

    def test_metadata_never_leaks_into_a_caveat_text(self):
        # Die Flaechenliste steht im selben Eintrag wie die Texte. Ein
        # Rueckfall ueber alle Werte des Eintrags haette sie als Caveat
        # ausgeliefert, sobald eine Sprache fehlt.
        self.assertEqual(claims.disclaimer("past_not_forecast", "en", path=self.path), "Keine Prognose.")

    def test_ui_register_shapes_both_languages_and_one(self):
        beide = claims.ui_register(path=self.path)
        self.assertEqual(beide["disclaimers"]["thin_sample"]["en"], "Sample too small for a verdict.")
        self.assertEqual(beide["disclaimers"]["thin_sample"]["surfaces"], ["web/js/pages/beispiel.js"])
        self.assertEqual(beide["allowed_claims"][0]["id"], "fresh")
        einzeln = claims.ui_register("de", path=self.path)
        self.assertEqual(einzeln["disclaimers"]["thin_sample"]["text"], "Stichprobe zu klein fuer ein Urteil.")
        self.assertNotIn("en", einzeln["disclaimers"]["thin_sample"])

    def test_caveat_calls_read_both_frontend_and_python_syntax(self):
        quelle = (
            "const a = caveatZeile('thin_sample', { vorsatz: 'x' });\n"
            "const b = caveat('past_not_forecast');\n"
            "const c = caveatText('thin_sample');\n"
            'py = claims.disclaimer("thin_sample", "en")\n'
        )
        self.assertEqual(
            claims.caveat_calls(quelle),
            [(1, "thin_sample"), (2, "past_not_forecast"), (3, "thin_sample"), (4, "thin_sample")],
        )

    def test_unregistered_caveat_is_found_registered_text_is_not(self):
        hand = "  + '<div>This is information, not investment advice.</div>'"
        treffer = claims.find_unregistered_caveats(hand, path=self.path)
        self.assertEqual([(1, "not investment advice")], [(n, m) for n, m, _ in treffer])
        # Ein Registertext selbst ist kein Fund, auch wenn er Markerworte traegt.
        self.path.write_text(
            FIXTURE_YAML.replace('en: "Sample too small for a verdict."',
                                 'en: "Sample too small: information, not investment advice."'),
            encoding="utf-8")
        registriert = "  en: 'Sample too small: information, not investment advice.'"
        self.assertEqual(claims.find_unregistered_caveats(registriert, path=self.path), [])

    def test_registered_allowance_keeps_method_prose_out_of_the_report(self):
        prosa = "a price move, not proof the market heard anything; rows marked (away)"
        self.assertEqual(claims.find_unregistered_caveats(prosa, path=self.path), [])
        self.assertTrue(claims.find_unregistered_caveats("this is not proof of wrongdoing", path=self.path))

    def test_compiled_module_round_trip(self):
        quelle = claims.frontend_module_source(self.path)
        self.assertIn("GENERATED FILE", quelle)
        zurueck = claims.parse_frontend_module(quelle)
        self.assertEqual(zurueck, claims.frontend_register(self.path))
        self.assertEqual(zurueck["disclaimers"]["thin_sample"]["en"], "Sample too small for a verdict.")
        # Flaechen gehoeren nicht in das Modul: der Browser rendert Texte.
        self.assertNotIn("surfaces", zurueck["disclaimers"]["thin_sample"])
        self.assertIsNone(claims.parse_frontend_module("export default 1;"))


class RegisterReachesTheSurfaceTests(unittest.TestCase):
    """Jeder Eintrag mit benannter Flaeche wird dort auch gerendert.

    Das ist der Befund aus dem Design-Review vom 2026-08-28: das Register
    hatte in web/ keinen einzigen Verbraucher, vier Eintraege waren damit
    tot. Ein Test, der das bemerkt, gehoert in die Suite und nicht nur in
    den Lint-Schritt der CI.
    """

    def test_every_declared_surface_renders_its_entry(self):
        for surface, keys in claims.surface_map().items():
            text = (REPO_ROOT / surface).read_text(encoding="utf-8")
            gerendert = {key for _, key in claims.caveat_calls(text)}
            for key in keys:
                with self.subTest(surface=surface, key=key):
                    self.assertIn(key, gerendert)

    def test_the_four_entries_the_review_found_dead_have_a_reader(self):
        for key in ("leaderboard_caveat", "wallet_reader_caveat", "screen_not_proof", "backtest_modeled"):
            with self.subTest(key=key):
                self.assertTrue(claims.surfaces(key), f"{key} names no surface")

    def test_every_caveat_call_in_the_frontend_names_a_registered_entry(self):
        bekannt = set(claims.disclaimer_keys())
        for pfad in sorted((REPO_ROOT / "web" / "js").rglob("*.js")):
            if pfad.name == "claims_register.js":
                continue
            for zeile, key in claims.caveat_calls(pfad.read_text(encoding="utf-8")):
                with self.subTest(datei=pfad.name, zeile=zeile):
                    self.assertIn(key, bekannt)

    def test_compiled_module_matches_the_register(self):
        vorhanden = claims.FRONTEND_MODULE_PATH.read_text(encoding="utf-8")
        self.assertEqual(vorhanden, claims.frontend_module_source(),
                         msg="web/js/claims_register.js ist veraltet: python scripts/publish_claims.py")


class LintCaveatChecksTests(unittest.TestCase):
    """Die drei neuen Pruefungen des Linters, ohne Unterprozess."""

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "lint_claims_modul", REPO_ROOT / "scripts" / "lint_claims.py")
        modul = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modul)
        cls.lint = modul

    def test_hand_written_disclaimer_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            datei = Path(tmp) / "seite.js"
            datei.write_text("export const x = 'Scores here are not a recommendation to act.';\n",
                             encoding="utf-8")
            befunde, gerendert = self.lint.lint_caveats([datei])
        self.assertEqual(gerendert, {})
        self.assertEqual(len(befunde), 1)
        self.assertIn("hand-written caveat", befunde[0])
        self.assertIn("not a recommendation", befunde[0])

    def test_unknown_key_is_reported_and_known_key_is_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            datei = Path(tmp) / "seite.js"
            datei.write_text("caveatZeile('score_generic');\ncaveat('gibt_es_nicht');\n", encoding="utf-8")
            befunde, gerendert = self.lint.lint_caveats([datei])
        self.assertEqual(gerendert[datei.as_posix()], {"score_generic", "gibt_es_nicht"})
        self.assertEqual(len(befunde), 1)
        self.assertIn("gibt_es_nicht", befunde[0])

    def test_entry_that_stopped_being_rendered_is_reported(self):
        # Nichts gerendert: jede Flaeche des Registers meldet sich.
        befunde = self.lint.lint_surfaces({})
        self.assertTrue(befunde)
        self.assertTrue(any("not among the linted sources" in b for b in befunde))
        # Datei da, Eintrag fehlt: der praezise Fall aus dem Review.
        alle = {datei: set() for datei in claims.surface_map()}
        befunde = self.lint.lint_surfaces(alle)
        self.assertTrue(any("never calls caveat('leaderboard_caveat')" in b for b in befunde))
        # Alles gerendert: kein Befund.
        self.assertEqual(self.lint.lint_surfaces({d: set(k) for d, k in claims.surface_map().items()}), [])

    def test_compiled_register_check_is_clean_in_the_repo(self):
        self.assertEqual(self.lint.lint_compiled_register(), [])


class ClaimsRouteTests(unittest.TestCase):
    """/api/claims: die Sprachwahl und der Pfad, aus dem gelesen wird."""

    @classmethod
    def setUpClass(cls):
        try:
            from api import server
        except Exception as exc:  # fastapi fehlt lokal
            raise unittest.SkipTest(f"api.server nicht importierbar: {exc}")
        cls.server = server

    def test_route_liefert_beide_sprachen(self):
        payload = self.server.claims_register()
        self.assertEqual(payload["source"], "data/claims.yaml")
        self.assertEqual(len(payload["disclaimers"]), len(claims.disclaimer_keys()))
        self.assertIn("de", payload["disclaimers"]["score_generic"])

    def test_route_filtert_auf_eine_sprache(self):
        payload = self.server.claims_register(lang="de")
        self.assertEqual(payload["disclaimers"]["score_generic"]["text"],
                         claims.disclaimer("score_generic", "de"))

    def test_route_weist_eine_unbekannte_sprache_ab(self):
        with self.assertRaises(Exception) as ctx:
            self.server.claims_register(lang="fr")
        self.assertEqual(getattr(ctx.exception, "status_code", None), 400)

    def test_register_wird_unabhaengig_vom_arbeitsverzeichnis_gelesen(self):
        # Der API-Prozess startet, wo der Host ihn startet. Mit dem frueheren
        # relativen Pfad war die Antwort dort leer, und ein leerer Vorbehalt
        # ist genau der Fehler, den dieses Modul verhindern soll.
        alt = os.getcwd()
        try:
            os.chdir(tempfile.gettempdir())
            claims.load_claims.__globals__["_CACHE"].clear()
            payload = self.server.claims_register()
        finally:
            os.chdir(alt)
        self.assertTrue(payload["disclaimers"]["screen_not_proof"]["en"])


class BothSurfacesAreBoundTests(unittest.TestCase):
    """Der Lint bindet beide Oberflaechen, nicht nur die veroeffentlichte.

    Nach PR #116 las das Web-Frontend seine Vorbehalte aus dem Register,
    waehrend der Streamlit-Monolith ein Dutzend eigene Disclaimer als Prosa
    trug, mehrere davon eine zweite Fassung desselben Satzes. Eine Regel,
    die nur eine von zwei Oberflaechen liest, ist genau der Zustand, aus dem
    solche Dubletten entstehen.
    """

    MONOLITH = REPO_ROOT / "prediction_terminal.py"

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "lint_claims_beide", REPO_ROOT / "scripts" / "lint_claims.py")
        modul = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modul)
        cls.lint = modul

    def test_the_monolith_is_inside_the_caveat_scope(self):
        self.assertIn("prediction_terminal.py", self.lint.CAVEAT_SOURCES)
        gefunden = self.lint.collect_files(
            self.lint.CAVEAT_SOURCES,
            excluded=self.lint.EXCLUDED | self.lint.CAVEAT_EXCLUDED,
        )
        self.assertIn(Path("prediction_terminal.py"), [Path(p.as_posix()) for p in gefunden])

    def test_the_monolith_writes_no_standing_caveat_by_hand(self):
        text = self.MONOLITH.read_text(encoding="utf-8")
        befunde = claims.find_unregistered_caveats(text)
        self.assertEqual(
            befunde, [],
            msg="handgeschriebener Vorbehalt im Monolithen: "
                + "; ".join(f"Zeile {n} ({m})" for n, m, _ in befunde))

    def test_the_monolith_renders_the_entries_that_name_it(self):
        text = self.MONOLITH.read_text(encoding="utf-8")
        gerendert = {key for _, key in claims.caveat_calls(text)}
        self.assertTrue(gerendert, "der Monolith ruft das Register gar nicht auf")
        bekannt = set(claims.disclaimer_keys())
        for key in sorted(gerendert):
            with self.subTest(key=key):
                self.assertIn(key, bekannt)
        for key in claims.surface_map().get("prediction_terminal.py", []):
            with self.subTest(key=key):
                self.assertIn(key, gerendert)

    def test_the_duplicated_sentences_now_have_one_wording(self):
        """Saetze, die vorher in beiden Oberflaechen verschieden lauteten."""

        monolith = set(
            key for _, key in claims.caveat_calls(self.MONOLITH.read_text(encoding="utf-8")))
        for key in ("research_tool_only", "screen_not_proof", "paper_desk_only",
                    "paper_log_no_return_claim"):
            with self.subTest(key=key):
                flaechen = claims.surfaces(key)
                self.assertIn("prediction_terminal.py", flaechen)
                self.assertTrue([f for f in flaechen if f != "prediction_terminal.py"],
                                f"{key} steht nur noch auf einer Flaeche")
                self.assertIn(key, monolith)


class DiePluralformKamDurchTests(unittest.TestCase):
    """Ein Marker im Singular laesst die Mehrzahl durch.

    Derselbe Satz stand in zwei Fassungen auf zwei Oberflaechen -- die
    Dublette, gegen die dieser Lint gebaut wurde:

        web/js/pages/system_pages.js: "Signals are rule matches, not
        recommendations; each rejection reason is a pre-registered gate."
        prediction_terminal.py: "Rule matches found by the read-only watcher
        (not recommendations)."

    Der Marker hiess ``not a recommendation``, beide Zeilen schreiben ``not
    recommendations``, und deshalb sah die Pruefung keine von beiden.
    """

    SATZ = "Signals are rule matches, not recommendations; the rest is prose."

    def test_die_mehrzahl_wird_gefunden(self):
        befunde = claims.find_unregistered_caveats(self.SATZ)
        self.assertTrue(befunde, "die Mehrzahl 'not recommendations' faellt weiter durch")
        self.assertIn("not recommendations", [marker for _, marker, _ in befunde])

    def test_der_registrierte_satz_selbst_faellt_nicht_auf(self):
        text = claims.disclaimer("signals_not_recommendations", "en")
        self.assertTrue(text, "signals_not_recommendations fehlt im Register")
        self.assertEqual(claims.find_unregistered_caveats(text), [])

    def test_beide_oberflaechen_lesen_denselben_eintrag(self):
        flaechen = claims.surfaces("signals_not_recommendations")
        self.assertIn("prediction_terminal.py", flaechen)
        self.assertIn("web/js/pages/system_pages.js", flaechen)


class StehendeVorbehalteAusPR122Tests(unittest.TestCase):
    """Vier Erklaerzeilen, gepruefte Entscheidung je Zeile.

    Register, wo ein Satz ein stehender Vorbehalt ist: eine Aussage darueber,
    was eine Zahl NICHT ist, die auf mehreren Flaechen wiederkehrt und
    zwischen ihnen driften kann. Prosa, wo er beschreibt, was diese eine
    Anzeige gerade tut oder in welcher Einheit sie rechnet.
    """

    MONOLITH = REPO_ROOT / "prediction_terminal.py"

    def test_die_hybrid_definition_steht_einmal_im_register(self):
        # "Der Tageswert, wenn heute gehandelt wurde, sonst das Lebensvolumen"
        # stand dreimal in drei Formulierungen: Monitor-Spalte, Overview-Gate
        # und die Sortier-Erklaerung unter TRENDING MARKETS.
        text = claims.disclaimer("activity_volume_hybrid", "en")
        self.assertTrue(text, "activity_volume_hybrid fehlt im Register")
        self.assertIn("prediction_terminal.py", claims.surfaces("activity_volume_hybrid"))
        monolith = self.MONOLITH.read_text(encoding="utf-8")
        aufrufe = [key for _, key in claims.caveat_calls(monolith)]
        self.assertGreaterEqual(
            aufrufe.count("activity_volume_hybrid"), 3,
            "die drei Stellen lesen den Eintrag nicht alle")

    def test_die_drei_alten_formulierungen_stehen_nicht_mehr_da(self):
        monolith = self.MONOLITH.read_text(encoding="utf-8")
        for satz in (
            "the day's figure where there is one",
            "the day's turnover where a market traded today, its lifetime",
        ):
            with self.subTest(satz=satz):
                self.assertNotIn(satz, monolith)

    def test_der_backtester_kopf_liest_den_registereintrag(self):
        monolith = self.MONOLITH.read_text(encoding="utf-8")
        self.assertIn("prediction_terminal.py", claims.surfaces("backtest_modeled"))
        self.assertIn("backtest_modeled", [key for _, key in claims.caveat_calls(monolith)])
        self.assertNotIn("Run the numbers before you risk the bankroll", monolith)

    def test_was_prosa_bleibt_bleibt_prosa(self):
        # Zwei Zeilen sind KEIN stehender Vorbehalt und werden deshalb nicht
        # registriert. Beide sagen, was eine Zahl IST, nicht was sie nicht ist:
        #
        # 1. Der Nenner-Satz unter "Venue volume 24h" nennt zwei gemessene
        #    Zahlen (n von N geladenen Maerkten) und die Einheiten beider
        #    Venues. Ein Registereintrag ist ein fester Satz, keine
        #    Formatvorlage mit zwei Messwerten darin.
        # 2. Der Hilfetext an der Value-Spalte ist eine Einheitenlegende je
        #    Signalart. Er kann auch nicht gegen das Web-Frontend driften:
        #    beide Oberflaechen bilden die Spalte ueber
        #    api_views.signal_value_label.
        monolith = self.MONOLITH.read_text(encoding="utf-8")
        self.assertIn("loaded markets", monolith)
        self.assertIn("Unit follows the signal type", monolith)
        # Und sie duerfen keinen Marker ausloesen: waeren sie stehende
        # Vorbehalte, wuerde der Lint sie melden.
        for zeile in monolith.splitlines():
            if "loaded markets" in zeile or "Unit follows the signal type" in zeile:
                with self.subTest(zeile=zeile.strip()[:60]):
                    self.assertEqual(claims.find_unregistered_caveats(zeile), [])


class MetaJsonPrinciplesTests(unittest.TestCase):
    """Die Grundsaetze aus public/data/meta.json stehen im Register.

    Sie reisen als Textzeilen in einer laufzeitgenerierten Datei, die ein
    anderes Repo schreibt: Produkt-Copy, die in diesem Repo nie ein Review
    gesehen hat. PR #116 hat einen der vier Saetze uebernommen, die drei
    anderen hatten danach immer noch keinen Leser.
    """

    def test_every_published_principle_is_registered(self):
        payload = json.loads((REPO_ROOT / "public" / "data" / "meta.json").read_text(encoding="utf-8"))
        zeilen = payload.get("disclaimer") or []
        self.assertTrue(zeilen, "meta.json fuehrt keine disclaimer-Zeilen mehr")
        self.assertEqual(claims.unregistered_texts(zeilen), [])

    def test_each_principle_names_both_surfaces(self):
        for key in ("daily_run_descriptive", "verification_not_signal",
                    "daily_run_no_advice", "daily_run_privacy"):
            with self.subTest(key=key):
                flaechen = claims.surfaces(key)
                self.assertIn("prediction_terminal.py", flaechen)
                self.assertIn("web/js/pages/system_pages.js", flaechen)

    def test_unregistered_texts_keeps_what_the_publisher_adds(self):
        registriert = claims.disclaimer("daily_run_privacy", "en")
        zeilen = ["  " + registriert.upper() + " ", "Something the register does not know.", "", None]
        self.assertEqual(claims.unregistered_texts(zeilen),
                         ["Something the register does not know."])

    def test_unregistered_texts_sees_a_reworded_sentence(self):
        # Kein Fuzzy-Vergleich: eine umformulierte Zusage ist eine andere
        # Zusage und muss sichtbar werden, nicht stillschweigend ersetzt.
        umformuliert = claims.disclaimer("daily_run_privacy", "en").replace("no keys", "no key material")
        self.assertEqual(claims.unregistered_texts([umformuliert]), [umformuliert])


class LintScriptTests(unittest.TestCase):
    def _run(self, extra_args):
        return subprocess.run(
            [sys.executable, "scripts/lint_claims.py", *extra_args],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=REPO_ROOT,
        )

    def test_lint_fails_on_planted_violation(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad_copy.md"
            bad.write_text("Our score predicts future returns, wirklich.", encoding="utf-8")
            result = self._run(["--paths", str(bad)])
        self.assertEqual(result.returncode, 1)
        self.assertIn("predicts future returns", result.stdout)

    def test_lint_passes_on_clean_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "good_copy.md"
            good.write_text("Describes settled trades with n and CI.", encoding="utf-8")
            result = self._run(["--paths", str(good)])
        self.assertEqual(result.returncode, 0)

    def test_lint_passes_on_current_repo(self):
        result = self._run([])
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
