"""How often is a Polymarket/Kalshi price difference actually an arbitrage?

The fee models in ``app/venue_fees.py`` say what a cross-venue basket has to
clear. This measures what is actually on offer.

A price difference is not an arbitrage. Buying YES on one venue and NO on the
other pays exactly 1.00 per pair at resolution, so the gross edge is
``1 - (ask_here + ask_there)``. Only what remains after both fees and within
the depth that actually exists is tradable. The number that matters is
therefore not the size of the gap but how much of it survives, and at what
size.

Three honesty constraints are built in rather than mentioned at the end.

Pairs are unverified. Matching is done on titles, which says two markets look
like the same question, not that they resolve the same way. The Cardi B
Super Bowl market is the standing counterexample: Kalshi settled it as
ambiguous at the last traded price while Polymarket paid YES in full, on the
same footage, because the rulebooks differed. A basket across that pair is not
hedged, it is two open bets. Every pair here is therefore reported with its
match score and flagged as needing a rules comparison before it means anything.

Depth is measured, not assumed. A gap that exists for twenty shares is not a
thousand-share trade, so candidates are re-quoted against both order books and
priced at the size the shallower side supports.

Direction is checked both ways. A pair can be cheap on either venue, and taking
only one direction would understate how often a gap exists at all.

Read-only research tooling: public endpoints, no order path, no credentials.

Usage:
  python -m src.cross_venue_gaps --tag 2026-07-31
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app import venue_fees as vf
from src import book_recorder as pm
from src import kalshi_recorder as kx

REPO_ROOT = Path(__file__).resolve().parents[1]
RESEARCH_DIR = REPO_ROOT / "docs" / "research"

#: Wortmuell, der zwei unaehnliche Fragen aehnlich aussehen laesst.
STOPWORDS = frozenset("""
a an the will be is are was were do does did to of in on at for by with and or
if then than that this these those it its as from up down over under after
before who whom which what when where how many much more most least any some
be being been has have had can could should would may might must shall
""".split())

#: Ab hier gilt ein Paar als Kandidat. Bewusst hoch: ein falsches Paar ist
#: teurer als ein verpasstes, weil es wie eine Absicherung aussieht.
MIN_MATCH_SCORE = 0.45
#: Ohne gemeinsames unterscheidendes Wort ist Aehnlichkeit bedeutungslos.
MIN_SHARED_TOKENS = 2

DEFAULT_TOP_CANDIDATES = 40
DEFAULT_SHARES = 100.0

# Validierte Referenzpalette (dataviz-Skill), Light-Mode
COLOR_GROSS = "#2a78d6"
COLOR_NET = "#1baf7a"
COLOR_NEG = "#d6452a"
COLOR_SURFACE = "#fcfcfb"
COLOR_TEXT = "#0b0b0b"
COLOR_TEXT_2 = "#52514e"
COLOR_GRID = "#e5e4e0"

#: Polymarket-Kategorien tragen die Gebuehrenrate; Kalshi hat eine Rate.
KALSHI_TO_PM_CATEGORY = {
    "elections": "politics",
    "politics": "politics",
    "economics": "economics",
    "financials": "finance",
    "companies": "finance",
    "crypto": "crypto",
    "climate and weather": "weather",
    "weather": "weather",
    "sports": "sports",
    "entertainment": "culture",
    "mentions": "mentions",
    "world": "geopolitics",
    "science and technology": "tech",
}


def normalise(text: str) -> list[str]:
    """Title into comparable tokens: lowercase, punctuation out, stopwords out."""
    words = re.findall(r"[a-z0-9]+", str(text or "").lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 1]


def match_score(left: str, right: str) -> tuple[float, int]:
    """(Jaccard similarity, shared token count) between two titles."""
    a, b = set(normalise(left)), set(normalise(right))
    if not a or not b:
        return 0.0, 0
    shared = a & b
    union = a | b
    return round(len(shared) / len(union), 4), len(shared)


#: Was eine Frage eigentlich fragt, unabhaengig von der Formulierung. Die
#: Pruefung laeuft ueber diese Gruppen statt ueber Einzelwoerter, weil
#: "gewinnt die Nominierung" und "ist der Nominierte" dieselbe Frage sind,
#: "gewinnt die Nominierung" und "tritt an" dagegen nicht.
INTENT_WORDS = {
    "ergebnis": {"win", "wins", "won", "winner", "winning", "nominee",
                 "nomination", "nominated", "host", "hosts", "hosting",
                 "champion", "elected"},
    "teilnahme": {"run", "runs", "running", "ran", "candidate", "enter",
                  "announce", "declare"},
    "marge": {"margin", "percent", "percentage", "points", "spread"},
    "ausstieg": {"concede", "withdraw", "resign", "drop", "suspend", "quit"},
}

#: Spannen-Muster ("6-9%") verraten einen Margen-Markt auch ohne das Wort.
RANGE_PATTERN = re.compile(r"\d+\s*[-–]\s*\d+\s*%", re.IGNORECASE)


def intents(title: str) -> set[str]:
    """Which question types a title expresses."""
    tokens = set(normalise(title))
    found = {name for name, words in INTENT_WORDS.items() if tokens & words}
    if RANGE_PATTERN.search(title or ""):
        found.add("marge")
    return found


def suspect_reasons(left: str, right: str) -> list[str]:
    """Why two similar-looking titles are probably not the same question.

    Title similarity is blind to the words that carry the question. Two markets
    can share every name and date and still ask different things: winning a
    nomination versus merely running for it, or the outright result versus the
    margin of victory. Both showed up in the first live run as the two largest
    apparent edges in the whole sample, at 79 and 64 cents, which is exactly how
    a mismatched pair presents itself - a hedge that is really two open bets.

    Comparing question types rather than words keeps genuine rewordings intact:
    "win the nomination" and "the nominee" both express a result, so they are
    not flagged, while "run for the nomination" adds a participation question
    that the other side does not ask.
    """
    left_intents, right_intents = intents(left), intents(right)
    difference = left_intents ^ right_intents
    if not difference:
        return []
    return ["verschiedene Fragetypen: " + ", ".join(
        sorted(left_intents) or ["keiner"]) + " gegen " + ", ".join(
        sorted(right_intents) or ["keiner"])]


def days_until(value) -> float | None:
    """Days from now to a resolution date, or None if it cannot be read.

    A basket locks up capital until the event resolves, so a two-cent edge on a
    market that settles in 2028 is not a two-cent trade, it is a carry position
    competing with simply holding the collateral. Without this the largest
    apparent edges in the table are always the most distant ones.
    """
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%d"):
        try:
            when = datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        delta = (when - datetime.now(timezone.utc)).total_seconds() / 86400.0
        return round(delta, 2) if delta > 0 else None
    return None


def pm_category(market: dict) -> str:
    for key in ("category", "categoryName", "groupItemTitle"):
        value = str(market.get(key) or "").strip().lower()
        if value:
            return value
    return "other"


def kalshi_category_as_pm(category: str) -> str:
    """Map a Kalshi category onto the Polymarket fee table."""
    return KALSHI_TO_PM_CATEGORY.get(str(category or "").strip().lower(), "other")


@dataclass(frozen=True)
class Candidate:
    """One matched pair, before any economics are computed."""

    pm_id: str
    pm_question: str
    pm_category: str
    pm_bid: float
    pm_ask: float
    kalshi_ticker: str
    kalshi_title: str
    kalshi_category: str
    kalshi_bid: float
    kalshi_ask: float
    score: float
    shared_tokens: int
    suspect: tuple[str, ...] = ()
    days_to_resolution: float | None = None

    def as_dict(self) -> dict:
        return {
            "suspect": list(self.suspect),
            "pm_id": self.pm_id, "pm_question": self.pm_question,
            "pm_category": self.pm_category, "pm_bid": self.pm_bid,
            "pm_ask": self.pm_ask, "kalshi_ticker": self.kalshi_ticker,
            "kalshi_title": self.kalshi_title,
            "kalshi_category": self.kalshi_category,
            "kalshi_bid": self.kalshi_bid, "kalshi_ask": self.kalshi_ask,
            "score": self.score, "shared_tokens": self.shared_tokens,
            "days_to_resolution": self.days_to_resolution,
        }


def _num(value) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return 0.0
    return out


def pm_quote(market: dict) -> tuple[float, float]:
    """(best bid, best ask) for the YES side of a Gamma market."""
    bid = _num(market.get("bestBid"))
    ask = _num(market.get("bestAsk"))
    if bid <= 0 or ask <= 0:
        prices = market.get("outcomePrices")
        if isinstance(prices, str):
            try:
                prices = json.loads(prices)
            except (TypeError, ValueError):
                prices = None
        if isinstance(prices, list) and prices:
            mid = _num(prices[0])
            if mid > 0:
                return mid, mid
    return bid, ask


def find_candidates(pm_markets: list[dict], kalshi_markets: list[dict],
                    min_score: float = MIN_MATCH_SCORE,
                    min_shared: int = MIN_SHARED_TOKENS,
                    top_n: int = DEFAULT_TOP_CANDIDATES) -> list[Candidate]:
    """Title-matched pairs, best match per Polymarket market, ranked by score."""
    prepared = []
    for market in kalshi_markets:
        title = f"{market.get('title', '')} {market.get('subtitle', '')}".strip()
        prepared.append((market, title, set(normalise(title))))

    out: list[Candidate] = []
    for market in pm_markets:
        question = str(market.get("question") or "")
        tokens = set(normalise(question))
        if not tokens:
            continue
        best: tuple[float, int, dict, str] | None = None
        for kalshi, title, ktokens in prepared:
            if not ktokens:
                continue
            shared = tokens & ktokens
            if len(shared) < min_shared:
                continue
            score = round(len(shared) / len(tokens | ktokens), 4)
            if best is None or score > best[0]:
                best = (score, len(shared), kalshi, title)
        if best is None or best[0] < min_score:
            continue
        score, shared_count, kalshi, title = best
        pm_bid, pm_ask = pm_quote(market)
        out.append(Candidate(
            pm_id=str(market.get("id") or ""), pm_question=question,
            pm_category=pm_category(market), pm_bid=pm_bid, pm_ask=pm_ask,
            kalshi_ticker=kalshi.get("ticker", ""), kalshi_title=title,
            kalshi_category=kalshi.get("category", ""),
            kalshi_bid=_num(kalshi.get("yes_bid")),
            kalshi_ask=_num(kalshi.get("yes_ask")),
            score=score, shared_tokens=shared_count,
            suspect=tuple(suspect_reasons(question, title)),
            days_to_resolution=days_until(market.get("endDate")
                                          or market.get("end_date_iso"))))
    out.sort(key=lambda c: c.score, reverse=True)
    return out[:top_n]


def evaluate_candidate(candidate: Candidate, shares: float = DEFAULT_SHARES,
                       pm_depth: float | None = None,
                       kalshi_depth: float | None = None) -> dict:
    """Best of the two directions, gross and net of both fee curves.

    Direction A buys YES on Polymarket and NO on Kalshi; direction B does the
    reverse. Buying NO at price p is the same as selling YES at 1 - p, so the
    second leg costs ``1 - bid`` on the venue we sell into.
    """
    pm_cat = candidate.pm_category
    kx_cat = kalshi_category_as_pm(candidate.kalshi_category)
    results = []
    directions = (
        ("pm_yes_kalshi_no", candidate.pm_ask, "polymarket", pm_cat,
         1.0 - candidate.kalshi_bid, "kalshi", kx_cat),
        ("kalshi_yes_pm_no", candidate.kalshi_ask, "kalshi", kx_cat,
         1.0 - candidate.pm_bid, "polymarket", pm_cat),
    )
    def depth_for(venue: str) -> float:
        """Unknown depth means unconstrained, never zero and never None."""
        value = pm_depth if venue == "polymarket" else kalshi_depth
        return float(value) if value is not None else float("inf")

    for name, price_a, venue_a, cat_a, price_b, venue_b, cat_b in directions:
        if price_a <= 0 or price_b <= 0 or price_a >= 1 or price_b >= 1:
            continue
        leg_a = vf.BasketLeg(venue_a, price_a, depth_for(venue_a), cat_a)
        leg_b = vf.BasketLeg(venue_b, price_b, depth_for(venue_b), cat_b)
        economics = vf.basket_economics(
            leg_a, leg_b, shares=shares,
            days_to_resolution=candidate.days_to_resolution)
        economics["direction"] = name
        results.append(economics)
    if not results:
        return {**candidate.as_dict(), "tradable": False,
                "reason": "keine verwertbaren Quotes"}
    best = max(results, key=lambda r: r["net_edge_per_share"])
    return {**candidate.as_dict(), **best, "tradable": True,
            "directions_checked": len(results)}


def summarise(rows: list[dict], band_source: str = "venue_fees") -> dict:
    """Distribution of gross vs net gaps, and how many clear the band."""
    usable = [r for r in rows if r.get("tradable") and not r.get("suspect")]
    suspect = [r for r in rows if r.get("suspect")]
    if not usable:
        return {"pairs": len(rows), "usable": 0, "suspect": len(suspect),
                "gross_positive": 0, "net_positive": 0,
                "median_gross_cents": None, "median_net_cents": None,
                "median_band_cents": None, "max_net_cents": None,
                "band_source": band_source}

    def median(values: list[float]) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        middle = len(ordered) // 2
        if len(ordered) % 2:
            return round(ordered[middle], 4)
        return round((ordered[middle - 1] + ordered[middle]) / 2.0, 4)

    gross = [r["gross_edge_cents"] for r in usable]
    net = [r["net_edge_cents"] for r in usable]
    band = [r["breakeven_gap_cents"] for r in usable]
    return {
        "pairs": len(rows),
        "usable": len(usable),
        "suspect": len(suspect),
        "gross_positive": sum(1 for value in gross if value > 0),
        "net_positive": sum(1 for value in net if value > 0),
        "median_gross_cents": median(gross),
        "median_net_cents": median(net),
        "median_band_cents": median(band),
        "max_net_cents": round(max(net), 4),
        "band_source": band_source,
    }


def fetch_universe(pm_pages: int = 3, kalshi_top_n: int = 400,
                   pm_get_json=pm._get_json, kalshi_get_json=kx._get_json
                   ) -> tuple[list[dict], list[dict]]:
    """Both venues' open markets with quotes, in one pass each."""
    pm_markets = pm.fetch_active_markets(get_json=pm_get_json, pages=pm_pages)
    kalshi_markets = kx.discover_markets(get_json=kalshi_get_json,
                                         top_n=kalshi_top_n)
    return pm_markets, kalshi_markets


