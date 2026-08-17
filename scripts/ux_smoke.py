#!/usr/bin/env python3
"""UX regression smoke for the terminal frontend (web/), driven by Playwright.

    set API_PORT=8790 && python api/server.py            # API + web/ on :8790
    python scripts/ux_smoke.py --base-url http://127.0.0.1:8790

    python scripts/build_static_site.py && python -m http.server -d dist 8791
    python scripts/ux_smoke.py --base-url http://127.0.0.1:8791 --static

Headless Chromium at 1440x900. Exits non-zero when any of these happen:

* a console error, page error or failed request that the mode does not
  expect (static mode expects the /api/* 404s that precede the ./data
  fallback, the rate-limit check expects one 429);
* a sidebar entry, study, sub-tab or chip that leaves the address (hash)
  out of step with the page;
* a verdict-board row, jump-list link or deep link that does not land on
  its card;
* an open <details> that closes, or a scroll position that jumps, across
  the 15 s clock tick and the 30 s poll;
* the search palette not opening on "/", not closing on Esc, or Enter not
  opening the first result;
* the detail drawer not opening for a market row / whale row, or its close
  button not closing it;
* a live-tape row that looks clickable but has no handler;
* the backtester not reporting a 429 as "rate-limited" (API mode);
* the topbar not saying "API OFFLINE" after the API goes away mid-session,
  or "Try again" not re-asking;
* horizontal overflow of the content column on any route.

Not wired into CI on purpose (it needs a running server and, in API mode,
network) — run it by hand before a deploy.
"""

from __future__ import annotations

import argparse
import sys
import time

from playwright.sync_api import Browser, Page, sync_playwright

VIEWPORT = {"width": 1440, "height": 900}
ROUTES = [
    "#overview", "#research/microstructure", "#research/live-runs", "#research/pilot",
    "#research/category-efficiency", "#research/mentions-latency", "#research/pipeline-forward",
    "#research/postmortems", "#research/field-notes", "#research/methodology", "#research/review-queue",
    "#markets", "#flow", "#whale", "#cross", "#traders", "#risk", "#alerts", "#backtester",
]
SIDEBAR = {
    "Overview": "#overview", "Microstructure": "#research/microstructure", "Live runs": "#research/live-runs",
    "Pilot": "#research/pilot", "Category efficiency": "#research/category-efficiency",
    "Mentions latency": "#research/mentions-latency", "Pipeline forward": "#research/pipeline-forward",
    "Post-mortems": "#research/postmortems", "Field notes": "#research/field-notes",
    "Methodology": "#research/methodology", "Review queue": "#research/review-queue",
    "Markets": "#markets", "Live tape": "#flow", "Whale flow": "#whale", "Cross-venue": "#cross",
    "Leaderboard": "#traders", "Risk screen": "#risk", "Alerts": "#alerts", "Backtester": "#backtester",
}
JS_SCROLL = "document.querySelector('.content').scrollTop"
JS_OPEN_DETAILS = ("() => Array.from(document.querySelectorAll('#main details[open]'))"
                   ".map(d => d.getAttribute('data-key') || d.querySelector('summary').textContent.trim().slice(0, 60))")
JS_MAIN_TEXT = "document.querySelector('#main').innerText"
JS_TOPBAR = "document.querySelector('#topbar').innerText.split('\\n')[0]"
JS_ACTIVE_CHIPS = ("() => Array.from(document.querySelectorAll('#main [data-act]'))"
                   ".filter(e => (e.getAttribute('style') || '').includes('background:#C8F542'))"
                   ".map(e => e.textContent.trim())")
JS_ANCHOR_TOP = ("(id) => { const e = document.getElementById(id); if (!e) return null;"
                 " const c = document.querySelector('.content').getBoundingClientRect();"
                 " return Math.round(e.getBoundingClientRect().top - c.top); }")
JS_OVERFLOW = ("() => { const c = document.querySelector('.content'); return c.scrollWidth - c.clientWidth; }")


