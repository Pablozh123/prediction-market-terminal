"""Smoke-check local Streamlit routes.

This is a lightweight server check, not a full browser render test.
Run it while the app is already listening on the configured base URL.
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass


DEFAULT_BASE_URL = "http://127.0.0.1:8503"
DEFAULT_ROUTES = [
    "/",
    "/?q=bitcoin&platform=polymarket&featured=any&marketRows=9&minVolume=10000&showNews=false",
    "/search?q=bitcoin&platform=polymarket&type=markets,traders,cross-venue&minValue=10000",
    "/markets",
    "/markets/will-bitcoin-hit-100k",
    "/markets?q=bitcoin&platform=polymarket&status=active&probMin=0.05&probMax=0.95&volumeMin=10000",
    "/traders",
    "/track",
    "/track?q=tony&platform=polymarket&signal=tight-spread&minWatchVolume=10000&minWalletValue=2500",
    "/live-trades",
    "/live-trades?q=swisstony&platform=polymarket&side=buy&minNotional=2500&whale=true",
    "/whale-flow?q=iran&platform=polymarket&minPrint=5000&bias=yes&trackedWallets=false",
    "/cross-venue?q=bitcoin&minSimilarity=0.35&minGap=0.08&lower=kalshi&priceMin=0.05&priceMax=0.95",
    "/monitor",
    "/monitor?q=bitcoin&platform=polymarket&signal=whale-print,tight-spread&minWhale=2500&maxSpread=0.07",
    "/alerts?q=iran&signal=fast-mover&hitsOnly=true&minWhale=5000",
    "/resolved?q=iran&outcome=yes,no&decisiveOnly=true&minVolume=10000&closedWindow=30d&finalYesMin=0.95",
    "/portfolio",
    "/portfolio?q=tony&platform=polymarket&source=research,copy&copyStatus=copied,settled&minValue=100&losersOnly=false",
    "/copy-trade",
    "/copy-trade?q=tony&side=buy&status=copied,baseline&minTonyNotional=1000&minCopyNotional=10&reason=redeem&latencyOnly=true",
    "/sign-in",
    "/sign-up",
    "/traders/p/@swisstony",
    "/traders?bot=true&apMin=101",
    "/wallets/0x204f72f35326db932158cba6adff0b9a1da95e14",
]


@dataclass(frozen=True)
class RouteResult:
    route: str
    status: int
    ok: bool
    error: str = ""


def fetch_status(url: str, timeout: float) -> int:
    request = urllib.request.Request(url, headers={"User-Agent": "prediction-terminal-smoke/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return int(response.status)


def check_routes(base_url: str, routes: list[str], timeout: float) -> list[RouteResult]:
    base = base_url.rstrip("/")
    results: list[RouteResult] = []
    for route in routes:
        path = route if route.startswith("/") else f"/{route}"
        try:
            status = fetch_status(f"{base}{path}", timeout)
            results.append(RouteResult(route=path, status=status, ok=200 <= status < 400))
        except urllib.error.HTTPError as exc:
            results.append(RouteResult(route=path, status=int(exc.code), ok=False, error=str(exc)))
        except Exception as exc:
            results.append(RouteResult(route=path, status=0, ok=False, error=str(exc)))
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-check local Prediction Market Terminal routes.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"App base URL. Default: {DEFAULT_BASE_URL}")
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout per route in seconds.")
    parser.add_argument("--route", action="append", dest="routes", help="Route to check. Can be supplied more than once.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    routes = args.routes or DEFAULT_ROUTES
    results = check_routes(str(args.base_url), [str(route) for route in routes], float(args.timeout))
    for result in results:
        label = "OK" if result.ok else "FAIL"
        suffix = f" ({result.error})" if result.error else ""
        print(f"{label:4} {result.status:>3} {result.route}{suffix}")
    return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":
    sys.exit(main())
