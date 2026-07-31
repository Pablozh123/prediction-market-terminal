"""Book state for the Kalshi socket feed. Pure logic, no socket, no files.

Split out of ``src/kalshi_stream.py`` so the parts that can silently corrupt a
book are testable without a network. Three rules, each of which is a distinct
way to get it wrong:

Deltas are changes. Kalshi sends the amount a level moved, not its new size, so
a level is updated by addition and disappears when the running total reaches
zero. Applying Polymarket's assignment semantics here would drift within
seconds and never raise an error.

Both ladders are bids. ``yes`` and ``no`` both hold bids. The YES ask side is
the reflection of the NO bids, because a NO bid at 25 cents is an offer to sell
YES at 75.

Sequence numbers are load bearing. A gap means the local book no longer matches
the exchange, so the book is dropped and no rows are written for that market
until a fresh snapshot arrives. Writing rows from a book known to be wrong is
worse than writing none.

Prices arrive as integer cents and are stored in dollars, so every downstream
study sees the same units as the Polymarket recorders.
"""

from __future__ import annotations

DEPTH_LEVELS = 5


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

    __slots__ = ("yes_bids", "no_bids", "seq", "broken")

    def __init__(self) -> None:
        self.yes_bids: dict[float, float] = {}
        self.no_bids: dict[float, float] = {}
        self.seq: int | None = None
        self.broken = False

    def apply_snapshot(self, yes: list, no: list, seq: int | None = None) -> None:
        self.yes_bids = self._parse(yes)
        self.no_bids = self._parse(no)
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
        book = self.yes_bids if str(side).lower().startswith("y") else self.no_bids
        total = book.get(dollars, 0.0) + change
        if total > 0:
            book[dollars] = total
        else:
            book.pop(dollars, None)

    def check_seq(self, seq) -> bool:
        """True if the sequence follows on. A gap marks the book broken."""
        try:
            value = int(seq)
        except (TypeError, ValueError):
            return True  # ohne seq keine Luecke feststellbar
        if self.seq is None:
            self.seq = value
            return True
        if value == self.seq + 1 or value == self.seq:
            self.seq = value
            return True
        self.seq = value
        self.broken = True
        return False

    def best_bid(self) -> float | None:
        return max(self.yes_bids) if self.yes_bids else None

    def best_ask(self) -> float | None:
        """Reflection of the best NO bid: a NO bid at p is a YES offer at 1 - p."""
        if not self.no_bids:
            return None
        return round(1.0 - max(self.no_bids), 6)

    def ask_levels(self, levels: int = DEPTH_LEVELS) -> list[tuple[float, float]]:
        prices = sorted(self.no_bids, reverse=True)[:levels]
        return [(round(1.0 - price, 6), self.no_bids[price]) for price in prices]

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
                self.yes_bids.get(max(self.yes_bids)) if self.yes_bids else None,
                self.no_bids.get(max(self.no_bids)) if self.no_bids else None)

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
            "bid_size_touch": self.yes_bids.get(max(self.yes_bids)) if self.yes_bids else None,
            "ask_size_touch": self.no_bids.get(max(self.no_bids)) if self.no_bids else None,
            "bid_levels": len(self.yes_bids),
            "ask_levels": len(self.no_bids),
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
        self._last_touch: dict[str, tuple] = {}

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
        market = str(message.get("market_ticker") or "")
        if not market:
            return

        if event_type == "orderbook_snapshot":
            book = self._book(market)
            book.apply_snapshot(message.get("yes"), message.get("no"),
                                event.get("seq"))
            self._emit_if_touch_moved(market, recv_ts, "snapshot")

        elif event_type == "orderbook_delta":
            book = self._book(market)
            if not book.check_seq(event.get("seq")):
                self.seq_gaps += 1
                self._last_touch.pop(market, None)
                return
            if book.broken:
                return
            book.apply_delta(message.get("price"), message.get("delta"),
                             message.get("side"))
            self._emit_if_touch_moved(market, recv_ts, "delta")

        elif event_type == "trade":
            taker = str(message.get("taker_side") or "").lower()
            self.trade_rows.append({
                "recv_ts": recv_ts,
                "exchange_ts": message.get("ts"),
                "market_id": market,
                "side": "BUY" if taker.startswith("y") else "SELL",
                "price": to_dollars(message.get("yes_price")),
                "size": message.get("count"),
                "trade_id": message.get("trade_id"),
            })

    def drain(self) -> tuple[list[dict], list[dict]]:
        books, trades = self.book_rows, self.trade_rows
        self.book_rows, self.trade_rows = [], []
        return books, trades
