"""Paper market-making simulator with dynamic inventory skew.

Replays recorded order books (May forward-replay SQLite capture or
``src/book_recorder.py`` CSVs) and quotes both sides of each binary
market around the observed mid:

    variance    = mid * (1 - mid)              (binary-outcome variance)
    ratio       = clamp(inventory_usd / cap, -1, 1)
    reservation = mid - gamma * variance * ratio
    bid / ask   = reservation -/+ half_spread  (clipped, non-crossing)

Long inventory shifts both quotes down (buy less, sell faster), short
inventory shifts them up - the Avellaneda-Stoikov intuition with the
prediction-market twist that variance dies toward 0 and 1.

Fill model (documented approximation): the May capture has no public
trade tape, so a resting quote counts as filled only when the OPPOSITE
touch crosses it between consecutive snapshots (next best ask at or
below our bid, next best bid at or above our ask). That is conservative:
it ignores queue-position fills at the touch and thus understates fill
counts rather than overstating them.

Diagnostics per run, each with skew on vs off: fill counts, spread
capture at fill, 5-minute markout (the standard adverse-selection
measure: how the mid moved against the fill), inventory paths, and
mark-to-mid PnL.

Paper-only research tooling: no order path, no credentials, no wallets.

Usage:
  python -m src.mm_simulator --sqlite <forward-clean.db> --tag 2026-05-30
  python -m src.mm_simulator --recorder-dir data/microstructure --tag live
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = REPO_ROOT / "reports"

TICK = 0.001
MARKOUT_HORIZON_S = 300.0
MARKOUT_MAX_EXTRA_S = 300.0
MIN_SNAPSHOTS_PER_TOKEN = 200
MAX_QUOTE_SPREAD = 0.10  # keine Quotes in kaputte/leere Buecher
MID_BOUNDS = (0.05, 0.95)  # nahe 0/1 ist Aufloesungszone, kein MM-Terrain

# Validierte Referenzpalette (dataviz-Skill), Light-Mode
COLOR_SKEW_ON = "#2a78d6"   # Slot 1 blau
COLOR_SKEW_OFF = "#1baf7a"  # Slot 2 aqua
COLOR_SURFACE = "#fcfcfb"
COLOR_TEXT = "#0b0b0b"
COLOR_TEXT_2 = "#52514e"
COLOR_GRID = "#e5e4e0"


@dataclass(frozen=True)
class QuoteParams:
    half_spread: float = 0.01
    gamma: float = 0.08          # max. Skew-Shift = gamma * var * 1.0
    quote_usd: float = 50.0
    inventory_cap_usd: float = 250.0


@dataclass
class Fill:
    ts: float
    side: str        # "buy" oder "sell" (unsere Seite)
    price: float
    shares: float
    mid_at_fill: float
    markout: float | None = None


@dataclass
class TokenResult:
    token_id: str
    fills: list[Fill] = field(default_factory=list)
    equity_final: float = 0.0
    inventory_path: list[tuple[float, float]] = field(default_factory=list)

    @property
    def spread_capture_mean(self) -> float | None:
        if not self.fills:
            return None
        return sum(abs(f.price - f.mid_at_fill) for f in self.fills) / len(self.fills)

    @property
    def markout_mean(self) -> float | None:
        vals = [f.markout for f in self.fills if f.markout is not None]
        if not vals:
            return None
        return sum(vals) / len(vals)


def variance_proxy(mid: float) -> float:
    return mid * (1.0 - mid)


def compute_quotes(mid: float, best_bid: float, best_ask: float,
                   inventory_usd: float, p: QuoteParams
                   ) -> tuple[float | None, float | None]:
    """(bid, ask) fuer diesen Snapshot; None = Seite wird nicht quotiert.

    Skew verschiebt beide Quotes gegen das Inventar; am Cap wird die
    aufbauende Seite ganz gezogen. Quotes kreuzen nie die Gegenseite.
    """
    ratio = max(-1.0, min(1.0, inventory_usd / p.inventory_cap_usd))
    reservation = mid - p.gamma * variance_proxy(mid) * ratio
    bid: float | None = round(reservation - p.half_spread, 4)
    ask: float | None = round(reservation + p.half_spread, 4)
    bid = min(bid, round(best_ask - TICK, 4))  # nicht kreuzen
    ask = max(ask, round(best_bid + TICK, 4))
    bid = max(bid, TICK)
    ask = min(ask, 1.0 - TICK)
    if inventory_usd >= p.inventory_cap_usd:
        bid = None   # voll long: nicht weiter kaufen
    if inventory_usd <= -p.inventory_cap_usd:
        ask = None   # voll short: nicht weiter verkaufen
    return bid, ask


def infer_fills(bid: float | None, ask: float | None,
                next_best_bid: float, next_best_ask: float) -> list[str]:
    """Konservative Fill-Regel: Gegenseite kreuzt unsere Quote."""
    fills: list[str] = []
    if bid is not None and next_best_ask <= bid:
        fills.append("buy")
    if ask is not None and next_best_bid >= ask:
        fills.append("sell")
    return fills


def run_token(token_id: str,
              series: list[tuple[float, float, float]],
              p: QuoteParams) -> TokenResult:
    """Simuliert einen Token; series = zeitsortierte (ts_s, bid, ask)."""
    result = TokenResult(token_id=token_id)
    cash = 0.0
    inventory = 0.0  # Shares, + = long
    quoted_bid: float | None = None
    quoted_ask: float | None = None
    last_mid = None

    for ts, best_bid, best_ask in series:
        if best_ask <= best_bid or best_ask - best_bid > MAX_QUOTE_SPREAD:
            quoted_bid = quoted_ask = None
            continue
        mid = (best_bid + best_ask) / 2.0
        last_mid = mid

        for side in infer_fills(quoted_bid, quoted_ask, best_bid, best_ask):
            price = quoted_bid if side == "buy" else quoted_ask
            shares = round(p.quote_usd / price, 2)
            if side == "buy":
                inventory += shares
                cash -= shares * price
            else:
                inventory -= shares
                cash += shares * price
            result.fills.append(Fill(ts=ts, side=side, price=price,
                                     shares=shares, mid_at_fill=mid))

        inventory_usd = inventory * mid
        result.inventory_path.append((ts, round(inventory_usd, 2)))
        if MID_BOUNDS[0] < mid < MID_BOUNDS[1]:
            quoted_bid, quoted_ask = compute_quotes(
                mid, best_bid, best_ask, inventory_usd, p
            )
        else:
            quoted_bid = quoted_ask = None  # Aufloesungszone: flat gehen

    if last_mid is not None:
        result.equity_final = round(cash + inventory * last_mid, 2)

    # Markouts: Mid nach ~5 Minuten gegen den Fill-Preis, Vorzeichen so,
    # dass negativ = der Markt lief gegen uns (Adverse Selection).
    mids = [(ts, (b + a) / 2.0) for ts, b, a in series if a > b]
    j = 0
    for fill in result.fills:
        target = fill.ts + MARKOUT_HORIZON_S
        limit = target + MARKOUT_MAX_EXTRA_S
        while j < len(mids) and mids[j][0] < target:
            j += 1
        if j >= len(mids) or mids[j][0] > limit:
            j = min(j, len(mids) - 1)
            continue
        later_mid = mids[j][1]
        signed = (later_mid - fill.price if fill.side == "buy"
                  else fill.price - later_mid)
        fill.markout = round(signed * 100.0, 4)  # Cents
    return result


def load_sqlite_touch(path: str) -> dict[str, list[tuple[float, float, float]]]:
    """Per-Token (ts_s, best_bid, best_ask) aus dem Mai-Capture."""
    con = sqlite3.connect(path)
    cur = con.cursor()
    query = (
        "SELECT token_id, captured_at, best_bid, best_ask "
        "FROM orderbook_snapshots "
        "WHERE best_bid IS NOT NULL AND best_ask IS NOT NULL "
        "ORDER BY token_id, captured_at"
    )
    series: dict[str, list[tuple[float, float, float]]] = {}
    for token, ts_ms, bid, ask in cur.execute(query):
        try:
            bid, ask = float(bid), float(ask)
        except (TypeError, ValueError):
            continue
        series.setdefault(str(token), []).append((ts_ms / 1000.0, bid, ask))
    con.close()
    return {
        token: values for token, values in series.items()
        if len(values) >= MIN_SNAPSHOTS_PER_TOKEN
    }


def load_recorder_touch(directory: str) -> dict[str, list[tuple[float, float, float]]]:
    from datetime import datetime, timezone

    series: dict[str, list[tuple[float, float, float]]] = {}
    for path in sorted(Path(directory).glob("books_*.csv")):
        with open(path, newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                try:
                    bid = float(row["best_bid"])
                    ask = float(row["best_ask"])
                except (TypeError, ValueError, KeyError):
                    continue
                ts = datetime.strptime(
                    row["ts_utc"], "%Y-%m-%dT%H:%M:%SZ"
                ).replace(tzinfo=timezone.utc).timestamp()
                series.setdefault(row["token_id"], []).append((ts, bid, ask))
    for values in series.values():
        values.sort(key=lambda item: item[0])
    return {
        token: values for token, values in series.items()
        if len(values) >= 3
    }


def run_experiment(series: dict[str, list[tuple[float, float, float]]],
                   p: QuoteParams) -> dict[str, dict]:
    """Beide Modi (Skew an / gamma=0) ueber alle Tokens."""
    modes = {"skew_on": p, "skew_off": QuoteParams(
        half_spread=p.half_spread, gamma=0.0,
        quote_usd=p.quote_usd, inventory_cap_usd=p.inventory_cap_usd)}
    out: dict[str, dict] = {}
    for mode, params in modes.items():
        token_results = [run_token(t, s, params) for t, s in series.items()]
        fills = [f for r in token_results for f in r.fills]
        markouts = [f.markout for f in fills if f.markout is not None]
        captures = [abs(f.price - f.mid_at_fill) for f in fills]
        inv_abs = [abs(usd) for r in token_results
                   for _, usd in r.inventory_path]
        out[mode] = {
            "params": params,
            "tokens": len(token_results),
            "fills": len(fills),
            "equity_final_sum": round(sum(r.equity_final for r in token_results), 2),
            "spread_capture_mean_cents": round(
                100 * sum(captures) / len(captures), 3) if captures else None,
            "markout_mean_cents": round(
                sum(markouts) / len(markouts), 3) if markouts else None,
            "inventory_abs_mean_usd": round(
                sum(inv_abs) / len(inv_abs), 2) if inv_abs else 0.0,
            "inventory_abs_max_usd": round(max(inv_abs), 2) if inv_abs else 0.0,
            "token_results": token_results,
        }
    return out


def _minute_profile(token_results: list[TokenResult]) -> tuple[list[float], list[float]]:
    """Mittleres |Inventar| in USD je Stunde seit Datenbeginn (Profilkurve)."""
    points = [(ts, abs(usd)) for r in token_results for ts, usd in r.inventory_path]
    if not points:
        return [], []
    t0 = min(ts for ts, _ in points)
    buckets: dict[int, list[float]] = {}
    for ts, usd in points:
        buckets.setdefault(int((ts - t0) // 3600), []).append(usd)
    hours = sorted(buckets)
    return ([h + 0.5 for h in hours],
            [sum(buckets[h]) / len(buckets[h]) for h in hours])


def render_png(experiment: dict[str, dict], meta: dict, out_path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(11.0, 5.0), dpi=150, facecolor=COLOR_SURFACE
    )
    fig.subplots_adjust(top=0.80, bottom=0.13, left=0.08, right=0.98, wspace=0.22)
    for ax in (ax1, ax2):
        ax.set_facecolor(COLOR_SURFACE)
        ax.grid(axis="y", color=COLOR_GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        for spine in ("left", "bottom"):
            ax.spines[spine].set_color(COLOR_GRID)
        ax.tick_params(colors=COLOR_TEXT_2, labelsize=9)

    farben = {"skew_on": COLOR_SKEW_ON, "skew_off": COLOR_SKEW_OFF}
    titel = {"skew_on": "Skew an", "skew_off": "Skew aus"}
    for mode in ("skew_off", "skew_on"):
        hours, profile = _minute_profile(experiment[mode]["token_results"])
        ax1.plot(hours, profile, color=farben[mode], linewidth=2.0,
                 label=titel[mode])
    ax1.set_title("Mittleres |Inventar| ueber den Tag (USD)",
                  color=COLOR_TEXT, fontsize=11, loc="left")
    ax1.set_xlabel("Stunden seit Datenbeginn", color=COLOR_TEXT_2, fontsize=9)
    ax1.legend(frameon=False, fontsize=9, labelcolor=COLOR_TEXT_2)

    metriken = [
        ("Fills", "fills", 1.0),
        ("Spread-Ertrag\n(Cents/Fill)", "spread_capture_mean_cents", 1.0),
        ("Markout 5min\n(Cents/Fill)", "markout_mean_cents", 1.0),
    ]
    x = range(len(metriken))
    breite = 0.36
    for offset, mode in ((-breite / 2, "skew_off"), (breite / 2, "skew_on")):
        werte = []
        for _, key, _ in metriken:
            wert = experiment[mode][key]
            werte.append(0.0 if wert is None else float(wert))
        # Fills auf Hundert normieren, damit eine Achse reicht (Anti-Pattern
        # Doppelachse vermeiden; echte Werte stehen als Label am Balken).
        skaliert = [werte[0] / 100.0] + werte[1:]
        bars = ax2.bar([i + offset for i in x], skaliert, width=breite,
                       color=farben[mode], label=titel[mode])
        for bar, roh in zip(bars, werte):
            ax2.text(bar.get_x() + bar.get_width() / 2,
                     bar.get_height() + (0.02 if bar.get_height() >= 0 else -0.06),
                     f"{roh:+.2f}" if abs(roh) < 100 else f"{roh:.0f}",
                     ha="center", fontsize=8, color=COLOR_TEXT_2)
    ax2.axhline(0, color=COLOR_TEXT_2, linewidth=1.0)
    ax2.set_xticks(list(x))
    ax2.set_xticklabels([m[0] for m in metriken], fontsize=8.5)
    ax2.set_title("Kernmetriken je Modus (Fills in Hundert)",
                  color=COLOR_TEXT, fontsize=11, loc="left")
    ax2.legend(frameon=False, fontsize=9, labelcolor=COLOR_TEXT_2)

    fig.suptitle(
        f"Paper-MM-Simulator — {meta['quelle']} ({meta['tokens']} Tokens, "
        f"halber Spread {meta['half_spread']}, gamma {meta['gamma']}, "
        f"konservative Fill-Regel)",
        color=COLOR_TEXT, fontsize=12, x=0.02, y=0.95, ha="left",
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, facecolor=COLOR_SURFACE)
    plt.close(fig)


def write_outputs(experiment: dict[str, dict], meta: dict, tag: str,
                  reports_dir: Path = REPORTS_DIR) -> dict[str, Path]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    csv_path = reports_dir / f"mm_sim_{tag}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["mode", "token_id", "fills", "equity_final_usd",
                         "spread_capture_mean_cents", "markout_mean_cents"])
        for mode, data in experiment.items():
            for r in data["token_results"]:
                writer.writerow([
                    mode, r.token_id, len(r.fills), r.equity_final,
                    round(100 * r.spread_capture_mean, 3)
                    if r.spread_capture_mean is not None else None,
                    r.markout_mean,
                ])

    png_path = reports_dir / f"mm_sim_{tag}.png"
    render_png(experiment, meta, png_path)

    md_path = reports_dir / f"mm_sim_{tag}.md"
    lines = [
        f"# Paper-MM-Simulator ({tag})",
        "",
        f"Quelle: {meta['quelle']} — {meta['tokens']} Tokens, halber Spread "
        f"{meta['half_spread']}, gamma {meta['gamma']}, Quote "
        f"{meta['quote_usd']} USD, Inventar-Cap {meta['cap_usd']} USD.",
        "",
        "| Metrik | Skew aus | Skew an |",
        "|---|---|---|",
    ]
    zeilen = [
        ("Fills", "fills", "{:.0f}"),
        ("Spread-Ertrag (Cents/Fill)", "spread_capture_mean_cents", "{:+.2f}"),
        ("Markout 5min (Cents/Fill)", "markout_mean_cents", "{:+.2f}"),
        ("Mittleres |Inventar| (USD)", "inventory_abs_mean_usd", "{:.2f}"),
        ("Max |Inventar| (USD)", "inventory_abs_max_usd", "{:.2f}"),
        ("Endwert mark-to-mid (USD)", "equity_final_sum", "{:+.2f}"),
    ]
    for name, key, fmt in zeilen:
        aus = experiment["skew_off"][key]
        an = experiment["skew_on"][key]
        lines.append(
            f"| {name} | {fmt.format(aus) if aus is not None else '-'} "
            f"| {fmt.format(an) if an is not None else '-'} |"
        )
    lines += [
        "",
        "Fill-Regel: konservativ — eine Quote gilt nur als gefuellt, wenn die "
        "Gegenseite sie zwischen zwei Snapshots kreuzt (kein oeffentliches "
        "Tape im Mai-Capture; Queue-Fills am Touch fehlen bewusst). Markout "
        "negativ = der Markt lief nach dem Fill gegen uns (Adverse "
        "Selection). Mark-to-mid ohne Aufloesungs-Modellierung; Quotes nur "
        "bei Mid in (0.05, 0.95) und Spread <= 0.10. Paper-only, keine "
        "Handelsempfehlung.",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return {"csv": csv_path, "png": png_path, "md": md_path}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--sqlite")
    source.add_argument("--recorder-dir")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--half-spread", type=float, default=0.01)
    parser.add_argument("--gamma", type=float, default=0.08)
    parser.add_argument("--quote-usd", type=float, default=50.0)
    parser.add_argument("--cap-usd", type=float, default=250.0)
    args = parser.parse_args(argv)

    if args.sqlite:
        series = load_sqlite_touch(args.sqlite)
        quelle = Path(args.sqlite).name
    else:
        series = load_recorder_touch(args.recorder_dir)
        quelle = f"book_recorder ({args.recorder_dir})"

    params = QuoteParams(half_spread=args.half_spread, gamma=args.gamma,
                         quote_usd=args.quote_usd,
                         inventory_cap_usd=args.cap_usd)
    experiment = run_experiment(series, params)
    meta = {
        "quelle": quelle, "tokens": len(series),
        "half_spread": args.half_spread, "gamma": args.gamma,
        "quote_usd": args.quote_usd, "cap_usd": args.cap_usd,
    }
    paths = write_outputs(experiment, meta, args.tag)
    for mode in ("skew_off", "skew_on"):
        data = {k: v for k, v in experiment[mode].items()
                if k not in ("token_results", "params")}
        print(mode, data)
    print({key: str(path) for key, path in paths.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
