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

Two fill models run side by side, because neither is right on its own:

  touch  a resting quote fills only when the opposite touch crosses it between
         snapshots. Ignores queue fills, so it understates fills. Pessimistic.
  tape   a resting quote fills when a public print crosses its price. Ignores
         queue position, so it assumes we were at the front. Optimistic.

The honest answer lies between them, and reporting both makes the width of that
band visible instead of hiding it in one arbitrary assumption.

Paper-only research tooling: no order path, no credentials, no wallets.

Usage:
  python -m src.mm_pnl --recorder-dir data/microstructure --tag july
  python -m src.mm_pnl --recorder-dir data/microstructure --tag stream --stream
"""

from __future__ import annotations

import argparse
import csv
import json
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

# Validierte Referenzpalette (dataviz-Skill), Light-Mode
COLOR_POS = "#1baf7a"
COLOR_NEG = "#d6452a"
COLOR_NEUTRAL = "#2a78d6"
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
        }


@dataclass
class TokenRun:
    token_id: str
    fills: list[MMFill] = field(default_factory=list)
    inventory_path: list[float] = field(default_factory=list)
    #: (ts, mid, quoted_bid, quoted_ask) je Snapshot, fuer die Reward-Rechnung.
    quote_path: list[tuple[float, float, float | None, float | None]] = field(
        default_factory=list)

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
                   category: str = "sports", quote_mode: str = "symmetric"
                   ) -> tuple[Decomposition, list[TokenRun]]:
    runs = [run_token(token, series, tape.get(token, []), params, fill_model,
                      quote_mode=quote_mode)
            for token, series in books.items()
            if len(series) >= MIN_SNAPSHOTS_PER_TOKEN]
    return decompose(runs, category=category), runs


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
                          modes: tuple[str, ...] = QUOTE_MODES) -> list[dict]:
    """Does letting the signal decide which side to show reduce adverse selection?

    Symmetric quoting is the control. The number to watch is markout per fill,
    not total PnL: pulling a side also removes fills, so a mode can look better
    simply by trading less. Markout per fill isolates whether the fills that do
    happen are less poisoned.
    """
    rows = []
    for mode in modes:
        decomposition, runs = run_experiment(books, tape, base, fill_model,
                                             category, quote_mode=mode)
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
                fill_model: str = "touch", category: str = "sports") -> list[dict]:
    """Score each skew strength. Gamma 0 is the no-skew control."""
    rows = []
    for gamma in gammas:
        params = QuoteParams(half_spread=base.half_spread, gamma=gamma,
                             quote_usd=base.quote_usd,
                             inventory_cap_usd=base.inventory_cap_usd)
        decomposition, _ = run_experiment(books, tape, params, fill_model, category)
        rows.append({"gamma": gamma, **decomposition.as_dict()})
    return rows


def half_spread_sweep(books: dict[str, list[ofs.BookPoint]],
                      tape: dict[str, list[ofs.TradePoint]], base: QuoteParams,
                      half_spreads: tuple[float, ...] = HALF_SPREAD_GRID,
                      fill_model: str = "touch",
                      category: str = "sports") -> list[dict]:
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
        decomposition, _ = run_experiment(books, tape, params, fill_model, category)
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
                       category: str = "sports") -> dict:
    """Pick gamma on the early days, then report what it did on the later ones.

    A skew parameter tuned and scored on the same days will always look good.
    The number that matters is the out-of-sample column.
    """
    train, test = split_books_by_day(books)
    train_rows = gamma_sweep(train, tape, base, gammas, fill_model, category)
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
    result["test"] = run_experiment(test, tape, chosen, fill_model, category)[0].as_dict()
    result["control_test"] = run_experiment(test, tape, control, fill_model,
                                            category)[0].as_dict()
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
              gammas: tuple[float, ...] = GAMMA_GRID) -> dict:
    """Full decomposition study over one data directory, both fill models."""
    books = ofs.load_books(directory, stream=stream)
    tape = ofs.load_tape(directory, stream=stream)
    base = QuoteParams(half_spread=half_spread, gamma=gamma,
                       quote_usd=quote_usd, inventory_cap_usd=cap_usd)
    results: dict = {
        "source": str(directory), "stream": stream,
        "tokens": len(books),
        "snapshots": sum(len(v) for v in books.values()),
        "tape_prints": sum(len(v) for v in tape.values()),
        "days": sorted({p.day for v in books.values() for p in v}),
        "params": {"half_spread": half_spread, "gamma": gamma,
                   "quote_usd": quote_usd, "cap_usd": cap_usd},
        "category": category,
        "fee_model_version": vf.FEE_MODEL_VERSION,
        "fill_models": {},
    }
    for fill_model in ("touch", "tape"):
        decomposition, runs = run_experiment(books, tape, base, fill_model, category)
        daily = per_day_totals(runs, category)
        ci = ofs.block_bootstrap_ci(list(daily.values()), list(daily.keys()))
        rewards = reward_estimate(runs, quote_usd)
        results["fill_models"][fill_model] = {
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
            "gamma_sweep": gamma_sweep(books, tape, base, gammas, fill_model, category),
            "half_spread_sweep": half_spread_sweep(books, tape, base,
                                                   fill_model=fill_model,
                                                   category=category),
            "quote_modes": quote_mode_comparison(books, tape, base, fill_model,
                                                 category),
            "walk_forward": walk_forward_gamma(books, tape, base, gammas,
                                               fill_model, category),
        }
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
    width = 0.36
    for offset, model in ((-width / 2, "touch"), (width / 2, "tape")):
        data = results["fill_models"][model]["decomposition"]
        values = [data[k] for k in keys]
        colors = [COLOR_POS if v >= 0 else COLOR_NEG for v in values]
        positions = [i + offset for i in range(len(keys))]
        ax1.bar(positions, values, width=width, color=colors,
                edgecolor=COLOR_NEUTRAL if model == "tape" else "none",
                linewidth=1.2)
    ax1.axhline(0, color=COLOR_TEXT_2, linewidth=1.0)
    ax1.set_xticks(range(len(labels)))
    ax1.set_xticklabels(labels, fontsize=8)
    ax1.set_ylabel("USD", color=COLOR_TEXT_2, fontsize=9)
    ax1.set_title("PnL decomposition (left touch model, right tape model)",
                  color=COLOR_TEXT, fontsize=11, loc="left")

    for model, colour in (("touch", COLOR_NEUTRAL), ("tape", COLOR_POS)):
        rows = results["fill_models"][model]["gamma_sweep"]
        ax2.plot([r["gamma"] for r in rows], [r["total_usd"] for r in rows],
                 color=colour, linewidth=2.0, marker="o", markersize=4,
                 label=f"{model} model")
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
        f"quote {params['quote_usd']} USD, inventory cap {params['cap_usd']} USD. "
        f"Maker economics for category {results['category']}, fee schedule "
        f"{results['fee_model_version']}.",
        "",
        "| Item | Touch model (USD) | Tape model (USD) |",
        "|---|---|---|",
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
    ]
    for label, key, fmt in rows:
        touch = results["fill_models"]["touch"]["decomposition"][key]
        tape = results["fill_models"]["tape"]["decomposition"][key]
        lines.append(f"| {label} | {_fmt(touch, fmt)} | {_fmt(tape, fmt)} |")

    for model in ("touch", "tape"):
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
        "The two fill models bracket the truth. Touch fills only when the "
        "other side crosses our quote, so it ignores fills at the touch and "
        "understates the fill count. Tape fills on every crossing print, so "
        "it assumes queue priority and overstates it. Computing only one "
        "model means choosing the result with the assumption.",
        "",
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
    lines += [
        "",
        "Further limits: mark-to-mid without resolution modelling, quotes only "
        "where the mid is in (0.05, 0.95) and the spread at most 0.10, no "
        "queue position, no partial fills. Paper only. Not trading advice.",
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
    args = parser.parse_args(argv)

    results = run_study(args.recorder_dir, stream=args.stream,
                        half_spread=args.half_spread, gamma=args.gamma,
                        quote_usd=args.quote_usd, cap_usd=args.cap_usd,
                        category=args.category)
    paths = write_outputs(results, args.tag)
    for model, entry in results["fill_models"].items():
        print(model, entry["decomposition"])
    print({key: str(path) for key, path in paths.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
