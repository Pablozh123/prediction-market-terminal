"""scripts/cloudflare_zone_setup.py: payloads, the update-or-create decision and the dry-run guard.

The script keeps its HTTP in one function (_call); these tests replace it with
an in-memory fake, so nothing here touches the network or needs a token.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "cloudflare_zone_setup.py"
TOKEN = "test-token-that-must-never-be-printed"


def _load_module():
    spec = importlib.util.spec_from_file_location("cloudflare_zone_setup", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


cf = _load_module()
ZONE = {"id": "zone123", "name": "marketintel.dev", "status": "active", "plan": {"legacy_id": "free"}}
GOOD_SETTINGS = {"ssl": "strict", "min_tls_version": "1.2", "always_use_https": "on", "browser_cache_ttl": 0}


class FakeApi:
    """Stands in for _call: answers reads from a small state and records every call."""

    def __init__(self, *, zone=ZONE, settings=None, fight_mode=False, rulesets=None, fail_on=()):
        self.zone = zone
        self.settings = dict(settings or {})
        self.fight_mode = fight_mode
        self.rulesets = {phase: json.loads(json.dumps(ruleset)) for phase, ruleset in (rulesets or {}).items()}
        self.fail_on = set(fail_on)
        self.calls: list[tuple[str, str, dict | None]] = []

    def writes(self):
        return [call for call in self.calls if call[0] != "GET"]

    def __call__(self, method, path, body=None):
        self.calls.append((method, path, body))
        if (method, path) in self.fail_on:
            raise cf.ApiError(400, "1004: simulated failure")
        if method == "GET" and path.startswith("/zones?name="):
            return {"success": True, "result": [self.zone]}
        if "/settings/" in path:
            setting = path.rsplit("/", 1)[1]
            if method == "PATCH":
                self.settings[setting] = body["value"]
            return {"success": True, "result": {"id": setting, "value": self.settings.get(setting)}}
        if path.endswith("/bot_management"):
            if method == "PUT":
                self.fight_mode = body["fight_mode"]
            return {"success": True, "result": {"fight_mode": self.fight_mode}}
        if "/rulesets/phases/" in path and method == "GET":
            phase = path.split("/phases/")[1].split("/")[0]
            if phase not in self.rulesets:
                raise cf.ApiError(404, "10007: could not find the entry point ruleset")
            return {"success": True, "result": self.rulesets[phase]}
        if path == "/zones/zone123/rulesets" and method == "POST":
            rules = [dict(rule, id=f"r-{index}") for index, rule in enumerate(body["rules"])]
            self.rulesets[body["phase"]] = {"id": "rs-" + body["phase"], "phase": body["phase"], "rules": rules}
            return {"success": True, "result": self.rulesets[body["phase"]]}
        if "/rules" in path and method in ("POST", "PATCH"):
            ruleset_id = path.split("/rulesets/")[1].split("/")[0]
            ruleset = next(entry for entry in self.rulesets.values() if entry["id"] == ruleset_id)
            if method == "POST":
                ruleset["rules"].append(dict(body, id=f"r-new-{len(ruleset['rules'])}"))
            else:
                rule_id = path.rsplit("/", 1)[1]
                ruleset["rules"] = [dict(body, id=rule_id) if r["id"] == rule_id else r for r in ruleset["rules"]]
            return {"success": True, "result": ruleset}
        raise AssertionError(f"unexpected call {method} {path}")


def _run(args, fake):
    out = io.StringIO()
    with mock.patch.dict(os.environ, {cf.TOKEN_ENV: TOKEN}), mock.patch.object(cf, "_call", fake), \
            contextlib.redirect_stdout(out):
        code = cf.main(args)
    return code, out.getvalue()


class PayloadTests(unittest.TestCase):
    def test_settings_map(self):
        self.assertEqual(cf.SETTINGS, GOOD_SETTINGS)
        self.assertIs(type(cf.SETTINGS["browser_cache_ttl"]), int)  # 0 = Respect Existing Headers, not "0"

    def test_rate_limit_rule_on_the_free_plan_keys_on_the_path_only(self):
        rule = cf.rate_limit_rule("api.marketintel.dev", host_field_available=False)
        self.assertEqual(rule["expression"], '(starts_with(http.request.uri.path, "/api/"))')
        self.assertEqual(rule["action"], "block")
        self.assertTrue(rule["enabled"])
        self.assertEqual(rule["description"], cf.RATE_LIMIT_DESCRIPTION)
        self.assertEqual(rule["ratelimit"], {
            "characteristics": ["cf.colo.id", "ip.src"],
            "period": 10,
            "requests_per_period": 60,
            "mitigation_timeout": 10,
        })
        self.assertNotIn("action_parameters", rule)

    def test_rate_limit_rule_on_a_paid_plan_names_the_api_host(self):
        rule = cf.rate_limit_rule("api.marketintel.dev", host_field_available=True)
        self.assertEqual(
            rule["expression"],
            '(http.host eq "api.marketintel.dev" and starts_with(http.request.uri.path, "/api/"))',
        )

    def test_redirect_rule(self):
        rule = cf.redirect_rule("marketintel.dev")
        self.assertEqual(rule["expression"], '(http.host eq "www.marketintel.dev")')
        self.assertEqual(rule["action"], "redirect")
        self.assertEqual(rule["action_parameters"], {"from_value": {
            "status_code": 301,
            "target_url": {"expression": 'concat("https://marketintel.dev", http.request.uri.path)'},
            "preserve_query_string": True,
        }})

    def test_country_block_rule(self):
        rule = cf.country_block_rule("CH")
        self.assertEqual(rule["expression"], '(ip.src.country eq "CH")')
        self.assertEqual(rule["action"], "block")
        self.assertTrue(rule["enabled"])
        self.assertEqual(rule["description"], cf.GEOBLOCK_DESCRIPTION)

    def test_new_ruleset_wraps_the_rule_as_a_zone_entry_point(self):
        rule = cf.country_block_rule()
        ruleset = cf.new_ruleset(cf.PHASE_CUSTOM, rule)
        self.assertEqual(ruleset["kind"], "zone")
        self.assertEqual(ruleset["phase"], "http_request_firewall_custom")
        self.assertEqual(ruleset["rules"], [rule])
        self.assertTrue(ruleset["name"])

    def test_descriptions_are_distinct_and_payloads_serialise(self):
        rules = [cf.rate_limit_rule("api.example.org", False), cf.redirect_rule("example.org"), cf.country_block_rule()]
        self.assertEqual(len({rule["description"] for rule in rules}), 3)
        for rule in rules:
            json.dumps(rule)


class DecisionTests(unittest.TestCase):
    def setUp(self):
        self.wanted = cf.redirect_rule("marketintel.dev")

    def test_absent_rule_is_created(self):
        other = {"id": "r0", "description": "something else", "expression": "true", "action": "skip"}
        self.assertEqual(cf.plan_rule([other], self.wanted), ("create", None))
        self.assertEqual(cf.plan_rule([], self.wanted), ("create", None))

    def test_rule_with_the_same_description_is_updated_not_duplicated(self):
        stale = dict(self.wanted, id="r1", expression='(http.host eq "www.old.example")')
        self.assertEqual(cf.plan_rule([stale], self.wanted), ("update", "r1"))

    def test_disabled_copy_is_updated(self):
        disabled = dict(self.wanted, id="r1", enabled=False)
        self.assertEqual(cf.plan_rule([disabled], self.wanted), ("update", "r1"))

    def test_identical_server_copy_is_skipped_despite_extra_fields(self):
        server_copy = dict(self.wanted, id="r1", version="3", last_updated="2026-09-04T10:00:00Z", ref="r1",
                           logging={"enabled": True})
        self.assertEqual(cf.plan_rule([server_copy], self.wanted), ("skip", "r1"))

    def test_characteristics_order_does_not_matter(self):
        wanted = cf.rate_limit_rule("api.marketintel.dev", False)
        server_copy = json.loads(json.dumps(wanted))
        server_copy["id"] = "r7"
        server_copy["ratelimit"]["characteristics"] = ["ip.src", "cf.colo.id"]
        server_copy["ratelimit"]["requests_to_origin"] = False
        self.assertEqual(cf.plan_rule([server_copy], wanted), ("skip", "r7"))
        server_copy["ratelimit"]["requests_per_period"] = 100
        self.assertEqual(cf.plan_rule([server_copy], wanted), ("update", "r7"))


class DryRunTests(unittest.TestCase):
    def test_dry_run_sends_nothing_but_the_zone_lookup(self):
        fake = FakeApi()
        code, out = _run(["--dry-run", "--geoblock-ch"], fake)
        self.assertEqual(code, 0, out)
        self.assertEqual([(method, path) for method, path, _ in fake.calls], [("GET", "/zones?name=marketintel.dev")])
        self.assertEqual(fake.writes(), [])
        for text in (
            "PATCH /zones/zone123/settings/ssl",
            '{"value": "strict"}',
            "PATCH /zones/zone123/settings/browser_cache_ttl",
            '{"value": 0}',
            "PUT /zones/zone123/bot_management",
            '{"fight_mode": true}',
            "http_ratelimit",
            "http_request_dynamic_redirect",
            "http_request_firewall_custom",
            '(ip.src.country eq \\"CH\\")',
            "POST /zones/zone123/rulesets",
        ):
            self.assertIn(text, out)
        self.assertNotIn(TOKEN, out)
        self.assertNotIn("FAIL", out)

    def test_dry_run_without_the_flag_leaves_the_geoblock_out(self):
        fake = FakeApi()
        code, out = _run(["--dry-run"], fake)
        self.assertEqual(code, 0)
        self.assertNotIn("ip.src.country", out)
        self.assertIn("skip  geoblock CH", out)

    def test_paid_plan_adds_the_host_clause(self):
        zone = dict(ZONE, plan={"legacy_id": "pro"})
        code, out = _run(["--dry-run"], FakeApi(zone=zone))
        self.assertEqual(code, 0)
        self.assertIn('http.host eq \\"api.marketintel.dev\\"', out)

    def test_missing_token_is_a_usage_error_without_any_call(self):
        fake = FakeApi()
        out = io.StringIO()
        with mock.patch.dict(os.environ), mock.patch.object(cf, "_call", fake), contextlib.redirect_stdout(out):
            os.environ.pop(cf.TOKEN_ENV, None)
            code = cf.main(["--dry-run"])
        self.assertEqual(code, 2)
        self.assertEqual(fake.calls, [])
        self.assertIn(cf.TOKEN_ENV, out.getvalue())


class ApplyTests(unittest.TestCase):
    def _fake(self, **overrides):
        stale_redirect = dict(cf.redirect_rule("marketintel.dev"), id="r1", expression='(http.host eq "www.old")')
        foreign = {"id": "r9", "description": "allow the office", "expression": "(ip.src eq 203.0.113.9)",
                   "action": "skip"}
        state = {
            "settings": {"ssl": "full", "min_tls_version": "1.0", "always_use_https": "on", "browser_cache_ttl": 14400},
            "fight_mode": False,
            "rulesets": {
                cf.PHASE_REDIRECT: {"id": "rs-redirect", "rules": [stale_redirect]},
                cf.PHASE_CUSTOM: {"id": "rs-custom", "rules": [foreign]},
            },
        }
        state.update(overrides)
        return FakeApi(**state)

    def test_reads_before_it_writes_and_updates_by_description(self):
        fake = self._fake()
        code, out = _run(["--geoblock-ch"], fake)
        self.assertEqual(code, 0, out)
        writes = [(method, path) for method, path, _ in fake.writes()]
        self.assertEqual(writes, [
            ("PATCH", "/zones/zone123/settings/ssl"),
            ("PATCH", "/zones/zone123/settings/min_tls_version"),
            ("PATCH", "/zones/zone123/settings/browser_cache_ttl"),
            ("PUT", "/zones/zone123/bot_management"),
            ("POST", "/zones/zone123/rulesets"),
            ("PATCH", "/zones/zone123/rulesets/rs-redirect/rules/r1"),
            ("POST", "/zones/zone123/rulesets/rs-custom/rules"),
        ])
        bodies = {path: body for _, path, body in fake.writes()}
        self.assertEqual(bodies["/zones/zone123/settings/ssl"], {"value": "strict"})
        self.assertEqual(bodies["/zones/zone123/bot_management"], {"fight_mode": True})
        created = bodies["/zones/zone123/rulesets"]
        self.assertEqual((created["kind"], created["phase"]), ("zone", cf.PHASE_RATELIMIT))
        self.assertEqual(created["rules"][0]["ratelimit"]["requests_per_period"], 60)
        self.assertEqual(bodies["/zones/zone123/rulesets/rs-redirect/rules/r1"], cf.redirect_rule("marketintel.dev"))
        self.assertEqual(bodies["/zones/zone123/rulesets/rs-custom/rules"], cf.country_block_rule("CH"))
        self.assertIn("skip  always_use_https", out)
        self.assertEqual(len(fake.rulesets[cf.PHASE_CUSTOM]["rules"]), 2)  # the foreign rule survived

    def test_second_run_changes_nothing(self):
        fake = self._fake()
        _run(["--geoblock-ch"], fake)
        writes_after_first_run = len(fake.writes())
        code, out = _run(["--geoblock-ch"], fake)
        self.assertEqual(code, 0, out)
        self.assertEqual(len(fake.writes()), writes_after_first_run)
        self.assertEqual(out.count("skip "), 8, out)  # four settings, bot fight mode, three rules

    def test_a_failed_step_does_not_stop_the_others(self):
        fake = self._fake(fail_on=[("PATCH", "/zones/zone123/settings/ssl")])
        code, out = _run([], fake)
        self.assertEqual(code, 1)
        self.assertIn("FAIL  ssl", out)
        self.assertIn("simulated failure", out)
        self.assertIn(("PUT", "/zones/zone123/bot_management", {"fight_mode": True}), fake.calls)
        self.assertIn("FAIL  summary", out)

    def test_without_the_flag_the_geoblock_is_never_created(self):
        fake = self._fake()
        code, out = _run([], fake)
        self.assertEqual(code, 0)
        self.assertNotIn(("POST", "/zones/zone123/rulesets/rs-custom/rules"), [(m, p) for m, p, _ in fake.calls])
        self.assertIn("skip  geoblock CH", out)

    def test_rate_limit_slot_taken_by_another_rule_reports_a_hint(self):
        taken = {"id": "rs-rl", "rules": [{"id": "x", "description": "my own limiter", "expression": "true",
                                           "action": "block"}]}
        fake = self._fake(rulesets={cf.PHASE_RATELIMIT: taken},
                          fail_on=[("POST", "/zones/zone123/rulesets/rs-rl/rules")])
        code, out = _run([], fake)
        self.assertEqual(code, 1)
        self.assertIn("FAIL  rate limit", out)
        self.assertIn("'my own limiter'", out)


class VerifyTests(unittest.TestCase):
    def test_verify_only_reads_and_flags_differences(self):
        fake = FakeApi(settings=dict(GOOD_SETTINGS, ssl="full"), fight_mode=True)
        code, out = _run(["--verify"], fake)
        self.assertEqual(code, 1)
        self.assertEqual(fake.writes(), [])
        self.assertIn("FAIL  ssl", out)
        self.assertIn("ok    min_tls_version", out)
        self.assertIn("ok    bot fight mode", out)
        self.assertIn("FAIL  rate limit", out)
        self.assertIn("skip  geoblock CH", out)  # optional, not requested

    def test_verify_passes_on_a_finished_zone(self):
        rulesets = {
            cf.PHASE_RATELIMIT: {"id": "a", "rules": [dict(cf.rate_limit_rule("api.marketintel.dev", False), id="1")]},
            cf.PHASE_REDIRECT: {"id": "b", "rules": [dict(cf.redirect_rule("marketintel.dev"), id="2")]},
            cf.PHASE_CUSTOM: {"id": "c", "rules": [dict(cf.country_block_rule("CH"), id="3", enabled=False)]},
        }
        fake = FakeApi(settings=GOOD_SETTINGS, fight_mode=True, rulesets=rulesets)
        code, out = _run(["--verify"], fake)
        self.assertEqual(code, 0, out)
        self.assertIn("ok    geoblock CH        present but not in the script's form", out)
        code, out = _run(["--verify", "--geoblock-ch"], fake)
        self.assertEqual(code, 1)
        self.assertIn("FAIL  geoblock CH", out)
        self.assertEqual(fake.writes(), [])


if __name__ == "__main__":
    unittest.main()
