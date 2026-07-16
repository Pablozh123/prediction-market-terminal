"""Book-imbalance vs. forward mid-drift on recorded Polymarket order books.

Question: does the bid share of top-5 depth (imbalance in [0, 1]) predict
the direction of the mid price over the next minutes?

Data sources:
- ``orderbook_snapshots`` from a prediction-alpha-bot forward-replay
  SQLite capture (May 2026), or
- the day-partitioned CSVs written by ``src/book_recorder.py``.

Outputs (under ``reports/``): a two-panel PNG (mean drift and directional
hit rate per imbalance bucket, 5-minute horizon), a CSV with all horizons,
and a short markdown summary with the applied filters.

Read-only research tooling: no order path, no credentials, no wallets.

Usage:
  python -m src.imbalance_study --sqlite <forward-clean.db> --tag 2026-05-30
  python -m src.imbalance_study --recorder-dir data/microstructure --tag live
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = REPO_ROOT / "reports"

HORIZONS_S = (60, 300, 1800)
PLOT_HORIZON_S = 300
BUCKETS = ((0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0001))
NEUTRAL_BUCKET = 2  # 0.4-0.6 traegt keine Richtung

# Filter (Engineering-Wahl, im Report dokumentiert)
MAX_SPREAD = 0.10
MID_BOUNDS = (0.02, 0.98)
MIN_TOP5_USD = 50.0

# Validierte Referenzpalette (dataviz-Skill), Light-Mode
COLOR_SERIES = "#2a78d6"
COLOR_SURFACE = "#fcfcfb"
COLOR_TEXT = "#0b0b0b"
COLOR_TEXT_2 = "#52514e"
COLOR_GRID = "#e5e4e0"


def wilson_lb(successes: int, n: int, z: float = 1.96) -> float:
    """Lower bound of the Wilson score interval (95% default)."""
    if n <= 0:
        return 0.0
    p = successes / n
    denom = 1.0 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return max(0.0, (centre - margin) / denom)


def _levels_usd(levels_json: str | None, levels: int = 5) -> float | None:
    if not levels_json:
        return None
    try:
        parsed = json.loads(levels_json)
    except (TypeError, ValueError):
        return None
    usd = 0.0
    count = 0
    for level in parsed:
        try:
            price, size = float(level[0]), float(level[1])
        except (TypeError, ValueError, KeyError, IndexError):
            try:
                price, size = float(level["price"]), float(level["size"])
            except (TypeError, ValueError, KeyError):
                continue
        usd += price * size
        count += 1
        if count >= levels:
            break
    return usd


def imbalance_from_json(bids_json: str | None, asks_json: str | None,
                        min_total_usd: float = MIN_TOP5_USD) -> float | None:
    """Bid share of top-5 USD depth, or None if the book is too thin."""
    bid_usd = _levels_usd(bids_json)
    ask_usd = _levels_usd(asks_json)
    if bid_usd is None or ask_usd is None:
        return None
    total = bid_usd + ask_usd
    if total < min_total_usd:
        return None
    return bid_usd / total


def forward_pairs(series: list[tuple[float, float, float]],
                  horizon_s: float) -> list[tuple[float, float]]:
    """(imbalance, forward drift in cents) per snapshot of one token.

    ``series`` is time-sorted ``(ts_seconds, mid, imbalance)``. The forward
    mid is the first snapshot at least ``horizon_s`` later but no more than
    ``2 * horizon_s`` later (as-of join with bounded staleness).
    """
    pairs: list[tuple[float, float]] = []
    j = 0
    for i, (ts, mid, imb) in enumerate(series):
        target = ts + horizon_s
        limit = ts + 2 * horizon_s
        if j <= i:
            j = i + 1
        while j < len(series) and series[j][0] < target:
            j += 1
        if j >= len(series) or series[j][0] > limit:
            continue
        pairs.append((imb, round((series[j][1] - mid) * 100.0, 4)))
    return pairs


def bucketize(pairs: list[tuple[float, float]]) -> list[dict]:
    """Aggregate (imbalance, drift) pairs into the fixed buckets.

    Auf duennen Maerkten ist der 5-Minuten-Drift meistens exakt null,
    darum ist die Trefferquote BEDINGT definiert: Richtungsanteil unter
    den Paaren, die sich ueberhaupt bewegt haben. ``moved_share`` macht
    den Anteil bewegter Paare sichtbar.
    """
    rows = []
    for index, (lo, hi) in enumerate(BUCKETS):
        bucket = [drift for imb, drift in pairs if lo <= imb < hi]
        n = len(bucket)
        moved = [drift for drift in bucket if drift != 0.0]
        mean_drift = sum(bucket) / n if n else 0.0
        if index == NEUTRAL_BUCKET or not moved:
            hits = None
        elif index < NEUTRAL_BUCKET:
            hits = sum(1 for drift in moved if drift < 0)
        else:
            hits = sum(1 for drift in moved if drift > 0)
        rows.append({
            "bucket": f"{lo:.1f}-{min(hi, 1.0):.1f}",
            "n": n,
            "moved": len(moved),
            "moved_share": round(len(moved) / n, 4) if n else None,
            "mean_drift_cents": round(mean_drift, 3),
            "hits": hits,
            "hit_rate": round(hits / len(moved), 4) if hits is not None else None,
            "wilson_lb95": round(wilson_lb(hits, len(moved)), 4)
            if hits is not None else None,
        })
    return rows


def load_sqlite(path: str) -> dict[str, list[tuple[float, float, float]]]:
    """Per-token time series from a forward-replay capture."""
    con = sqlite3.connect(path)
    cur = con.cursor()
    query = (
        "SELECT token_id, captured_at, best_bid, best_ask, bids_json, asks_json "
        "FROM orderbook_snapshots "
        "WHERE best_bid IS NOT NULL AND best_ask IS NOT NULL "
        "ORDER BY token_id, captured_at"
    )
    series: dict[str, list[tuple[float, float, float]]] = {}
    for token, ts_ms, bid, ask, bids_json, asks_json in cur.execute(query):
        try:
            bid, ask = float(bid), float(ask)
        except (TypeError, ValueError):
            continue
        if ask - bid > MAX_SPREAD or ask <= bid:
            continue
        mid = (bid + ask) / 2.0
        if not (MID_BOUNDS[0] < mid < MID_BOUNDS[1]):
            continue
        imb = imbalance_from_json(bids_json, asks_json)
        if imb is None:
            continue
        series.setdefault(str(token), []).append((ts_ms / 1000.0, mid, imb))
    con.close()
    return series


def load_recorder(directory: str) -> dict[str, list[tuple[float, float, float]]]:
    """Per-token series from book_recorder CSVs (books_*.csv)."""
    from datetime import datetime, timezone

    series: dict[str, list[tuple[float, float, float]]] = {}
    for path in sorted(Path(directory).glob("books_*.csv")):
        with open(path, newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                try:
                    mid = float(row["mid"])
                    imb = float(row["imbalance_top"])
                    spread = float(row["spread"])
                except (TypeError, ValueError, KeyError):
                    continue
                if spread > MAX_SPREAD or not (MID_BOUNDS[0] < mid < MID_BOUNDS[1]):
                    continue
                ts = datetime.strptime(
                    row["ts_utc"], "%Y-%m-%dT%H:%M:%SZ"
                ).replace(tzinfo=timezone.utc).timestamp()
                series.setdefault(row["token_id"], []).append((ts, mid, imb))
    for values in series.values():
        values.sort(key=lambda item: item[0])
    return series


def analyse(series: dict[str, list[tuple[float, float, float]]]) -> dict[int, list[dict]]:
    results: dict[int, list[dict]] = {}
    for horizon in HORIZONS_S:
        pairs: list[tuple[float, float]] = []
        for token_series in series.values():
            pairs.extend(forward_pairs(token_series, horizon))
        results[horizon] = bucketize(pairs)
    return results


MIN_MOVED_FOR_HIT_PANEL = 30  # Buckets mit weniger bewegten Paaren ausblenden


def _tsd(value: int) -> str:
    return f"{value:,}".replace(",", "'")


def render_png(rows: list[dict], meta: dict, out_path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = [row["bucket"] for row in rows]
    drifts = [row["mean_drift_cents"] for row in rows]
    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(11.0, 5.0), dpi=150, facecolor=COLOR_SURFACE
    )
    fig.subplots_adjust(top=0.80, bottom=0.13, left=0.07, right=0.98, wspace=0.20)
    for ax in (ax1, ax2):
        ax.set_facecolor(COLOR_SURFACE)
        ax.grid(axis="y", color=COLOR_GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        for spine in ("left", "bottom"):
            ax.spines[spine].set_color(COLOR_GRID)
        ax.tick_params(colors=COLOR_TEXT_2, labelsize=9)

    bars = ax1.bar(labels, drifts, width=0.62, color=COLOR_SERIES)
    ax1.axhline(0, color=COLOR_TEXT_2, linewidth=1.0)
    span = max(abs(d) for d in drifts) or 0.01
    ax1.set_ylim(min(0.0, min(drifts)) - 0.55 * span, max(drifts) + 0.55 * span)
    ax1.set_title("Mittlerer Mid-Drift nach 5 Minuten (Cents)",
                  color=COLOR_TEXT, fontsize=11, loc="left")
    ax1.set_xlabel("Imbalance-Bucket (Bid-Anteil Top-5-Tiefe)",
                   color=COLOR_TEXT_2, fontsize=9)
    for bar, row in zip(bars, rows):
        above = bar.get_height() >= 0
        offset = 0.06 * span if above else -0.06 * span
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + offset,
                 f"{row['mean_drift_cents']:+.2f}\nn={_tsd(row['n'])}",
                 ha="center", va="bottom" if above else "top",
                 fontsize=8, color=COLOR_TEXT_2)

    shown = [row for row in rows
             if row["hit_rate"] is not None
             and row["moved"] >= MIN_MOVED_FOR_HIT_PANEL]
    hidden = [row["bucket"] for row in rows
              if row["hit_rate"] is not None
              and row["moved"] < MIN_MOVED_FOR_HIT_PANEL]
    bars2 = ax2.bar([r["bucket"] for r in shown], [r["hit_rate"] for r in shown],
                    width=0.62, color=COLOR_SERIES)
    ax2.axhline(0.5, color=COLOR_TEXT_2, linewidth=1.0, linestyle=(0, (4, 3)))
    ax2.set_ylim(0.0, 1.0)
    ax2.set_title("Trefferquote bei Bewegung (Punkt und Wilson-lb95)",
                  color=COLOR_TEXT, fontsize=11, loc="left")
    xlabel = "Basis: bewegte Paare"
    if hidden:
        xlabel += f"; ohne {', '.join(hidden)} (bewegt<{MIN_MOVED_FOR_HIT_PANEL})"
    ax2.set_xlabel(xlabel, color=COLOR_TEXT_2, fontsize=8.5)
    for bar, row in zip(bars2, shown):
        x = bar.get_x() + bar.get_width() / 2
        ax2.plot([x - 0.18, x + 0.18], [row["wilson_lb95"]] * 2,
                 color=COLOR_TEXT, linewidth=1.6)
        ax2.text(x, row["hit_rate"] + 0.035,
                 f"{row['hit_rate']:.0%} (n={_tsd(row['moved'])})",
                 ha="center", fontsize=8, color=COLOR_TEXT_2)

    fig.suptitle(
        f"Book-Imbalance vs. Forward-Drift — {meta['quelle']} "
        f"({_tsd(meta['paare_5min'])} Paare, {meta['tokens']} Tokens)",
        color=COLOR_TEXT, fontsize=12, x=0.02, y=0.95, ha="left",
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, facecolor=COLOR_SURFACE)
    plt.close(fig)


def write_outputs(results: dict[int, list[dict]], meta: dict, tag: str,
                  reports_dir: Path = REPORTS_DIR) -> dict[str, Path]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    csv_path = reports_dir / f"imbalance_study_{tag}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["horizon_s", "bucket", "n", "moved", "moved_share",
                         "mean_drift_cents", "hits", "hit_rate", "wilson_lb95"])
        for horizon, rows in sorted(results.items()):
            for row in rows:
                writer.writerow([horizon, row["bucket"], row["n"],
                                 row["moved"], row["moved_share"],
                                 row["mean_drift_cents"], row["hits"],
                                 row["hit_rate"], row["wilson_lb95"]])

    png_path = reports_dir / f"imbalance_study_{tag}.png"
    render_png(results[PLOT_HORIZON_S], meta, png_path)

    md_path = reports_dir / f"imbalance_study_{tag}.md"
    rows5 = results[PLOT_HORIZON_S]
    lines = [
        f"# Book-Imbalance-Studie ({tag})",
        "",
        f"Quelle: {meta['quelle']} — {meta['tokens']} Tokens, "
        f"{meta['snapshots']:,} gefilterte Snapshots, "
        f"{meta['paare_5min']:,} 5-Minuten-Paare.".replace(",", "'"),
        "",
        "Filter: Spread <= 0.10, Mid in (0.02, 0.98), Top-5-Tiefe >= 50 USD, "
        "Forward-Join first snapshot in [H, 2H].",
        "",
        "| Bucket | n | bewegt | Drift 5min (c) | Hit-Rate (bewegt) | Wilson lb95 |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows5:
        hit = f"{row['hit_rate']:.1%}" if row["hit_rate"] is not None else "-"
        lb = f"{row['wilson_lb95']:.1%}" if row["wilson_lb95"] is not None else "-"
        moved = (f"{row['moved_share']:.1%}"
                 if row["moved_share"] is not None else "-")
        lines.append(
            f"| {row['bucket']} | {row['n']:,} | {moved} "
            f"| {row['mean_drift_cents']:+.2f} | {hit} | {lb} |".replace(",", "'")
        )
    lines += [
        "",
        "Lesart: Buckets unter 0.5 gelten als Treffer bei negativem Drift, "
        "ueber 0.5 bei positivem; die neutrale Mitte (0.4-0.6) traegt keine "
        "Richtung. Die Trefferquote ist bedingt auf Paare mit Bewegung "
        "(auf duennen Maerkten ist der 5-Minuten-Drift meist exakt null).",
        "",
        "Caveat Datenquelle (Mai-Capture): Die Snapshots stammen aus dem "
        "Arb-Scanner-Forward-Replay; das Universum sind Basket-/Arb-Legs "
        "und damit ask-lastige Buecher (Grossteil der Paare im Bucket "
        "0.0-0.2). Das ist Selektions-Bias, kein Marktquerschnitt. Die "
        "saubere Wiederholung laeuft auf den Recorder-Daten "
        "(src/book_recorder.py, volumenstaerkste Maerkte, beide Tokens). "
        "Keine Handelsempfehlung.",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return {"csv": csv_path, "png": png_path, "md": md_path}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--sqlite", help="forward-replay capture (orderbook_snapshots)")
    source.add_argument("--recorder-dir", help="directory with books_*.csv")
    parser.add_argument("--tag", required=True, help="output filename tag")
    args = parser.parse_args(argv)

    if args.sqlite:
        series = load_sqlite(args.sqlite)
        quelle = Path(args.sqlite).name
    else:
        series = load_recorder(args.recorder_dir)
        quelle = f"book_recorder ({args.recorder_dir})"

    snapshots = sum(len(values) for values in series.values())
    results = analyse(series)
    meta = {
        "quelle": quelle,
        "tokens": len(series),
        "snapshots": snapshots,
        "paare_5min": sum(row["n"] for row in results[PLOT_HORIZON_S]),
    }
    paths = write_outputs(results, meta, args.tag)
    for row in results[PLOT_HORIZON_S]:
        print(row)
    print({key: str(path) for key, path in paths.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
