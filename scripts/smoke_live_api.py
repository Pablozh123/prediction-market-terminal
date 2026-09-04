"""Smoke the live API after a deploy.

    python scripts/smoke_live_api.py https://api.marketintel.dev [--timeout 30]

Requests a fixed list of routes and checks the status code, the shape of the
JSON payload and, for one route, the security headers. One line per route, a
summary, exit status 1 on any failure. Standard library only, so the
scheduled smoke (.github/workflows/smoke-api.yml) runs it on a bare runner
without installing requirements.txt.

Three 200s on /healthz prove that a container answers; they say nothing about
the image being complete. A data file that did not make it into the build or
a dropped middleware ships with a healthy /healthz, and that is what this
catches. /api/risk and /api/cross are left out on purpose: both take 20 s or
more on a cold container and would turn every deploy into a race against the
timeout.
"""

from __future__ import annotations

import argparse
import http.client
import json
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from typing import Any

USER_AGENT = "marketintel-smoke/1.0"
DEFAULT_TIMEOUT = 30.0

# The checks ``evaluate`` knows, applied on top of the status code:
#   json     the body parses as a JSON object
#   rows     the object carries a ``rows`` list
#   claims   the claims register is populated (``version`` is not 0)
#   headers  the response carries the API security headers
CHECKS = ("json", "rows", "claims", "headers")

# One entry per request, in the order they are made. ``label`` distinguishes
# two requests to the same route in the printed output.
ROUTES: list[dict[str, Any]] = [
    {"method": "HEAD", "path": "/healthz", "status": 200},
    {"method": "GET", "path": "/healthz", "status": 200, "expect": ["json"]},
    {"method": "GET", "path": "/api/health", "status": 200, "expect": ["json"]},
    {"method": "GET", "path": "/api/markets?limit=5", "status": 200, "expect": ["json", "rows"]},
    {"method": "GET", "path": "/api/tape?limit=5", "status": 200, "expect": ["json", "rows"]},
    {"method": "GET", "path": "/api/research/live-runs", "status": 200, "expect": ["json"]},
    {"method": "GET", "path": "/api/claims", "status": 200, "expect": ["json", "claims"]},
    {"method": "GET", "path": "/api/resolved?limit=5", "status": 200, "expect": ["json"]},
    # The paper copy desk: reads are public, so it answers without a token.
    {"method": "GET", "path": "/api/copy", "status": 200, "expect": ["json"]},
    {"method": "GET", "path": "/api/health", "status": 200, "expect": ["headers"], "label": "security headers"},
]

# What an empty register means, spelled out where the failure is read.
EMPTY_CLAIMS = (
    "claims register is empty (version 0): data/claims.yaml is not in the running image, so "
    "/api/claims serves no disclaimers and the frontend falls back to its compiled copy; "
    "the Dockerfile must COPY data/claims.yaml and the API be redeployed"
)

Response = tuple[int, dict[str, str], bytes, float]
Fetch = Callable[[str, str, float], Response]


def route_name(route: Mapping[str, Any]) -> str:
    name = f"{route.get('method', 'GET')} {route['path']}"
    label = route.get("label")
    return f"{name} ({label})" if label else name


def missing_security_headers(headers: Mapping[str, str]) -> list[str]:
    """The API headers (api/server.py, API_SECURITY_HEADERS) a response lacks. Header names are case-insensitive."""

    lower = {str(name).lower(): str(value) for name, value in headers.items()}
    missing: list[str] = []
    if lower.get("x-frame-options", "").strip().upper() != "DENY":
        missing.append("X-Frame-Options: DENY")
    if not lower.get("content-security-policy", "").strip():
        missing.append("Content-Security-Policy")
    return missing


def _excerpt(body: bytes, limit: int = 120) -> str:
    text = " ".join(body.decode("utf-8", errors="replace").split())
    if not text:
        return ""
    return " - " + (text[:limit] + "..." if len(text) > limit else text)


def evaluate(route: Mapping[str, Any], status: int, headers: Mapping[str, str], body: bytes) -> tuple[bool, str]:
    """Judge one response against its route entry: (ok, detail).

    Pure - no network, no clock - so the tests feed it fake responses. Status
    0 stands for no HTTP answer at all; the body then carries the reason.
    """

    if status == 0:
        return False, "no response" + _excerpt(body)
    wanted = int(route.get("status", 200))
    if status != wanted:
        return False, f"expected {wanted}, got {status}" + _excerpt(body)

    checks = [str(check) for check in route.get("expect", ())]
    notes: list[str] = []
    data: Any = None
    if any(check in checks for check in ("json", "rows", "claims")):
        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return False, "body is not JSON" + _excerpt(body)
        if not isinstance(data, dict):
            return False, f"expected a JSON object, got {type(data).__name__}"
        notes.append("json")
    if "rows" in checks:
        rows = data.get("rows")
        if not isinstance(rows, list):
            return False, f"no 'rows' list in the payload (keys: {', '.join(sorted(data)) or 'none'})"
        notes.append(f"{len(rows)} rows")
    if "claims" in checks:
        version = int(data.get("version") or 0)
        if not version:
            return False, EMPTY_CLAIMS
        notes.append(f"version {version}, {len(data.get('allowed_claims') or [])} claims")
    if "headers" in checks:
        missing = missing_security_headers(headers)
        if missing:
            return False, "missing " + ", ".join(missing) + " (the api_schutzheader middleware is not in this build)"
        notes.append("X-Frame-Options, Content-Security-Policy")
    return True, ", ".join(notes)


def fetch(url: str, method: str, timeout: float) -> Response:
    """One request: (status, headers, body, milliseconds). Status 0 means no HTTP answer; the body says why."""

    request = urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status, headers, body = int(response.status), dict(response.headers.items()), response.read()
    except urllib.error.HTTPError as exc:
        status, headers, body = int(exc.code), dict(exc.headers.items()), exc.read()
    except (OSError, http.client.HTTPException) as exc:
        # URLError, timeouts, refused connections and TLS failures all derive from OSError.
        status, headers, body = 0, {}, str(exc).encode()
    return status, headers, body, (time.perf_counter() - started) * 1000.0


def format_line(route: Mapping[str, Any], status: int, ms: float, ok: bool, detail: str) -> str:
    label = "ok  " if ok else "FAIL"
    return f"{label}  {route_name(route):<44} {status:>3} {ms:>6.0f} ms  {detail}".rstrip()


def run(base_url: str, routes: Sequence[Mapping[str, Any]], timeout: float, fetch_one: Fetch = fetch) -> int:
    """Request every route, print one line each plus a summary; 0 when all pass, 1 otherwise."""

    base = base_url.rstrip("/")
    if "://" not in base:
        base = "https://" + base
    print(f"smoke {base}  ({len(routes)} requests, timeout {timeout:g} s)")
    failed = 0
    for route in routes:
        status, headers, body, ms = fetch_one(base + route["path"], route.get("method", "GET"), timeout)
        ok, detail = evaluate(route, status, headers, body)
        failed += 0 if ok else 1
        print(format_line(route, status, ms, ok, detail))
    passed = len(routes) - failed
    print(f"{passed}/{len(routes)} ok" + (f", {failed} FAILED" if failed else ""))
    return 1 if failed else 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke the live Market Intel API: fixed routes, status, payload shape, security headers.")
    parser.add_argument("base_url", help="API origin, e.g. https://api.marketintel.dev")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                        help=f"seconds per request (default {DEFAULT_TIMEOUT:g}); a cold container is slow, not down")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    return run(str(args.base_url), ROUTES, float(args.timeout))


if __name__ == "__main__":
    sys.exit(main())
