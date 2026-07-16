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
