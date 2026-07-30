"""Where, if anywhere, does a signal survive its costs?

The order-flow study ends on an aggregate: book imbalance points the right way
about 55 percent of the time and still loses money as a taker, with only about
4 percent of firings ending net positive. That aggregate is the wrong place to
stop. The useful question is whether those 4 percent sit somewhere you can
recognise BEFORE the trade, or whether they are scattered noise.

That distinction is the whole game. A filter built on something knowable at
decision time (the spread you can see, the price level, how far the signal is
from neutral, which fee category the market sits in) is a strategy. A filter
built on anything only knowable afterwards is a backtest artefact.

So every segmentation here is restricted to ex-ante observables, and every
segment is scored three ways:

  in-sample     the mean net edge over all days, which is what data mining
                would report and by itself proves nothing
  walk-forward  the same segment scored only on days after the ones used to
                find it
  bootstrap CI  resampled by whole days, because snapshots within a day are
                anything but independent

A segment counts as a candidate only when the out-of-sample number survives
too. The module deliberately reports the losers as well: with enough segments
something always looks good in sample, and hiding that is how a backtest turns
into a story.

Read-only research tooling: no order path, no credentials, no wallets.

Usage:
  python -m src.edge_segments --recorder-dir data/microstructure --tag july
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from app import venue_fees as vf
from src import orderflow_study as ofs

REPO_ROOT = Path(__file__).resolve().parents[1]
RESEARCH_DIR = REPO_ROOT / "docs" / "research"

#: Kategorien, deren Taker-Gebuehr sich real unterscheidet. Geopolitik ist
#: gebuehrenfrei und damit der schaerfste Test: dort bleibt nur der Spread.
FEE_SCENARIOS = ("sports", "politics", "geopolitics")

#: Ex-ante bekannte Schnitte. Jede Grenze ist beim Entscheiden sichtbar.
SPREAD_BUCKETS_CENTS = ((0.0, 0.5), (0.5, 1.0), (1.0, 2.0), (2.0, 5.0), (5.0, 10.1))
PRICE_BUCKETS = ((0.05, 0.15), (0.15, 0.35), (0.35, 0.65), (0.65, 0.85), (0.85, 0.95))
STRENGTH_BUCKETS = ((0.65, 0.75), (0.75, 0.85), (0.85, 0.95), (0.95, 1.01))

#: Ohne diese Mindestzahl je Segment ist die Aussage nicht belastbar.
MIN_OBSERVATIONS = 300

# Validierte Referenzpalette (dataviz-Skill), Light-Mode
COLOR_POS = "#1baf7a"
COLOR_NEG = "#d6452a"
COLOR_SURFACE = "#fcfcfb"
COLOR_TEXT = "#0b0b0b"
COLOR_TEXT_2 = "#52514e"
COLOR_GRID = "#e5e4e0"


def _bucket_label(lo: float, hi: float, unit: str = "") -> str:
    return f"{lo:g}-{hi:g}{unit}"


def spread_segment(observation: ofs.Observation) -> str | None:
    for lo, hi in SPREAD_BUCKETS_CENTS:
        if lo <= observation.spread_cents < hi:
            return _bucket_label(lo, hi, "c")
    return None


def price_segment(observation: ofs.Observation) -> str | None:
    for lo, hi in PRICE_BUCKETS:
        if lo <= observation.entry_mid < hi:
            return _bucket_label(lo, hi)
    return None


def strength_segment(observation: ofs.Observation) -> str | None:
    """How far from neutral the signal fired, mirrored so both sides share bins."""
    distance = max(observation.strength, 1.0 - observation.strength)
    for lo, hi in STRENGTH_BUCKETS:
        if lo <= distance < hi:
            return _bucket_label(lo, hi)
    return None


SEGMENTERS = {
    "spread": spread_segment,
    "price": price_segment,
    "strength": strength_segment,
}


def rescore(observation: ofs.Observation, category: str,
            venue: str = "polymarket") -> float:
    """Net edge of one observation under a different fee category.

    The observation already carries its gross move and its spread cost, both of
    which are independent of the fee. Only the fee leg changes, so a category
    swap is arithmetic rather than a re-run over the raw data.
    """
    fee = 2.0 * vf.fee_cents_per_share(venue, observation.entry_mid, category,
                                       shares=100.0)
    return round(observation.gross_cents - observation.spread_cost_cents - fee, 4)


def score_segment(observations: list[ofs.Observation], category: str,
                  train_share: float = 0.6) -> dict:
    """In-sample, out-of-sample and a day-resampled interval for one segment."""
    if not observations:
        return {"n": 0}
    nets = [rescore(o, category) for o in observations]
    days = [o.day for o in observations]
    train, test = ofs.walk_forward_split(observations, train_share)
    gross = [o.gross_cents for o in observations]
    moved = [o for o in observations if o.gross_cents != 0.0]
    hits = sum(1 for o in moved if o.gross_cents > 0)
    return {
        "n": len(observations),
        "days": len(set(days)),
        "mean_gross_cents": round(sum(gross) / len(gross), 4),
        "mean_net_cents": round(sum(nets) / len(nets), 4),
        "hit_rate": round(hits / len(moved), 4) if moved else None,
        "wilson_lb95": round(ofs.wilson_lb(hits, len(moved)), 4) if moved else None,
        "net_positive_share": round(
            sum(1 for value in nets if value > 0) / len(nets), 4),
        "train_net_cents": round(
            sum(rescore(o, category) for o in train) / len(train), 4) if train else None,
        "test_net_cents": round(
            sum(rescore(o, category) for o in test) / len(test), 4) if test else None,
        "net_ci95_cents": ofs.block_bootstrap_ci(nets, days),
    }


def segment_table(observations: list[ofs.Observation], key: str,
                  category: str, min_observations: int = MIN_OBSERVATIONS) -> list[dict]:
    """Score every bucket of one segmentation, thin buckets included but flagged."""
    segmenter = SEGMENTERS[key]
    buckets: dict[str, list[ofs.Observation]] = {}
    for observation in observations:
        label = segmenter(observation)
        if label is not None:
            buckets.setdefault(label, []).append(observation)
    rows = []
    for label in sorted(buckets):
        stats = score_segment(buckets[label], category)
        stats.update({
            "segment": key,
            "bucket": label,
            "category": category,
            "thin": stats["n"] < min_observations,
        })
        rows.append(stats)
    return rows


def cross_segment_table(observations: list[ofs.Observation], category: str,
                        min_observations: int = MIN_OBSERVATIONS) -> list[dict]:
    """Spread crossed with signal strength.

    Single cuts can hide each other: a tight spread helps only if the signal is
    also strong, and a strong signal in a wide book still pays the spread. The
    cross is where a usable filter would show up if there is one.
    """
    buckets: dict[tuple[str, str], list[ofs.Observation]] = {}
    for observation in observations:
        spread = spread_segment(observation)
        strength = strength_segment(observation)
        if spread is None or strength is None:
            continue
        buckets.setdefault((spread, strength), []).append(observation)
    rows = []
    for (spread, strength) in sorted(buckets):
        stats = score_segment(buckets[(spread, strength)], category)
        stats.update({
            "spread_bucket": spread,
            "strength_bucket": strength,
            "category": category,
            "thin": stats["n"] < min_observations,
        })
        rows.append(stats)
    return rows


def survivors(rows: list[dict], min_observations: int = MIN_OBSERVATIONS) -> list[dict]:
    """Segments that are positive in sample AND out of sample AND not thin.

    The out-of-sample condition is the one that matters. Everything that only
    clears the in-sample bar is what data mining produces for free.
    """
    out = []
    for row in rows:
        if row.get("n", 0) < min_observations:
            continue
        net = row.get("mean_net_cents")
        test = row.get("test_net_cents")
        if net is None or test is None:
            continue
        if net > 0 and test > 0:
            out.append(row)
    return sorted(out, key=lambda r: r["test_net_cents"], reverse=True)


def run_study(directory: str | Path, stream: bool = False,
              signal: str = "imbalance", threshold: float = 0.65,
              horizon_s: float = 300.0,
              categories: tuple[str, ...] = FEE_SCENARIOS) -> dict:
    """Segment one signal's firings across every ex-ante cut and fee scenario."""
    books = ofs.load_books(directory, stream=stream)
    tape = ofs.load_tape(directory, stream=stream)
    observations = ofs.build_observations(
        books, tape, signal=signal, threshold=threshold,
        delays_s=(0.0,), horizons_s=(horizon_s,), category=categories[0])
    results: dict = {
        "source": str(directory),
        "stream": stream,
        "signal": signal,
        "threshold": threshold,
        "horizon_s": horizon_s,
        "observations": len(observations),
        "days": sorted({o.day for o in observations}),
        "fee_model_version": vf.FEE_MODEL_VERSION,
        "min_observations": MIN_OBSERVATIONS,
        "by_category": {},
    }
    for category in categories:
        entry = {
            "overall": score_segment(observations, category),
            "segments": {key: segment_table(observations, key, category)
                         for key in SEGMENTERS},
            "cross": cross_segment_table(observations, category),
        }
        pooled = [row for rows in entry["segments"].values() for row in rows]
        pooled += entry["cross"]
        entry["survivors"] = survivors(pooled)
        entry["tested_segments"] = len(pooled)
        results["by_category"][category] = entry
    return results


