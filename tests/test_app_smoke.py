"""Headless smoke test for the Streamlit app.

Uses streamlit's AppTest to execute the full app script for each page and
asserts no uncaught exception. Network-dependent and slow (~1-3 min), so it is
gated behind the RUN_APP_SMOKE env var and skipped in the fast unit run:

    RUN_APP_SMOKE=1 python -m unittest tests.test_app_smoke -v

Data fetches are wrapped in the app's ``safe_load`` fallbacks, so the smoke
asserts "the page renders without crashing" even when the public APIs are
unreachable.
"""

import os
import unittest
from pathlib import Path

APP = str(Path(__file__).resolve().parents[1] / "prediction_terminal.py")

PAGE_SLUGS = [
    "overview",
    "search",
    "markets",
    "traders",
    "track",
    "live-trades",
    "wallets",
    "backtester",
    "copy-trade",
    "whale-flow",
    "suspicious",
    "cross-venue",
    "monitor",
    "resolved",
    "portfolio",
    "settings",
]


@unittest.skipUnless(
    os.environ.get("RUN_APP_SMOKE"),
    "set RUN_APP_SMOKE=1 to run the (network-dependent) Streamlit AppTest smoke",
)
class AppSmokeTests(unittest.TestCase):
    def test_every_page_loads_without_exception(self) -> None:
        from streamlit.testing.v1 import AppTest

        for slug in PAGE_SLUGS:
            with self.subTest(page=slug):
                app = AppTest.from_file(APP, default_timeout=60)
                app.query_params["page"] = slug
                app.run()
                self.assertFalse(bool(app.exception), f"{slug}: {app.exception}")


FAKE_AUTH_SECRETS = {
    "redirect_uri": "http://localhost:8503/oauth2callback",
    "cookie_secret": "smoke-test-secret",
    "client_id": "smoke-client-id",
    "client_secret": "smoke-client-secret",
    "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration",
}


@unittest.skipUnless(
    os.environ.get("RUN_APP_SMOKE"),
    "set RUN_APP_SMOKE=1 to run the (network-dependent) Streamlit AppTest smoke",
)
class AuthGateSmokeTests(unittest.TestCase):
    """Settings admin gate: open without [auth] secrets, fail-closed with them."""

    def _run_settings(self, with_auth_secrets: bool):
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file(APP, default_timeout=60)
        app.query_params["page"] = "settings"
        if with_auth_secrets:
            app.secrets["auth"] = dict(FAKE_AUTH_SECRETS)
        app.run()
        self.assertFalse(bool(app.exception), str(app.exception))
        return app

    def test_settings_open_in_local_mode_without_auth_secrets(self) -> None:
        app = self._run_settings(with_auth_secrets=False)
        self.assertTrue(len(app.slider) > 0, "settings widgets should render in open mode")
        markdown_text = " ".join(str(block.value) for block in app.markdown)
        self.assertNotIn("Admin access required", markdown_text)
        button_keys = {getattr(button, "key", "") for button in app.button}
        self.assertNotIn("sidebar_sign_in", button_keys, "no sign-in surface without auth secrets")

    def test_settings_fail_closed_with_auth_secrets_and_anonymous_user(self) -> None:
        app = self._run_settings(with_auth_secrets=True)
        self.assertEqual(len(app.slider), 0, "settings widgets must stay hidden behind the gate")
        markdown_text = " ".join(str(block.value) for block in app.markdown)
        self.assertIn("Admin access required", markdown_text)
        button_keys = {getattr(button, "key", "") for button in app.button}
        self.assertIn("settings_sign_in", button_keys)
        self.assertIn("sidebar_sign_in", button_keys)


if __name__ == "__main__":
    unittest.main()
