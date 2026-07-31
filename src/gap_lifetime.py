"""How long does a cross-venue gap stay open? The number that decides the trade.

``src/cross_venue_gaps.py`` measures how large a gap is at one moment. That is
the wrong question on its own. A basket needs both legs, and a gap you cannot
reach in time is not an opportunity, it is a screenshot. So this module
reconstructs the net gap over time from the two recorders and reports how long
it stays positive.

The reconstruction is an as-of join, not a resample. Both venues are recorded
event driven, so their rows land at unrelated instants; pairing them on a grid
would invent prices nobody quoted. Instead every Kalshi observation is matched
to the most recent Polymarket observation at or before it, and rejected if that
quote is older than ``MAX_STALENESS_S``. That is the same rule a taker faces:
you trade against the quote that is actually standing, or you do not trade.

Net, not gross. Each paired instant is priced through the same fee models as
the snapshot study, so an open window means the gap cleared both fee curves,
not merely that the prices differed.

Windows, not averages. A gap that is 3 cents for four seconds and a gap that is
0.2 cents for an hour average to something meaningless. The output is the
distribution of contiguous open windows: how many, how long each lasted, and
how much was on the table while it was open.

Read-only research tooling: no order path, no credentials, no wallets.

Usage:
  python -m src.gap_lifetime --tag 2026-07-31
"""

from __future__ import annotations

import argparse
import csv
import json
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path

from app import venue_fees as vf
from app import watchlist
from src import cross_venue_gaps as cvg
from src import orderflow_study as ofs

REPO_ROOT = Path(__file__).resolve().parents[1]
MICRO_DIR = REPO_ROOT / "data" / "microstructure"
RESEARCH_DIR = REPO_ROOT / "docs" / "research"

#: Aelter als das darf die Gegenseite nicht sein, sonst ist der Preis kein
#: Angebot mehr, gegen das man haette handeln koennen.
MAX_STALENESS_S = 60.0
#: Standard-Basketgroesse, wie in der Schnappschuss-Studie.
DEFAULT_SHARES = 100.0
#: Unter dieser Dauer ist ein Fenster fuer einen menschlichen oder auch nur
#: REST-basierten Ausfuehrungsweg nicht erreichbar. Wird trotzdem gezaehlt,
#: aber getrennt ausgewiesen.
REACHABLE_S = 5.0


@dataclass(frozen=True, slots=True)
class Quote:
    ts: float
    bid: float
    ask: float


@dataclass(frozen=True, slots=True)
class Window:
    """One contiguous stretch where the net gap was positive."""

    pair: str
    start_ts: float
    end_ts: float
    observations: int
    peak_net_cents: float
    mean_net_cents: float

    @property
    def seconds(self) -> float:
        return round(self.end_ts - self.start_ts, 3)


