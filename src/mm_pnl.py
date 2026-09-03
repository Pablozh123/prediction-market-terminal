r"""Where a market maker's money actually comes from, and where it goes.

``src/mm_simulator.py`` answers whether inventory skew changes fill counts and
markouts. It does not answer the question a desk asks first: of the PnL that
ended up on the books, how much was earned spread and how much was handed back
to better-informed counterparties. Without that split, a positive result can be
pure luck on inventory and a negative one can hide a perfectly good quoting
engine.

The decomposition here is an identity, not an estimate. For a fill of ``s``
shares at price ``p`` while the mid is ``m``, with a final mid ``M``:

    buy :  terminal value = s * (M - p) = s * (m - p) + s * (M - m)
    sell:  terminal value = s * (p - M) = s * (p - m) + s * (m - M)
                                          \_________/   \_________/
                                          Spread-Ertrag   Drift danach

and the drift after the fill splits again at the markout horizon:

    Drift danach = Markout (Adverse Selektion) + spaeterer Drift (Inventar)

So terminal mark-to-mid PnL equals spread capture plus markout plus late drift,
exactly, per fill. Add fees and rebates and the four terms sum to the result.
On Polymarket makers pay no fee and receive a rebate, so the fee term is a
credit rather than a cost, which is precisely why market making is the one
strategy in this repo that is not automatically killed by the 2026 fee rollout.

Four fill models run side by side, because none is right on its own:

  touch        a resting quote fills only when the opposite touch crosses it
               between snapshots. Ignores queue fills, so it understates
               fills. Pessimistic.
  tape         a resting quote fills when a public print crosses its price.
               Ignores queue position, so it assumes we were at the front.
               Optimistic.
  queue_front  a resting quote joins the line behind what already rests at
               its price, moves up as prints consume that line, fills
               partially once it reaches the front, and loses its place every
               time it is re-priced. Cancels ahead of us are assumed to come
               from the front of the line.
  queue_back   the same, but cancels are assumed to come from behind us, and
               a level whose depth the recorder never saw is assumed crowded
               until it is observed.

The two queue models sit between touch and tape and differ only in the one
thing the data cannot show: where in the line a cancel happened. The gap
between them is the honest width of what a paper simulation can say about
queue position. A latency parameter keeps the previous quote live for that
long after every requote decision, so being picked on a stale price is part
of the measurement instead of an assumption.

Paper-only research tooling: no order path, no credentials, no wallets.

Usage:
  python -m src.mm_pnl --recorder-dir data/microstructure --tag july
  python -m src.mm_pnl --recorder-dir data/microstructure --tag stream --stream
  python -m src.mm_pnl --recorder-dir data/microstructure --stream \
      --fill-models queue_front,queue_back --latency 1.0 \
      --day-from 2026-08-26 --day-to 2026-09-03 --tag queue-test
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from bisect import bisect_left
from dataclasses import dataclass, field
from pathlib import Path

from app import liquidity_rewards as lr
from app import venue_fees as vf
from src import orderflow_study as ofs
from src.mm_simulator import QuoteParams, compute_quotes

REPO_ROOT = Path(__file__).resolve().parents[1]
RESEARCH_DIR = REPO_ROOT / "docs" / "research"

MARKOUT_HORIZON_S = 300.0
MARKOUT_STALENESS_S = 300.0
MAX_QUOTE_SPREAD = 0.10
MID_BOUNDS = (0.05, 0.95)
MIN_SNAPSHOTS_PER_TOKEN = 20

#: Gamma-Kandidaten fuer den walk-forward Sweep.
GAMMA_GRID = (0.0, 0.04, 0.08, 0.16, 0.32)
#: Quote-Breiten fuer die Break-even-Frage (halber Spread in Preiseinheiten).
HALF_SPREAD_GRID = (0.005, 0.01, 0.02, 0.04, 0.08)
#: Schwelle, ab der die Buch-Imbalance als Richtungssignal gilt (wie in der
#: Order-Flow-Studie).
SIGNAL_THRESHOLD = 0.65
#: Quoting-Modi im Vergleich: ohne Signal, Signal zieht die Gegenseite, mild.
QUOTE_MODES = ("symmetric", "signal", "lean")
#: Fill-Modelle. touch und tape klammern, die Queue-Modelle liegen dazwischen
#: und unterscheiden sich nur in der Storno-Annahme.
FILL_MODELS = ("touch", "tape", "queue_front", "queue_back")
QUEUE_MODELS = ("queue_front", "queue_back")
#: Sekunden zwischen Buchbewegung und neuer Quote im Buch, fuer den Sweep.
LATENCY_GRID = (0.0, 0.25, 1.0, 5.0)
#: Preise sind auf 4 bis 6 Stellen gerundet; alles darunter ist derselbe Tick.
PRICE_EPS = 5e-7
#: Polymarket handelt je Markt auf einem dieser Raster und wechselt zur
#: Laufzeit; das Raster wird deshalb aus den beobachteten Preisen gelesen.
TICK_CANDIDATES = (0.01, 0.001, 0.0001)

# Validierte Referenzpalette (dataviz-Skill), Light-Mode
COLOR_POS = "#1baf7a"
COLOR_NEG = "#d6452a"
COLOR_NEUTRAL = "#2a78d6"
COLOR_MODEL = {"touch": "#2a78d6", "tape": "#1baf7a",
               "queue_front": "#d69a2a", "queue_back": "#8a5cd6"}
COLOR_SURFACE = "#fcfcfb"
COLOR_TEXT = "#0b0b0b"
COLOR_TEXT_2 = "#52514e"
COLOR_GRID = "#e5e4e0"


@dataclass(frozen=True, slots=True)
class MMFill:
    """One simulated fill, with the three mids the decomposition needs."""

    token_id: str
    day: str
    ts: float
    side: str            # "buy" oder "sell", unsere Seite
    price: float
    shares: float
    mid_at_fill: float
    mid_markout: float | None
    mid_final: float
    #: Sekunden zwischen Einstellen der Order und diesem Fill; None bei den
    #: Modellen, die keine ruhende Order kennen.
    wait_s: float | None = None
    #: True, wenn nach diesem Fill noch ein Rest der Order im Buch stand.
    partial: bool = False

    @property
    def signed_shares(self) -> float:
        return self.shares if self.side == "buy" else -self.shares

    @property
    def spread_capture_usd(self) -> float:
        """What we earned versus the mid at the moment of the fill."""
        edge = (self.mid_at_fill - self.price if self.side == "buy"
                else self.price - self.mid_at_fill)
        return edge * self.shares

    @property
    def markout_usd(self) -> float:
        """Adverse selection: how the mid moved against us over the horizon."""
        if self.mid_markout is None:
            return 0.0
        return self.signed_shares * (self.mid_markout - self.mid_at_fill)

    @property
    def late_drift_usd(self) -> float:
        """Everything after the markout horizon: the cost of carrying inventory."""
        reference = self.mid_markout if self.mid_markout is not None else self.mid_at_fill
        return self.signed_shares * (self.mid_final - reference)

    @property
    def terminal_usd(self) -> float:
        return self.signed_shares * (self.mid_final - self.price)


@dataclass
class Decomposition:
    """Additive PnL split over a set of fills, in USD."""

    fills: int = 0
    shares: float = 0.0
    notional_usd: float = 0.0
    spread_capture_usd: float = 0.0
    markout_usd: float = 0.0
    late_drift_usd: float = 0.0
    rebate_usd: float = 0.0
    fee_usd: float = 0.0
    inventory_abs_mean_usd: float = 0.0
    inventory_abs_max_usd: float = 0.0
    days: int = 0
    wait_total_s: float = 0.0
    waited_fills: int = 0
    partial_fills: int = 0

    @property
    def mark_to_mid_usd(self) -> float:
        """The identity: the three price terms reconstruct terminal PnL."""
        return self.spread_capture_usd + self.markout_usd + self.late_drift_usd

    @property
    def total_usd(self) -> float:
        return self.mark_to_mid_usd + self.rebate_usd - self.fee_usd

    def as_dict(self) -> dict:
        per_fill = (lambda value: round(value / self.fills, 6)) if self.fills else (lambda _: None)
        return {
            "fills": self.fills,
            "shares": round(self.shares, 2),
            "notional_usd": round(self.notional_usd, 2),
            "spread_capture_usd": round(self.spread_capture_usd, 4),
            "markout_usd": round(self.markout_usd, 4),
            "late_drift_usd": round(self.late_drift_usd, 4),
            "rebate_usd": round(self.rebate_usd, 4),
            "fee_usd": round(self.fee_usd, 4),
            "mark_to_mid_usd": round(self.mark_to_mid_usd, 4),
            "total_usd": round(self.total_usd, 4),
            "spread_capture_cents_per_fill": per_fill(100 * self.spread_capture_usd),
            "markout_cents_per_fill": per_fill(100 * self.markout_usd),
            "total_cents_per_fill": per_fill(100 * self.total_usd),
            "inventory_abs_mean_usd": round(self.inventory_abs_mean_usd, 2),
            "inventory_abs_max_usd": round(self.inventory_abs_max_usd, 2),
            "days": self.days,
            "mean_wait_s": (round(self.wait_total_s / self.waited_fills, 2)
                            if self.waited_fills else None),
            "partial_fill_share": (round(self.partial_fills / self.fills, 4)
                                   if self.fills else None),
        }


@dataclass
class TokenRun:
    token_id: str
    fills: list[MMFill] = field(default_factory=list)
    inventory_path: list[float] = field(default_factory=list)
    #: (ts, mid, quoted_bid, quoted_ask) je Snapshot, fuer die Reward-Rechnung.
    quote_path: list[tuple[float, float, float | None, float | None]] = field(
        default_factory=list)
    #: Nur die Queue-Modelle fuellen diese Zaehler.
    requotes: int = 0        # Aktivierungen, bei denen mindestens eine Seite neu stand
    queue_resets: int = 0    # Seiten, die wegen Preiswechsel ihren Platz verloren
    unknown_joins: int = 0   # Einreihungen an einer Stufe ohne beobachtete Tiefe

    def reward_samples(self) -> list[tuple[float, float, float | None, float | None, float]]:
        """Quotes weighted by how long each one stood, for the reward score."""
        samples = []
        for (ts, mid, bid, ask), (next_ts, _, _, _) in zip(self.quote_path,
                                                           self.quote_path[1:]):
            duration = next_ts - ts
            if duration > 0:
                samples.append((duration, mid, bid, ask, mid))
        return samples


def quote_sides(imbalance: float, threshold: float,
                mode: str = "symmetric") -> tuple[bool, bool]:
    """Which sides to show, given what the book is signalling.

    Returns ``(quote_bid, quote_ask)``.

    The order-flow study leaves one usable conclusion: the imbalance signal is
    directionally real but its gross edge, around a tenth of a cent, is far too
    small to pay a spread for. A maker does not pay the spread, it earns it, so
    the signal belongs in the quoting decision rather than in a taker order.

    Adverse selection is asymmetric by nature: a maker gets hurt on the side the
    market then runs away from. If the book is bid-heavy and the price tends to
    rise, the dangerous side is our ask, because being sold to means being short
    into a rise. ``signal`` mode therefore keeps the side the signal favours and
    pulls the other one. ``lean`` keeps both sides up and only pulls the
    dangerous one when the signal is extreme, which trades less protection for
    more fills.
    """
    if mode == "symmetric":
        return True, True
    bullish = imbalance >= threshold
    bearish = imbalance <= 1.0 - threshold
    if mode == "signal":
        if bullish:
            return True, False
        if bearish:
            return False, True
        return True, True
    if mode == "lean":
        extreme = max(threshold, 1.0 - (1.0 - threshold) / 2.0)
        if imbalance >= extreme:
            return True, False
        if imbalance <= 1.0 - extreme:
            return False, True
        return True, True
    raise ValueError(f"unbekannter Quoting-Modus: {mode}")


def touch_fills(bid: float | None, ask: float | None,
                next_bid: float, next_ask: float) -> list[str]:
    """Pessimistic model: only a crossing touch fills us."""
    out: list[str] = []
    if bid is not None and next_ask <= bid:
        out.append("buy")
    if ask is not None and next_bid >= ask:
        out.append("sell")
    return out


def tape_fills(bid: float | None, ask: float | None,
               prints: list[tuple[float, float, float]]) -> list[tuple[str, float]]:
    """Optimistic model: a public print through our price fills us.

    ``prints`` is a list of ``(ts, price, signed_usd)`` in the interval. A
    taker SELL (negative signed flow) hits bids, so it can fill our resting
    bid at or below its price; a taker BUY lifts offers and can fill our ask.

    Each side fills at most once per interval: our quote has a finite size, and
    once it is taken it is gone until we re-post at the next snapshot. Without
    that limit a busy token fills the same 50-dollar quote on every print in
    the interval and the inventory cap becomes meaningless.
    """
    out: list[tuple[str, float]] = []
    filled: set[str] = set()
    for _, price, signed_usd in prints:
        if signed_usd < 0 and bid is not None and price <= bid and "buy" not in filled:
            out.append(("buy", bid))
            filled.add("buy")
        elif signed_usd > 0 and ask is not None and price >= ask and "sell" not in filled:
            out.append(("sell", ask))
            filled.add("sell")
        if len(filled) == 2:
            break
    return out


@dataclass
class RestingOrder:
    """One paper order standing in the book, with what we know of its line.

    ``queue_ahead`` is the number of shares that must trade or cancel before
    a print reaches us. ``None`` means the recorder never showed our level
    and the back variant refuses to guess. ``level_seen`` is the resting
    size at our price the last time it was observable, so a shrink between
    two snapshots can be split into prints (known) and cancels (assumed).
    """

    side: str
    price: float
    shares: float
    quote_mid: float
    posted_ts: float
    queue_ahead: float | None
    level_seen: float | None
    printed_at_level: float = 0.0


def level_size(levels: tuple[tuple[float, float], ...],
               price: float) -> float | None:
    """Resting size at exactly ``price``, or None if the ladder has no such level."""
    for level_price, size in levels:
        if abs(level_price - price) < PRICE_EPS:
            return size
    return None


def infer_tick(*prices: float | None) -> float:
    """Coarsest grid every observed price sits on, finest candidate as fallback."""
    values = [p for p in prices if p is not None]
    if not values:
        return TICK_CANDIDATES[-1]
    for tick in TICK_CANDIDATES:
        if all(abs(round(v / tick) * tick - v) < 1e-9 for v in values):
            return tick
    return TICK_CANDIDATES[-1]


def snap_to_grid(bid: float | None, ask: float | None,
                 tick: float) -> tuple[float | None, float | None]:
    """Rest a quote where an order can actually rest: bid down, ask up.

    A quote at mid minus a half spread usually lands between two ticks. The
    touch and tape models let it fill there, which is harmless for them but
    fatal for a queue model: no print ever trades at a price nobody can
    post, so there would never be a line to stand in. Rounding away from
    the mid is the conservative direction, it never buys more edge than the
    quote asked for.
    """
    snapped_bid = None if bid is None else round(math.floor(bid / tick + 1e-9) * tick, 6)
    snapped_ask = None if ask is None else round(math.ceil(ask / tick - 1e-9) * tick, 6)
    if snapped_bid is not None and snapped_bid <= 0:
        snapped_bid = None
    if snapped_ask is not None and snapped_ask >= 1:
        snapped_ask = None
    return snapped_bid, snapped_ask


def _improves(side: str, price: float, best: float | None) -> bool:
    if best is None:
        return True
    return price > best + PRICE_EPS if side == "buy" else price < best - PRICE_EPS


def join_queue(levels: tuple[tuple[float, float], ...], best: float | None,
               price: float, side: str, variant: str
               ) -> tuple[float | None, float | None]:
    """(queue_ahead, level_seen) for an order posted now at ``price``.

    Improving on the touch means nobody rests at our price yet. Joining a
    level the ladder shows means everyone there was first. A level deeper
    than the ladder is the blind spot: the front variant assumes it empty,
    the back variant refuses to fill there until the level has been seen.
    """
    if _improves(side, price, best):
        return 0.0, 0.0
    size = level_size(levels, price)
    if size is not None:
        return size, size
    return (0.0 if variant == "front" else None), None


def queue_fills(order: RestingOrder, prints: list[tuple[float, float, float]],
                variant: str) -> list[tuple[float, float]]:
    """Fills of ``order`` from prints in time order, as (ts, shares). Mutates.

    A print at our price consumes the line ahead of us first and reaches us
    with whatever is left, so fills are partial by nature. A print through
    a worse price than ours means price priority already emptied our level:
    that fills the whole remainder regardless of what was assumed ahead.
    Taker buys never touch a resting bid, taker sells never a resting ask.
    """
    out: list[tuple[float, float]] = []
    for ts, price, signed_usd in prints:
        if order.shares <= 0:
            break
        if order.side == "buy":
            if signed_usd >= 0 or price > order.price + PRICE_EPS:
                continue
            swept = price < order.price - PRICE_EPS
        else:
            if signed_usd <= 0 or price < order.price - PRICE_EPS:
                continue
            swept = price > order.price + PRICE_EPS
        if swept:
            filled = order.shares
            order.queue_ahead = 0.0
        else:
            if order.queue_ahead is None:
                continue
            size = abs(signed_usd) / price if price > 0 else 0.0
            ahead = min(order.queue_ahead, size)
            order.queue_ahead -= ahead
            filled = min(order.shares, size - ahead)
            order.printed_at_level += ahead + max(filled, 0.0)
            if filled <= 0:
                continue
        order.shares -= filled
        out.append((ts, filled))
    return out


def refresh_queue(order: RestingOrder, levels: tuple[tuple[float, float], ...],
                  best: float | None, variant: str) -> None:
    """Fold a new snapshot of the ladder into what we know about our line.

    Prints at our level were already subtracted as they happened. Whatever
    else shrank since the last look is a cancel, and which end of the line it
    left from is exactly the assumption the two variants differ in.
    """
    size_now = level_size(levels, order.price)
    if size_now is None:
        if _improves(order.side, order.price, best):
            order.queue_ahead = 0.0
            order.level_seen = 0.0
        order.printed_at_level = 0.0
        return
    if order.level_seen is None:
        if order.queue_ahead is None:
            order.queue_ahead = size_now
        else:
            order.queue_ahead = min(order.queue_ahead, size_now)
    else:
        decline = order.level_seen - order.printed_at_level - size_now
        if decline > 0 and variant == "front":
            order.queue_ahead = max(0.0, order.queue_ahead - decline)
        if order.queue_ahead is not None:
            order.queue_ahead = min(order.queue_ahead, size_now)
    order.level_seen = size_now
    order.printed_at_level = 0.0


def _prints_between(trades: list[ofs.TradePoint], start: float,
                    end: float) -> list[tuple[float, float, float]]:
    if not trades:
        return []
    index = bisect_left([t.ts for t in trades], start)
    out: list[tuple[float, float, float]] = []
    for trade in trades[index:]:
        if trade.ts > end:
            break
        out.append((trade.ts, trade.price, trade.signed_usd))
    return out


def _mid_at(series: list[ofs.BookPoint], mids: list[float], stamps: list[float],
            target: float, staleness: float) -> float | None:
    index = bisect_left(stamps, target)
    if index >= len(stamps) or stamps[index] - target > staleness:
        return None
    return mids[index]


def run_token(token_id: str, series: list[ofs.BookPoint],
              trades: list[ofs.TradePoint], params: QuoteParams,
              fill_model: str = "touch",
              markout_horizon_s: float = MARKOUT_HORIZON_S,
              quote_mode: str = "symmetric",
              signal_threshold: float = SIGNAL_THRESHOLD) -> TokenRun:
    """Quote across one token's series and record every fill.

    ``quote_mode`` selects how the book imbalance feeds the quoting decision;
    see :func:`quote_sides`.
    """
    run = TokenRun(token_id=token_id)
    stamps = [p.ts for p in series]
    mids = [p.mid for p in series]
    if len(series) < 2:
        return run
    mid_final = mids[-1]

    inventory = 0.0
    quoted_bid: float | None = None
    quoted_ask: float | None = None
    # Referenz-Mid ist der Mid, gegen den wir die Quote gestellt haben, nicht
    # der Mid nach der Bewegung, die uns gefuellt hat. Sonst wandert die ganze
    # Adverse Selektion in den Spread-Ertrag und macht ihn per Konstruktion
    # negativ.
    quote_mid: float | None = None
    previous_ts = series[0].ts

    for point in series:
        best_bid = point.mid - point.spread / 2.0
        best_ask = point.mid + point.spread / 2.0
        if point.spread <= 0 or point.spread > MAX_QUOTE_SPREAD:
            quoted_bid = quoted_ask = None
            previous_ts = point.ts
            continue

        if fill_model == "tape":
            prints = _prints_between(trades, previous_ts, point.ts)
            events = tape_fills(quoted_bid, quoted_ask, prints)
        else:
            events = [(side, quoted_bid if side == "buy" else quoted_ask)
                      for side in touch_fills(quoted_bid, quoted_ask,
                                              best_bid, best_ask)]

        for side, price in events:
            if price is None or price <= 0 or quote_mid is None:
                continue
            shares = round(params.quote_usd / price, 2)
            inventory += shares if side == "buy" else -shares
            run.fills.append(MMFill(
                token_id=token_id, day=point.day, ts=point.ts, side=side,
                price=price, shares=shares, mid_at_fill=quote_mid,
                mid_markout=_mid_at(series, mids, stamps,
                                    point.ts + markout_horizon_s,
                                    MARKOUT_STALENESS_S),
                mid_final=mid_final))

        inventory_usd = inventory * point.mid
        run.inventory_path.append(inventory_usd)
        if MID_BOUNDS[0] < point.mid < MID_BOUNDS[1]:
            quoted_bid, quoted_ask = compute_quotes(point.mid, best_bid, best_ask,
                                                    inventory_usd, params)
            show_bid, show_ask = quote_sides(point.imbalance, signal_threshold,
                                             quote_mode)
            if not show_bid:
                quoted_bid = None
            if not show_ask:
                quoted_ask = None
            quote_mid = point.mid
        else:
            quoted_bid = quoted_ask = None
            quote_mid = None
        run.quote_path.append((point.ts, point.mid, quoted_bid, quoted_ask))
        previous_ts = point.ts
    return run


def run_token_queue(token_id: str, series: list[ofs.BookPoint],
                    trades: list[ofs.TradePoint], params: QuoteParams,
                    variant: str = "front", latency_s: float = 0.0,
                    markout_horizon_s: float = MARKOUT_HORIZON_S,
                    quote_mode: str = "symmetric",
                    signal_threshold: float = SIGNAL_THRESHOLD) -> TokenRun:
    """Quote one token with resting orders that keep, and lose, their place.

    Unlike :func:`run_token`, an order that keeps its price across snapshots
    keeps its position in line and its remaining size; only a re-price
    cancels and re-joins at the back. Quotes rest on the market's tick grid
    (bid rounded down, ask up), because a line can only form at a price
    someone can post at. With ``latency_s`` the decision taken
    at a snapshot lands that many seconds later, and until it lands the old
    order stays live and can be picked; a decision made while one is still
    in flight is dropped, as a slow system would.
    """
    run = TokenRun(token_id=token_id)
    if len(series) < 2:
        return run
    stamps = [p.ts for p in series]
    mids = [p.mid for p in series]
    mid_final = mids[-1]
    inventory = 0.0
    resting: dict[str, RestingOrder | None] = {"buy": None, "sell": None}
    pending: dict | None = None
    previous_ts = series[0].ts

    def activate(pend: dict, ts: float) -> None:
        posted = False
        for side, price in (("buy", pend["bid"]), ("sell", pend["ask"])):
            current = resting[side]
            if price is None:
                resting[side] = None
                continue
            if current is not None and abs(current.price - price) < PRICE_EPS:
                continue
            if current is not None:
                run.queue_resets += 1
            levels = pend["bid_levels"] if side == "buy" else pend["ask_levels"]
            best = pend["best_bid"] if side == "buy" else pend["best_ask"]
            ahead, seen = join_queue(levels, best, price, side, variant)
            if ahead is None:
                run.unknown_joins += 1
            resting[side] = RestingOrder(
                side=side, price=price, shares=round(params.quote_usd / price, 2),
                quote_mid=pend["quote_mid"], posted_ts=ts,
                queue_ahead=ahead, level_seen=seen)
            posted = True
        if posted:
            run.requotes += 1

    def settle(side: str, order: RestingOrder, day: str,
               prints: list[tuple[float, float, float]]) -> None:
        nonlocal inventory
        for fill_ts, shares in queue_fills(order, prints, variant):
            inventory += shares if side == "buy" else -shares
            run.fills.append(MMFill(
                token_id=token_id, day=day, ts=fill_ts, side=side,
                price=order.price, shares=shares, mid_at_fill=order.quote_mid,
                mid_markout=_mid_at(series, mids, stamps,
                                    fill_ts + markout_horizon_s,
                                    MARKOUT_STALENESS_S),
                mid_final=mid_final, wait_s=fill_ts - order.posted_ts,
                partial=order.shares > 0))
        if order.shares <= 0:
            resting[side] = None

    for point in series:
        best_bid = point.bid_levels[0][0] if point.bid_levels else point.mid - point.spread / 2.0
        best_ask = point.ask_levels[0][0] if point.ask_levels else point.mid + point.spread / 2.0

        for single in _prints_between(trades, previous_ts, point.ts):
            if pending is not None and single[0] >= pending["activate_ts"]:
                activate(pending, pending["activate_ts"])
                pending = None
            for side in ("buy", "sell"):
                order = resting[side]
                if order is not None:
                    settle(side, order, point.day, [single])
        if pending is not None and point.ts >= pending["activate_ts"]:
            activate(pending, pending["activate_ts"])
            pending = None

        for side in ("buy", "sell"):
            order = resting[side]
            if order is not None:
                refresh_queue(order,
                              point.bid_levels if side == "buy" else point.ask_levels,
                              best_bid if side == "buy" else best_ask, variant)

        inventory_usd = inventory * point.mid
        run.inventory_path.append(inventory_usd)
        quotable = (0 < point.spread <= MAX_QUOTE_SPREAD
                    and MID_BOUNDS[0] < point.mid < MID_BOUNDS[1])
        if quotable:
            bid, ask = compute_quotes(point.mid, best_bid, best_ask, inventory_usd, params)
            tick = infer_tick(best_bid, best_ask,
                              *(price for price, _ in point.bid_levels[:2]),
                              *(price for price, _ in point.ask_levels[:2]))
            bid, ask = snap_to_grid(bid, ask, tick)
            show_bid, show_ask = quote_sides(point.imbalance, signal_threshold, quote_mode)
            if not show_bid:
                bid = None
            if not show_ask:
                ask = None
            quote_mid: float | None = point.mid
        else:
            bid = ask = None
            quote_mid = None
        decision = {
            "activate_ts": point.ts + latency_s, "bid": bid, "ask": ask,
            "quote_mid": quote_mid, "bid_levels": point.bid_levels,
            "ask_levels": point.ask_levels, "best_bid": best_bid,
            "best_ask": best_ask,
        }
        if latency_s <= 0:
            activate(decision, point.ts)
        elif pending is None:
            pending = decision
        run.quote_path.append((point.ts, point.mid, bid, ask))
        previous_ts = point.ts
    return run


def decompose(runs: list[TokenRun], category: str = "sports",
              rebate_share: float = vf.POLYMARKET_MAKER_REBATE_SHARE,
              venue: str = "polymarket") -> Decomposition:
    """Aggregate fills into the additive split, including maker economics."""
    out = Decomposition()
    inventory_values: list[float] = []
    days: set[str] = set()
    for run in runs:
        inventory_values.extend(abs(v) for v in run.inventory_path)
        for fill in run.fills:
            out.fills += 1
            out.shares += fill.shares
            out.notional_usd += fill.shares * fill.price
            out.spread_capture_usd += fill.spread_capture_usd
            out.markout_usd += fill.markout_usd
            out.late_drift_usd += fill.late_drift_usd
            days.add(fill.day)
            if fill.wait_s is not None:
                out.wait_total_s += fill.wait_s
                out.waited_fills += 1
            if fill.partial:
                out.partial_fills += 1
            if venue.lower().startswith("kalshi"):
                out.fee_usd += vf.kalshi_maker_fee(fill.shares, fill.price)
            else:
                out.rebate_usd += vf.polymarket_maker_rebate(
                    fill.shares, fill.price, category, rebate_share)
    if inventory_values:
        out.inventory_abs_mean_usd = sum(inventory_values) / len(inventory_values)
        out.inventory_abs_max_usd = max(inventory_values)
    out.days = len(days)
    return out


def run_experiment(books: dict[str, list[ofs.BookPoint]],
                   tape: dict[str, list[ofs.TradePoint]],
                   params: QuoteParams, fill_model: str = "touch",
                   category: str = "sports", quote_mode: str = "symmetric",
                   latency_s: float = 0.0
                   ) -> tuple[Decomposition, list[TokenRun]]:
    if fill_model in QUEUE_MODELS:
        variant = fill_model.split("_", 1)[1]
        runs = [run_token_queue(token, series, tape.get(token, []), params,
                                variant=variant, latency_s=latency_s,
                                quote_mode=quote_mode)
                for token, series in books.items()
                if len(series) >= MIN_SNAPSHOTS_PER_TOKEN]
    elif fill_model in ("touch", "tape"):
        runs = [run_token(token, series, tape.get(token, []), params, fill_model,
                          quote_mode=quote_mode)
                for token, series in books.items()
                if len(series) >= MIN_SNAPSHOTS_PER_TOKEN]
    else:
        raise ValueError(f"unbekanntes Fill-Modell: {fill_model}")
    return decompose(runs, category=category), runs


def queue_stats(runs: list[TokenRun]) -> dict:
    """What the queue models learned about standing in line, summed over tokens."""
    return {
        "requotes": sum(r.requotes for r in runs),
        "queue_resets": sum(r.queue_resets for r in runs),
        "unknown_joins": sum(r.unknown_joins for r in runs),
    }


def latency_sweep(books: dict[str, list[ofs.BookPoint]],
                  tape: dict[str, list[ofs.TradePoint]], base: QuoteParams,
                  fill_model: str, latencies: tuple[float, ...] = LATENCY_GRID,
                  category: str = "sports") -> list[dict]:
    """How much of the markout comes back when the requote lands late.

    Zero latency is the seconds-data result: every book move is answered at
    once. Each step up keeps the old quote live that much longer, which is
    the window in which it can be picked on a stale price. The slope of
    markout per fill over this table is the price of being slow.
    """
    rows = []
    for latency in latencies:
        decomposition, runs = run_experiment(books, tape, base, fill_model,
                                             category, latency_s=latency)
        rows.append({"latency_s": latency, **decomposition.as_dict(),
                     **queue_stats(runs)})
    return rows


def reward_estimate(runs: list[TokenRun], quote_usd: float,
                    pool_usd: float = lr.POOL_MEDIAN_USD) -> lr.RewardEstimate:
    """Liquidity-reward score of a whole quoting run, pooled across tokens.

    Each token is one market for the program, so the per-market payout is
    multiplied by how many markets we quoted rather than shared between them.
    """
    samples: list[tuple[float, float, float | None, float | None, float]] = []
    active = 0
    for run in runs:
        token_samples = run.reward_samples()
        if token_samples:
            active += 1
            samples.extend(token_samples)
    if not samples:
        return lr.RewardEstimate(0.0, 0.0, 0.0, pool_usd, 0)
    # Der Score ist ein Zeitmittel; die Dauer darf sich ueber die Tokens nicht
    # aufsummieren, sonst waere ein Portfolio automatisch laenger am Markt.
    estimate = lr.estimate_from_quotes(samples, quote_usd=quote_usd,
                                       pool_usd=pool_usd, markets=active)
    return lr.RewardEstimate(
        hours_quoted=estimate.hours_quoted / max(1, active),
        mean_score=estimate.mean_score,
        qualifying_share=estimate.qualifying_share,
        pool_usd_per_day=pool_usd,
        markets=active,
    )


def quote_mode_comparison(books: dict[str, list[ofs.BookPoint]],
                          tape: dict[str, list[ofs.TradePoint]],
                          base: QuoteParams, fill_model: str = "touch",
                          category: str = "sports",
                          modes: tuple[str, ...] = QUOTE_MODES,
                          latency_s: float = 0.0) -> list[dict]:
    """Does letting the signal decide which side to show reduce adverse selection?

    Symmetric quoting is the control. The number to watch is markout per fill,
    not total PnL: pulling a side also removes fills, so a mode can look better
    simply by trading less. Markout per fill isolates whether the fills that do
    happen are less poisoned.
    """
    rows = []
    for mode in modes:
        decomposition, runs = run_experiment(books, tape, base, fill_model,
                                             category, quote_mode=mode,
                                             latency_s=latency_s)
        daily = per_day_totals(runs, category)
        data = decomposition.as_dict()
        rows.append({
            "quote_mode": mode,
            **data,
            "daily_ci95_usd": ofs.block_bootstrap_ci(list(daily.values()),
                                                     list(daily.keys())),
        })
    return rows


def gamma_sweep(books: dict[str, list[ofs.BookPoint]],
                tape: dict[str, list[ofs.TradePoint]], base: QuoteParams,
                gammas: tuple[float, ...] = GAMMA_GRID,
                fill_model: str = "touch", category: str = "sports",
                latency_s: float = 0.0) -> list[dict]:
    """Score each skew strength. Gamma 0 is the no-skew control."""
    rows = []
    for gamma in gammas:
        params = QuoteParams(half_spread=base.half_spread, gamma=gamma,
                             quote_usd=base.quote_usd,
                             inventory_cap_usd=base.inventory_cap_usd)
        decomposition, _ = run_experiment(books, tape, params, fill_model, category,
                                          latency_s=latency_s)
        rows.append({"gamma": gamma, **decomposition.as_dict()})
    return rows


def half_spread_sweep(books: dict[str, list[ofs.BookPoint]],
                      tape: dict[str, list[ofs.TradePoint]], base: QuoteParams,
                      half_spreads: tuple[float, ...] = HALF_SPREAD_GRID,
                      fill_model: str = "touch",
                      category: str = "sports",
                      latency_s: float = 0.0) -> list[dict]:
    """How wide must the quote be before the spread earned beats the markout?

    This is the break-even question for the whole strategy. Spread capture
    grows with the quoted width while adverse selection is driven by how far
    the market moves, so somewhere there is a width where the two cross - or
    the fills dry up before they do, which is itself the answer.
    """
    rows = []
    for half_spread in half_spreads:
        params = QuoteParams(half_spread=half_spread, gamma=base.gamma,
                             quote_usd=base.quote_usd,
                             inventory_cap_usd=base.inventory_cap_usd)
        decomposition, _ = run_experiment(books, tape, params, fill_model, category,
                                          latency_s=latency_s)
        data = decomposition.as_dict()
        capture = decomposition.spread_capture_usd
        markout = decomposition.markout_usd
        data["capture_over_markout"] = (
            round(capture / abs(markout), 4) if markout else None)
        rows.append({"half_spread": half_spread, **data})
    return rows


def split_books_by_day(books: dict[str, list[ofs.BookPoint]],
                       train_share: float = 0.6
                       ) -> tuple[dict[str, list[ofs.BookPoint]],
                                  dict[str, list[ofs.BookPoint]]]:
    """Split the book series by calendar day for an honest parameter choice."""
    days = sorted({p.day for series in books.values() for p in series})
    if len(days) < 2:
        return books, {}
    cut = max(1, int(len(days) * train_share))
    train_days = set(days[:cut])
    train: dict[str, list[ofs.BookPoint]] = {}
    test: dict[str, list[ofs.BookPoint]] = {}
    for token, series in books.items():
        early = [p for p in series if p.day in train_days]
        late = [p for p in series if p.day not in train_days]
        if early:
            train[token] = early
        if late:
            test[token] = late
    return train, test


def walk_forward_gamma(books: dict[str, list[ofs.BookPoint]],
                       tape: dict[str, list[ofs.TradePoint]], base: QuoteParams,
                       gammas: tuple[float, ...] = GAMMA_GRID,
                       fill_model: str = "touch",
                       category: str = "sports",
                       latency_s: float = 0.0) -> dict:
    """Pick gamma on the early days, then report what it did on the later ones.

    A skew parameter tuned and scored on the same days will always look good.
    The number that matters is the out-of-sample column.
    """
    train, test = split_books_by_day(books)
    train_rows = gamma_sweep(train, tape, base, gammas, fill_model, category,
                             latency_s=latency_s)
    scored = [row for row in train_rows if row["fills"] > 0]
    best = max(scored, key=lambda r: r["total_usd"]) if scored else None
    result = {"train": train_rows, "chosen_gamma": best["gamma"] if best else None,
              "test": None, "control_test": None}
    if best is None or not test:
        return result
    chosen = QuoteParams(half_spread=base.half_spread, gamma=best["gamma"],
                         quote_usd=base.quote_usd,
                         inventory_cap_usd=base.inventory_cap_usd)
    control = QuoteParams(half_spread=base.half_spread, gamma=0.0,
                          quote_usd=base.quote_usd,
                          inventory_cap_usd=base.inventory_cap_usd)
    result["test"] = run_experiment(test, tape, chosen, fill_model, category,
                                    latency_s=latency_s)[0].as_dict()
    result["control_test"] = run_experiment(test, tape, control, fill_model,
                                            category, latency_s=latency_s)[0].as_dict()
    return result


def per_day_totals(runs: list[TokenRun], category: str = "sports") -> dict[str, float]:
    """Total PnL per calendar day, the unit a block bootstrap resamples."""
    by_day: dict[str, list[MMFill]] = {}
    for run in runs:
        for fill in run.fills:
            by_day.setdefault(fill.day, []).append(fill)
    return {
        day: decompose([TokenRun(token_id="day", fills=fills)],
                       category=category).total_usd
        for day, fills in by_day.items()
    }


def run_study(directory: str | Path, stream: bool = False,
              half_spread: float = 0.01, gamma: float = 0.08,
              quote_usd: float = 50.0, cap_usd: float = 250.0,
              category: str = "sports",
              gammas: tuple[float, ...] = GAMMA_GRID,
              fill_models: tuple[str, ...] = ("touch", "tape"),
              latency_s: float = 0.0,
              latencies: tuple[float, ...] = LATENCY_GRID,
              day_from: str | None = None,
              day_to: str | None = None) -> dict:
    """Full decomposition study over one data directory, chosen fill models.

    ``latency_s`` is the requote delay every experiment runs with; the queue
    models additionally sweep ``latencies`` from zero so the cost of being
    slow is a table rather than a single assumption. ``day_from``/``day_to``
    restrict the days loaded, which is how a parameter choice frozen on one
    window gets scored on another.
    """
    books = ofs.load_books(directory, stream=stream, day_from=day_from, day_to=day_to)
    tape = ofs.load_tape(directory, stream=stream, day_from=day_from, day_to=day_to)
    base = QuoteParams(half_spread=half_spread, gamma=gamma,
                       quote_usd=quote_usd, inventory_cap_usd=cap_usd)
    results: dict = {
        "source": str(directory), "stream": stream,
        "tokens": len(books),
        "snapshots": sum(len(v) for v in books.values()),
        "tape_prints": sum(len(v) for v in tape.values()),
        "days": sorted({p.day for v in books.values() for p in v}),
        "day_window": {"from": day_from, "to": day_to},
        "params": {"half_spread": half_spread, "gamma": gamma,
                   "quote_usd": quote_usd, "cap_usd": cap_usd,
                   "latency_s": latency_s},
        "category": category,
        "fee_model_version": vf.FEE_MODEL_VERSION,
        "fill_models": {},
    }
    for fill_model in fill_models:
        decomposition, runs = run_experiment(books, tape, base, fill_model, category,
                                             latency_s=latency_s)
        daily = per_day_totals(runs, category)
        ci = ofs.block_bootstrap_ci(list(daily.values()), list(daily.keys()))
        rewards = reward_estimate(runs, quote_usd)
        entry = {
            "decomposition": decomposition.as_dict(),
            "liquidity_rewards": rewards.as_dict(),
            "total_with_rewards_usd": {
                str(row["competition_multiple"]):
                    round(decomposition.total_usd + row["reward_usd"], 2)
                for row in rewards.sensitivity()
            },
            "daily_total_usd": {day: round(value, 4)
                                for day, value in sorted(daily.items())},
            "daily_ci95_usd": ci,
            "gamma_sweep": gamma_sweep(books, tape, base, gammas, fill_model, category,
                                       latency_s=latency_s),
            "half_spread_sweep": half_spread_sweep(books, tape, base,
                                                   fill_model=fill_model,
                                                   category=category,
                                                   latency_s=latency_s),
            "quote_modes": quote_mode_comparison(books, tape, base, fill_model,
                                                 category, latency_s=latency_s),
            "walk_forward": walk_forward_gamma(books, tape, base, gammas,
                                               fill_model, category,
                                               latency_s=latency_s),
        }
        if fill_model in QUEUE_MODELS:
            entry["queue"] = queue_stats(runs)
            entry["latency_sweep"] = latency_sweep(books, tape, base, fill_model,
                                                   latencies, category)
        results["fill_models"][fill_model] = entry
    return results


def render_png(results: dict, out_path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.0, 5.0), dpi=150,
                                   facecolor=COLOR_SURFACE)
    fig.subplots_adjust(top=0.80, bottom=0.16, left=0.09, right=0.98, wspace=0.24)
    for ax in (ax1, ax2):
        ax.set_facecolor(COLOR_SURFACE)
        ax.grid(axis="y", color=COLOR_GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        for spine in ("left", "bottom"):
            ax.spines[spine].set_color(COLOR_GRID)
        ax.tick_params(colors=COLOR_TEXT_2, labelsize=9)

    labels = ["Spread\nearned", "Markout\n(adverse\nselection)",
              "Late\ndrift", "Rebate", "Total"]
    keys = ["spread_capture_usd", "markout_usd", "late_drift_usd",
            "rebate_usd", "total_usd"]
    models = list(results["fill_models"])
    width = 0.8 / max(1, len(models))
    for index, model in enumerate(models):
        offset = (index - (len(models) - 1) / 2.0) * width
        data = results["fill_models"][model]["decomposition"]
        values = [data[k] for k in keys]
        colors = [COLOR_POS if v >= 0 else COLOR_NEG for v in values]
        positions = [i + offset for i in range(len(keys))]
        ax1.bar(positions, values, width=width, color=colors,
                edgecolor=COLOR_MODEL.get(model, COLOR_NEUTRAL), linewidth=1.2)
    ax1.axhline(0, color=COLOR_TEXT_2, linewidth=1.0)
    ax1.set_xticks(range(len(labels)))
    ax1.set_xticklabels(labels, fontsize=8)
    ax1.set_ylabel("USD", color=COLOR_TEXT_2, fontsize=9)
    ax1.set_title(f"PnL decomposition (left to right: {', '.join(models)})",
                  color=COLOR_TEXT, fontsize=11, loc="left")

    for model in models:
        rows = results["fill_models"][model]["gamma_sweep"]
        ax2.plot([r["gamma"] for r in rows], [r["total_usd"] for r in rows],
                 color=COLOR_MODEL.get(model, COLOR_NEUTRAL), linewidth=2.0,
                 marker="o", markersize=4, label=f"{model} model")
    ax2.axhline(0, color=COLOR_TEXT_2, linewidth=1.0)
    ax2.set_xlabel("gamma (strength of the inventory skew)", color=COLOR_TEXT_2,
                   fontsize=9)
    ax2.set_ylabel("Total PnL (USD)", color=COLOR_TEXT_2, fontsize=9)
    ax2.set_title("Effect of skew strength", color=COLOR_TEXT, fontsize=11,
                  loc="left")
    ax2.legend(frameon=False, fontsize=9, labelcolor=COLOR_TEXT_2)

    params = results["params"]
    fig.suptitle(
        f"Paper market-making PnL decomposition — {results['tokens']} tokens, "
        f"{len(results['days'])} days, half spread {params['half_spread']}, "
        f"quote {params['quote_usd']} USD, cap {params['cap_usd']} USD",
        color=COLOR_TEXT, fontsize=11.5, x=0.02, y=0.95, ha="left")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, facecolor=COLOR_SURFACE)
    plt.close(fig)


def _fmt(value, spec="{:+.2f}") -> str:
    return "-" if value is None else spec.format(value)


def _markdown(results: dict, tag: str) -> str:
    days = results["days"]
    params = results["params"]
    models = list(results["fill_models"])
    lines = [
        f"# Paper market-making PnL decomposition ({tag})",
        "",
        f"Source: {results['source']} "
        f"({'stream, event driven' if results['stream'] else 'REST, 120s grid'}), "
        f"{results['tokens']} tokens, {results['snapshots']:,} snapshots, "
        f"{results['tape_prints']:,} tape prints, {len(days)} days "
        f"({days[0] if days else '-'} to {days[-1] if days else '-'}).",
        "",
        f"Quoting: half spread {params['half_spread']}, gamma {params['gamma']}, "
        f"quote {params['quote_usd']} USD, inventory cap {params['cap_usd']} USD"
        + (f", requote latency {params['latency_s']} s" if params.get("latency_s") else "")
        + f". Maker economics for category {results['category']}, fee schedule "
        f"{results['fee_model_version']}.",
        "",
        "| Item | " + " | ".join(f"{m} model (USD)" for m in models) + " |",
        "|---|" + "---|" * len(models),
    ]
    rows = [
        ("Fills", "fills", "{:,.0f}"),
        ("Spread earned", "spread_capture_usd", "{:+.2f}"),
        ("Markout 5min (adverse selection)", "markout_usd", "{:+.2f}"),
        ("Late drift (inventory)", "late_drift_usd", "{:+.2f}"),
        ("Maker rebate", "rebate_usd", "{:+.2f}"),
        ("Mark-to-mid (identity)", "mark_to_mid_usd", "{:+.2f}"),
        ("Total", "total_usd", "{:+.2f}"),
        ("Spread earned per fill (cents)", "spread_capture_cents_per_fill", "{:+.3f}"),
        ("Markout per fill (cents)", "markout_cents_per_fill", "{:+.3f}"),
        ("Result per fill (cents)", "total_cents_per_fill", "{:+.3f}"),
        ("Mean |inventory| (USD)", "inventory_abs_mean_usd", "{:.2f}"),
        ("Max |inventory| (USD)", "inventory_abs_max_usd", "{:.2f}"),
        ("Mean wait until fill (s)", "mean_wait_s", "{:.1f}"),
        ("Partial fills (share)", "partial_fill_share", "{:.1%}"),
    ]
    for label, key, fmt in rows:
        cells = [_fmt(results["fill_models"][m]["decomposition"].get(key), fmt)
                 for m in models]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")

    for model in models:
        entry = results["fill_models"][model]
        ci = entry["daily_ci95_usd"]
        walk = entry["walk_forward"]
        lines += [
            "",
            f"## {model} fill model",
            "",
            f"Block-bootstrap 95% CI at day level for the daily total: "
            f"{ci if ci else 'not computable'} USD.",
            "",
            "| gamma | Fills | Spread earned | Markout | Total | mean \\|inventory\\| |",
            "|---|---|---|---|---|---|",
        ]
        for row in entry["gamma_sweep"]:
            lines.append(
                f"| {row['gamma']:.2f} | {row['fills']:,} | "
                f"{_fmt(row['spread_capture_usd'])} | {_fmt(row['markout_usd'])} | "
                f"{_fmt(row['total_usd'])} | {_fmt(row['inventory_abs_mean_usd'], '{:.2f}')} |")
        rewards = entry["liquidity_rewards"]
        lines += [
            "",
            f"Liquidity rewards: on average "
            f"{rewards['qualifying_share']:.0%} of quoting time inside the "
            f"reward band, {rewards['markets']} markets, pool assumption "
            f"{rewards['pool_usd_per_day']} USD per market per day "
            f"(median of the {lr.MARKETS_WITH_POOL:,} markets carrying a pool, "
            f"as of {rewards['snapshot_date']}).",
            "",
            "| Competition (multiple of own score) | own share | "
            "Reward (USD) | Total incl. reward (USD) |",
            "|---|---|---|---|",
        ]
        for row in rewards["sensitivity"]:
            total = entry["total_with_rewards_usd"][str(row["competition_multiple"])]
            lines.append(
                f"| {row['competition_multiple']:.0f}x | "
                f"{row['our_share']:.1%} | {_fmt(row['reward_usd'])} | "
                f"{_fmt(total)} |")

        lines += [
            "",
            "| Quoting mode | Fills | Spread earned per fill (c) | Markout per "
            "fill (c) | Total (USD) | CI95 daily total |",
            "|---|---|---|---|---|---|",
        ]
        for row in entry["quote_modes"]:
            lines.append(
                f"| {row['quote_mode']} | {row['fills']:,} | "
                f"{_fmt(row['spread_capture_cents_per_fill'], '{:+.2f}')} | "
                f"{_fmt(row['markout_cents_per_fill'], '{:+.2f}')} | "
                f"{_fmt(row['total_usd'])} | {row['daily_ci95_usd'] or '-'} |")

        lines += [
            "",
            "| Half spread | Fills | Spread earned | Markout | Earned/markout | Total |",
            "|---|---|---|---|---|---|",
        ]
        for row in entry["half_spread_sweep"]:
            lines.append(
                f"| {row['half_spread']:.3f} | {row['fills']:,} | "
                f"{_fmt(row['spread_capture_usd'])} | {_fmt(row['markout_usd'])} | "
                f"{_fmt(row.get('capture_over_markout'), '{:.2f}')} | "
                f"{_fmt(row['total_usd'])} |")

        chosen = walk.get("chosen_gamma")
        test = walk.get("test")
        control = walk.get("control_test")
        lines += [
            "",
            f"Walk-forward: gamma chosen on the early days "
            f"{chosen if chosen is not None else '-'}; on the late days it "
            f"yields {_fmt(test['total_usd'] if test else None)} USD against "
            f"{_fmt(control['total_usd'] if control else None)} USD without skew "
            f"(gamma 0).",
        ]

        if "latency_sweep" in entry:
            queue = entry.get("queue", {})
            lines += [
                "",
                f"Standing in line: {queue.get('requotes', 0):,} requotes, "
                f"{queue.get('queue_resets', 0):,} of them re-priced a resting "
                f"order and sent it to the back, {queue.get('unknown_joins', 0):,} "
                f"joins at a level whose depth the recorder never showed.",
                "",
                "| Requote latency (s) | Fills | Spread earned per fill (c) | "
                "Markout per fill (c) | Mean wait (s) | Total (USD) |",
                "|---|---|---|---|---|---|",
            ]
            for row in entry["latency_sweep"]:
                lines.append(
                    f"| {row['latency_s']:.2f} | {row['fills']:,} | "
                    f"{_fmt(row['spread_capture_cents_per_fill'], '{:+.2f}')} | "
                    f"{_fmt(row['markout_cents_per_fill'], '{:+.2f}')} | "
                    f"{_fmt(row.get('mean_wait_s'), '{:.1f}')} | "
                    f"{_fmt(row['total_usd'])} |")

    lines += [
        "",
        "## How to read this",
        "",
        "The three price items are not an estimate but an identity: spread "
        "earned plus markout plus late drift reconstructs the terminal "
        "mark-to-mid value per fill exactly. Spread earned is what the "
        "quoting made, markout is what informed counterparties took back "
        "out of it, and late drift is the price of the inventory carried.",
        "",
        "The touch and tape fill models bracket the truth. Touch fills only "
        "when the other side crosses our quote, so it ignores fills at the "
        "touch and understates the fill count. Tape fills on every crossing "
        "print, so it assumes queue priority and overstates it. Computing "
        "only one model means choosing the result with the assumption.",
        "",
    ]
    if any(m in QUEUE_MODELS for m in models):
        lines += [
            "The queue models stand between those two. A resting order joins "
            "the line behind whatever the ladder already shows at its price, "
            "moves up as prints consume that line, fills partially once it "
            "reaches the front, and loses its place every time it is "
            "re-priced. What the data cannot show is which end of the line a "
            "cancel left from: queue_front assumes the front, queue_back the "
            "back, and queue_back also treats a level the recorder never "
            "showed as crowded until it has been seen. The gap between the "
            "two is the honest width of what a paper simulation can say "
            "about queue position. The latency table keeps the previous "
            "quote live for that long after each requote decision, so being "
            "picked on a stale price is measured rather than assumed.",
            "",
        ]
    lines += [
        "The earned/markout column in the width table is the break-even "
        "ratio: below 1, adverse selection eats more than the quoting takes "
        "in. It rises with quote width, because spread earned grows with "
        "width while the adverse move is set by the market and not by our "
        "quote. Where the ratio crosses 1, the fills collapse at the same "
        "time - a quote that wide stands past the market.",
        "",
        "Makers pay no fee on Polymarket and receive a share of the taker "
        "fees collected. The rebate here is the upper bound on that share; "
        "the actual daily distribution can come out lower.",
        "",
        "Liquidity rewards are the third revenue line and the only one that "
        "does not depend on a fill happening at all: what is paid for is "
        "presence near the mid. Your own share cannot be computed, because "
        "it depends on every other maker in the same market, so a range "
        "stands there instead of a number. The pool assumption is the median "
        "across all markets carrying a pool and therefore deliberately "
        "conservative: the distribution is strongly right skewed, the "
        "largest pool "
        f"sits at {lr.POOL_MAX_USD:.0f} USD per day against a median of "
        f"{lr.POOL_MEDIAN_USD:.0f}. The lever on this revenue line is "
        "therefore market selection, not quoting tighter - a statement this "
        "calculation suggests rather than proves, because nothing here was "
        "selected by pool size.",
        "",
    ]
    lines += _limits_section(results)
    if any(m in QUEUE_MODELS for m in models):
        closing = ("queue position only as deep as the recorder's ladder, cancels "
                   "ahead of us assumed rather than observed, no own market impact")
    else:
        closing = "no queue position, no partial fills"
    lines += [
        "",
        "Further limits: mark-to-mid without resolution modelling, quotes only "
        f"where the mid is in (0.05, 0.95) and the spread at most 0.10, {closing}. "
        "Paper only. Not trading advice.",
    ]
    return "\n".join(lines)


#: Unter diesen Werten ist ein Lauf ein erster Blick, kein Ergebnis.
MIN_DAYS_FOR_CLAIM = 3
MIN_FILLS_FOR_CLAIM = 1000


def _limits_section(results: dict) -> list[str]:
    """Limits that depend on the data actually used, not a fixed paragraph.

    A stream run must not carry the REST run's 120-second caveat, and a run
    over a single hour must not read like a result. Getting this wrong would
    put a false sentence into a frozen artefact.
    """
    if results["stream"]:
        lines = [
            "Resolution: quotes are reposted on every top-of-book move, at a "
            "median of under a second. That is the case the REST run cannot "
            "measure, and the only one in which the market-making question "
            "is posed sensibly at all.",
        ]
    else:
        lines = [
            "The most important limitation, and at the same time the actual "
            "finding: the 120-second grid means every quote stands unchanged "
            "in the book for two minutes. Exactly that staleness is the "
            "adverse selection being measured - you are filled preferentially "
            "when the market has walked past the stale quote. A real market "
            "maker requotes on a millisecond scale. These numbers therefore "
            "do not measure whether market making works on Polymarket, but "
            "what happens when you fail to requote for two minutes.",
        ]

    days = len(results.get("days") or [])
    fills = max((entry["decomposition"]["fills"]
                 for entry in results["fill_models"].values()), default=0)
    signs = {entry["decomposition"]["total_usd"] >= 0
             for entry in results["fill_models"].values()}
    if days < MIN_DAYS_FOR_CLAIM or fills < MIN_FILLS_FOR_CLAIM:
        lines += [
            "",
            f"SAMPLE WARNING: {days} day(s), at most {fills:,} fills. Below "
            f"{MIN_DAYS_FOR_CLAIM} days neither a walk-forward split nor a "
            "daily bootstrap can be computed, and the selection of tokens "
            "and times of day is not representative. This run is a first "
            "look from which no statement about profitability follows.",
        ]
    if len(signs) > 1:
        lines += [
            "",
            "The two fill models do not even agree on the sign here. The result "
            "is therefore undecided: in this run the sign reported would be "
            "chosen by the fill assumption rather than by the data.",
        ]
    return lines


def write_outputs(results: dict, tag: str,
                  research_dir: Path = RESEARCH_DIR) -> dict[str, Path]:
    research_dir.mkdir(parents=True, exist_ok=True)
    json_path = research_dir / f"mm_pnl_{tag}.json"
    json_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

    csv_path = research_dir / f"mm_pnl_{tag}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["fill_model", "gamma", "fills", "spread_capture_usd",
                         "markout_usd", "late_drift_usd", "rebate_usd",
                         "total_usd", "inventory_abs_mean_usd"])
        for model, entry in results["fill_models"].items():
            for row in entry["gamma_sweep"]:
                writer.writerow([model, row["gamma"], row["fills"],
                                 row["spread_capture_usd"], row["markout_usd"],
                                 row["late_drift_usd"], row["rebate_usd"],
                                 row["total_usd"], row["inventory_abs_mean_usd"]])

    md_path = research_dir / f"mm_pnl_{tag}.md"
    md_path.write_text(_markdown(results, tag), encoding="utf-8")

    paths = {"json": json_path, "csv": csv_path, "md": md_path}
    png_path = research_dir / f"mm_pnl_{tag}.png"
    try:
        render_png(results, png_path)
        paths["png"] = png_path
    except Exception as exc:  # noqa: BLE001 - Grafik darf den Report nicht kippen
        print(f"[mm_pnl] PNG uebersprungen: {exc}")
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--recorder-dir", required=True)
    parser.add_argument("--stream", action="store_true")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--half-spread", type=float, default=0.01)
    parser.add_argument("--gamma", type=float, default=0.08)
    parser.add_argument("--quote-usd", type=float, default=50.0)
    parser.add_argument("--cap-usd", type=float, default=250.0)
    parser.add_argument("--category", default="sports")
    parser.add_argument("--fill-models", default="touch,tape",
                        help=f"comma list from {', '.join(FILL_MODELS)}")
    parser.add_argument("--latency", type=float, default=0.0,
                        help="seconds until a requote decision stands in the book")
    parser.add_argument("--latencies", default=",".join(str(x) for x in LATENCY_GRID),
                        help="comma list for the queue models' latency sweep")
    parser.add_argument("--day-from", default=None, help="first ISO day to load")
    parser.add_argument("--day-to", default=None, help="last ISO day to load")
    args = parser.parse_args(argv)

    fill_models = tuple(m.strip() for m in args.fill_models.split(",") if m.strip())
    unknown = [m for m in fill_models if m not in FILL_MODELS]
    if unknown:
        parser.error(f"unknown fill model(s): {', '.join(unknown)}")
    latencies = tuple(float(x) for x in args.latencies.split(",") if x.strip())

    results = run_study(args.recorder_dir, stream=args.stream,
                        half_spread=args.half_spread, gamma=args.gamma,
                        quote_usd=args.quote_usd, cap_usd=args.cap_usd,
                        category=args.category, fill_models=fill_models,
                        latency_s=args.latency, latencies=latencies,
                        day_from=args.day_from, day_to=args.day_to)
    paths = write_outputs(results, args.tag)
    for model, entry in results["fill_models"].items():
        print(model, entry["decomposition"])
    print({key: str(path) for key, path in paths.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