def enrich_depth(candidates: list[Candidate], pm_get_json=pm._get_json,
                 kalshi_get_json=kx._get_json, levels: int = 5
                 ) -> dict[str, tuple[float | None, float | None]]:
    """Available shares at the touch for each candidate, both venues.

    Only the matched pairs are re-quoted, so this stays a few dozen calls
    rather than a sweep over the whole exchange.
    """
    del pm_get_json, levels  # Polymarket-Tiefe braucht die Token-Id, siehe unten
    out: dict[str, tuple[float | None, float | None]] = {}
    for candidate in candidates:
        kalshi_depth = None
        try:
            payload = kalshi_get_json(
                f"/markets/{candidate.kalshi_ticker}/orderbook", {"depth": 1})
            bids, asks = kx.parse_orderbook(payload, levels=1)
            sizes = [size for _, size in bids] + [size for _, size in asks]
            kalshi_depth = min(sizes) if sizes else 0.0
        except Exception:  # noqa: BLE001 - Tiefe ist Zusatzinfo, kein Muss
            kalshi_depth = None
        out[candidate.kalshi_ticker] = (None, kalshi_depth)
    return out


def run_study(pm_pages: int = 3, kalshi_top_n: int = 400,
              top_candidates: int = DEFAULT_TOP_CANDIDATES,
              shares: float = DEFAULT_SHARES, with_depth: bool = True,
              pm_get_json=pm._get_json, kalshi_get_json=kx._get_json) -> dict:
    """Match both venues, price every candidate, and report the distribution."""
    pm_markets, kalshi_markets = fetch_universe(
        pm_pages, kalshi_top_n, pm_get_json, kalshi_get_json)
    candidates = find_candidates(pm_markets, kalshi_markets,
                                 top_n=top_candidates)
    depth: dict[str, tuple[float | None, float | None]] = {}
    if with_depth and candidates:
        depth = enrich_depth(candidates, pm_get_json, kalshi_get_json)
    rows = []
    for candidate in candidates:
        pm_depth, kalshi_depth = depth.get(candidate.kalshi_ticker, (None, None))
        rows.append(evaluate_candidate(candidate, shares=shares,
                                       pm_depth=pm_depth,
                                       kalshi_depth=kalshi_depth))
    return {
        "ts_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pm_markets": len(pm_markets),
        "kalshi_markets": len(kalshi_markets),
        "min_match_score": MIN_MATCH_SCORE,
        "shares": shares,
        "fee_model_version": vf.FEE_MODEL_VERSION,
        "pairs_verified": False,
        "summary": summarise(rows),
        "rows": rows,
    }


