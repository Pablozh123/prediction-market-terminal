"""CORS-Voreinstellungen des API-Servers.

Die produktiven Origins des Projekts sind Fakten, keine Konfiguration:
ohne Umgebungsvariablen muss marketintel.dev die eigene API rufen duerfen
und die Vorschau-Domains muessen auf das Muster passen. Genau daran
scheiterte das Live-Band einmal, waehrend healthz laengst antwortete —
der Browser verwarf jede /api-Antwort mangels CORS-Header.
"""

from __future__ import annotations

import os
import re
import unittest
from unittest import mock

from api import server


class CorsDefaultTests(unittest.TestCase):
    def test_default_liste_enthaelt_produktion_und_lokal(self) -> None:
        with mock.patch.dict(os.environ):
            os.environ.pop("CORS_ORIGINS", None)
            origins = server._cors_origins()
        self.assertIn("https://marketintel.dev", origins)
        self.assertIn("https://www.marketintel.dev", origins)
        self.assertIn("http://localhost:8787", origins)
        self.assertIn("http://127.0.0.1:8787", origins)

    def test_env_ersetzt_die_liste_vollstaendig(self) -> None:
        with mock.patch.dict(os.environ, {"CORS_ORIGINS": "https://example.org"}):
            self.assertEqual(server._cors_origins(), ["https://example.org"])

    def test_default_muster_passt_nur_auf_die_vorschau_domains(self) -> None:
        with mock.patch.dict(os.environ):
            os.environ.pop("CORS_ORIGIN_REGEX", None)
            muster = server._cors_origin_regex()
        # Starlette prueft das Muster mit fullmatch — genau so hier.
        self.assertIsNotNone(re.fullmatch(muster, "https://claude-branch.prediction-market-terminal.pages.dev"))
        self.assertIsNone(re.fullmatch(muster, "https://evil.example.org"))
        self.assertIsNone(re.fullmatch(muster, "https://x.prediction-market-terminal.pages.dev.example.org"))

    def test_env_ersetzt_das_muster(self) -> None:
        with mock.patch.dict(os.environ, {"CORS_ORIGIN_REGEX": r"https://nur\.hier"}):
            self.assertEqual(server._cors_origin_regex(), r"https://nur\.hier")
