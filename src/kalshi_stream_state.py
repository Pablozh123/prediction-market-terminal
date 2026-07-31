"""Book state for the Kalshi socket feed. Pure logic, no socket, no files.

Split out of ``src/kalshi_stream.py`` so the parts that can silently corrupt a
book are testable without a network. Three rules, each of which is a distinct
way to get it wrong:

Deltas are changes. Kalshi sends the amount a level moved, not its new size, so
a level is updated by addition and disappears when the running total reaches
zero. Applying Polymarket's assignment semantics here would drift within
seconds and never raise an error.

Both ladders arrive in YES pricing. The subscription pins
``use_yes_price: true``, so the no-side levels are already YES ask prices and
must NOT be reflected again. Without the flag the two sides use different
scales and the no side needs ``1 - p``; doing both, or neither, inverts every
spread. The flag is pinned precisely so this file only has to be right about
one convention.

Sequence numbers are load bearing, and they count per subscription rather than
per market. A single stream numbers every message across all subscribed
markets, so a gap does not tell you which book lost an update - it tells you
the connection did. Every book is therefore marked untrusted at once and no
rows are written until fresh snapshots arrive. Tracking the counter per market
instead looks reasonable and reports a gap on almost every message, because
each market only ever sees a subset of a shared counter.

Prices arrive as integer cents and are stored in dollars, so every downstream
study sees the same units as the Polymarket recorders.
"""

from __future__ import annotations

DEPTH_LEVELS = 5


def _first(message: dict, *names: str):
    """First present field. The socket uses ``*_fp`` names, older docs do not."""
    for name in names:
        if name in message and message[name] is not None:
            return message[name]
    return None


def to_dollars(price) -> float | None:
    """Cents to dollars. Values already in (0, 1) are passed through."""
    try:
        value = float(price)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    if value > 1.0:  # Cent-Notation der Socket-API
        value = value / 100.0
    return round(value, 6) if 0 < value < 1 else None


class BookState:
    """One market's YES book, kept from a snapshot plus additive deltas."""

    __slots__ = ("yes_bids", "asks", "seq", "broken")

    def __init__(self) -> None:
        self.yes_bids: dict[float, float] = {}
        self.asks: dict[float, float] = {}
        self.seq: int | None = None
        self.broken = False

    def apply_snapshot(self, yes: list, no: list, seq: int | None = None) -> None:
        self.yes_bids = self._parse(yes)
        self.asks = self._parse(no)
        self.seq = seq
        self.broken = False

    @staticmethod
    def _parse(levels: list) -> dict[float, float]:
        out: dict[float, float] = {}
        for level in levels or []:
            try:
                price, size = level[0], float(level[1])
            except (TypeError, ValueError, IndexError, KeyError):
                continue
            dollars = to_dollars(price)
            if dollars is not None and size > 0:
                out[dollars] = size
        return out

    def apply_delta(self, price, delta, side: str) -> None:
        """Add ``delta`` to a level. Non-positive totals remove it."""
        dollars = to_dollars(price)
        try:
            change = float(delta)
        except (TypeError, ValueError):
            return
        if dollars is None:
            return
        book = self.yes_bids if str(side).lower().startswith("y") else self.asks
        total = book.get(dollars, 0.0) + change
        if total > 0:
            book[dollars] = total
        else:
            book.pop(dollars, None)

    def mark_broken(self) -> None:
        """Stop trusting this book until a fresh snapshot arrives."""
        self.broken = True

    def best_bid(self) -> float | None:
        return max(self.yes_bids) if self.yes_bids else None

    def best_ask(self) -> float | None:
        """Lowest offer. Already in YES pricing thanks to ``use_yes_price``."""
        return min(self.asks) if self.asks else None

    def ask_levels(self, levels: int = DEPTH_LEVELS) -> list[tuple[float, float]]:
        prices = sorted(self.asks)[:levels]
        return [(price, self.asks[price]) for price in prices]

    def bid_levels(self, levels: int = DEPTH_LEVELS) -> list[tuple[float, float]]:
        prices = sorted(self.yes_bids, reverse=True)[:levels]
        return [(price, self.yes_bids[price]) for price in prices]

    def depth_usd(self, levels: int = DEPTH_LEVELS) -> tuple[float, float]:
        bid = sum(price * size for price, size in self.bid_levels(levels))
        ask = sum(price * size for price, size in self.ask_levels(levels))
        return round(bid, 4), round(ask, 4)

    def touch_signature(self) -> tuple:
        bid, ask = self.best_bid(), self.best_ask()
        return (bid, ask,
                self.yes_bids.get(bid) if bid is not None else None,
                self.asks.get(ask) if ask is not None else None)

    def top_row(self, recv_ts: str, event_type: str,
                levels: int = DEPTH_LEVELS) -> dict:
        bid, ask = self.best_bid(), self.best_ask()
        bid_usd, ask_usd = self.depth_usd(levels)
        total = bid_usd + ask_usd
        two_sided = bid is not None and ask is not None
        return {
            "recv_ts": recv_ts,
            "seq": self.seq,
            "market_id": "",
            "event_type": event_type,
            "best_bid": bid,
            "best_ask": ask,
            "spread": round(ask - bid, 6) if two_sided else None,
            "mid": round((ask + bid) / 2.0, 6) if two_sided else None,
            "bid_usd_top": bid_usd,
            "ask_usd_top": ask_usd,
            "imbalance_top": round(bid_usd / total, 6) if total > 0 else None,
            "bid_size_touch": self.yes_bids.get(bid) if bid is not None else None,
            "ask_size_touch": self.asks.get(ask) if ask is not None else None,
            "bid_levels": len(self.yes_bids),
            "ask_levels": len(self.asks),
        }


