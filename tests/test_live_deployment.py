import unittest

from scripts.check_live_deployment import evaluate


class DeploymentCheckTests(unittest.TestCase):
    def check(self, status=200, body=None, headers=None, age=60):
        if body is None:
            body = b'{"ok":true,"commit":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}'
        return evaluate(status, headers or {}, body, "a" * 40, age, 20)

    def test_current_commit_runs_smoke(self):
        self.assertEqual(self.check()[0], "current")

    def test_challenge_is_never_reported_as_stale_or_grace(self):
        for age in (1, 60):
            state, message = self.check(403, b'<html>challenge</html>',
                                       {"cf-mitigated": "challenge", "cf-ray": "example"}, age)
            self.assertEqual(state, "error")
            self.assertIn("403", message)
            self.assertIn("Cloudflare", message)

    def test_recent_valid_old_commit_gets_grace_but_old_main_fails(self):
        old = b'{"ok":true,"commit":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}'
        self.assertEqual(self.check(body=old, age=1)[0], "deploying")
        self.assertEqual(self.check(body=old, age=20)[0], "error")

    def test_bad_health_is_an_error_even_during_grace(self):
        for body in (b'{}', b'[]', b'not json', b'{"ok":false,"commit":"abc"}',
                     b'{"ok":true,"commit":42}'):
            self.assertEqual(self.check(body=body, age=1)[0], "error")

    def test_network_and_origin_failures_are_distinct(self):
        self.assertIn("network", self.check(status=0, body=b'timed out')[1].lower())
        self.assertIn("502", self.check(status=502, body=b'bad gateway')[1])
