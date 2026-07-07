"""Visual smoke-check for the local Streamlit app.

Run this while the app is already listening on the configured base URL. The
check launches a local Chromium-compatible browser, verifies key route text,
captures screenshots, and rejects blank or traceback pages.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageStat
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import Page
from playwright.sync_api import sync_playwright


DEFAULT_BASE_URL = "http://127.0.0.1:8503"
DEFAULT_OUTPUT_DIR = Path("artifacts/visual_smoke")
DEFAULT_CHROME_PATHS = [
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
]


@dataclass(frozen=True)
class RouteCheck:
    route: str
    required_text: tuple[str, ...]
    screenshot_name: str


ROUTES = [
    RouteCheck("/", ("Read the market", "Copy Trade"), "overview.png"),
    RouteCheck("/markets", ("Markets", "Search markets"), "markets.png"),
    RouteCheck("/traders", ("Traders", "Leaderboard"), "traders.png"),
    RouteCheck("/track", ("Track", "Wallet to track"), "track.png"),
    RouteCheck("/live-trades", ("Live Trades", "Trade tape"), "live_trades.png"),
    RouteCheck("/monitor", ("Monitor", "Signal"), "monitor.png"),
    RouteCheck("/portfolio", ("Portfolio", "Marked value"), "portfolio.png"),
    RouteCheck("/backtester", ("Backtester", "RUN BACKTEST"), "backtester.png"),
    RouteCheck("/suspicious", ("Suspicious", "not legal findings"), "suspicious.png"),
    RouteCheck("/settings", ("Settings", "Backtester defaults"), "settings.png"),
    RouteCheck("/copy-trade", ("Copy Trade", "Paper mode only"), "copy_trade.png"),
]


def chrome_executable(explicit: str | None = None) -> str | None:
    if explicit:
        path = Path(explicit)
        return str(path) if path.exists() else explicit
    for path in DEFAULT_CHROME_PATHS:
        if path.exists():
            return str(path)
    return None


def screenshot_is_nonblank(path: Path) -> bool:
    with Image.open(path) as image:
        image = image.convert("RGB")
        stat = ImageStat.Stat(image)
        extrema = image.getextrema()
        spread = sum(high - low for low, high in extrema)
        brightness = sum(stat.mean) / len(stat.mean)
        return spread > 15 and brightness > 2


def route_url(base_url: str, route: str) -> str:
    return f"{base_url.rstrip('/')}{route if route.startswith('/') else '/' + route}"


def visible_text_contains(body_text: str, expected: str) -> bool:
    return expected.casefold() in body_text.casefold()


def wait_for_streamlit(page: Page, timeout_ms: int) -> None:
    page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    page.wait_for_selector("[data-testid='stAppViewContainer'], .stApp", timeout=timeout_ms)


def wait_for_required_text(page: Page, required_text: tuple[str, ...], timeout_ms: int) -> None:
    page.wait_for_function(
        """(texts) => {
          const body = document.body ? document.body.innerText.toLocaleLowerCase() : "";
          return texts.every((text) => body.includes(String(text).toLocaleLowerCase()));
        }""",
        arg=list(required_text),
        timeout=timeout_ms,
    )


def select_routes(requested_routes: list[str] | None) -> list[RouteCheck]:
    if not requested_routes:
        return ROUTES

    routes_by_path = {route.route: route for route in ROUTES}
    selected: list[RouteCheck] = []
    unknown: list[str] = []
    for requested in requested_routes:
        route_path = requested if requested.startswith("/") else f"/{requested}"
        route = routes_by_path.get(route_path)
        if route:
            selected.append(route)
        else:
            unknown.append(route_path)
    if unknown:
        known = ", ".join(route.route for route in ROUTES)
        raise ValueError(f"Unknown route(s): {', '.join(unknown)}. Known routes: {known}")
    return selected


def check_route(page: Page, base_url: str, output_dir: Path, route: RouteCheck, timeout_ms: int) -> list[str]:
    errors: list[str] = []
    url = route_url(base_url, route.route)
    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    wait_for_streamlit(page, timeout_ms)
    try:
        wait_for_required_text(page, route.required_text, timeout_ms)
    except PlaywrightTimeoutError:
        pass
    body_text = page.locator("body").inner_text(timeout=timeout_ms)
    bad_markers = ["Traceback", "ModuleNotFoundError", "NameError:", "SyntaxError:", "RuntimeError:"]
    for marker in bad_markers:
        if marker in body_text:
            errors.append(f"{route.route}: found error marker {marker!r}")
    for text in route.required_text:
        if not visible_text_contains(body_text, text):
            errors.append(f"{route.route}: missing visible text {text!r}")
    screenshot_path = output_dir / route.screenshot_name
    page.screenshot(path=str(screenshot_path), full_page=False)
    if not screenshot_is_nonblank(screenshot_path):
        errors.append(f"{route.route}: screenshot appears blank ({screenshot_path})")
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Visual smoke-check local Prediction Market Terminal routes.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--chrome", default=None, help="Optional chrome.exe/msedge.exe path.")
    parser.add_argument("--timeout-ms", type=int, default=60000)
    parser.add_argument("--fail-console", action="store_true", help="Fail on browser console errors.")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument(
        "--route",
        action="append",
        dest="routes",
        help="Run only one known route. Repeat for multiple routes, for example --route / --route /markets.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    executable = chrome_executable(args.chrome)
    failures: list[str] = []
    console_errors: list[str] = []
    try:
        routes = select_routes(args.routes)
    except ValueError as exc:
        print(exc)
        return 2

    try:
        with sync_playwright() as playwright:
            launch_kwargs = {"headless": not bool(args.headed), "args": ["--disable-gpu", "--no-sandbox"]}
            if executable:
                launch_kwargs["executable_path"] = executable
            browser = playwright.chromium.launch(**launch_kwargs)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            for route in routes:
                print(f"Checking {route.route} ...", flush=True)
                route_failures = check_route(page, str(args.base_url), output_dir, route, int(args.timeout_ms))
                failures.extend(route_failures)
                if route_failures:
                    print(f"FAIL {route.route}", flush=True)
                else:
                    print(f"OK {route.route}", flush=True)
            browser.close()
    except PlaywrightTimeoutError as exc:
        failures.append(f"timeout: {exc}")
    except PlaywrightError as exc:
        failures.append(f"playwright error: {exc}")

    noisy_console = [
        item
        for item in console_errors
        if "favicon" not in item.lower() and "websocket" not in item.lower() and "ResizeObserver" not in item
    ]
    if noisy_console and bool(args.fail_console):
        failures.extend(f"console error: {item[:300]}" for item in noisy_console[:5])

    if failures:
        print("Visual smoke failed:")
        for failure in failures:
            print(f"- {failure}")
        print(f"Screenshots: {output_dir.resolve()}")
        return 1

    print(f"Visual smoke passed for {len(routes)} routes.")
    print(f"Screenshots: {output_dir.resolve()}")
    if executable:
        print(f"Browser: {executable}")
    else:
        print("Browser: Playwright bundled Chromium")
    return 0


if __name__ == "__main__":
    sys.exit(main())