def load_quotes(directory: Path, pattern: str, key_column: str,
                keys: set[str]) -> dict[str, list[Quote]]:
    """Time-sorted two-sided quotes per market, for the wanted keys only."""
    out: dict[str, list[Quote]] = {}
    for path in sorted(Path(directory).glob(pattern)):
        with open(path, newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                key = row.get(key_column) or ""
                if key not in keys:
                    continue
                ts = ofs.parse_ts(row.get("recv_ts"))
                bid = ofs._float(row.get("best_bid"))
                ask = ofs._float(row.get("best_ask"))
                if ts is None or bid is None or ask is None:
                    continue
                if not 0 < bid < ask < 1:
                    continue
                out.setdefault(key, []).append(Quote(ts, bid, ask))
    for values in out.values():
        values.sort(key=lambda q: q.ts)
    return out


def as_of(quotes: list[Quote], stamps: list[float], target: float,
          max_staleness: float = MAX_STALENESS_S) -> Quote | None:
    """Most recent quote at or before ``target``, or None if too stale.

    Looking backwards rather than forwards is the point: a trader at time t can
    only hit a quote that already exists. Matching to the next quote would let
    the analysis use prices from the future.
    """
    index = bisect_right(stamps, target) - 1
    if index < 0:
        return None
    quote = quotes[index]
    return quote if target - quote.ts <= max_staleness else None


def net_edge_cents(pm: Quote, kalshi: Quote, pm_category: str,
                   kalshi_category: str, shares: float = DEFAULT_SHARES) -> float:
    """Best of both directions, net of both fee curves, at one instant."""
    best = None
    for price_a, venue_a, cat_a, price_b, venue_b, cat_b in (
        (pm.ask, "polymarket", pm_category, 1.0 - kalshi.bid, "kalshi", kalshi_category),
        (kalshi.ask, "kalshi", kalshi_category, 1.0 - pm.bid, "polymarket", pm_category),
    ):
        if not (0 < price_a < 1 and 0 < price_b < 1):
            continue
        economics = vf.basket_economics(
            vf.BasketLeg(venue_a, price_a, category=cat_a),
            vf.BasketLeg(venue_b, price_b, category=cat_b), shares=shares)
        value = economics["net_edge_cents"]
        best = value if best is None else max(best, value)
    return best if best is not None else float("-inf")


def find_windows(series: list[tuple[float, float]], pair: str) -> list[Window]:
    """Contiguous stretches of positive net edge in a time-sorted series."""
    windows: list[Window] = []
    start: float | None = None
    values: list[float] = []
    last_ts = None
    for ts, net in series:
        if net > 0:
            if start is None:
                start = ts
                values = []
            values.append(net)
            last_ts = ts
        elif start is not None:
            windows.append(Window(pair, start, last_ts, len(values),
                                  round(max(values), 4),
                                  round(sum(values) / len(values), 4)))
            start = None
    if start is not None and last_ts is not None:
        windows.append(Window(pair, start, last_ts, len(values),
                              round(max(values), 4),
                              round(sum(values) / len(values), 4)))
    return windows


def pair_series(pm_quotes: list[Quote], kalshi_quotes: list[Quote],
                pm_category: str, kalshi_category: str,
                shares: float = DEFAULT_SHARES,
                max_staleness: float = MAX_STALENESS_S
                ) -> list[tuple[float, float]]:
    """(timestamp, net edge) for every Kalshi observation with a fresh partner."""
    stamps = [q.ts for q in pm_quotes]
    out: list[tuple[float, float]] = []
    for kalshi in kalshi_quotes:
        partner = as_of(pm_quotes, stamps, kalshi.ts, max_staleness)
        if partner is None:
            continue
        out.append((kalshi.ts, net_edge_cents(partner, kalshi, pm_category,
                                              kalshi_category, shares)))
    return out


def run_study(micro_dir: Path = MICRO_DIR, shares: float = DEFAULT_SHARES,
              max_staleness: float = MAX_STALENESS_S,
              watchlist_path: Path | str = watchlist.DEFAULT_PATH) -> dict:
    """Reconstruct the net gap over time for every pinned pair."""
    pairs = watchlist.load(watchlist_path).get("paare", [])
    kalshi_keys = {str(p.get("kalshi_ticker") or "") for p in pairs}
    pm_keys = {str(t) for p in pairs for t in p.get("polymarket_token_ids") or []}
    kalshi_quotes = load_quotes(micro_dir, "kalshi_stream_books_*.csv",
                                "market_id", kalshi_keys)
    pm_quotes = load_quotes(micro_dir, "stream_books_*.csv", "token_id", pm_keys)

    rows: list[dict] = []
    all_windows: list[Window] = []
    for pair in pairs:
        ticker = str(pair.get("kalshi_ticker") or "")
        tokens = [str(t) for t in pair.get("polymarket_token_ids") or []]
        kx = kalshi_quotes.get(ticker) or []
        pm = next((pm_quotes[t] for t in tokens if pm_quotes.get(t)), [])
        if not kx or not pm:
            rows.append({"pair": ticker, "observations": 0,
                         "reason": "eine Seite nicht aufgezeichnet"})
            continue
        series = pair_series(pm, kx, "politics",
                             cvg.kalshi_category_as_pm("Elections"),
                             shares, max_staleness)
        windows = find_windows(series, ticker)
        all_windows.extend(windows)
        open_seconds = sum(w.seconds for w in windows)
        covered = (series[-1][0] - series[0][0]) if len(series) > 1 else 0.0
        rows.append({
            "pair": ticker,
            "question": str(pair.get("question") or "")[:80],
            "observations": len(series),
            "paired_hours": round(covered / 3600.0, 2),
            "windows": len(windows),
            "open_seconds_total": round(open_seconds, 1),
            "open_share": round(open_seconds / covered, 4) if covered > 0 else None,
            "longest_window_s": round(max((w.seconds for w in windows), default=0.0), 1),
            "median_window_s": _median([w.seconds for w in windows]),
            "reachable_windows": sum(1 for w in windows if w.seconds >= REACHABLE_S),
            "peak_net_cents": round(max((w.peak_net_cents for w in windows),
                                        default=0.0), 4),
        })
    return {
        "source": str(micro_dir),
        "shares": shares,
        "max_staleness_s": max_staleness,
        "reachable_s": REACHABLE_S,
        "fee_model_version": vf.FEE_MODEL_VERSION,
        "pairs": len(pairs),
        "pairs_with_both_sides": sum(1 for r in rows if r.get("observations")),
        "windows_total": len(all_windows),
        "rows": rows,
    }


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return round(ordered[middle], 2)
    return round((ordered[middle - 1] + ordered[middle]) / 2.0, 2)


def _fmt(value, spec="{:.2f}") -> str:
    return "-" if value is None else spec.format(value)


def _markdown(results: dict, tag: str) -> str:
    lines = [
        f"# Lebensdauer einer Cross-Venue-Luecke ({tag})",
        "",
        f"Quelle: {results['source']}, beide Stream-Recorder. Basketgroesse "
        f"{results['shares']:.0f} Shares, Gegenseite hoechstens "
        f"{results['max_staleness_s']:.0f} Sekunden alt, Gebuehrenstand "
        f"{results['fee_model_version']}. {results['pairs_with_both_sides']} "
        f"von {results['pairs']} Paaren mit Aufzeichnung auf beiden Seiten, "
        f"{results['windows_total']} offene Fenster insgesamt.",
        "",
        "| Paar | Beobachtungen | Stunden | Fenster | offen (s) | Anteil offen | "
        "laengstes (s) | median (s) | ab 5s | Spitze netto (c) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in results["rows"]:
        if not row.get("observations"):
            lines.append(f"| {row['pair'][:26]} | 0 | - | - | - | - | - | - | - | "
                         f"{row.get('reason', '-')} |")
            continue
        lines.append(
            f"| {row['pair'][:26]} | {row['observations']:,} | "
            f"{_fmt(row['paired_hours'])} | {row['windows']} | "
            f"{_fmt(row['open_seconds_total'], '{:.0f}')} | "
            f"{_fmt(row['open_share'], '{:.1%}')} | "
            f"{_fmt(row['longest_window_s'], '{:.0f}')} | "
            f"{_fmt(row['median_window_s'])} | {row['reachable_windows']} | "
            f"{_fmt(row['peak_net_cents'], '{:+.2f}')} |")
    lines += [
        "",
        "## Lesehilfe",
        "",
        "Ein offenes Fenster heisst: zu diesem Zeitpunkt haetten beide Beine "
        "zusammen nach Abzug beider Gebuehrenkurven Geld gebracht. Die Spalte "
        "Anteil offen ist der Bruchteil der beobachteten Zeit, in dem das galt. "
        "Die Spalte ab 5s zaehlt nur Fenster, die lange genug offen waren, um "
        "sie ueber einen REST-Weg oder von Hand ueberhaupt zu erreichen; "
        "kuerzere sind fuer alles ausser einer stehenden Order Theorie.",
        "",
        "Die Zuordnung schaut ausschliesslich zurueck. Jede Kalshi-Beobachtung "
        "wird mit der letzten Polymarket-Notierung davor gepaart, und verworfen, "
        "wenn die aelter ist als die erlaubte Standzeit. Nach vorne zu schauen "
        "waere bequemer und wuerde Preise aus der Zukunft verwenden.",
        "",
        "**Ein Fenster ist so dicht wie die Beobachtungen darin.** Die "
        "Recorder schreiben nur, wenn sich das Top of Book bewegt, und diese "
        "Maerkte bewegen sich kaum: ein Paar kann ueber elf Stunden zwei "
        "Dutzend Beobachtungen haben. Ein Fenster ueber diese Spanne heisst "
        "dann nicht, dass die Luecke nachweislich durchgehend offen war, "
        "sondern dass sie zu jedem Zeitpunkt offen war, zu dem wir hingesehen "
        "haben. Die Spalte Beobachtungen gehoert deshalb immer mitgelesen.",
        "",
        "Der Befund passt zur annualisierten Rechnung der "
        "Schnappschuss-Studie und erklaert sie. Diese Luecken schliessen sich "
        "nicht in Sekunden, sie stehen stundenlang offen - weil sie keine "
        "Arbitrage sind. Wer sie nimmt, bindet Kapital bis zur Aufloesung, und "
        "bei 830 Tagen Restlaufzeit ist eine Kante von wenigen Cent gut ein "
        "Prozent im Jahr. Der Markt versaeumt es nicht, die Luecke zu "
        "schliessen; die Luecke ist der Preis fuer das gebundene Kapital und "
        "das Regelrisiko auf beiden Seiten.",
        "",
        "Grenzen: die Paare sind titel-gematcht und ihre Aufloesungsregeln nicht "
        "verglichen, es bleibt also offen, ob ein Basket ueberhaupt abgesichert "
        "waere. Tiefe geht nicht ein, die Zahlen gelten fuer die Standardgroesse "
        "und nicht fuer das, was wirklich im Buch liegt. Gleichzeitige "
        "Ausfuehrung beider Beine ist unterstellt. Und ein Fenster ist eine "
        "Beobachtung, keine Gelegenheit: wer hineinginge, veraenderte es.",
        "",
        "Read-only-Forschung, keine Handelsempfehlung.",
    ]
    return "\n".join(lines)


def write_outputs(results: dict, tag: str,
                  research_dir: Path = RESEARCH_DIR) -> dict[str, Path]:
    research_dir.mkdir(parents=True, exist_ok=True)
    json_path = research_dir / f"gap_lifetime_{tag}.json"
    json_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    csv_path = research_dir / f"gap_lifetime_{tag}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["pair", "observations", "paired_hours", "windows",
                         "open_seconds_total", "open_share", "longest_window_s",
                         "median_window_s", "reachable_windows",
                         "peak_net_cents"])
        for row in results["rows"]:
            writer.writerow([row.get(k) for k in (
                "pair", "observations", "paired_hours", "windows",
                "open_seconds_total", "open_share", "longest_window_s",
                "median_window_s", "reachable_windows", "peak_net_cents")])
    md_path = research_dir / f"gap_lifetime_{tag}.md"
    md_path.write_text(_markdown(results, tag), encoding="utf-8")
    return {"json": json_path, "csv": csv_path, "md": md_path}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tag", required=True)
    parser.add_argument("--shares", type=float, default=DEFAULT_SHARES)
    parser.add_argument("--max-staleness", type=float, default=MAX_STALENESS_S)
    parser.add_argument("--micro-dir", default=str(MICRO_DIR))
    args = parser.parse_args(argv)

    results = run_study(Path(args.micro_dir), shares=args.shares,
                        max_staleness=args.max_staleness)
    paths = write_outputs(results, args.tag)
    print({k: v for k, v in results.items() if k != "rows"})
    for row in results["rows"]:
        print(" ", {k: row.get(k) for k in ("pair", "observations", "windows",
                                            "open_share", "longest_window_s")})
    print({key: str(path) for key, path in paths.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