def render_png(results: dict, out_path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    categories = list(results["by_category"])
    fig, axes = plt.subplots(1, len(categories), figsize=(4.0 * len(categories), 5.0),
                             dpi=150, facecolor=COLOR_SURFACE, squeeze=False)
    for index, category in enumerate(categories):
        ax = axes[0][index]
        ax.set_facecolor(COLOR_SURFACE)
        ax.grid(axis="x", color=COLOR_GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        for spine in ("left", "bottom"):
            ax.spines[spine].set_color(COLOR_GRID)
        ax.tick_params(colors=COLOR_TEXT_2, labelsize=8)

        rows = [r for r in results["by_category"][category]["segments"]["spread"]
                if not r["thin"]]
        labels = [r["bucket"] for r in rows]
        values = [r["mean_net_cents"] for r in rows]
        colors = [COLOR_POS if v > 0 else COLOR_NEG for v in values]
        ax.barh(range(len(labels)), values, color=colors)
        ax.axvline(0, color=COLOR_TEXT_2, linewidth=1.0)
        ax.set_yticks(range(len(labels)))
        ax.set_yticklabels(labels, fontsize=8)
        ax.set_xlabel("Netto (Cents je Signal)", color=COLOR_TEXT_2, fontsize=9)
        ax.set_title(f"{category} (Rate {vf.polymarket_category_rate(category)})",
                     color=COLOR_TEXT, fontsize=10, loc="left")

    fig.suptitle(
        f"Netto-Kante je Spread-Bucket und Gebuehrenkategorie — Signal "
        f"{results['signal']}, {results['observations']:,} Firings, "
        f"{len(results['days'])} Tage",
        color=COLOR_TEXT, fontsize=11.5, x=0.02, y=0.97, ha="left")
    fig.subplots_adjust(top=0.84, bottom=0.11, left=0.09, right=0.98, wspace=0.35)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, facecolor=COLOR_SURFACE)
    plt.close(fig)


def _fmt(value, spec="{:+.3f}") -> str:
    return "-" if value is None else spec.format(value)


def _markdown(results: dict, tag: str) -> str:
    days = results["days"]
    lines = [
        f"# Wo sitzt die Kante? Segmentierung ({tag})",
        "",
        f"Quelle: {results['source']} "
        f"({'Stream' if results['stream'] else 'REST, 120s-Raster'}), Signal "
        f"{results['signal']} mit Schwelle {results['threshold']}, Horizont "
        f"{int(results['horizon_s'])}s, {results['observations']:,} Firings an "
        f"{len(days)} Tagen ({days[0] if days else '-'} bis "
        f"{days[-1] if days else '-'}). Gebuehrenstand "
        f"{results['fee_model_version']}.",
        "",
        "Alle Schnitte sind ex ante bekannt: Spread und Preis stehen beim "
        "Entscheiden im Buch, die Signalstaerke ergibt sich aus dem Signal "
        "selbst, die Gebuehrenkategorie aus dem Markt. Kein Schnitt benutzt "
        "etwas, das erst hinterher bekannt ist.",
        "",
    ]
    for category, entry in results["by_category"].items():
        overall = entry["overall"]
        rate = vf.polymarket_category_rate(category)
        lines += [
            f"## Gebuehrenkategorie {category} (Rate {rate})",
            "",
            f"Gesamt: netto {_fmt(overall['mean_net_cents'])} Cents je Signal, "
            f"brutto {_fmt(overall['mean_gross_cents'])}, netto positiv in "
            f"{_fmt(overall['net_positive_share'], '{:.1%}')} der Faelle. "
            f"Getestete Segmente: {entry['tested_segments']}.",
            "",
        ]
        for key, rows in entry["segments"].items():
            lines += [
                f"### Schnitt: {key}",
                "",
                "| Bucket | n | Brutto | Netto | Netto in-sample | Netto "
                "out-of-sample | CI95 | duenn |",
                "|---|---|---|---|---|---|---|---|",
            ]
            for row in rows:
                lines.append(
                    f"| {row['bucket']} | {row['n']:,} | "
                    f"{_fmt(row['mean_gross_cents'])} | "
                    f"{_fmt(row['mean_net_cents'])} | "
                    f"{_fmt(row['train_net_cents'])} | "
                    f"{_fmt(row['test_net_cents'])} | "
                    f"{row['net_ci95_cents'] or '-'} | "
                    f"{'ja' if row['thin'] else 'nein'} |")
            lines.append("")
        winners = entry["survivors"]
        if winners:
            lines += [
                "### Kandidaten (positiv in-sample UND out-of-sample, nicht duenn)",
                "",
                "| Segment | n | Netto | out-of-sample | CI95 |",
                "|---|---|---|---|---|",
            ]
            for row in winners:
                label = row.get("bucket") or (
                    f"{row.get('spread_bucket')} x {row.get('strength_bucket')}")
                lines.append(
                    f"| {row.get('segment', 'spread x strength')}: {label} | "
                    f"{row['n']:,} | {_fmt(row['mean_net_cents'])} | "
                    f"{_fmt(row['test_net_cents'])} | "
                    f"{row['net_ci95_cents'] or '-'} |")
            lines.append("")
        else:
            lines += [
                "### Kandidaten",
                "",
                f"Keine. Von {entry['tested_segments']} getesteten Segmenten "
                "ueberlebt keines gleichzeitig die In-sample- und die "
                "Out-of-sample-Bedingung bei ausreichender Fallzahl.",
                "",
            ]
    lines += [
        "## Lesehilfe",
        "",
        "Die Spalte out-of-sample ist die einzige, die zaehlt. Ein Segment, das "
        "nur in-sample positiv ist, ist genau das, was Data Mining gratis "
        "liefert: bei genuegend vielen Schnitten sieht immer irgendeiner gut "
        "aus. Die Zahl der getesteten Segmente steht deshalb im Kopf jedes "
        "Abschnitts, damit die Auswahlwahrscheinlichkeit sichtbar bleibt.",
        "",
        "Die Gebuehrenkategorien sind das schaerfste Instrument in dieser "
        "Tabelle, weil sie denselben Datensatz unter verschiedenen Kosten "
        "zeigen. Geopolitik ist gebuehrenfrei, dort bleibt als Kosten nur der "
        "Spread. Bleibt die Kante auch dort negativ, liegt es nicht an den "
        "Gebuehren, sondern daran, dass die Bewegung zu klein ist.",
        "",
        "Duenne Segmente sind markiert und aus der Kandidatenliste "
        "ausgeschlossen, aber absichtlich mit abgedruckt: ein Segment mit 40 "
        "Beobachtungen und grosser Zahl ist kein Fund, sondern Rauschen, und "
        "das soll man sehen statt es wegzulassen.",
        "",
        "Read-only-Forschung, keine Handelsempfehlung.",
    ]
    return "\n".join(lines)


def write_outputs(results: dict, tag: str,
                  research_dir: Path = RESEARCH_DIR) -> dict[str, Path]:
    research_dir.mkdir(parents=True, exist_ok=True)
    json_path = research_dir / f"edge_segments_{tag}.json"
    json_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

    csv_path = research_dir / f"edge_segments_{tag}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["category", "segment", "bucket", "n", "days",
                         "mean_gross_cents", "mean_net_cents",
                         "train_net_cents", "test_net_cents", "hit_rate",
                         "net_positive_share", "thin"])
        for category, entry in results["by_category"].items():
            for key, rows in entry["segments"].items():
                for row in rows:
                    writer.writerow([category, key, row["bucket"], row["n"],
                                     row["days"], row["mean_gross_cents"],
                                     row["mean_net_cents"], row["train_net_cents"],
                                     row["test_net_cents"], row["hit_rate"],
                                     row["net_positive_share"], row["thin"]])
            for row in entry["cross"]:
                writer.writerow([category, "spread x strength",
                                 f"{row['spread_bucket']} x {row['strength_bucket']}",
                                 row["n"], row["days"], row["mean_gross_cents"],
                                 row["mean_net_cents"], row["train_net_cents"],
                                 row["test_net_cents"], row["hit_rate"],
                                 row["net_positive_share"], row["thin"]])

    md_path = research_dir / f"edge_segments_{tag}.md"
    md_path.write_text(_markdown(results, tag), encoding="utf-8")

    paths = {"json": json_path, "csv": csv_path, "md": md_path}
    png_path = research_dir / f"edge_segments_{tag}.png"
    try:
        render_png(results, png_path)
        paths["png"] = png_path
    except Exception as exc:  # noqa: BLE001 - Grafik darf den Report nicht kippen
        print(f"[edge_segments] PNG uebersprungen: {exc}")
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--recorder-dir", required=True)
    parser.add_argument("--stream", action="store_true")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--signal", default="imbalance")
    parser.add_argument("--threshold", type=float, default=0.65)
    args = parser.parse_args(argv)

    results = run_study(args.recorder_dir, stream=args.stream,
                        signal=args.signal, threshold=args.threshold)
    paths = write_outputs(results, args.tag)
    for category, entry in results["by_category"].items():
        print(category, "overall", entry["overall"]["mean_net_cents"],
              "Kandidaten", len(entry["survivors"]), "von",
              entry["tested_segments"])
    print({key: str(path) for key, path in paths.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
