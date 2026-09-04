"""Findings of the live audit of marketintel.dev (2026-09-04), as rendered.

Two of them concern what the pages draw, so they are checked on the output
of the same Node harness as test_web_leerzustand.py, in both modes:

1. Every page variant carries exactly one <h1>. The wallet graph had none —
   its title was a styled div inside the first card, and the loading and
   error states had no title at all.
2. The Methodology page explains the ``backend`` field of the published
   public/data/meta.json in plain words: the file said ``backend: "mock"``
   in a public artifact, and no page said what the word refers to.

Ohne node wird uebersprungen, in der CI nicht.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
HARNESS = WURZEL / "tests" / "web_render_harness.mjs"

GRAPH_VARIANTEN = ("graph", "graph_data", "graph_unavailable")


def _h1(html: str) -> list[str]:
    return re.findall(r"<h1[^>]*>(.*?)</h1>", html, re.S)


def _sichtbarer_text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", html)).strip()


class WebLaunchHygieneTest(unittest.TestCase):
    ausgabe: dict

    @classmethod
    def setUpClass(cls) -> None:
        node = shutil.which("node")
        if node is None:
            if os.environ.get("CI"):
                raise AssertionError(
                    "node fehlt in der CI, der Render-Test der Weboberflaeche "
                    "kann nicht laufen (setup-node im Workflow pruefen)")
            raise unittest.SkipTest("node ist nicht installiert")
        lauf = subprocess.run(
            [node, str(HARNESS)],
            cwd=str(WURZEL),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
        )
        if lauf.returncode != 0:
            raise AssertionError(f"Harness brach ab:\n{lauf.stderr}")
        cls.ausgabe = json.loads(lauf.stdout)

    # -- 1. one <h1> per page ----------------------------------------------
    def test_jede_seitenvariante_hat_genau_ein_h1(self) -> None:
        for modus in ("leer", "live"):
            for name, html in self.ausgabe[modus].items():
                # Keys with a leading underscore are helper outputs (JSON
                # strings), not pages.
                if name.startswith("_") or not isinstance(html, str):
                    continue
                with self.subTest(modus=modus, seite=name):
                    self.assertEqual(len(_h1(html)), 1, f"{modus}/{name} has {len(_h1(html))} <h1>")

    def test_der_wallet_graph_hat_in_jedem_zustand_seinen_kopf(self) -> None:
        # Loading (leer/graph), with data and without a graph on the host:
        # kicker, the title as <h1>, and the lead — not a second title.
        for modus in ("leer", "live"):
            for name in GRAPH_VARIANTEN:
                html = self.ausgabe[modus][name]
                with self.subTest(modus=modus, seite=name):
                    self.assertEqual(_h1(html), ["Wallet graph"])
                    text = _sichtbarer_text(html)
                    self.assertIn("WALLET GRAPH", text)
                    self.assertIn("Accounts linked over public on-chain evidence", text)
                    self.assertEqual(text.count("Wallet graph"), 1)

    # -- 2. the backend field of meta.json is explained --------------------
    def test_methodology_erklaert_das_backend_feld_von_meta_json(self) -> None:
        # The sentence is documentation and stands with and without the
        # audit payload, next to the backend count the page reports.
        for modus in ("leer", "live"):
            text = _sichtbarer_text(self.ausgabe[modus]["research_methodology"])
            with self.subTest(modus=modus):
                self.assertIn("public/data/meta.json, carries a backend field of its own", text)
                self.assertIn("mock is the deterministic stand-in with no network access", text)
                self.assertIn("not where the market data came from", text)


if __name__ == "__main__":
    unittest.main()
