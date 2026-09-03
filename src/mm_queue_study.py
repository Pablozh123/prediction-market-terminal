"""Driver for the pre-registered queue-position study: one day at a time.

``src/mm_pnl.py`` answers "what does this quoting rule earn" for one data
window loaded whole. The pre-registered study needs something narrower and
more robust: every candidate parameter set scored on every day separately,
so the choice rule can be applied to per-day totals, the daily bootstrap
can run over them, and a run that takes hours can be resumed after a crash
without redoing the days it already finished.

Days are loaded one at a time, which keeps memory flat and makes the
mark-to-mid horizon a day rather than the whole window. Rows are appended
to a JSONL file as each day completes; a rerun with the same tag skips the
days already in it.

The choice rule is deliberately dumb and written down before the test
window exists: the candidate with the highest total on the training days
in the ``queue_back`` model, among candidates with at least
``MIN_FILLS_FOR_CHOICE`` fills. The back model is the pessimistic one, so a
candidate that wins there did not win by assuming the front of the line.

Paper-only research tooling: no order path, no credentials, no wallets.

Usage:
  python -m src.mm_queue_study --recorder-dir data/microstructure \\
      --day-from 2026-07-30 --day-to 2026-09-03 --tag train
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src import mm_pnl
from src import orderflow_study as ofs
from src.mm_simulator import QuoteParams

REPO_ROOT = Path(__file__).resolve().parents[1]
RESEARCH_DIR = REPO_ROOT / "docs" / "research"

#: Kandidaten, festgeschrieben in der Praeregistrierung vom 2026-09-03.
HALF_SPREADS = (0.005, 0.01, 0.02)
GAMMAS = (0.0, 0.08)
CANDIDATES: tuple[dict, ...] = tuple(
    {"half_spread": hs, "gamma": g, "latency_s": 0.0}
    for hs in HALF_SPREADS for g in GAMMAS
)
MODELS = ("queue_back", "queue_front")
#: Referenzlauf mit den publizierten Parametern, damit die Queue-Zahlen
#: neben dem bekannten optimistischen Modell stehen.
REFERENCE = {"model": "tape", "half_spread": 0.01, "gamma": 0.08, "latency_s": 0.0}
#: Unterhalb dieser Fillzahl ueber das Trainingsfenster ist ein Kandidat
#: kein Kandidat, sondern Rauschen.
MIN_FILLS_FOR_CHOICE = 1000
CHOICE_MODEL = "queue_back"


def candidate_key(candidate: dict) -> str:
    return (f"hs{candidate['half_spread']}_g{candidate['gamma']}"
            f"_lat{candidate['latency_s']}")


def run_day(directory: str | Path, day: str,
            candidates: tuple[dict, ...] = CANDIDATES,
            models: tuple[str, ...] = MODELS,
            reference: dict | None = REFERENCE,
            quote_usd: float = 50.0, cap_usd: float = 250.0,
            category: str = "sports") -> list[dict]:
    """Every candidate on every model for one day, plus the reference row."""
    books = ofs.load_books(directory, stream=True, day_from=day, day_to=day)
    tape = ofs.load_tape(directory, stream=True, day_from=day, day_to=day)
    jobs = [dict(candidate, model=model) for model in models for candidate in candidates]
    if reference:
        jobs.append(dict(reference))
    rows = []
    for job in jobs:
        params = QuoteParams(half_spread=job["half_spread"], gamma=job["gamma"],
                             quote_usd=quote_usd, inventory_cap_usd=cap_usd)
        decomposition, runs = mm_pnl.run_experiment(
            books, tape, params, job["model"], category, latency_s=job["latency_s"])
        rows.append({
            "day": day, "model": job["model"],
            "half_spread": job["half_spread"], "gamma": job["gamma"],
            "latency_s": job["latency_s"],
            "candidate": candidate_key(job),
            "tokens": len(books),
            "snapshots": sum(len(v) for v in books.values()),
            **decomposition.as_dict(),
            **mm_pnl.queue_stats(runs),
        })
    return rows


def aggregate(rows: list[dict]) -> list[dict]:
    """One line per (model, candidate) across days, with the daily bootstrap."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        groups.setdefault((row["model"], row["candidate"]), []).append(row)
    out = []
    for (model, candidate), items in sorted(groups.items()):
        items = sorted(items, key=lambda r: r["day"])
        days = [r["day"] for r in items]
        totals = [r["total_usd"] for r in items]
        fills = sum(r["fills"] for r in items)
        capture = sum(r["spread_capture_usd"] for r in items)
        markout = sum(r["markout_usd"] for r in items)
        first = items[0]
        out.append({
            "model": model, "candidate": candidate,
            "half_spread": first["half_spread"], "gamma": first["gamma"],
            "latency_s": first["latency_s"],
            "days": len(days), "fills": fills,
            "total_usd": round(sum(totals), 4),
            "mean_daily_usd": round(sum(totals) / len(totals), 4),
            "daily_ci95_usd": ofs.block_bootstrap_ci(totals, days),
            "spread_capture_cents_per_fill": round(100 * capture / fills, 3) if fills else None,
            "markout_cents_per_fill": round(100 * markout / fills, 3) if fills else None,
            "daily_totals": {day: round(total, 4) for day, total in zip(days, totals)},
        })
    return out


