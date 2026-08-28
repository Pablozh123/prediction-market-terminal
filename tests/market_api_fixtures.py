"""Ein stehendes Marktbild fuer den Seiten-Smoke, ohne Netz.

Warum es das gibt: der Seiten-Smoke lief gegen die echten oeffentlichen
APIs und war deshalb langsam und opt-in. In genau der Zeit, in der er nicht
lief, ist ein KeyError in ``trader_flow_scores`` ueber mehrere PRs hinweg
unbemerkt geblieben und hat die Seiten Search und Traders zerlegt, waehrend
die CI gruen war.

Warum die Fixtures Zeilen liefern muessen und nicht bloss leere Listen:
faellt das Netz aus, faengt ``safe_load`` im Monolithen die Ausnahme ab und
gibt einen leeren Frame zurueck. Fast jede Aggregation steigt auf einem
leeren Frame sofort wieder aus (``if trades.empty: return``) -- ein Smoke
gegen leere Antworten haette genau den Fehler nicht gesehen, den er finden
sollte. Die Payloads hier tragen darum echte Feldnamen und Werte, damit die
Seiten mit gefuellten Tabellen rendern und die Rechenwege wirklich laufen.

Bewusst knapp: abgedeckt sind die Endpunkte, die die Seiten mit Daten
fuellen. Alles andere beantwortet der Router mit einer leeren, aber richtig
geformten Antwort. Das ist derselbe Zustand, den ein nicht erreichbarer
Endpunkt erzeugt, und den die Seiten laut Smoke schadlos rendern.
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch
from urllib.parse import urlparse

WALLETS = [
    "0x1111111111111111111111111111111111111111",
    "0x2222222222222222222222222222222222222222",
    "0x3333333333333333333333333333333333333333",
]

#: Zwei Folgen derselben wiederkehrenden Frage unter zwei conditionIds. Genau
#: diese Konstellation trennt "ein Markt" von "ein Titel" und war der Anlass
#: fuer market_identity.
CONDITION_IDS = [
    "0x" + "ab" * 32,
    "0x" + "cd" * 32,
    "0x" + "ef" * 32,
]

TITLES = [
    'Will "Nvidia" be said during the next episode of the All-In Podcast?',
    'Will "Nvidia" be said during the next episode of the All-In Podcast?',
    "Will the incumbent win the 2026 midterms?",
]

SLUGS = ["all-in-podcast-week-1", "all-in-podcast-week-2", "midterms-2026"]

KALSHI_TICKERS = ["KXPRES-26-DEM", "KXPRES-26-REP"]


def _now() -> int:
    return int(time.time())


def _iso(offset_seconds: float) -> str:
    stamp = time.gmtime(_now() + offset_seconds)
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", stamp)


def polymarket_markets() -> list[dict[str, Any]]:
    rows = []
    for index, (condition, title, slug) in enumerate(zip(CONDITION_IDS, TITLES, SLUGS)):
        yes = 0.35 + 0.2 * index
        rows.append(
            {
                "id": str(500000 + index),
                "conditionId": condition,
                "question": title,
                "slug": slug,
                "description": "Fixture market for the page smoke.",
                "category": "Politics" if index == 2 else "Pop Culture",
                "outcomes": json.dumps(["Yes", "No"]),
                "outcomePrices": json.dumps([f"{yes:.2f}", f"{1 - yes:.2f}"]),
                "clobTokenIds": json.dumps([f"{700000 + index * 2}", f"{700001 + index * 2}"]),
                "bestBid": round(yes - 0.01, 3),
                "bestAsk": round(yes + 0.01, 3),
                "spread": 0.02,
                "lastTradePrice": yes,
                "oneHourPriceChange": 0.01,
                "oneDayPriceChange": 0.04,
                "oneWeekPriceChange": -0.02,
                "volumeNum": 1_250_000.0 - index * 100_000,
                "volume1hr": 12_000.0,
                "volume24hr": 180_000.0,
                "volume1wk": 640_000.0,
                "volume1mo": 900_000.0,
                "liquidityNum": 140_000.0 - index * 10_000,
                "startDateIso": _iso(-30 * 86400),
                "endDateIso": _iso(9 * 86400),
                "createdAt": _iso(-40 * 86400),
                "updatedAt": _iso(-600),
                "active": True,
                "closed": False,
                "icon": "",
                "events": [{"slug": slug, "category": "Politics", "title": title}],
            }
        )
    return rows


def polymarket_closed_events() -> list[dict[str, Any]]:
    events = []
    for index, (condition, title, slug) in enumerate(zip(CONDITION_IDS, TITLES, SLUGS)):
        market = dict(polymarket_markets()[index])
        market.update(
            {
                "active": False,
                "closed": True,
                "endDateIso": _iso(-3 * 86400),
                "closedTime": _iso(-3 * 86400),
                "outcomePrices": json.dumps(["1", "0"]),
                "umaResolutionStatus": "resolved",
            }
        )
        events.append(
            {
                "id": str(900 + index),
                "slug": slug,
                "title": title,
                "category": "Politics",
                "closed": True,
                "endDate": _iso(-3 * 86400),
                "markets": [market],
            }
        )
    return events


def polymarket_trades() -> list[dict[str, Any]]:
    rows = []
    for index in range(24):
        # Wallet und Markt laufen absichtlich in verschiedenen Schritten,
        # sonst handelt jede Wallet genau einen Markt und jede Zaehlung
        # ueber market_identity liefert stumpf die 1.
        wallet = WALLETS[index % len(WALLETS)]
        market = (index // 2) % len(CONDITION_IDS)
        rows.append(
            {
                "proxyWallet": wallet,
                "name": f"trader-{index % len(WALLETS)}",
                "pseudonym": f"Fixture-{index % len(WALLETS)}",
                "timestamp": _now() - index * 90,
                "size": 4000.0 + index * 120,
                "price": 0.35 + 0.02 * (index % 8),
                "side": "BUY" if index % 2 == 0 else "SELL",
                "outcome": "Yes" if index % 3 else "No",
                "title": TITLES[market],
                "conditionId": CONDITION_IDS[market],
                "asset": f"{700000 + market * 2}",
                "transactionHash": "0x" + f"{index:064x}",
                "slug": SLUGS[market],
                "eventSlug": SLUGS[market],
            }
        )
    return rows


def polymarket_leaderboard() -> list[dict[str, Any]]:
    return [
        {
            "rank": index + 1,
            "proxyWallet": wallet,
            "userName": f"trader-{index}",
            "pnl": 250_000.0 - index * 40_000,
            "vol": 8_000_000.0 - index * 900_000,
            "xUsername": "",
            "verifiedBadge": index == 0,
            "profileImage": "",
        }
        for index, wallet in enumerate(WALLETS)
    ]


def polymarket_activity() -> list[dict[str, Any]]:
    rows = []
    for index, trade in enumerate(polymarket_trades()):
        row = dict(trade)
        row["type"] = "TRADE" if index % 4 else "REDEEM"
        row["usdcSize"] = float(trade["size"]) * float(trade["price"])
        rows.append(row)
    return rows


def polymarket_positions() -> list[dict[str, Any]]:
    return [
        {
            "proxyWallet": WALLETS[index % len(WALLETS)],
            "conditionId": CONDITION_IDS[index],
            "title": TITLES[index],
            "outcome": "Yes",
            "asset": f"{700000 + index * 2}",
            "size": 12_000.0 - index * 2_000,
            "avgPrice": 0.32 + 0.05 * index,
            "curPrice": 0.41 + 0.05 * index,
            "currentValue": 5_000.0 - index * 600,
            "endDate": _iso(9 * 86400),
            "slug": SLUGS[index],
            "eventSlug": SLUGS[index],
            "icon": "",
        }
        for index in range(len(CONDITION_IDS))
    ]


def polymarket_closed_positions() -> list[dict[str, Any]]:
    rows = []
    for index, position in enumerate(polymarket_positions()):
        row = dict(position)
        row.update(
            {
                "realizedPnl": 1_800.0 - index * 500,
                "totalBought": 4_000.0 + index * 300,
                "avgPrice": 0.3 + 0.05 * index,
                "outcome": "Yes" if index % 2 == 0 else "No",
                "redeemable": True,
                "endDate": _iso(-4 * 86400),
            }
        )
        rows.append(row)
    return rows


def polymarket_holders() -> list[dict[str, Any]]:
    return [
        {
            "token": f"{700000 + index * 2}",
            "holders": [
                {
                    "proxyWallet": wallet,
                    "name": f"trader-{position}",
                    "pseudonym": f"Fixture-{position}",
                    "amount": 40_000.0 - position * 9_000,
                    "outcomeIndex": index,
                }
                for position, wallet in enumerate(WALLETS)
            ],
        }
        for index in range(2)
    ]


def polymarket_market_positions() -> list[dict[str, Any]]:
    return [
        {
            "token": f"{700000 + index * 2}",
            "positions": [
                {
                    "proxyWallet": wallet,
                    "name": f"trader-{position}",
                    "size": 30_000.0 - position * 7_000,
                    "avgPrice": 0.4,
                    "outcome": "Yes" if index == 0 else "No",
                    "outcomeIndex": index,
                }
                for position, wallet in enumerate(WALLETS)
            ],
        }
        for index in range(2)
    ]


def polymarket_orderbook() -> dict[str, Any]:
    return {
        "bids": [{"price": f"{0.40 - level * 0.01:.2f}", "size": f"{2000 + level * 500}"} for level in range(8)],
        "asks": [{"price": f"{0.42 + level * 0.01:.2f}", "size": f"{1800 + level * 400}"} for level in range(8)],
    }


def polymarket_price_history() -> dict[str, Any]:
    start = _now() - 30 * 86400
    return {"history": [{"t": start + step * 86400, "p": 0.30 + 0.005 * step} for step in range(30)]}


def polymarket_user_pnl() -> list[dict[str, Any]]:
    start = _now() - 30 * 86400
    return [{"t": start + step * 86400, "p": 100.0 * step} for step in range(30)]


def polymarket_public_search() -> dict[str, Any]:
    return {
        "events": [
            {
                "slug": SLUGS[0],
                "title": TITLES[0],
                "category": "Pop Culture",
                "markets": polymarket_markets()[:1],
            }
        ],
        "profiles": [{"name": "trader-0", "proxyWallet": WALLETS[0], "pseudonym": "Fixture-0"}],
        "tags": [],
    }


def kalshi_markets() -> dict[str, Any]:
    return {
        "cursor": "",
        "markets": [
            {
                "ticker": ticker,
                "event_ticker": ticker.rsplit("-", 1)[0],
                "series_ticker": ticker.split("-", 1)[0],
                "title": f"Fixture Kalshi market {index}",
                "subtitle": "Yes",
                "status": "active",
                "yes_bid_dollars": 0.44 + 0.05 * index,
                "yes_ask_dollars": 0.46 + 0.05 * index,
                "last_price_dollars": 0.45 + 0.05 * index,
                "liquidity_dollars": 88_000.0 - index * 9_000,
                "volume_fp": 420_000.0 - index * 50_000,
                "volume_24h_fp": 31_000.0,
                "open_interest_fp": 210_000.0,
                "open_time": _iso(-25 * 86400),
                "close_time": _iso(11 * 86400),
                "category": "Politics",
                "rules_primary": "Fixture rules.",
            }
            for index, ticker in enumerate(KALSHI_TICKERS)
        ],
    }


def kalshi_trades() -> dict[str, Any]:
    return {
        "cursor": "",
        "trades": [
            {
                "trade_id": f"fixture-{index}",
                "ticker": KALSHI_TICKERS[index % len(KALSHI_TICKERS)],
                "created_time": _iso(-index * 120),
                "taker_side": "yes" if index % 2 == 0 else "no",
                "taker_outcome_side": "yes" if index % 2 == 0 else "no",
                "yes_price_dollars": 0.45 + 0.01 * (index % 6),
                "count_fp": 3_000.0 + index * 250,
            }
            for index in range(20)
        ],
    }


NEWS_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Fixture news</title>
<item><title>Fixture headline</title><link>https://example.invalid/a</link>
<pubDate>Mon, 25 Aug 2026 09:00:00 GMT</pubDate><source>Fixture Wire</source></item>
</channel></rss>"""


