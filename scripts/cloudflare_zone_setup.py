"""Bring the marketintel.dev Cloudflare zone to its documented production state.

docs/PRODUCTION_READINESS.md section 8a lists what has to be set in the
Cloudflare dashboard. This script sets the same things through the API
(https://api.cloudflare.com/client/v4), so the owner only has to paste one
token into a terminal:

  ssl                Full (strict)                     PATCH /zones/{id}/settings/ssl
  min_tls_version    1.2                               PATCH /zones/{id}/settings/min_tls_version
  always_use_https   on                                PATCH /zones/{id}/settings/always_use_https
  browser_cache_ttl  0 = Respect Existing Headers      PATCH /zones/{id}/settings/browser_cache_ttl
  bot fight mode     on                                PUT   /zones/{id}/bot_management {"fight_mode": true}
  rate limit         /api/: 60 requests per 10 s per   phase http_ratelimit, action block
                     IP, block for 10 s
  www redirect       www.<zone>/* -> https://<zone>/*  phase http_request_dynamic_redirect, 301,
                                                       query string kept
  geoblock CH        ip.src.country eq "CH" -> block   phase http_request_firewall_custom,
                                                       only with --geoblock-ch

Rules live in the zone's phase entry point rulesets. The script reads the
entry point (GET /zones/{id}/rulesets/phases/{phase}/entrypoint), creates it
together with the rule when it does not exist (POST /zones/{id}/rulesets,
kind "zone"), otherwise finds the rule by its description and updates it in
place (PATCH .../rulesets/{ruleset_id}/rules/{rule_id}) or adds it
(POST .../rulesets/{ruleset_id}/rules). Settings are read before they are
written. A second run therefore changes nothing and prints "skip" lines.

Modes: --dry-run prints every write it would send and performs only the zone
lookup; --verify performs only reads and prints the current value of every
setting and rule. Without either flag the zone is changed.

Token
-----
CLOUDFLARE_API_TOKEN is read from the environment, never from an argument,
and never printed. Create it under My Profile -> API Tokens -> Create Token
-> Custom token with these permissions, all in the Zone group:

  Zone              Read    zone lookup, GET /zones?name=
  Zone Settings     Edit    ssl, min_tls_version, always_use_https, browser_cache_ttl
  Zone WAF          Edit    rate limiting rule, optional country block
  Bot Management    Edit    Bot Fight Mode
  Single Redirect   Edit    the www redirect (older dashboards call it Dynamic Redirect)

Zone Resources: Include -> Specific zone -> marketintel.dev. No account-level
permission is needed.

Free plan limits that shaped the payloads (developers.cloudflare.com/waf/rate-limiting-rules/):
one rate limiting rule, counting period 10 s, mitigation timeout 10 s, IP as
the only characteristic, and the rule expression may use the path (and the
verified-bot flag) but not the hostname. The hostname clause is therefore
only sent when the zone is on a paid plan; /api/ exists on the API host alone,
so the path-only rule means the same thing.

Exit code: 0 when every step was ok or skipped, 1 when a step failed (the
remaining steps still run), 2 when the token is missing.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from functools import partial
from typing import Any, Callable

API_BASE = "https://api.cloudflare.com/client/v4"
TOKEN_ENV = "CLOUDFLARE_API_TOKEN"
DEFAULT_ZONE = "marketintel.dev"
DEFAULT_API_HOST = "api.marketintel.dev"
TIMEOUT_SECONDS = 30

# Zone settings, setting id -> value: PATCH /zones/{id}/settings/{setting_id} {"value": ...}
SETTINGS: dict[str, str | int] = {
    "ssl": "strict",  # Full (strict)
    "min_tls_version": "1.2",
    "always_use_https": "on",
    "browser_cache_ttl": 0,  # 0 = Respect Existing Headers
}

PHASE_RATELIMIT = "http_ratelimit"
PHASE_REDIRECT = "http_request_dynamic_redirect"
PHASE_CUSTOM = "http_request_firewall_custom"

# The description is the idempotency key: an existing rule with the same
# description is updated, never duplicated. The dashboard shows it as the rule
# name, so the paste sheet in docs/PRODUCTION_READINESS.md uses the same text.
RATE_LIMIT_DESCRIPTION = "API rate limit (cloudflare_zone_setup.py)"
REDIRECT_DESCRIPTION = "www to apex 301 (cloudflare_zone_setup.py)"
GEOBLOCK_DESCRIPTION = "Block Switzerland (cloudflare_zone_setup.py)"

RULESET_NAME = "default"
RULESET_DESCRIPTION = "Zone entry point, created by scripts/cloudflare_zone_setup.py"

RATE_LIMIT_REQUESTS = 60
RATE_LIMIT_PERIOD_SECONDS = 10
RATE_LIMIT_BLOCK_SECONDS = 10


# --- payloads ---------------------------------------------------------------


def rate_limit_rule(api_host: str, host_field_available: bool) -> dict[str, Any]:
    """Rate limiting rule for the API paths: 60 requests per 10 s per IP, then block for 10 s.

    The hostname clause needs a paid plan (Free plan expressions know only the
    path and the verified-bot flag), so it is optional; /api/ is served by the
    API host alone, which makes the path-only form equivalent.
    """
    path_clause = 'starts_with(http.request.uri.path, "/api/")'
    expression = f'(http.host eq "{api_host}" and {path_clause})' if host_field_available else f"({path_clause})"
    return {
        "description": RATE_LIMIT_DESCRIPTION,
        "expression": expression,
        "action": "block",
        "enabled": True,
        "ratelimit": {
            "characteristics": ["cf.colo.id", "ip.src"],
            "period": RATE_LIMIT_PERIOD_SECONDS,
            "requests_per_period": RATE_LIMIT_REQUESTS,
            "mitigation_timeout": RATE_LIMIT_BLOCK_SECONDS,
        },
    }


def redirect_rule(zone: str) -> dict[str, Any]:
    """Permanent redirect of www.<zone>/* to https://<zone>/*, path and query string kept."""
    return {
        "description": REDIRECT_DESCRIPTION,
        "expression": f'(http.host eq "www.{zone}")',
        "action": "redirect",
        "enabled": True,
        "action_parameters": {
            "from_value": {
                "status_code": 301,
                "target_url": {"expression": f'concat("https://{zone}", http.request.uri.path)'},
                "preserve_query_string": True,
            }
        },
    }


def country_block_rule(country: str = "CH") -> dict[str, Any]:
    """WAF custom rule that blocks every request from one country (ISO 3166-1 alpha-2)."""
    return {
        "description": GEOBLOCK_DESCRIPTION,
        "expression": f'(ip.src.country eq "{country}")',
        "action": "block",
        "enabled": True,
    }


def new_ruleset(phase: str, rule: dict[str, Any]) -> dict[str, Any]:
    """Body of POST /zones/{id}/rulesets: a zone entry point for `phase` that starts with `rule`."""
    return {
        "name": RULESET_NAME,
        "kind": "zone",
        "phase": phase,
        "description": RULESET_DESCRIPTION,
        "rules": [rule],
    }


# --- idempotency ------------------------------------------------------------

_MISSING = object()


def plan_rule(existing_rules: list[dict[str, Any]], wanted: dict[str, Any]) -> tuple[str, str | None]:
    """Decide between "skip", "update" and "create" by looking for the description of `wanted`.

    Returns the decision and, for skip and update, the id of the existing rule.
    """
    for rule in existing_rules:
        if rule.get("description") == wanted["description"]:
            rule_id = rule.get("id")
            decision = "skip" if _covers(rule, wanted) else "update"
            return decision, (str(rule_id) if rule_id is not None else None)
    return "create", None


def _covers(existing: Any, wanted: Any) -> bool:
    """True when every value the script would send is already in the server copy; extra server fields are ignored."""
    if isinstance(wanted, dict):
        if not isinstance(existing, dict):
            return False
        return all(_covers(existing.get(key, _MISSING), value) for key, value in wanted.items())
    if isinstance(wanted, list):
        if not isinstance(existing, list) or len(existing) != len(wanted):
            return False
        return sorted(map(_canonical, existing)) == sorted(map(_canonical, wanted))
    return existing == wanted


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def _same(current: Any, wanted: Any) -> bool:
    return current == wanted or str(current) == str(wanted)


# --- HTTP -------------------------------------------------------------------


class ApiError(Exception):
    """An answer from the API that is not a success; status 0 means no answer at all."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def _call(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """The one function that talks HTTP (tests replace it). Returns the decoded JSON envelope."""
    token = os.environ.get(TOKEN_ENV, "")
    if not token:
        raise ApiError(0, f"{TOKEN_ENV} is not set")
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        API_BASE + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "marketintel-cloudflare-zone-setup/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            payload = _decode(response.read())
    except urllib.error.HTTPError as exc:
        payload = _decode(exc.read())
        raise ApiError(exc.code, _error_text(payload) or f"HTTP {exc.code}") from None
    except urllib.error.URLError as exc:
        raise ApiError(0, f"no answer from the API: {exc.reason}") from None
    if payload.get("success") is False:
        raise ApiError(200, _error_text(payload) or "the API answered success=false")
    return payload


def _decode(raw: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _error_text(payload: dict[str, Any]) -> str:
    parts = []
    for error in payload.get("errors") or []:
        if isinstance(error, dict):
            code = error.get("code")
            message = str(error.get("message", ""))
            parts.append(f"{code}: {message}" if code is not None else message)
    return "; ".join(parts)


# --- steps ------------------------------------------------------------------


class Runner:
    """Runs the steps in order; every step prints one `ok|skip|FAIL  what  detail` line."""

    def __init__(self, zone: str, api_host: str, *, dry_run: bool, verify: bool, geoblock: bool) -> None:
        self.zone = zone
        self.api_host = api_host
        self.verify = verify
        self.dry_run = dry_run and not verify
        self.geoblock = geoblock
        self.zone_id = ""
        self.host_field = False  # rate limiting expressions may name the host (paid plans only)
        self.failed = 0

    def run(self) -> int:
        if not self.step_zone():
            return 1
        for setting_id, value in SETTINGS.items():
            self.step(setting_id, partial(self.step_setting, setting_id, value))
        self.step("bot fight mode", self.step_bot_fight_mode)
        rate_rule = rate_limit_rule(self.api_host, self.host_field)
        self.step("rate limit", partial(self.step_rule, "rate limit", PHASE_RATELIMIT, rate_rule))
        self.step("www redirect", partial(self.step_rule, "www redirect", PHASE_REDIRECT, redirect_rule(self.zone)))
        if self.geoblock or self.verify:
            block = partial(self.step_rule, "geoblock CH", PHASE_CUSTOM, country_block_rule("CH"),
                            optional=not self.geoblock)
            self.step("geoblock CH", block)
        else:
            self.report("skip", "geoblock CH", "off by default; --geoblock-ch creates the block rule")
        return 1 if self.failed else 0

    def step(self, what: str, action: Callable[[], None]) -> None:
        try:
            action()
        except ApiError as exc:
            self.report("FAIL", what, str(exc))
        except Exception as exc:  # a broken step must not take the remaining steps down with it
            self.report("FAIL", what, f"{type(exc).__name__}: {exc}")

    def report(self, status: str, what: str, detail: str) -> None:
        if status == "FAIL":
            self.failed += 1
        print(f"{status:<5} {what:<18} {detail}")

    def plan(self, what: str, summary: str, body: dict[str, Any]) -> None:
        self.report("ok", what, "dry-run: " + summary)
        print("      " + json.dumps(body, sort_keys=True))

    def step_zone(self) -> bool:
        try:
            payload = _call("GET", "/zones?name=" + urllib.parse.quote(self.zone))
        except ApiError as exc:
            self.report("FAIL", "zone", str(exc))
            return False
        zones = [zone for zone in payload.get("result") or [] if zone.get("name") == self.zone]
        if not zones:
            self.report("FAIL", "zone", f"{self.zone} is not visible to this token (Zone: Read on this zone?)")
            return False
        zone = zones[0]
        self.zone_id = str(zone["id"])
        plan_id = str((zone.get("plan") or {}).get("legacy_id") or "unknown")
        self.host_field = plan_id not in ("free", "unknown")
        scope = "host and path" if self.host_field else "path only (Free plan: no hostname field in rate limiting)"
        self.report("ok", "zone", f"{self.zone} -> {self.zone_id}, plan {plan_id}, rate limit keyed on {scope}")
        return True

    def step_setting(self, setting_id: str, wanted: str | int) -> None:
        path = f"/zones/{self.zone_id}/settings/{setting_id}"
        body = {"value": wanted}
        if self.dry_run:
            self.plan(setting_id, f"PATCH {path}", body)
            return
        current = (_call("GET", path).get("result") or {}).get("value")
        if self.verify:
            if _same(current, wanted):
                self.report("ok", setting_id, repr(current))
            else:
                self.report("FAIL", setting_id, f"{current!r} (wanted {wanted!r})")
            return
        if _same(current, wanted):
            self.report("skip", setting_id, f"already {wanted!r}")
            return
        _call("PATCH", path, body)
        self.report("ok", setting_id, f"{current!r} -> {wanted!r}")

    def step_bot_fight_mode(self) -> None:
        path = f"/zones/{self.zone_id}/bot_management"
        body = {"fight_mode": True}
        if self.dry_run:
            self.plan("bot fight mode", f"PUT {path}", body)
            return
        current = (_call("GET", path).get("result") or {}).get("fight_mode")
        if self.verify:
            self.report("ok" if current is True else "FAIL", "bot fight mode", f"fight_mode={current!r}")
            return
        if current is True:
            self.report("skip", "bot fight mode", "already on")
            return
        _call("PUT", path, body)
        self.report("ok", "bot fight mode", f"fight_mode={current!r} -> True")

    def step_rule(self, what: str, phase: str, rule: dict[str, Any], *, optional: bool = False) -> None:
        rulesets = f"/zones/{self.zone_id}/rulesets"
        if self.dry_run:
            summary = (
                f"POST {rulesets} (no {phase} ruleset yet: create it with this rule, kind zone) | "
                f"POST {rulesets}/<ruleset_id>/rules (ruleset exists, rule missing) | "
                f"PATCH {rulesets}/<ruleset_id>/rules/<rule_id> (rule {rule['description']!r} exists)"
            )
            self.plan(what, summary, rule)
            return
        ruleset = self._entrypoint(phase)
        rules = list((ruleset or {}).get("rules") or [])
        decision, rule_id = plan_rule(rules, rule)
        if self.verify:
            self._report_rule_state(what, phase, ruleset, rules, rule, decision, optional)
            return
        if ruleset is None:
            _call("POST", rulesets, new_ruleset(phase, rule))
            self.report("ok", what, f"created the {phase} ruleset with the rule")
        elif decision == "skip":
            self.report("skip", what, "rule already in place")
        elif decision == "update":
            if rule_id is None:
                raise ApiError(0, f"rule {rule['description']!r} exists but the API returned no id for it")
            _call("PATCH", f"{rulesets}/{ruleset['id']}/rules/{rule_id}", rule)
            self.report("ok", what, f"updated rule {rule_id}")
        else:
            try:
                _call("POST", f"{rulesets}/{ruleset['id']}/rules", rule)
            except ApiError as exc:
                if phase == PHASE_RATELIMIT and rules:
                    taken = ", ".join(repr(existing.get("description", "")) for existing in rules)
                    hint = f"rate limiting slots hold {taken}; rename one to {rule['description']!r} or delete it"
                    raise ApiError(exc.status, f"{exc}; {hint}") from None
                raise
            self.report("ok", what, f"added the rule to ruleset {ruleset['id']}")

    def _entrypoint(self, phase: str) -> dict[str, Any] | None:
        try:
            return _call("GET", f"/zones/{self.zone_id}/rulesets/phases/{phase}/entrypoint").get("result")
        except ApiError as exc:
            if exc.status == 404:  # documented: the phase has no entry point ruleset yet
                return None
            raise

    def _report_rule_state(self, what: str, phase: str, ruleset: dict[str, Any] | None, rules: list[dict[str, Any]],
                           wanted: dict[str, Any], decision: str, optional: bool) -> None:
        if decision == "create":
            where = f"no {phase} ruleset" if ruleset is None else f"not among the {len(rules)} rule(s) of {phase}"
            if optional:
                self.report("skip", what, f"not configured ({where}); optional, --geoblock-ch adds it")
            else:
                self.report("FAIL", what, f"rule missing: {where}")
            return
        existing = next(rule for rule in rules if rule.get("description") == wanted["description"])
        summary = _rule_summary(existing)
        if decision == "skip":
            self.report("ok", what, summary)
        elif optional:
            self.report("ok", what, f"present but not in the script's form: {summary}")
        else:
            self.report("FAIL", what, f"differs from the script's form: {summary}")


def _rule_summary(rule: dict[str, Any]) -> str:
    text = f"enabled={rule.get('enabled')!r} action={rule.get('action')!r} expression={rule.get('expression')!r}"
    extra = rule.get("ratelimit") or (rule.get("action_parameters") or {}).get("from_value")
    return text if extra is None else f"{text} {json.dumps(extra, sort_keys=True)}"


# --- entry point ------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Set the Cloudflare zone to the state documented in docs/PRODUCTION_READINESS.md section 8a.",
        epilog=f"The API token is read from ${TOKEN_ENV}; see the module docstring for the permissions it needs.",
    )
    parser.add_argument("--zone", default=DEFAULT_ZONE, help=f"zone name, default {DEFAULT_ZONE}")
    parser.add_argument("--api-host", default=DEFAULT_API_HOST,
                        help=f"host the rate limit is meant for, default {DEFAULT_API_HOST}")
    parser.add_argument("--dry-run", action="store_true",
                        help="print every write with method, path and body; only the zone lookup is sent")
    parser.add_argument("--verify", action="store_true",
                        help="only read: print the current value of every setting and rule")
    parser.add_argument("--geoblock-ch", action="store_true",
                        help="also create the WAF rule that blocks Switzerland (a business decision, off by default)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not os.environ.get(TOKEN_ENV):
        print(f"FAIL  token              {TOKEN_ENV} is not set; export it in the shell (there is no token argument)")
        return 2
    runner = Runner(args.zone, args.api_host, dry_run=args.dry_run, verify=args.verify, geoblock=args.geoblock_ch)
    code = runner.run()
    mode = "verify" if args.verify else ("dry-run" if args.dry_run else "apply")
    print(f"{'FAIL' if code else 'ok':<5} {'summary':<18} {mode}: {runner.failed} failed")
    return code


if __name__ == "__main__":
    sys.exit(main())
