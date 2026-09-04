"""The live-API smoke (scripts/smoke_live_api.py), checked without a network.

The script runs after every deploy (deploy-api.yml). Its request loop is
thin; what matters is that ``evaluate`` judges a response the way the deploy
expects - it is fed fake responses here - and that the route table cannot
drift into something the loop cannot run.
"""

from __future__ import annotations

import importlib.util
import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "smoke_live_api_under_test",
    Path(__file__).resolve().parents[1] / "scripts" / "smoke_live_api.py",
)
smoke = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(smoke)

API_HEADERS = {
    "Content-Type": "application/json",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}


def _route(path: str, method: str = "GET", label: str | None = None) -> dict:
    for route in smoke.ROUTES:
        if route["path"] == path and route.get("method", "GET") == method and route.get("label") == label:
            return route
    raise AssertionError(f"{method} {path} ({label}) is not in ROUTES")


def _json(payload: object) -> bytes:
    return json.dumps(payload).encode("utf-8")


class RouteTableTests(unittest.TestCase):
    def test_every_route_is_well_formed(self) -> None:
        for route in smoke.ROUTES:
            with self.subTest(route=smoke.route_name(route)):
                self.assertIsInstance(route, dict)
                self.assertTrue(route["path"].startswith("/"), route["path"])
                self.assertIn(route.get("method", "GET"), ("GET", "HEAD"))
                self.assertIsInstance(route.get("status", 200), int)
                checks = route.get("expect", [])
                self.assertIsInstance(checks, list)
                self.assertTrue(set(checks) <= set(smoke.CHECKS), checks)
                if route.get("method") == "HEAD":
                    # a HEAD body is empty by definition, so nothing can be read from it
                    self.assertFalse(set(checks) & {"json", "rows", "claims"}, checks)

    def test_printed_names_are_unique(self) -> None:
        names = [smoke.route_name(route) for route in smoke.ROUTES]
        self.assertEqual(len(names), len(set(names)), names)

    def test_the_deploy_contract_is_in_the_table(self) -> None:
        self.assertEqual(_route("/healthz", "HEAD")["status"], 200)
        self.assertIn("json", _route("/healthz")["expect"])
        for path in ("/api/markets?limit=5", "/api/tape?limit=5"):
            self.assertIn("rows", _route(path)["expect"], path)
        self.assertIn("claims", _route("/api/claims")["expect"])
        self.assertIn("headers", _route("/api/health", label="security headers")["expect"])
        for path in ("/api/research/live-runs", "/api/resolved?limit=5", "/api/copy"):
            self.assertIn("json", _route(path)["expect"], path)

    def test_the_slow_routes_stay_out(self) -> None:
        # /api/risk and /api/cross take 20 s or more on a cold container.
        paths = {route["path"].split("?")[0] for route in smoke.ROUTES}
        self.assertFalse(paths & {"/api/risk", "/api/cross"}, paths)


class EvaluateTests(unittest.TestCase):
    def test_json_object_with_rows_passes(self) -> None:
        ok, detail = smoke.evaluate(_route("/api/markets?limit=5"), 200, API_HEADERS, _json({"rows": [1, 2, 3]}))
        self.assertTrue(ok, detail)
        self.assertIn("3 rows", detail)

    def test_head_with_an_empty_body_passes(self) -> None:
        ok, detail = smoke.evaluate(_route("/healthz", "HEAD"), 200, API_HEADERS, b"")
        self.assertTrue(ok, detail)

    def test_wrong_status_names_both_codes_and_the_body(self) -> None:
        ok, detail = smoke.evaluate(_route("/api/health"), 503, {}, _json({"detail": "warming up"}))
        self.assertFalse(ok)
        self.assertIn("expected 200, got 503", detail)
        self.assertIn("warming up", detail)

    def test_no_response_is_a_failure_with_the_reason(self) -> None:
        ok, detail = smoke.evaluate(_route("/api/health"), 0, {}, b"timed out")
        self.assertFalse(ok)
        self.assertIn("no response", detail)
        self.assertIn("timed out", detail)

    def test_missing_rows_lists_the_keys_it_saw(self) -> None:
        ok, detail = smoke.evaluate(_route("/api/tape?limit=5"), 200, API_HEADERS, _json({"total": 0, "as_of": "x"}))
        self.assertFalse(ok)
        self.assertIn("rows", detail)
        self.assertIn("as_of, total", detail)

    def test_rows_must_be_a_list(self) -> None:
        ok, _ = smoke.evaluate(_route("/api/tape?limit=5"), 200, API_HEADERS, _json({"rows": None}))
        self.assertFalse(ok)

    def test_html_where_json_was_expected_fails(self) -> None:
        ok, detail = smoke.evaluate(_route("/api/health"), 200, {}, b"<html><body>Bad gateway</body></html>")
        self.assertFalse(ok)
        self.assertIn("not JSON", detail)
        self.assertIn("Bad gateway", detail)

    def test_a_json_list_is_not_an_object(self) -> None:
        ok, detail = smoke.evaluate(_route("/api/health"), 200, {}, _json([1, 2]))
        self.assertFalse(ok)
        self.assertIn("got list", detail)

    def test_empty_claims_register_fails_and_says_what_it_means(self) -> None:
        live_shape = {"version": 0, "updated": "", "disclaimers": {}, "allowed_claims": [], "source": "data/claims.yaml"}
        ok, detail = smoke.evaluate(_route("/api/claims"), 200, API_HEADERS, _json(live_shape))
        self.assertFalse(ok)
        self.assertIn("version 0", detail)
        self.assertIn("data/claims.yaml", detail)
        self.assertIn("Dockerfile", detail)

    def test_populated_claims_register_passes(self) -> None:
        payload = {"version": 3, "disclaimers": {"a": {}}, "allowed_claims": [{"id": "x"}, {"id": "y"}]}
        ok, detail = smoke.evaluate(_route("/api/claims"), 200, API_HEADERS, _json(payload))
        self.assertTrue(ok, detail)
        self.assertIn("version 3", detail)
        self.assertIn("2 claims", detail)

    def test_security_headers_pass_regardless_of_case(self) -> None:
        headers = {"x-frame-options": "DENY", "content-security-policy": "default-src 'none'"}
        ok, detail = smoke.evaluate(_route("/api/health", label="security headers"), 200, headers, _json({"ok": True}))
        self.assertTrue(ok, detail)

    def test_missing_csp_is_named(self) -> None:
        ok, detail = smoke.evaluate(_route("/api/health", label="security headers"), 200, {"X-Frame-Options": "DENY"}, b"{}")
        self.assertFalse(ok)
        self.assertIn("Content-Security-Policy", detail)
        self.assertNotIn("X-Frame-Options", detail.split("(")[0])

    def test_frame_options_must_be_deny(self) -> None:
        headers = {"X-Frame-Options": "SAMEORIGIN", "Content-Security-Policy": "default-src 'none'"}
        ok, detail = smoke.evaluate(_route("/api/health", label="security headers"), 200, headers, b"{}")
        self.assertFalse(ok)
        self.assertIn("X-Frame-Options: DENY", detail)

    def test_missing_headers_helper_lists_both(self) -> None:
        self.assertEqual(smoke.missing_security_headers({}), ["X-Frame-Options: DENY", "Content-Security-Policy"])
        self.assertEqual(smoke.missing_security_headers(API_HEADERS), [])


