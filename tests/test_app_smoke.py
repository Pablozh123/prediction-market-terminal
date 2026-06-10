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
    "picks",
    "track",
    "live-trades",
    "wallets",
    "backtester",
    "copy-trade",
    "whale-flow",
    "cross-venue",
    "monitor",
    "alerts",
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


if __name__ == "__main__":
    unittest.main()
