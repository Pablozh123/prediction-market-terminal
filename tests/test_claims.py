import importlib.util
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