def _fake_fetch(responses: dict[tuple[str, str], tuple[int, dict, bytes]]):
    """A stand-in for ``fetch`` keyed by (method, path); anything else is a 404."""

    def fetch_one(url: str, method: str, timeout: float):
        path = url.split("://", 1)[1].split("/", 1)[1]
        status, headers, body = responses.get((method, "/" + path), (404, {}, b'{"detail":"Not Found"}'))
        return status, headers, body, 12.5

    return fetch_one


def _healthy_responses() -> dict[tuple[str, str], tuple[int, dict, bytes]]:
    claims = _json({"version": 2, "allowed_claims": [{"id": "a"}]})
    rows = _json({"rows": [{"market_key": "m"}], "total": 1})
    return {
        ("HEAD", "/healthz"): (200, API_HEADERS, b""),
        ("GET", "/healthz"): (200, API_HEADERS, _json({"ok": True})),
        ("GET", "/api/health"): (200, API_HEADERS, _json({"ok": True})),
        ("GET", "/api/markets?limit=5"): (200, API_HEADERS, rows),
        ("GET", "/api/tape?limit=5"): (200, API_HEADERS, rows),
        ("GET", "/api/research/live-runs"): (200, API_HEADERS, _json({"laeufe": []})),
        ("GET", "/api/claims"): (200, API_HEADERS, claims),
        ("GET", "/api/resolved?limit=5"): (200, API_HEADERS, rows),
        ("GET", "/api/copy"): (200, API_HEADERS, _json({"status": {}})),
    }


class RunTests(unittest.TestCase):
    def _run(self, responses: dict) -> tuple[int, list[str]]:
        out = io.StringIO()
        with redirect_stdout(out):
            code = smoke.run("api.example.test", smoke.ROUTES, 5.0, fetch_one=_fake_fetch(responses))
        return code, out.getvalue().splitlines()

    def test_all_green_exits_zero(self) -> None:
        code, lines = self._run(_healthy_responses())
        self.assertEqual(code, 0, lines)
        self.assertTrue(lines[0].startswith("smoke https://api.example.test"), lines[0])
        body = lines[1:-1]
        self.assertEqual(len(body), len(smoke.ROUTES))
        self.assertTrue(all(line.startswith("ok  ") for line in body), body)
        self.assertEqual(lines[-1], f"{len(smoke.ROUTES)}/{len(smoke.ROUTES)} ok")

    def test_one_failure_exits_one_and_is_visible(self) -> None:
        responses = _healthy_responses()
        responses[("GET", "/api/claims")] = (200, API_HEADERS, _json({"version": 0, "allowed_claims": []}))
        code, lines = self._run(responses)
        self.assertEqual(code, 1)
        failing = [line for line in lines if line.startswith("FAIL")]
        self.assertEqual(len(failing), 1, lines)
        self.assertIn("GET /api/claims", failing[0])
        self.assertIn("200", failing[0])
        self.assertIn("1 FAILED", lines[-1])

    def test_a_line_carries_status_and_timing(self) -> None:
        line = smoke.format_line(_route("/api/health"), 200, 87.4, True, "json")
        self.assertTrue(line.startswith("ok    GET /api/health"), line)
        self.assertIn(" 200 ", line)
        self.assertIn("87 ms", line)
        self.assertTrue(line.endswith("json"), line)


if __name__ == "__main__":
    unittest.main()