class FixtureResponse:
    """Das Stueck ``requests.Response``, das die Clients wirklich anfassen."""

    def __init__(self, payload: Any = None, *, content: bytes | None = None, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.content = content if content is not None else json.dumps(payload).encode("utf-8")
        self.text = self.content.decode("utf-8", errors="replace")
        self.headers: dict[str, str] = {"Content-Type": "application/json"}

    def json(self) -> Any:
        if self._payload is None:
            return json.loads(self.text)
        return self._payload

    def raise_for_status(self) -> None:
        return None


def _payload_for(url: str) -> tuple[Any, bytes | None]:
    parsed = urlparse(str(url))
    host = parsed.netloc
    path = parsed.path.rstrip("/")

    if host == "news.google.com":
        return None, NEWS_RSS
    if host == "gamma-api.polymarket.com":
        if path == "/markets":
            return polymarket_markets(), None
        if path == "/events":
            return polymarket_closed_events(), None
        if path.startswith("/events/slug/"):
            return polymarket_closed_events()[0], None
        if path == "/public-search":
            return polymarket_public_search(), None
        return [], None
    if host == "data-api.polymarket.com":
        if path == "/trades":
            return polymarket_trades(), None
        if path == "/v1/leaderboard":
            return polymarket_leaderboard(), None
        if path == "/activity":
            return polymarket_activity(), None
        if path == "/positions":
            return polymarket_positions(), None
        if path == "/closed-positions":
            return polymarket_closed_positions(), None
        if path == "/holders":
            return polymarket_holders(), None
        if path == "/v1/market-positions":
            return polymarket_market_positions(), None
        if path == "/value":
            return [{"user": WALLETS[0], "value": 42_000.0}], None
        return [], None
    if host == "clob.polymarket.com":
        if path == "/book":
            return polymarket_orderbook(), None
        if path == "/prices-history":
            return polymarket_price_history(), None
        if path == "/time":
            return _now(), None
        return {}, None
    if host == "user-pnl-api.polymarket.com":
        return polymarket_user_pnl(), None
    if host == "external-api.kalshi.com":
        if path.endswith("/markets/trades"):
            return kalshi_trades(), None
        if path.endswith("/markets"):
            return kalshi_markets(), None
        if path.endswith("/orderbook"):
            return {"orderbook": {"yes": [], "no": []}}, None
        return {}, None
    # Unbekannter Host: leer, aber wohlgeformt. Das ist derselbe Zustand wie
    # ein Endpunkt, den es nicht mehr gibt, und den die Seiten tragen muessen.
    return [], None


def fixture_get(url: str, params: Any = None, **kwargs: Any) -> FixtureResponse:
    payload, content = _payload_for(url)
    return FixtureResponse(payload, content=content)


def fixture_post(url: str, *args: Any, **kwargs: Any) -> FixtureResponse:
    return FixtureResponse({})


@contextmanager
def offline_market_apis():
    """Jeden HTTP-Aufruf des Prozesses auf das Fixture-Marktbild umlenken.

    ``requests.get`` wird am Modul gepatcht, nicht an den Aufrufern: sowohl
    ``src/prediction_markets.py`` als auch ``src/copy_trading.py`` loesen den
    Namen erst beim Aufruf auf, ein Patch trifft also beide.
    """

    with patch("requests.get", side_effect=fixture_get), patch("requests.post", side_effect=fixture_post):
        yield


def _mit_umbenanntem_feld(quelle: Any, schluessel: str, alt: str, neu: str):
    """Dieselbe Nutzlast, ein Feldname getauscht."""

    def umbenannt() -> dict[str, Any]:
        daten = quelle()
        daten[schluessel] = [
            {(neu if name == alt else name): wert for name, wert in zeile.items()}
            for zeile in daten.get(schluessel, [])
        ]
        return daten

    return umbenannt


@contextmanager
def renamed_field(venue: str, alt: str, neu: str):
    """Ein umbenanntes Feld in einer Venue-Antwort, sonst dasselbe Marktbild.

    Der Ausfall, den kein Netzfehler erzeugt: die API antwortet mit 200 und
    wohlgeformtem JSON, nur heisst eine Spalte anders. Ein Parser, der jedes
    Feld ueber ``.get(name, default)`` liest, merkt davon nichts und liefert
    eine Spalte voller Vorgabewerte; einer, der die Spalte rechnet, faellt
    mit einem AttributeError um, den weiter oben ein ``except Exception`` in
    eine Warnung schluckt. Beide Enden sehen von aussen gleich aus: die
    Seite meldet weiter LIVE und zeigt eine Venue weniger.

    ``venue`` ist ``kalshi_trades``, ``kalshi_markets`` oder
    ``polymarket_trades``.
    """

    quellen = {
        "kalshi_trades": (kalshi_trades, "trades"),
        "kalshi_markets": (kalshi_markets, "markets"),
    }
    if venue == "polymarket_trades":
        original = polymarket_trades

        def umbenannt_liste() -> list[dict[str, Any]]:
            return [
                {(neu if name == alt else name): wert for name, wert in zeile.items()}
                for zeile in original()
            ]

        with patch(f"{__name__}.polymarket_trades", umbenannt_liste):
            yield
        return
    if venue not in quellen:
        raise AssertionError(f"unknown fixture venue: {venue}")
    quelle, schluessel = quellen[venue]
    with patch(f"{__name__}.{venue}", _mit_umbenanntem_feld(quelle, schluessel, alt, neu)):
        yield
