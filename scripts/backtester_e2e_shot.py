"""One-shot E2E check for the Backtester page: fill wallet, run, screenshot results.

Run while the app is listening (default http://127.0.0.1:8503). Reuses the
system Chrome/Edge discovery from visual_smoke.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from visual_smoke import DEFAULT_BASE_URL, chrome_executable  # noqa: E402

DEFAULT_WALLET = "0x204f72f35326db932158cba6adff0b9a1da95e14"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--wallet", default=DEFAULT_WALLET)
    parser.add_argument("--output", default="artifacts/visual_smoke/backtester_results.png")
    parser.add_argument("--timeout", type=int, default=120_000)
    args = parser.parse_args()

    chrome = chrome_executable()
    if not chrome:
        print("No local Chrome/Edge found", file=sys.stderr)
        return 2

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chrome, headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1400})
        page.goto(f"{args.base_url}/backtester", wait_until="domcontentloaded", timeout=args.timeout)
        page.wait_for_selector("input[aria-label='Wallet address']", timeout=args.timeout)
        page.fill("input[aria-label='Wallet address']", args.wallet)
        page.get_by_text("RUN BACKTEST").click()
        page.wait_for_selector("[data-testid='stMetric']", timeout=args.timeout)
        page.wait_for_timeout(3_000)
        page.screenshot(path=str(output), full_page=False)
        metrics = page.locator("[data-testid='stMetric']").count()
        body = page.locator("body").inner_text()
        ok = metrics >= 6 and "Trade log" in body.casefold().replace("trade log", "Trade log")
        print(f"metrics: {metrics}; screenshot: {output}")
        browser.close()
        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