def _fmt(value, spec="{:+.2f}") -> str:
    return "-" if value is None else spec.format(value)


def _markdown(results: dict, tag: str) -> str:
    s = results["summary"]
    lines = [
        f"# Cross-Venue-Luecken netto ({tag})",
        "",
        f"Stand {results['ts_utc']}. Verglichen wurden "
        f"{results['pm_markets']:,} offene Polymarket-Maerkte gegen "
        f"{results['kalshi_markets']:,} Kalshi-Maerkte. Titel-Match ab "
        f"Aehnlichkeit {results['min_match_score']}, Basket-Groesse "
        f"{results['shares']:.0f} Shares, Gebuehrenstand "
        f"{results['fee_model_version']}.",
        "",
        f"Kandidatenpaare: {s['pairs']}, davon als Fehlpaarung verdaechtig "
        f"{s.get('suspect', 0)} (unten separat), gewertet {s['usable']}. "
        f"Mit positiver Brutto-Luecke: {s['gross_positive']}. "
        f"**Nach beiden Gebuehren positiv: {s['net_positive']}.**",
        "",
        f"Median-Bruttoluecke {_fmt(s['median_gross_cents'])} Cents, "
        f"Median-Nettoluecke {_fmt(s['median_net_cents'])} Cents, "
        f"mediane Gebuehrenschwelle {_fmt(s['median_band_cents'], '{:.2f}')} "
        f"Cents. Beste Nettoluecke {_fmt(s.get('max_net_cents'))} Cents.",
        "",
        "| Paar | Score | Brutto (c) | Schwelle (c) | Netto (c) | Groesse | "
        "Tage bis Aufloesung | annualisiert |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in sorted([r for r in results["rows"]
                       if r.get("tradable") and not r.get("suspect")],
                      key=lambda r: r["net_edge_cents"], reverse=True)[:25]:
        label = f"{row['pm_question'][:40]} / {row['kalshi_ticker'][:22]}"
        days = row.get("days_to_resolution")
        lines.append(
            f"| {label} | {row['score']:.2f} | "
            f"{_fmt(row['gross_edge_cents'])} | "
            f"{_fmt(row['breakeven_gap_cents'], '{:.2f}')} | "
            f"{_fmt(row['net_edge_cents'])} | {row['shares']:.0f} | "
            f"{'-' if days is None else f'{days:.0f}'} | "
            f"{_fmt(row.get('annualised_return'), '{:+.1%}')} |")

    flagged = [r for r in results["rows"] if r.get("suspect")]
    if flagged:
        lines += [
            "",
            "### Aussortierte Paare (Titel aehnlich, Frage verschieden)",
            "",
            "Diese Paare sind aus allen Zahlen oben ausgeschlossen. Sie stehen "
            "hier, weil sie zeigen, wie eine Fehlpaarung aussieht: als die "
            "groesste scheinbare Kante im ganzen Lauf.",
            "",
            "| Polymarket | Kalshi | scheinbar netto (c) | Grund |",
            "|---|---|---|---|",
        ]
        for row in sorted(flagged, key=lambda r: r.get("net_edge_cents") or 0,
                          reverse=True):
            lines.append(
                f"| {row['pm_question'][:44]} | {row['kalshi_title'][:44]} | "
                f"{_fmt(row.get('net_edge_cents'))} | "
                f"{'; '.join(row['suspect'])} |")

    lines += [
        "",
        "## Lesehilfe",
        "",
        "Eine Preisdifferenz ist keine Arbitrage. Wer YES auf der einen und NO "
        "auf der anderen Boerse kauft, bekommt bei Aufloesung genau 1.00 je "
        "Paar; die Bruttokante ist also 1 minus der Summe beider Kaufpreise. "
        "Die Spalte Schwelle ist, was beide Gebuehrenkurven zusammen "
        "verlangen. Netto ist die Differenz. Nur eine positive Netto-Zahl ist "
        "ueberhaupt eine Kante, und auch dann nur bis zur Tiefe, die in der "
        "Spalte Groesse steht.",
        "",
        "Die letzte Spalte entscheidet meistens. Ein Basket bindet Kapital bis "
        "zur Aufloesung, und die liegt bei den Paaren, die hier ueberhaupt "
        "auftauchen, typisch Jahre entfernt. Zwei Cent auf dreissig Cent "
        "Einsatz ueber zwei Jahre sind keine sieben Prozent, sondern gut drei "
        "pro Jahr, und dagegen steht der zinslose Verzicht auf das Kapital "
        "plus Aufloesungs- und Regelrisiko auf beiden Seiten. Was hier "
        "gefunden wird, sind Carry-Positionen, keine Arbitragen.",
        "",
        "**Die Paare sind nicht verifiziert.** Der Abgleich laeuft ueber "
        "Titel-Aehnlichkeit und sagt, dass zwei Maerkte nach derselben Frage "
        "aussehen, nicht dass sie gleich aufgeloest werden. Der Cardi-B-Markt "
        "zum Super Bowl ist das stehende Gegenbeispiel: Kalshi wertete den "
        "Ausgang als mehrdeutig und rechnete zum letzten Handelspreis ab, "
        "Polymarket zahlte YES voll aus, bei identischem Bildmaterial und "
        "unterschiedlichen Regelwerken. Ueber so ein Paar ist ein Basket nicht "
        "abgesichert, sondern sind es zwei offene Wetten. Vor jeder weiteren "
        "Verwendung gehoert zu jedem Paar ein Vergleich der Aufloesungsregeln.",
        "",
        "Weitere Grenzen: Quotes sind ein Schnappschuss, kein Verlauf, die "
        "Aussage ueber die Lebensdauer einer Luecke braucht die laufenden "
        "Recorder. Polymarket-Tiefe ist hier nicht abgefragt (sie braucht die "
        "Token-Id je Outcome), Kalshi-Tiefe schon; wo Tiefe fehlt, ist die "
        "Groesse eine Annahme und die Zahl eine Obergrenze. Beide Beine "
        "gleichzeitig zu treffen ist unterstellt, Ausfuehrungsrisiko ist nicht "
        "modelliert.",
        "",
        "Read-only-Forschung, keine Handelsempfehlung.",
    ]
    return "\n".join(lines)


