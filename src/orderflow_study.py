"""Do book imbalance and signed order flow predict the next move, net of costs?

The imbalance study in ``src/imbalance_study.py`` answered the gross question:
does the bid share of top-5 depth point the way the mid drifts. This module
asks the two questions that decide whether such a signal is worth acting on.

1. Net of costs. A taker pays the spread on entry, the spread on exit, and a
   fee on both. A signal can be right about direction and still lose money.
   Every observation here carries a gross drift AND a net drift after
   ``app.venue_fees.round_trip_cost_cents``.

2. Net of latency. Acting is not free in time either. Each observation is
   evaluated at a set of entry delays: the signal fires at t, but the entry
   price is the book at t + delay while the exit stays at t + horizon. The
   resulting latency-decay curve says how much edge survives being late, which
   is the number that decides whether a signal needs colocation-class speed or
   is reachable from a laptop.

Signals covered:

  imbalance   bid share of top-N USD depth (the book's standing intent)
  flow        signed taker volume over a trailing window (executed intent)
  combo       both agreeing

Sources: the 120-second REST recorder CSVs (``books_*.csv`` / ``trades_*.csv``)
or the event-driven stream CSVs (``stream_books_*.csv`` / ``stream_trades_*.csv``).
The REST files resolve delays only in 120-second steps; the stream files resolve
them in seconds. The same code runs on both so the study can be repeated at
finer resolution without changing its definitions.

Read-only research tooling: no order path, no credentials, no wallets.

Usage:
  python -m src.orderflow_study --recorder-dir data/microstructure --tag rest-july
  python -m src.orderflow_study --recorder-dir data/microstructure --stream --tag stream
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from bisect import bisect_left
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app import venue_fees as vf
from src.imbalance_study import wilson_lb

REPO_ROOT = Path(__file__).resolve().parents[1]
RESEARCH_DIR = REPO_ROOT / "docs" / "research"

# Filter (Engineering-Wahl, im Report dokumentiert)
MAX_SPREAD = 0.10
MID_BOUNDS = (0.05, 0.95)
MIN_TOP_USD = 50.0

#: Entry-Verzoegerungen in Sekunden fuer die Zerfallskurve.
DELAYS_S = (0.0, 1.0, 5.0, 30.0, 120.0, 300.0)
#: Halteperioden in Sekunden.
HORIZONS_S = (300.0, 900.0)
#: Trailing-Fenster fuer den signierten Order-Flow.
FLOW_WINDOW_S = 300.0

#: Signal-Schwellen: ueber HI = Aufwaertssignal, unter LO = Abwaertssignal.
DEFAULT_THRESHOLD = 0.65

#: Ein Fill braucht eine as-of-Zuordnung mit begrenzter Staleness.
STALENESS_FACTOR = 2.0

# Validierte Referenzpalette (dataviz-Skill), Light-Mode
COLOR_GROSS = "#2a78d6"
COLOR_NET = "#1baf7a"
COLOR_SURFACE = "#fcfcfb"
COLOR_TEXT = "#0b0b0b"
COLOR_TEXT_2 = "#52514e"
COLOR_GRID = "#e5e4e0"


@dataclass(frozen=True, slots=True)
class BookPoint:
    ts: float
    mid: float
    spread: float
    imbalance: float
    day: str


@dataclass(frozen=True, slots=True)
class TradePoint:
    ts: float
    signed_usd: float
    usd: float
    price: float = 0.0


@dataclass(frozen=True, slots=True)
class Observation:
    """One signal firing, priced at one entry delay and one horizon."""

    token_id: str
    day: str
    ts: float
    signal: str
    direction: int            # +1 erwartet steigend, -1 erwartet fallend
    strength: float
    delay_s: float
    horizon_s: float
    entry_mid: float
    exit_mid: float
    spread_cents: float
    gross_cents: float        # Drift in Signalrichtung, Entry -> Exit
    spread_cost_cents: float  # einmal kreuzen rein, einmal raus
    fee_cost_cents: float     # zwei Taker-Gebuehren
    net_cents: float          # gross - spread - fee (aggressiv ausgefuehrt)

    @property
    def cost_cents(self) -> float:
        return round(self.spread_cost_cents + self.fee_cost_cents, 4)

    @property
    def net_maker_cents(self) -> float:
        """Obere Schranke: passiv gefuellt, also ohne Kreuzen und ohne Gebuehr.

        Zwischen ``net_cents`` und ``net_maker_cents`` liegt der gesamte Wert
        der Ausfuehrungsart. Ist ein Signal nur in dieser Spanne positiv, ist
        es kein Taker-Signal, sondern hoechstens ein Grund, Quotes zu schieben.
        """
        return self.gross_cents


def parse_ts(value: str) -> float | None:
    """Recorder timestamps come as ISO-Z, with or without milliseconds."""
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return (datetime.strptime(text, fmt)
                    .replace(tzinfo=timezone.utc).timestamp())
        except ValueError:
            continue
    return None


def _float(value) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def load_books(directory: str | Path, stream: bool = False,
               max_spread: float = MAX_SPREAD) -> dict[str, list[BookPoint]]:
    """Per-token book series from recorder or stream CSVs, filtered and sorted."""
    pattern = "stream_books_*.csv" if stream else "books_*.csv"
    series: dict[str, list[BookPoint]] = {}
    for path in sorted(Path(directory).glob(pattern)):
        day = path.stem.split("_")[-1]
        with open(path, newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                mid = _float(row.get("mid"))
                spread = _float(row.get("spread"))
                imbalance = _float(row.get("imbalance_top"))
                ts = parse_ts(row.get("recv_ts") or row.get("ts_utc"))
                if None in (mid, spread, imbalance, ts):
                    continue
                if spread > max_spread or spread <= 0:
                    continue
                if not (MID_BOUNDS[0] < mid < MID_BOUNDS[1]):
                    continue
                token = str(row.get("token_id") or "")
                if not token:
                    continue
                series.setdefault(token, []).append(
                    BookPoint(ts=ts, mid=mid, spread=spread,
                              imbalance=imbalance, day=day))
    for values in series.values():
        values.sort(key=lambda p: p.ts)
    return series


def load_tape(directory: str | Path, stream: bool = False) -> dict[str, list[TradePoint]]:
    """Per-token signed taker flow.

    ``side`` is the taker's side, so BUY is USD lifting the offer and SELL is
    USD hitting the bid. The REST tape is polled and can miss prints between
    polls; the stream tape is event driven and does not.
    """
    pattern = "stream_trades_*.csv" if stream else "trades_*.csv"
    tape: dict[str, list[TradePoint]] = {}
    for path in sorted(Path(directory).glob(pattern)):
        with open(path, newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                token = str(row.get("token_id") or "")
                price = _float(row.get("price"))
                size = _float(row.get("size"))
                if not token or price is None or size is None:
                    continue
                ts = _float(row.get("trade_ts"))
                if ts is None:
                    ts = parse_ts(row.get("exchange_ts")) or parse_ts(row.get("recv_ts"))
                    if ts is None:
                        raw = _float(row.get("exchange_ts"))
                        ts = raw / 1000.0 if raw and raw > 1e11 else raw
                elif ts > 1e11:  # Millisekunden statt Sekunden
                    ts = ts / 1000.0
                if ts is None:
                    continue
                usd = price * size
                sign = 1.0 if str(row.get("side", "")).upper().startswith("B") else -1.0
                tape.setdefault(token, []).append(
                    TradePoint(ts=ts, signed_usd=sign * usd, usd=usd, price=price))
    for values in tape.values():
        values.sort(key=lambda t: t.ts)
    return tape


def flow_imbalance(trades: list[TradePoint], t_start: float, t_end: float,
                   min_usd: float = 1.0) -> float | None:
    """Signed taker flow over a window, scaled to [-1, 1]. None if too quiet."""
    if not trades:
        return None
    lo = bisect_left([t.ts for t in trades], t_start)
    signed = 0.0
    total = 0.0
    for trade in trades[lo:]:
        if trade.ts > t_end:
            break
        signed += trade.signed_usd
        total += trade.usd
    if total < min_usd:
        return None
    return signed / total


def as_of(series: list[BookPoint], target: float, staleness: float) -> BookPoint | None:
    """First point at or after ``target``, rejected if staler than allowed."""
    index = bisect_left([p.ts for p in series], target)
    if index >= len(series):
        return None
    point = series[index]
    return point if point.ts - target <= staleness else None


def direction_from(strength: float, threshold: float) -> int:
    """+1 above the threshold, -1 below its mirror, 0 in the dead zone.

    Every strength fed in here lives in [0, 1] and the threshold is above 0.5,
    so the short trigger is the mirrored value ``1 - threshold``.
    """
    if strength >= threshold:
        return 1
    if strength <= 1.0 - threshold:
        return -1
    return 0


def signal_direction(signal: str, imbalance: float, flow: float | None,
                     threshold: float) -> tuple[int, float]:
    """(direction, strength) for one of the supported signals."""
    if signal == "imbalance":
        return direction_from(imbalance, threshold), imbalance
    if signal == "flow":
        if flow is None:
            return 0, 0.0
        # Flow lebt in [-1, 1], auf [0, 1] abbilden, damit eine Schwelle reicht.
        scaled = (flow + 1.0) / 2.0
        return direction_from(scaled, threshold), scaled
    if signal == "combo":
        if flow is None:
            return 0, 0.0
        d_imb, _ = signal_direction("imbalance", imbalance, None, threshold)
        d_flow, _ = signal_direction("flow", imbalance, flow, threshold)
        if d_imb != 0 and d_imb == d_flow:
            return d_imb, (imbalance + (flow + 1.0) / 2.0) / 2.0
        return 0, 0.0
    raise ValueError(f"unbekanntes Signal: {signal}")


def build_observations(books: dict[str, list[BookPoint]],
                       tape: dict[str, list[TradePoint]],
                       signal: str = "imbalance",
                       threshold: float = DEFAULT_THRESHOLD,
                       delays_s: tuple[float, ...] = DELAYS_S,
                       horizons_s: tuple[float, ...] = HORIZONS_S,
                       flow_window_s: float = FLOW_WINDOW_S,
                       category: str = "sports",
                       venue: str = "polymarket") -> list[Observation]:
    """Price every signal firing at each (delay, horizon) pair.

    Entry is the book at ``ts + delay``, exit the book at ``ts + horizon``. A
    delay past the horizon is skipped rather than producing a negative hold.
    Cost is the full round trip: cross the spread twice plus two taker fees.
    """
    out: list[Observation] = []
    for token, series in books.items():
        trades = tape.get(token, [])
        for point in series:
            flow = flow_imbalance(trades, point.ts - flow_window_s, point.ts)
            direction, strength = signal_direction(signal, point.imbalance,
                                                   flow, threshold)
            if direction == 0:
                continue
            for horizon in horizons_s:
                exit_point = as_of(series, point.ts + horizon,
                                   horizon * STALENESS_FACTOR)
                if exit_point is None:
                    continue
                for delay in delays_s:
                    if delay >= horizon:
                        continue
                    entry = point if delay == 0 else as_of(
                        series, point.ts + delay,
                        max(delay, 1.0) * STALENESS_FACTOR)
                    if entry is None or entry.ts >= exit_point.ts:
                        continue
                    gross = direction * (exit_point.mid - entry.mid) * 100.0
                    spread_cents = entry.spread * 100.0
                    # Rein und raus kreuzen kostet zusammen einen vollen Spread.
                    spread_cost = spread_cents
                    fee_cost = 2.0 * vf.fee_cents_per_share(
                        venue, entry.mid, category, shares=100.0)
                    out.append(Observation(
                        token_id=token, day=point.day, ts=point.ts,
                        signal=signal, direction=direction, strength=strength,
                        delay_s=delay, horizon_s=horizon,
                        entry_mid=entry.mid, exit_mid=exit_point.mid,
                        spread_cents=round(spread_cents, 4),
                        gross_cents=round(gross, 4),
                        spread_cost_cents=round(spread_cost, 4),
                        fee_cost_cents=round(fee_cost, 4),
                        net_cents=round(gross - spread_cost - fee_cost, 4)))
    return out


def summarise(observations: list[Observation]) -> dict:
    """Hit rates and mean edge for one homogeneous slice of observations.

    The hit rate is conditional on movement: on thin books most horizons drift
    by exactly zero, and counting those as misses would understate a signal
    that is simply not always actionable. ``moved_share`` keeps that visible.
    """
    n = len(observations)
    if n == 0:
        return {"n": 0, "moved": 0, "moved_share": None, "hit_rate": None,
                "wilson_lb95": None, "mean_gross_cents": None,
                "mean_net_cents": None, "mean_cost_cents": None,
                "mean_spread_cost_cents": None, "mean_fee_cost_cents": None,
                "net_positive_share": None, "days": 0}
    moved = [o for o in observations if o.gross_cents != 0.0]
    hits = sum(1 for o in moved if o.gross_cents > 0)
    net_positive = sum(1 for o in observations if o.net_cents > 0)
    return {
        "n": n,
        "moved": len(moved),
        "moved_share": round(len(moved) / n, 4),
        "hit_rate": round(hits / len(moved), 4) if moved else None,
        "wilson_lb95": round(wilson_lb(hits, len(moved)), 4) if moved else None,
        "mean_gross_cents": round(sum(o.gross_cents for o in observations) / n, 4),
        "mean_spread_cost_cents": round(
            sum(o.spread_cost_cents for o in observations) / n, 4),
        "mean_fee_cost_cents": round(
            sum(o.fee_cost_cents for o in observations) / n, 4),
        "mean_cost_cents": round(sum(o.cost_cents for o in observations) / n, 4),
        "mean_net_cents": round(sum(o.net_cents for o in observations) / n, 4),
        "net_positive_share": round(net_positive / n, 4),
        "days": len({o.day for o in observations}),
    }


def latency_curve(observations: list[Observation], horizon_s: float) -> list[dict]:
    """One row per entry delay: what survives of the edge when acting late."""
    rows: list[dict] = []
    slice_ = [o for o in observations if o.horizon_s == horizon_s]
    for delay in sorted({o.delay_s for o in slice_}):
        stats = summarise([o for o in slice_ if o.delay_s == delay])
        stats["delay_s"] = delay
        stats["horizon_s"] = horizon_s
        rows.append(stats)
    return rows


#: Unter dieser Bruttokante ist eine Zerfallsquote nicht interpretierbar.
MIN_BASE_EDGE_CENTS = 0.01


def edge_retention(rows: list[dict],
                   min_base_cents: float = MIN_BASE_EDGE_CENTS) -> list[dict]:
    """Share of the zero-delay gross edge still there at each delay.

    Only defined when there is an edge to lose: dividing by a base that is zero
    or negative produces numbers like "200 percent retained" for a signal that
    never had an edge, which reads as a result and is noise.
    """
    if not rows:
        return []
    base = next((r["mean_gross_cents"] for r in rows if r["delay_s"] == 0.0), None)
    usable = base is not None and base >= min_base_cents
    out = []
    for row in rows:
        retained = None
        if usable and row["mean_gross_cents"] is not None:
            retained = round(row["mean_gross_cents"] / base, 4)
        out.append({**row, "edge_retained": retained})
    return out


def block_bootstrap_ci(values: list[float], groups: list[str],
                       iterations: int = 500, seed: int = 20260730,
                       alpha: float = 0.05) -> tuple[float, float] | None:
    """CI for a mean under intra-day correlation: resample whole days.

    Neighbouring snapshots of the same token on the same day are anything but
    independent, so a plain bootstrap would report a far too narrow interval.
    Resampling whole days keeps the within-day correlation intact.
    """
    if not values or len(values) != len(groups):
        return None
    buckets: dict[str, list[float]] = {}
    for value, group in zip(values, groups):
        buckets.setdefault(group, []).append(value)
    keys = sorted(buckets)
    if len(keys) < 2:
        return None
    rng = _Lcg(seed)
    means: list[float] = []
    for _ in range(iterations):
        pooled: list[float] = []
        for _ in range(len(keys)):
            pooled.extend(buckets[keys[rng.below(len(keys))]])
        if pooled:
            means.append(sum(pooled) / len(pooled))
    if not means:
        return None
    means.sort()
    lo = means[max(0, int(alpha / 2 * len(means)))]
    hi = means[min(len(means) - 1, int((1 - alpha / 2) * len(means)))]
    return round(lo, 4), round(hi, 4)


class _Lcg:
    """Tiny deterministic RNG so a report is reproducible without numpy seeds."""

    def __init__(self, seed: int) -> None:
        self.state = seed % (2 ** 31 - 1) or 1

    def below(self, n: int) -> int:
        self.state = (self.state * 48271) % (2 ** 31 - 1)
        return self.state % max(1, n)


def walk_forward_split(observations: list[Observation],
                       train_share: float = 0.6) -> tuple[list[Observation], list[Observation]]:
    """Split by calendar day, never at random: later days are the test set."""
    days = sorted({o.day for o in observations})
    if len(days) < 2:
        return observations, []
    cut = max(1, int(len(days) * train_share))
    train_days = set(days[:cut])
    train = [o for o in observations if o.day in train_days]
    test = [o for o in observations if o.day not in train_days]
    return train, test


def pick_threshold(books: dict[str, list[BookPoint]],
                   tape: dict[str, list[TradePoint]], signal: str,
                   candidates: tuple[float, ...],
                   horizon_s: float, **kwargs) -> dict:
    """Choose the threshold with the best in-sample net edge, honestly reported.

    Returns the winner plus every candidate's score, so the report can show how
    flat or peaked the choice was. A knife-edge optimum is a warning sign.
    """
    scores = []
    for threshold in candidates:
        observations = build_observations(books, tape, signal=signal,
                                          threshold=threshold,
                                          horizons_s=(horizon_s,),
                                          delays_s=(0.0,), **kwargs)
        stats = summarise(observations)
        scores.append({"threshold": threshold, **stats})
    ranked = [s for s in scores if s["n"] > 0]
    best = max(ranked, key=lambda s: s["mean_net_cents"]) if ranked else None
    return {"best": best, "candidates": scores}


def run_study(directory: str | Path, stream: bool = False,
              signals: tuple[str, ...] = ("imbalance", "flow", "combo"),
              threshold: float = DEFAULT_THRESHOLD,
              horizons_s: tuple[float, ...] = HORIZONS_S,
              delays_s: tuple[float, ...] = DELAYS_S,
              category: str = "sports") -> dict:
    """Full study over one data directory: signals x delays x horizons."""
    books = load_books(directory, stream=stream)
    tape = load_tape(directory, stream=stream)
    results: dict = {
        "source": str(directory),
        "stream": stream,
        "tokens": len(books),
        "snapshots": sum(len(v) for v in books.values()),
        "tape_tokens": len(tape),
        "tape_prints": sum(len(v) for v in tape.values()),
        "days": sorted({p.day for v in books.values() for p in v}),
        "threshold": threshold,
        "category": category,
        "fee_model_version": vf.FEE_MODEL_VERSION,
        "signals": {},
    }
    for signal in signals:
        observations = build_observations(books, tape, signal=signal,
                                          threshold=threshold,
                                          delays_s=delays_s,
                                          horizons_s=horizons_s,
                                          category=category)
        train, test = walk_forward_split(observations)
        entry = {
            "overall": summarise(observations),
            "train": summarise(train),
            "test": summarise(test),
            "latency": {},
        }
        base = [o for o in observations if o.delay_s == 0.0]
        ci = block_bootstrap_ci([o.net_cents for o in base],
                                [o.day for o in base])
        entry["net_ci95_cents"] = ci
        for horizon in horizons_s:
            entry["latency"][str(int(horizon))] = edge_retention(
                latency_curve(observations, horizon))
        results["signals"][signal] = entry
    return results


def render_png(results: dict, out_path: Path, horizon_s: float = 300.0) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    key = str(int(horizon_s))
    signals = [s for s in results["signals"] if results["signals"][s]["latency"].get(key)]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.0, 5.0), dpi=150,
                                   facecolor=COLOR_SURFACE)
    fig.subplots_adjust(top=0.80, bottom=0.14, left=0.08, right=0.98, wspace=0.22)
    for ax in (ax1, ax2):
        ax.set_facecolor(COLOR_SURFACE)
        ax.grid(axis="y", color=COLOR_GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        for spine in ("left", "bottom"):
            ax.spines[spine].set_color(COLOR_GRID)
        ax.tick_params(colors=COLOR_TEXT_2, labelsize=9)

    palette = [COLOR_GROSS, COLOR_NET, "#8b5cf6"]
    for index, signal in enumerate(signals):
        rows = results["signals"][signal]["latency"][key]
        delays = [r["delay_s"] for r in rows]
        ax1.plot(delays, [r["mean_gross_cents"] or 0.0 for r in rows],
                 color=palette[index % len(palette)], linewidth=2.0,
                 marker="o", markersize=4, label=f"{signal} brutto")
        ax1.plot(delays, [r["mean_net_cents"] or 0.0 for r in rows],
                 color=palette[index % len(palette)], linewidth=1.6,
                 linestyle="--", marker="s", markersize=3,
                 label=f"{signal} netto")
    ax1.axhline(0, color=COLOR_TEXT_2, linewidth=1.0)
    ax1.set_title("Kante je Entry-Verzoegerung (Cents pro Signal)",
                  color=COLOR_TEXT, fontsize=11, loc="left")
    ax1.set_xlabel("Verzoegerung bis Entry (Sekunden)", color=COLOR_TEXT_2, fontsize=9)
    ax1.legend(frameon=False, fontsize=8, labelcolor=COLOR_TEXT_2)

    labels, hit, lower = [], [], []
    for signal in signals:
        rows = results["signals"][signal]["latency"][key]
        row = next((r for r in rows if r["delay_s"] == 0.0), None)
        if row and row["hit_rate"] is not None:
            labels.append(signal)
            hit.append(100 * row["hit_rate"])
            lower.append(100 * (row["wilson_lb95"] or 0.0))
    x = range(len(labels))
    ax2.bar([i - 0.18 for i in x], hit, width=0.36, color=COLOR_GROSS,
            label="Trefferquote")
    ax2.bar([i + 0.18 for i in x], lower, width=0.36, color=COLOR_NET,
            label="Wilson-Untergrenze 95%")
    ax2.axhline(50, color=COLOR_TEXT_2, linewidth=1.0, linestyle=":")
    ax2.set_xticks(list(x))
    ax2.set_xticklabels(labels, fontsize=9)
    ax2.set_ylabel("Prozent", color=COLOR_TEXT_2, fontsize=9)
    ax2.set_title("Richtungstreffer ohne Verzoegerung (bedingt auf Bewegung)",
                  color=COLOR_TEXT, fontsize=11, loc="left")
    ax2.legend(frameon=False, fontsize=8, labelcolor=COLOR_TEXT_2)

    fig.suptitle(
        f"Order-Flow-Studie — {results['tokens']} Tokens, "
        f"{len(results['days'])} Tage, Horizont {int(horizon_s)}s, "
        f"Schwelle {results['threshold']}, Kosten nach Gebuehrenmodell "
        f"{results['fee_model_version']}",
        color=COLOR_TEXT, fontsize=11.5, x=0.02, y=0.95, ha="left")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, facecolor=COLOR_SURFACE)
    plt.close(fig)


def write_outputs(results: dict, tag: str,
                  research_dir: Path = RESEARCH_DIR) -> dict[str, Path]:
    research_dir.mkdir(parents=True, exist_ok=True)
    json_path = research_dir / f"orderflow_{tag}.json"
    json_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

    csv_path = research_dir / f"orderflow_{tag}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["signal", "horizon_s", "delay_s", "n", "moved",
                         "hit_rate", "wilson_lb95", "mean_gross_cents",
                         "mean_spread_cost_cents", "mean_fee_cost_cents",
                         "mean_cost_cents", "mean_net_cents", "edge_retained"])
        for signal, entry in results["signals"].items():
            for horizon, rows in entry["latency"].items():
                for row in rows:
                    writer.writerow([signal, horizon, row["delay_s"], row["n"],
                                     row["moved"], row["hit_rate"],
                                     row["wilson_lb95"], row["mean_gross_cents"],
                                     row["mean_spread_cost_cents"],
                                     row["mean_fee_cost_cents"],
                                     row["mean_cost_cents"], row["mean_net_cents"],
                                     row.get("edge_retained")])

    png_path = research_dir / f"orderflow_{tag}.png"
    try:
        render_png(results, png_path)
    except Exception as exc:  # noqa: BLE001 - Grafik darf den Report nicht kippen
        png_path = None
        print(f"[orderflow] PNG uebersprungen: {exc}")

    md_path = research_dir / f"orderflow_{tag}.md"
    md_path.write_text(_markdown(results, tag), encoding="utf-8")
    paths = {"json": json_path, "csv": csv_path, "md": md_path}
    if png_path is not None:
        paths["png"] = png_path
    return paths


def _fmt(value, spec="{:+.3f}") -> str:
    return "-" if value is None else spec.format(value)


def _markdown(results: dict, tag: str) -> str:
    days = results["days"]
    lines = [
        f"# Order-Flow-Studie ({tag})",
        "",
        f"Quelle: {results['source']} "
        f"({'Stream, ereignisgetrieben' if results['stream'] else 'REST, 120s-Raster'}), "
        f"{results['tokens']} Tokens, {results['snapshots']:,} Snapshots, "
        f"{results['tape_prints']:,} Tape-Prints, "
        f"{len(days)} Tage ({days[0] if days else '-'} bis {days[-1] if days else '-'}).",
        "",
        f"Schwelle {results['threshold']}, Kostenmodell "
        f"{results['category']}-Kategorie, Gebuehrenstand "
        f"{results['fee_model_version']}. Kosten je Runde = Spread + zwei "
        "Taker-Gebuehren. Trefferquote bedingt auf Bewegung.",
        "",
    ]
    for signal, entry in results["signals"].items():
        overall = entry["overall"]
        lines += [
            f"## Signal: {signal}",
            "",
            f"Beobachtungen {overall['n']:,} an {overall['days']} Tagen, "
            f"davon bewegt {_fmt(overall['moved_share'], '{:.1%}')}. "
            f"Trefferquote {_fmt(overall['hit_rate'], '{:.1%}')} "
            f"(Wilson-Untergrenze {_fmt(overall['wilson_lb95'], '{:.1%}')}).",
            "",
            "| Horizont | Verzoegerung | n | Treffer | Brutto (Cents) | "
            "Spread (Cents) | Gebuehr (Cents) | Netto (Cents) | Kante erhalten |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for horizon, rows in entry["latency"].items():
            for row in rows:
                lines.append(
                    f"| {horizon}s | {row['delay_s']:.0f}s | {row['n']:,} | "
                    f"{_fmt(row['hit_rate'], '{:.1%}')} | "
                    f"{_fmt(row['mean_gross_cents'])} | "
                    f"{_fmt(row['mean_spread_cost_cents'], '{:.3f}')} | "
                    f"{_fmt(row['mean_fee_cost_cents'], '{:.3f}')} | "
                    f"{_fmt(row['mean_net_cents'])} | "
                    f"{_fmt(row.get('edge_retained'), '{:.0%}')} |")
        ci = entry.get("net_ci95_cents")
        lines += [
            "",
            f"Walk-forward: Train (fruehe Tage) netto "
            f"{_fmt(entry['train']['mean_net_cents'])} Cents, Test (spaete Tage) "
            f"netto {_fmt(entry['test']['mean_net_cents'])} Cents.",
            f"Block-Bootstrap-CI 95% auf Tagesebene fuer netto ohne "
            f"Verzoegerung: {ci if ci else 'nicht berechenbar'} Cents.",
            "",
        ]
    lines += [
        "## Lesehilfe",
        "",
        "Brutto ist die Mid-Bewegung in Signalrichtung. Netto zieht die volle "
        "Runde ab: einmal Spread kreuzen beim Entry, einmal beim Exit, plus "
        "zwei Taker-Gebuehren. Ein Signal mit hoher Trefferquote und negativem "
        "Netto ist richtig und trotzdem unhandelbar.",
        "",
        "Die beiden Zahlen sind zugleich die Schranken der Ausfuehrungsart. "
        "Netto ist die untere Schranke (alles aggressiv genommen), brutto die "
        "obere (alles passiv gefuellt, auf Polymarket zahlen Maker keine "
        "Gebuehr). Liegt der Wert eines Signals nur zwischen diesen beiden "
        "Schranken, ist es kein Taker-Signal, sondern ein Grund, als Maker die "
        "Quotes zu verschieben. Die getrennten Spalten fuer Spread und Gebuehr "
        "zeigen, welcher der beiden Posten die Kante frisst.",
        "",
        "Die Verzoegerungsspalte simuliert Reaktionszeit: das Signal feuert zu "
        "t, der Entry-Preis ist das Buch zu t plus Verzoegerung, der Exit "
        "bleibt bei t plus Horizont. Faellt die Kante schon bei kleinen "
        "Verzoegerungen stark, ist es ein Latenzrennen und kein Research-Edge.",
        "",
        "Grenzen: das REST-Raster loest Verzoegerungen nur in 120-Sekunden-"
        "Schritten auf, kleinere Werte fallen deshalb auf denselben Snapshot "
        "und zeigen keinen Zerfall. Die Sekundenaufloesung liefert erst der "
        "Stream-Recorder. Der REST-Tape ist gepollt und kann Prints zwischen "
        "zwei Abrufen verpassen, was den Flow-Anteil unterschaetzt.",
        "",
        "Read-only-Forschung, keine Handelsempfehlung.",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--recorder-dir", required=True)
    parser.add_argument("--stream", action="store_true",
                        help="read stream_*.csv instead of the REST files")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--category", default="sports")
    args = parser.parse_args(argv)

    results = run_study(args.recorder_dir, stream=args.stream,
                        threshold=args.threshold, category=args.category)
    paths = write_outputs(results, args.tag)
    for signal, entry in results["signals"].items():
        print(signal, {k: v for k, v in entry["overall"].items()})
    print({key: str(path) for key, path in paths.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
