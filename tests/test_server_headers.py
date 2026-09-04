"""Schutzheader der API-Antworten und der Vorrang von CF-Connecting-IP.

api.marketintel.dev ist ein eigener Host: weder web/_headers (Pages) noch
deploy/Caddyfile erreichen seine Antworten, also traegt die API ihre Header
selbst — aber nur unter /api/ und /healthz. Das Frontend aus demselben
Prozess (/) darf die API-CSP nicht bekommen, default-src 'none' wuerde die
eigene Seite blockieren. Der zweite Block prueft, welche Adresse der
Rate-Limiter hinter dem Proxy sieht.
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

from fastapi.testclient import TestClient
from starlette.requests import Request

from api import server

API_CSP = "default-src 'none'; frame-ancestors 'none'"


def _request(headers: dict[str, str], peer: str = "172.70.0.1") -> Request:
    """Roh-Request ohne Server: nur Header und Socket-Peer zaehlen hier."""

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/health",
        "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": (peer, 40000),
    }
    return Request(scope)


class ApiHeaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Kein ``with``: der Lifespan wuerde die Hintergrund-Threads starten.
        cls.client = TestClient(server.app)

    def test_api_health_traegt_die_schutzheader(self) -> None:
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(r.headers["X-Frame-Options"], "DENY")
        self.assertEqual(r.headers["Referrer-Policy"], "no-referrer")
        self.assertEqual(r.headers["Content-Security-Policy"], API_CSP)

    def test_health_nennt_den_gebauten_commit(self) -> None:
        with mock.patch.dict(os.environ, {"RAILWAY_GIT_COMMIT_SHA": "abc123"}):
            self.assertEqual(self.client.get("/api/health").json()["commit"], "abc123")
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RAILWAY_GIT_COMMIT_SHA", None)
            self.assertEqual(self.client.get("/api/health").json()["commit"], "")

    def test_healthz_alias_ebenso_und_auch_per_head(self) -> None:
        for method in ("GET", "HEAD"):
            r = self.client.request(method, "/healthz")
            self.assertEqual(r.status_code, 200, f"{method} /healthz")
            self.assertEqual(r.headers["Content-Security-Policy"], API_CSP)
        self.assertEqual(self.client.head("/api/health").status_code, 200)

    def test_frontend_bleibt_ohne_api_csp(self) -> None:
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/html", r.headers.get("content-type", ""))
        self.assertNotIn("Content-Security-Policy", r.headers)
        self.assertNotIn("X-Frame-Options", r.headers)
        # kein_frontend_cache bleibt zustaendig
        self.assertEqual(r.headers["Cache-Control"], "no-store, must-revalidate")
        self.assertNotIn("X-Robots-Tag", r.headers)

    def test_frontend_auf_dem_api_host_ist_noindex(self) -> None:
        r = self.client.get("/", headers={"host": "api.marketintel.dev"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["X-Robots-Tag"], "noindex")
        # die JSON-Routen bleiben, wie sie sind: Schutzheader, kein Robots-Tag
        r = self.client.get("/api/health", headers={"host": "api.marketintel.dev"})
        self.assertNotIn("X-Robots-Tag", r.headers)


class ForwardedAddressTests(unittest.TestCase):
    def test_cf_connecting_ip_gewinnt_gegen_den_konfigurierten_header(self) -> None:
        req = _request({"CF-Connecting-IP": "203.0.113.9", "X-Forwarded-For": "198.51.100.7, 172.70.0.1"})
        with mock.patch.object(server, "RATE_LIMIT_TRUST_CF", True), \
                mock.patch.object(server, "RATE_LIMIT_IP_HEADER", "X-Forwarded-For"):
            self.assertEqual(server._request_ip(req), "203.0.113.9")

    def test_ohne_cf_header_zaehlt_der_konfigurierte(self) -> None:
        req = _request({"X-Forwarded-For": "198.51.100.7, 172.70.0.1"})
        with mock.patch.object(server, "RATE_LIMIT_TRUST_CF", True), \
                mock.patch.object(server, "RATE_LIMIT_IP_HEADER", "X-Forwarded-For"):
            self.assertEqual(server._request_ip(req), "198.51.100.7")

    def test_leerer_cf_header_faellt_durch(self) -> None:
        req = _request({"CF-Connecting-IP": "  ", "X-Forwarded-For": "198.51.100.7"})
        with mock.patch.object(server, "RATE_LIMIT_TRUST_CF", True), \
                mock.patch.object(server, "RATE_LIMIT_IP_HEADER", "X-Forwarded-For"):
            self.assertEqual(server._request_ip(req), "198.51.100.7")

    def test_ohne_jeden_header_der_socket_peer(self) -> None:
        self.assertEqual(server._request_ip(_request({}, peer="10.0.0.5")), "10.0.0.5")

    def test_abgeschaltet_ignoriert_cf(self) -> None:
        req = _request({"CF-Connecting-IP": "203.0.113.9", "X-Forwarded-For": "198.51.100.7"})
        with mock.patch.object(server, "RATE_LIMIT_TRUST_CF", False), \
                mock.patch.object(server, "RATE_LIMIT_IP_HEADER", "X-Forwarded-For"):
            self.assertEqual(server._request_ip(req), "198.51.100.7")

    def test_copy_desk_sieht_cf_als_proxied(self) -> None:
        # Ein Cloudflare-Header allein macht die Anfrage remote: ohne Token
        # kein Schreibzugriff, auch wenn der Socket-Peer Loopback ist.
        req = _request({"CF-Connecting-IP": "203.0.113.9"}, peer="127.0.0.1")
        with mock.patch.dict(os.environ), mock.patch.object(server, "RATE_LIMIT_TRUST_CF", True):
            os.environ.pop("COPY_ADMIN_TOKEN", None)
            self.assertFalse(server._copy_write_access(req).allowed)


if __name__ == "__main__":
    unittest.main()