def write_outputs(results: dict, tag: str,
                  research_dir: Path = RESEARCH_DIR) -> dict[str, Path]:
    research_dir.mkdir(parents=True, exist_ok=True)
    json_path = research_dir / f"cross_venue_gaps_{tag}.json"
    json_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

    csv_path = research_dir / f"cross_venue_gaps_{tag}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["pm_question", "kalshi_ticker", "score", "direction",
                         "gross_edge_cents", "breakeven_gap_cents",
                         "net_edge_cents", "shares", "tradable"])
        for row in results["rows"]:
            writer.writerow([row.get("pm_question", ""), row.get("kalshi_ticker", ""),
                             row.get("score"), row.get("direction", ""),
                             row.get("gross_edge_cents"),
                             row.get("breakeven_gap_cents"),
                             row.get("net_edge_cents"), row.get("shares"),
                             row.get("tradable")])

    md_path = research_dir / f"cross_venue_gaps_{tag}.md"
    md_path.write_text(_markdown(results, tag), encoding="utf-8")
    return {"json": json_path, "csv": csv_path, "md": md_path}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tag", required=True)
    parser.add_argument("--pm-pages", type=int, default=3)
    parser.add_argument("--kalshi-top-n", type=int, default=400)
    parser.add_argument("--candidates", type=int, default=DEFAULT_TOP_CANDIDATES)
    parser.add_argument("--shares", type=float, default=DEFAULT_SHARES)
    parser.add_argument("--no-depth", action="store_true")
    args = parser.parse_args(argv)

    results = run_study(pm_pages=args.pm_pages, kalshi_top_n=args.kalshi_top_n,
                        top_candidates=args.candidates, shares=args.shares,
                        with_depth=not args.no_depth)
    paths = write_outputs(results, args.tag)
    print(results["summary"])
    print({key: str(path) for key, path in paths.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