def choose(aggregates: list[dict], model: str = CHOICE_MODEL,
           min_fills: int = MIN_FILLS_FOR_CHOICE) -> dict | None:
    """The pre-registered rule: highest total in ``model`` with enough fills."""
    eligible = [a for a in aggregates if a["model"] == model and a["fills"] >= min_fills]
    if not eligible:
        return None
    return max(eligible, key=lambda a: a["total_usd"])


def rows_path(tag: str, research_dir: Path = RESEARCH_DIR) -> Path:
    return research_dir / f"mm_queue_{tag}.rows.jsonl"


def load_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def append_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def available_days(directory: str | Path, day_from: str | None,
                   day_to: str | None) -> list[str]:
    days = sorted(p.stem.split("_")[-1]
                  for p in Path(directory).glob("stream_books_*.csv"))
    return [d for d in days if ofs._day_in_range(d, day_from, day_to)]


def _fmt(value, spec: str = "{:+.2f}") -> str:
    return "-" if value is None else spec.format(value)


def _markdown(tag: str, rows: list[dict], aggregates: list[dict],
              chosen: dict | None) -> str:
    days = sorted({r["day"] for r in rows})
    lines = [
        f"# Queue-position study, per-day candidates ({tag})",
        "",
        f"{len(days)} days ({days[0] if days else '-'} to {days[-1] if days else '-'}), "
        f"{len(CANDIDATES)} candidates x {len(MODELS)} queue models, plus the tape "
        f"reference at the published parameters. Each day loaded and scored on "
        f"its own; the mark-to-mid horizon is the day.",
        "",
        "| Model | Half spread | Gamma | Days | Fills | Total (USD) | Mean/day (USD) | "
        "CI95 daily (USD) | Spread/fill (c) | Markout/fill (c) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for a in aggregates:
        lines.append(
            f"| {a['model']} | {a['half_spread']:.3f} | {a['gamma']:.2f} | {a['days']} | "
            f"{a['fills']:,} | {_fmt(a['total_usd'])} | {_fmt(a['mean_daily_usd'])} | "
            f"{a['daily_ci95_usd'] or 'not computable'} | "
            f"{_fmt(a['spread_capture_cents_per_fill'])} | "
            f"{_fmt(a['markout_cents_per_fill'])} |")
    lines += ["", "## Choice"]
    if chosen:
        lines.append(
            f"Pre-registered rule (highest total in {CHOICE_MODEL} with at least "
            f"{MIN_FILLS_FOR_CHOICE:,} fills): half spread {chosen['half_spread']}, "
            f"gamma {chosen['gamma']}, latency {chosen['latency_s']} s. Total "
            f"{_fmt(chosen['total_usd'])} USD over {chosen['days']} days, "
            f"CI95 {chosen['daily_ci95_usd'] or 'not computable'}.")
    else:
        lines.append(
            f"No candidate reached {MIN_FILLS_FOR_CHOICE:,} fills in {CHOICE_MODEL}; "
            "nothing is chosen and the test window is not run.")
    lines += [
        "",
        "## How to read this",
        "",
        "This is the training window. Nothing in it is a result: the numbers "
        "exist to pick one parameter set by a rule written down before the "
        "test window was recorded. The test window is scored once, with that "
        "set, and reported whatever it says.",
        "",
        "Read-only research. Not trading advice.",
    ]
    return "\n".join(lines)


def write_outputs(tag: str, rows: list[dict], research_dir: Path = RESEARCH_DIR
                  ) -> dict[str, Path]:
    research_dir.mkdir(parents=True, exist_ok=True)
    aggregates = aggregate(rows)
    chosen = choose(aggregates)
    payload = {"tag": tag, "candidates": list(CANDIDATES), "models": list(MODELS),
               "reference": REFERENCE, "choice_model": CHOICE_MODEL,
               "min_fills_for_choice": MIN_FILLS_FOR_CHOICE,
               "days": sorted({r["day"] for r in rows}),
               "aggregates": aggregates, "chosen": chosen}
    json_path = research_dir / f"mm_queue_{tag}.json"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path = research_dir / f"mm_queue_{tag}.md"
    md_path.write_text(_markdown(tag, rows, aggregates, chosen), encoding="utf-8")
    return {"json": json_path, "md": md_path}


def run_study(directory: str | Path, tag: str, day_from: str | None = None,
              day_to: str | None = None, research_dir: Path = RESEARCH_DIR,
              log=print) -> dict[str, Path]:
    """Score every missing day, appending as it goes, then write the summary."""
    path = rows_path(tag, research_dir)
    done = {r["day"] for r in load_rows(path)}
    for day in available_days(directory, day_from, day_to):
        if day in done:
            log(f"[queue] {day} already scored, skipping")
            continue
        rows = run_day(directory, day)
        append_rows(path, rows)
        log(f"[queue] {day} done: {len(rows)} rows, "
            f"{rows[0]['snapshots']:,} snapshots")
    return write_outputs(tag, load_rows(path), research_dir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--recorder-dir", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--day-from", default=None)
    parser.add_argument("--day-to", default=None)
    args = parser.parse_args(argv)
    paths = run_study(args.recorder_dir, args.tag, args.day_from, args.day_to)
    print({key: str(path) for key, path in paths.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