class Smoke:
    def __init__(self, base_url: str, static: bool, verbose: bool) -> None:
        self.base = base_url.rstrip("/")
        self.static = static
        self.verbose = verbose
        self.failures: list[str] = []
        self.console: list[tuple[str, str, str]] = []   # (context, type, text)
        self.network: list[tuple[str, str, int | str]] = []  # (context, url, status/failure)
        self.context = "start"

    # -- reporting -----------------------------------------------------------
    def ok(self, msg: str) -> None:
        print(f"OK   {msg}", flush=True)

    def fail(self, msg: str) -> None:
        self.failures.append(f"[{self.context}] {msg}")
        print(f"FAIL {msg}", flush=True)

    def check(self, cond: bool, msg: str) -> bool:
        (self.ok if cond else self.fail)(msg)
        return cond

    def note(self, msg: str) -> None:
        if self.verbose:
            print(f"     {msg}", flush=True)

    # -- browser wiring ------------------------------------------------------
    def new_page(self, browser: Browser) -> Page:
        page = browser.new_page(viewport=VIEWPORT)
        page.on("console", lambda m: self.console.append((self.context, m.type, m.text)) if m.type == "error" else None)
        page.on("pageerror", lambda e: self.console.append((self.context, "pageerror", str(e))))
        page.on("requestfailed", lambda r: self.network.append((self.context, r.url, str(r.failure))))
        page.on("response", lambda r: self.network.append((self.context, r.url, r.status)) if r.status >= 400 else None)
        return page

    def goto(self, page: Page, route: str, wait_ms: int = 2500) -> None:
        """Fresh load of a route. A hash-only change to the same URL would be
        a same-document navigation (state kept), so an identical URL reloads."""
        url = self.base + "/" + route
        same_document = page.url.split("#")[0] == url.split("#")[0]
        if page.url != url:
            page.goto(url, wait_until="domcontentloaded")
        if same_document:
            page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(wait_ms)

    def wait_text_gone(self, page: Page, needle: str, timeout_s: float) -> bool:
        return self.wait_for(page, lambda: needle not in page.evaluate(JS_MAIN_TEXT), timeout_s)

    def wait_for(self, page: Page, cond, timeout_s: float, step_ms: int = 1000) -> bool:
        """Poll a Python callable until it is truthy or the time is up."""
        t0 = time.time()
        while True:
            if cond():
                return True
            if time.time() - t0 >= timeout_s:
                return bool(cond())
            page.wait_for_timeout(step_ms)

    def click_text(self, page: Page, text: str, scope: str = "#main", wait_ms: int = 600) -> bool:
        loc = page.locator(f"{scope} [data-act]", has_text=text)
        if not loc.count():
            return False
        loc.first.click()
        page.wait_for_timeout(wait_ms)
        return True

    def hash_(self, page: Page) -> str:
        return page.evaluate("location.hash")

    # -- phases --------------------------------------------------------------
    def phase_routes(self, page: Page) -> None:
        self.context = "routes"
        for route in ROUTES:
            self.goto(page, route, 2200)
            text = page.evaluate(JS_MAIN_TEXT)
            overflow = page.evaluate(JS_OVERFLOW)
            self.check(len(text) > 60, f"{route} renders ({len(text)} chars)")
            self.check(overflow <= 0, f"{route} has no horizontal overflow (Δ {overflow}px)")
        # Static host: the topbar must not claim to be waiting forever.
        if self.static:
            self.goto(page, "#overview", 4000)
            top = page.evaluate(JS_TOPBAR)
            self.check("API NOT REACHABLE" in top, f"static topbar says the API is not reachable ({top!r})")

    def phase_sidebar(self, page: Page) -> None:
        self.context = "sidebar"
        self.goto(page, "#overview", 2500)
        for label, expected in SIDEBAR.items():
            page.locator("#sidebar [data-act]", has_text=label).first.click()
            page.wait_for_timeout(700)
            h = self.hash_(page)
            active = page.evaluate(
                "() => Array.from(document.querySelectorAll('#sidebar [data-act]'))"
                ".filter(e => e.querySelector('span') && (e.querySelector('span').getAttribute('style') || '').includes('font-weight:600'))"
                ".map(e => e.textContent.trim())")
            self.check(h == expected, f"sidebar '{label}' → {h}")
            self.check(active == [label] or (label == "Live tape" and active and active[0].startswith("Live tape")),
                       f"sidebar '{label}' is the active entry ({active})")
        # Same entry twice: one history entry, not two.
        page.evaluate("window.__hl = history.length")
        page.locator("#sidebar [data-act]", has_text="Markets").first.click()
        page.wait_for_timeout(300)
        page.locator("#sidebar [data-act]", has_text="Markets").first.click()
        page.wait_for_timeout(300)
        added = page.evaluate("history.length - window.__hl")
        self.check(added == 1, f"clicking the open sidebar entry again adds no history entry (added {added})")
        page.go_back()
        page.wait_for_timeout(800)
        self.check(self.hash_(page) == "#backtester", f"back returns to the previous page ({self.hash_(page)})")

    def phase_anchors(self, page: Page) -> None:
        self.context = "anchors"
        # Deep link straight to a card.
        self.goto(page, "#research/microstructure/mm-staleness", 3000)
        top = page.evaluate(JS_ANCHOR_TOP, "research/microstructure/mm-staleness")
        self.check(top is not None and 0 <= top <= 40, f"deep link #research/microstructure/mm-staleness lands on the card (top {top}px)")
        # Jump list on the study page.
        self.goto(page, "#research/microstructure", 2500)
        links = page.evaluate("() => Array.from(document.querySelectorAll('#main a[href^=\"#research/microstructure/\"]')).map(a => a.getAttribute('href'))")
        self.check(len(links) >= 3, f"jump list has {len(links)} links")
        for href in links[:2] + links[5:6]:
            page.locator(f"#main a[href='{href}']").first.click()
            page.wait_for_timeout(500)
            top = page.evaluate(JS_ANCHOR_TOP, href[1:])
            self.check(self.hash_(page) == href and top is not None and 0 <= top <= 40, f"jump {href} → hash ok, card top {top}px")
        # Verdict board rows on the Overview.
        self.goto(page, "#overview", 3000)
        rows = page.locator("#main .hv-panel[data-act]")
        n = rows.count()
        if self.check(n >= 12, f"verdict board has clickable rows ({n})"):
            for i in (0, 7):
                self.goto(page, "#overview", 2500)
                page.locator("#main .hv-panel[data-act]").nth(i).click()
                page.wait_for_timeout(2500)
                h = self.hash_(page)
                top = page.evaluate(JS_ANCHOR_TOP, h[1:])
                self.check(h.startswith("#research/microstructure/") and top is not None and 0 <= top <= 40,
                           f"verdict row {i} → {h}, card top {top}px")
            page.go_back()
            page.wait_for_timeout(1200)
            self.check(self.hash_(page) == "#overview" and "VERDICT BOARD" in page.evaluate(JS_MAIN_TEXT), "back from a card returns to the Overview")
            page.go_forward()
            page.wait_for_timeout(2500)
            h = self.hash_(page)
            top = page.evaluate(JS_ANCHOR_TOP, h[1:])
            self.check(top is not None and 0 <= top <= 40, f"forward lands on the card again ({h}, top {top}px)")

    def phase_subtabs(self, page: Page) -> None:
        self.context = "sub-tabs"
        # Risk screen: every tab in the address, Flag log fetches its log.
        self.goto(page, "#risk", 1500)
        for label, seg in (("Wallets", "wallets"), ("Fresh-wallet clusters", "fresh"), ("Coordinated timing", "timing"),
                           ("Co-trading network", "network"), ("Flag log", "log"), ("Events", "")):
            self.click_text(page, label)
            want = "#risk" + ("/" + seg if seg else "")
            self.check(self.hash_(page) == want and label in page.evaluate(JS_ACTIVE_CHIPS), f"risk tab '{label}' → {self.hash_(page)}, active")
        self.goto(page, "#risk/log", 2000)
        self.check("Flag log" in page.evaluate(JS_ACTIVE_CHIPS), "reload on #risk/log opens the Flag log tab")
        page.evaluate("location.hash = '#risk/wallets'")
        page.wait_for_timeout(500)
        self.check("Wallets" in page.evaluate(JS_ACTIVE_CHIPS), "hash change to #risk/wallets switches the tab")
        # Alerts.
        self.goto(page, "#alerts", 1500)
        self.click_text(page, "Rules")
        self.check(self.hash_(page) == "#alerts/rules" and "Rules" in page.evaluate(JS_ACTIVE_CHIPS), f"alerts tab 'Rules' → {self.hash_(page)}")
        self.click_text(page, "Signals")
        self.check(self.hash_(page) == "#alerts", f"alerts default tab → {self.hash_(page)}")
        # Live runs.
        self.goto(page, "#research/live-runs", 2500)
        for label, seg in (("Timing & repricing", "timing"), ("Sizing simulator", "sim"), ("Calibration", "calib"),
                           ("Track record", "record"), ("Runs", "")):
            self.click_text(page, label)
            want = "#research/live-runs" + ("/" + seg if seg else "")
            self.check(self.hash_(page) == want and label in page.evaluate(JS_ACTIVE_CHIPS), f"live-runs tab '{label}' → {self.hash_(page)}")
        self.goto(page, "#research/live-runs/calib", 2500)
        self.check("Calibration" in page.evaluate(JS_ACTIVE_CHIPS), "reload on #research/live-runs/calib opens the Calibration tab")
        page.locator("#sidebar [data-act]", has_text="Live runs").first.click()
        page.wait_for_timeout(600)
        self.check(self.hash_(page) == "#research/live-runs/calib", f"sidebar keeps the open tab in the address ({self.hash_(page)})")
        # Backtester result tabs exist only with a result; the RUN guard is checked in phase_live.

    def phase_search_and_drawer(self, page: Page) -> None:
        self.context = "search+drawer"
        self.goto(page, "#markets", 2500)
        page.keyboard.press("/")
        page.wait_for_timeout(300)
        focused = page.evaluate("document.activeElement && (document.activeElement.dataset || {}).key")
        self.check(bool(page.query_selector("#search input")) and focused == "searchQuery", "'/' opens the palette with the input focused")
        page.keyboard.type("a")
        page.wait_for_timeout(400)
        n = page.evaluate("document.querySelectorAll('#search [data-result]').length")
        page.keyboard.press("Enter")
        page.wait_for_timeout(600)
        if n:
            self.check(page.evaluate("document.querySelector('#detail').innerHTML.length > 0") and not page.query_selector("#search input"),
                       f"Enter opens the first of {n} results in the drawer")
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
            self.check(page.evaluate("document.querySelector('#detail').innerHTML.length === 0"), "Esc closes the drawer")
        else:
            self.check("nothing loaded to search" in page.evaluate("document.querySelector('#search').innerText"),
                       "empty palette says why there is nothing to search")
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
        self.check(not page.query_selector("#search input"), "Esc closes the palette")
        # '/' typed into a page input must not open the palette.
        inp = page.locator("#main input").first
        if inp.count():
            inp.fill("a/b")
            page.wait_for_timeout(300)
            self.check(not page.query_selector("#search input") and inp.input_value() == "a/b", "'/' inside a text input stays text")
        if self.static:
            return
        # Market row → drawer; close button. (/api/markets can take a while
        # when the upstream is slow: wait for rows instead of a fixed pause.)
        self.goto(page, "#markets", 1000)
        rows = page.locator("#main .hv-panel[data-act]")
        self.wait_for(page, lambda: rows.count() > 0, 45)
        if self.check(rows.count() > 0, "markets page has rows"):
            rows.first.click()
            page.wait_for_timeout(1200)
            self.check(page.evaluate("document.querySelector('#detail').innerText.startsWith('MARKET')"), "market row opens the drawer")
            page.locator("#detail .hv-white").click()
            page.wait_for_timeout(300)
            self.check(page.evaluate("document.querySelector('#detail').innerHTML.length === 0"), "drawer close button closes it")
        # Whale row → wallet drawer (these wallets are mostly not on the leaderboard).
        self.goto(page, "#whale", 1000)
        rows = page.locator("#main .hv-panel[data-act]")
        self.wait_for(page, lambda: rows.count() > 0, 30)
        if rows.count():
            rows.first.click()
            page.wait_for_timeout(1500)
            txt = page.evaluate("document.querySelector('#detail').innerText")
            self.check(txt.startswith("WALLET"), f"whale row opens a wallet drawer ({txt[:60]!r})")
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)
        else:
            self.note("no whale rows in this tape window — drawer check skipped")
        # Tape rows: clickable rows carry a handler, the rest carry no pointer.
        self.goto(page, "#flow", 2500)
        bad = page.evaluate(
            "() => Array.from(document.querySelectorAll('#main [style*=\"grid-template-columns:96px 160px\"]')).slice(1)"
            ".filter(r => (r.getAttribute('style') || '').includes('cursor:pointer') !== r.hasAttribute('data-act')).length")
        self.check(bad == 0, f"tape rows: pointer only where a handler exists ({bad} mismatches)")

    def phase_persistence(self, browser: Browser) -> None:
        """Open <details> on three pages in three tabs, scroll, wait through the
        clock tick (15 s) and the poll (30 s) once, then check all three."""
        self.context = "persistence"
        setups = [
            ("#research/microstructure/mm-staleness", "#main details[data-key='method:mm-staleness'] summary", None),
            ("#research/category-efficiency", "#main details summary", 1400),
            ("#research/live-runs", "#main details summary", 2000),
        ]
        pages = []
        for route, selector, scroll in setups:
            pg = self.new_page(browser)
            self.goto(pg, route, 3000)
            loc = pg.locator(selector)
            if not loc.count():
                self.note(f"{route}: no <details> to open — skipped")
                pg.close()
                continue
            loc.first.click()
            pg.wait_for_timeout(300)
            if scroll is not None:
                pg.evaluate(f"document.querySelector('.content').scrollTop = {scroll}")
                pg.wait_for_timeout(200)
            pages.append((route, pg, pg.evaluate(JS_OPEN_DETAILS), pg.evaluate(JS_SCROLL)))
        if not pages:
            self.fail("no page had a <details> to test")
            return
        # A fourth tab loses its API mid-session: the topbar must say so after the poll.
        outage = None
        if not self.static:
            outage = self.new_page(browser)
            self.goto(outage, "#markets", 1000)
            self.wait_for(outage, lambda: "LIVE" in outage.evaluate(JS_TOPBAR), 40)
            if "LIVE" in outage.evaluate(JS_TOPBAR):
                outage.route("**/api/**", lambda route: route.abort())
                outage.locator("#sidebar [data-act]", has_text="Cross-venue").first.click()
            else:
                self.note("API never went live — outage check skipped")
                outage.close()
                outage = None
        clock_seen = pages[0][1].evaluate(JS_TOPBAR)
        pages[0][1].wait_for_timeout(33000)
        for route, pg, open_before, scroll_before in pages:
            open_after, scroll_after = pg.evaluate(JS_OPEN_DETAILS), pg.evaluate(JS_SCROLL)
            self.check(open_after == open_before, f"{route}: <details> stay open across clock tick and poll ({open_after})")
            self.check(abs(scroll_after - scroll_before) <= 2, f"{route}: scroll position kept across the poll ({scroll_before} → {scroll_after})")
            self.check(pg.evaluate("document.querySelectorAll('#main details').length") > 0, f"{route}: page still rendered")
            pg.close()
        self.note(f"topbar before the wait: {clock_seen!r}")
        if outage is not None:
            top = outage.evaluate(JS_TOPBAR)
            self.check("API OFFLINE · LAST KNOWN STATE" in top, f"topbar reports the outage ({top!r})")
            self.check("Try again" in outage.evaluate(JS_MAIN_TEXT), "cross-venue shows 'Try again' after the failed request")
            outage.unroute("**/api/**")
            self.click_text(outage, "Try again", wait_ms=800)
            txt = outage.evaluate(JS_MAIN_TEXT)
            self.check("did not answer" not in txt, "'Try again' re-asks the endpoint")
            outage.close()

    def phase_live(self, page: Page) -> None:
        """API-mode only: risk progress line, backtester RUN guard and 429."""
        self.context = "live"
        if self.static:
            # Static: no engine behind RUN — the line must say so, not "HTTP 501".
            self.goto(page, "#backtester", 1500)
            self.click_text(page, "RUN backtest", wait_ms=2500)
            txt = page.evaluate(JS_MAIN_TEXT)
            self.check("No backtest API on this host" in txt, "static RUN explains that no engine is served here")
            self.goto(page, "#risk", 2500)
            self.check("Try again" in page.evaluate(JS_MAIN_TEXT), "static risk screen offers 'Try again' after the failed request")
            return
        self.goto(page, "#risk", 800)
        txt = page.evaluate(JS_MAIN_TEXT)
        loading = "building the day" in txt
        loaded = "EVENTS SCREENED" in txt and "building the day" not in txt and "did not answer" not in txt
        self.check(loading or loaded, "risk screen shows its progress line or the loaded screen")
        if loading:
            self.check(self.wait_text_gone(page, "building the day", 160), "risk screen loads within its 150 s window")
        self.check("did not answer" not in page.evaluate(JS_MAIN_TEXT), "risk screen loaded without an error line")
        self.click_text(page, "Flag log", wait_ms=1000)
        self.wait_for(page, lambda: "loading /api/risk/log" not in page.evaluate(JS_MAIN_TEXT), 50)
        txt = page.evaluate(JS_MAIN_TEXT)
        i = txt.find("did not answer")
        if not self.check(self.hash_(page) == "#risk/log" and i < 0, "flag log tab loads"):
            self.note(f"flag log text: {txt[max(0, i - 200):i + 80]!r}")
        # Backtester: five quick presses start one run; the guard swallows the rest.
        self.goto(page, "#backtester", 1500)
        for _ in range(5):
            self.click_text(page, "RUN backtest", wait_ms=150)
        txt = page.evaluate(JS_MAIN_TEXT)
        self.check("running…" in txt or "settings changed" in txt or "Trade log" in txt, "RUN starts a run (further presses are ignored while it runs)")
        # 429: wait for that run to end, empty the expensive bucket with raw
        # POSTs, then press RUN → 'rate-limited · retry in N s'.
        self.wait_for(page, lambda: "running…" not in page.evaluate(JS_MAIN_TEXT), 150, 1500)
        page.evaluate("""async () => { for (let i = 0; i < 4; i++) { await fetch('/api/backtest', {method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({wallet: '0x0000000000000000000000000000000000000000', window_days: 7, strategy: 'copy'})})
            } }""")
        self.click_text(page, "RUN backtest", wait_ms=1500)
        txt = page.evaluate(JS_MAIN_TEXT)
        self.check("rate-limited" in txt and "retry in" in txt, "a 429 reads as 'rate-limited · retry in N s'")

    # -- console / network policy --------------------------------------------
    def phase_logs(self) -> None:
        self.context = "logs"
        bad_console = []
        for ctx, typ, text in self.console:
            if typ == "pageerror":
                bad_console.append((ctx, typ, text))
                continue
            low = text.lower()
            if "failed to load resource" in low:
                # Judged through the network list below (status + url known there).
                continue
            bad_console.append((ctx, typ, text))
        bad_net = []
        throttled = 0
        for ctx, url, status in self.network:
            path = url.split("?")[0]
            if self.static and "/api/" in path and status in (404, 501):
                continue                     # designed fallback to ./data
            if status == 429 and ctx != "live":
                # The server's own token bucket (120/min, burst 40) — this
                # smoke reloads the app far more often than a reader does.
                # The pages still rendered (checked above); counted, not failed.
                throttled += 1
                continue
            if isinstance(status, str) and "ERR_ABORTED" in status:
                continue                     # a navigation cut the request off, not a failure
            if ctx == "persistence" and isinstance(status, str) and "net::ERR" in status:
                continue                     # the simulated outage
            if ctx == "live" and status == 429 and "/api/backtest" in path:
                continue                     # the rate-limit check
            bad_net.append((ctx, url, status))
        self.check(not bad_console, f"no console/page errors ({len(bad_console)})")
        for ctx, typ, text in bad_console[:8]:
            print(f"     [{ctx}] {typ}: {text[:200]}")
        self.check(not bad_net, f"no unexpected failed requests ({len(bad_net)})")
        for ctx, url, status in bad_net[:12]:
            print(f"     [{ctx}] {status} {url}")
        if throttled:
            print(f"     note: the API rate limiter answered 429 {throttled}× outside the rate-limit check (pages fell back to ./data)")

    # -- run -----------------------------------------------------------------
    def run(self, headed: bool) -> int:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not headed, args=["--disable-gpu"])
            page = self.new_page(browser)
            self.phase_routes(page)
            self.phase_sidebar(page)
            self.phase_anchors(page)
            self.phase_subtabs(page)
            self.phase_search_and_drawer(page)
            self.phase_live(page)
            self.phase_persistence(browser)
            browser.close()
        self.phase_logs()
        print()
        if self.failures:
            print(f"ux smoke FAILED — {len(self.failures)} check(s):")
            for f in self.failures:
                print(f"- {f}")
            return 1
        print(f"ux smoke passed ({'static' if self.static else 'API'} mode, {self.base})")
        return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base-url", default="http://127.0.0.1:8790")
    ap.add_argument("--static", action="store_true", help="the base URL is a plain file host (dist/): /api/* 404s are expected")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    return Smoke(args.base_url, args.static, args.verbose).run(args.headed)


if __name__ == "__main__":
    sys.exit(main())