class StreamState:
    """All books plus the rows produced so far."""

    def __init__(self, depth_levels: int = DEPTH_LEVELS) -> None:
        self.books: dict[str, BookState] = {}
        self.depth_levels = depth_levels
        self.book_rows: list[dict] = []
        self.trade_rows: list[dict] = []
        self.counts: dict[str, int] = {}
        self.seq_gaps = 0
        self.needs_resync = False
        #: Gekreuzte Buecher sind unmoeglich, solange die Preiskonvention
        #: stimmt. Jeder Wert ueber null ist ein Alarm, kein Rauschen.
        self.crossed_books = 0
        #: Subscription-Id aus der Bestaetigung, gebraucht fuer den Resnapshot.
        self.sid = None
        #: Der Zaehler laeuft je Subscription, nicht je Markt.
        self.seq_by_sid: dict[str, int] = {}
        self._last_touch: dict[str, tuple] = {}

    def check_seq(self, sid, seq) -> bool:
        """True if the stream is still in order. A gap invalidates every book.

        The counter belongs to the subscription, so one missed message means
        the connection dropped an update for some market we cannot identify.
        """
        try:
            value = int(seq)
        except (TypeError, ValueError):
            return True  # ohne seq laesst sich keine Luecke feststellen
        key = str(sid)
        previous = self.seq_by_sid.get(key)
        self.seq_by_sid[key] = value
        if previous is None or value in (previous, previous + 1):
            return True
        self.seq_gaps += 1
        self.needs_resync = True
        for book in self.books.values():
            book.mark_broken()
        self._last_touch.clear()
        return False

    def _book(self, market: str) -> BookState:
        return self.books.setdefault(market, BookState())

    def _emit_if_touch_moved(self, market: str, recv_ts: str,
                             event_type: str) -> None:
        book = self._book(market)
        if book.broken:
            return
        signature = book.touch_signature()
        if self._last_touch.get(market) == signature:
            return
        self._last_touch[market] = signature
        row = book.top_row(recv_ts, event_type, self.depth_levels)
        row["market_id"] = market
        # Lautes Signal gegen die stille Variante des Preis-Konventionsfehlers:
        # waeren die Seiten vertauscht oder doppelt gespiegelt, kreuzt fast
        # jedes Buch. Ein gesundes Buch kreuzt nie.
        if row["best_bid"] is not None and row["best_ask"] is not None \
                and row["best_ask"] <= row["best_bid"]:
            self.crossed_books += 1
        self.book_rows.append(row)

    def handle(self, event: dict, recv_ts: str) -> None:
        """Fold one socket message into the state."""
        if not isinstance(event, dict):
            return
        event_type = str(event.get("type") or "")
        self.counts[event_type or "unknown"] = self.counts.get(event_type or "unknown", 0) + 1
        message = event.get("msg")
        if not isinstance(message, dict):
            return
        if event_type == "subscribed":
            # Die Subscription-Id ist der einzige Weg, spaeter einen frischen
            # Snapshot anzufordern; ohne sie bleibt ein Buch nach einer Luecke
            # bis zum naechsten Verbindungszyklus tot.
            self.sid = message.get("sid", event.get("sid"))
            return
        market = str(message.get("market_ticker") or "")
        if not market:
            return

        if event_type == "orderbook_snapshot":
            self.check_seq(event.get("sid"), event.get("seq"))
            book = self._book(market)
            book.apply_snapshot(_first(message, "yes_dollars_fp", "yes"),
                                _first(message, "no_dollars_fp", "no"),
                                event.get("seq"))
            self._emit_if_touch_moved(market, recv_ts, "snapshot")

        elif event_type == "orderbook_delta":
            in_order = self.check_seq(event.get("sid"), event.get("seq"))
            book = self._book(market)
            if not in_order or book.broken:
                return
            book.seq = event.get("seq")
            book.apply_delta(_first(message, "price_dollars", "price"),
                             _first(message, "delta_fp", "delta"),
                             message.get("side"))
            self._emit_if_touch_moved(market, recv_ts, "delta")

        elif event_type == "trade":
            taker = str(message.get("taker_side") or "").lower()
            self.trade_rows.append({
                "recv_ts": recv_ts,
                "exchange_ts": message.get("ts"),
                "market_id": market,
                "side": "BUY" if taker.startswith("y") else "SELL",
                "price": to_dollars(_first(message, "yes_price_dollars",
                                           "yes_price")),
                "size": _first(message, "count_fp", "count"),
                "trade_id": message.get("trade_id"),
            })

    def drain(self) -> tuple[list[dict], list[dict]]:
        books, trades = self.book_rows, self.trade_rows
        self.book_rows, self.trade_rows = [], []
        return books, trades
