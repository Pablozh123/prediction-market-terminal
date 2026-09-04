"""Route-Waermer, Fehlertext-Kuerzung und Eingabegrenzen der API.

Der Waermer haelt /api/cross und die Risk-Rechnung im Hintergrund warm;
jede Route laeuft fuer sich, ein Fehler stoppt die andere nicht. Fehlertexte
nach draussen tragen keine Upstream-URLs mehr, nur den Host. Negative
Limits und endlose Suchstrings weist die Validierung ab.
"""

from __future__ import annotations

import unittest
from unittest import mock

from fastapi.testclient import TestClient

from api import server


class WarmRoutesTests(unittest.TestCase):
    def test_beide_routen_wenn_kein_sampler_laeuft(self) -> None:
        with mock.patch.object(server, "cross", return_value={}) as cross, \
                mock.patch.object(server, "build_risk_payload", return_value={}) as risk, \
                mock.patch.object(server, "_SAMPLER_STARTED") as started:
            started.is_set.return_value = False
            self.assertEqual(server.warm_routes_once(), {"cross": "ok", "risk": "ok"})
        cross.assert_called_once_with(query="", min_similarity=server.apv.CROSS_MIN_SIMILARITY, max_pairs=150)
        risk.assert_called_once_with()

    def test_risk_bleibt_beim_sampler(self) -> None:
        with mock.patch.object(server, "cross", return_value={}), \
                mock.patch.object(server, "build_risk_payload") as risk, \
                mock.patch.object(server, "_SAMPLER_STARTED") as started:
            started.is_set.return_value = True
            self.assertEqual(server.warm_routes_once(), {"cross": "ok"})
        risk.assert_not_called()

    def test_ein_fehler_stoppt_die_andere_route_nicht(self) -> None:
        with mock.patch.object(server, "cross", side_effect=RuntimeError("gamma down")), \
                mock.patch.object(server, "build_risk_payload", return_value={}), \
                mock.patch.object(server, "_SAMPLER_STARTED") as started:
            started.is_set.return_value = False
            ergebnis = server.warm_routes_once()
        self.assertEqual(ergebnis["risk"], "ok")
        self.assertEqual(ergebnis["cross"], "RuntimeError: gamma down")

    def test_aus_ohne_intervall(self) -> None:
        with mock.patch.object(server, "ROUTE_WARM_MIN", 0.0):
            self.assertFalse(server.start_route_warmer())
        self.assertFalse(server._WARMER_STARTED.is_set())


class OeffentlicherFehlertextTests(unittest.TestCase):
    def test_url_wird_zum_host(self) -> None:
        text = ("search unavailable: https://gamma-api.polymarket.com/public-search?q=<script>&limit=12 "
                "failed: 403 Client Error for url: https://gamma-api.polymarket.com/public-search?q=x")
        self.assertEqual(
            server._oeffentlich(text),
            "search unavailable: gamma-api.polymarket.com failed: 403 Client Error for url: gamma-api.polymarket.com")

    def test_text_ohne_url_bleibt(self) -> None:
        self.assertEqual(server._oeffentlich(ValueError("no trade tape available")), "no trade tape available")

    def test_suchfehler_nennt_keine_url(self) -> None:
        client = TestClient(server.app)
        with mock.patch.object(server, "cached", side_effect=RuntimeError(
                "https://gamma-api.polymarket.com/public-search?q=abc failed: 403")):
            r = client.get("/api/search", params={"q": "abc"})
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["detail"], "search unavailable: gamma-api.polymarket.com failed: 403")


class EingabegrenzenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(server.app)

    def test_negatives_limit_wird_abgewiesen(self) -> None:
        for pfad in ("/api/tape?limit=-1", "/api/tape?limit=0", "/api/resolved?limit=-5", "/api/search?q=a&limit=0"):
            with self.subTest(pfad=pfad):
                self.assertEqual(self.client.get(pfad).status_code, 422)

    def test_suchstring_hat_eine_obergrenze(self) -> None:
        r = self.client.get("/api/search", params={"q": "x" * 201})
        self.assertEqual(r.status_code, 422)
        r = self.client.get("/api/markets", params={"query": "x" * 201})
        self.assertEqual(r.status_code, 422)


if __name__ == "__main__":
    unittest.main()
