"""Do the two venues actually settle the same way? Side by side, for a human.

Every cross-venue number in this repo carries the same caveat: the pairs are
matched on titles, which says two markets look like the same question, not that
they resolve the same way. That is not a technicality. In the Super Bowl market
on whether Cardi B performed, Kalshi judged the outcome ambiguous and settled at
the last traded price while Polymarket paid YES in full - same footage, different
rulebooks. A basket across that pair was not hedged; it was two open bets.

So this module fetches both rulebooks for the confirmed pairs and puts them next
to each other. It deliberately does not judge. The failure mode is not
linguistic difference, which is everywhere and mostly harmless, but semantic
difference under an edge case - and no automatic comparison of these texts can
find that reliably. What it can do is surface the parts a human should read
first: the resolution source, the deadline, and whether either side documents
what happens when the outcome is unclear.

Those flags are prompts to look, never verdicts. A pair with no flags has not
been cleared; it has only failed to trip a keyword.

Read-only research tooling: public endpoints, no order path, no credentials.

Usage:
  python -m src.resolution_rules --tag 2026-07-31
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import requests

from app import watchlist

REPO_ROOT = Path(__file__).resolve().parents[1]
RESEARCH_DIR = REPO_ROOT / "docs" / "research"

KALSHI_MARKET_URL = "https://api.elections.kalshi.com/trade-api/v2/markets"
GAMMA_MARKETS_URL = "https://gamma-api.polymarket.com/markets"
HEADERS = {"User-Agent": "prediction-market-terminal research/1.0 (read-only)"}

#: Textstellen, die bei einem Regelvergleich zuerst gelesen gehoeren. Das sind
#: Lesehinweise, keine Urteile: ein Paar ohne Treffer ist nicht geprueft,
#: sondern nur nicht aufgefallen.
FLAG_PATTERNS = {
    "ambiguity": r"\bambiguous|\bunclear|\bdispute|\bcannot be determined"
                 r"|\bnicht eindeutig|last traded price|\bvoid\b",
    "source": r"\bsource\b|\baccording to\b|\bconsensus\b|credible report"
              r"|official\b|\bannounce",
    "deadline": r"\bdeadline|\bby \d|\bbefore \d|expiration|\bcutoff|\bet\b"
                r"|\butc\b|\bdate\b",
    "partial": r"\bpartial|\bpro rata|\bprorat|\bsplit\b",
    # Stufe 2 des Paar-Protokolls (2026-09-05): drei weitere Stellen, an
    # denen zwei Regelwerke bei demselben Sachverhalt auseinanderlaufen.
    # Eine Seite loest sofort bei der Ankuendigung auf, die andere erst beim
    # Ereignis (Eurovision-Fall); eine Seite kennt einen Ausgang "Other";
    # eine Seite regelt den Ersatz eines Kandidaten.
    "early_resolution": r"resolves? (?:immediately|early|as soon as)"
                        r"|upon (?:the )?(?:official )?announcement"
                        r"|regardless of whether",
    "other_outcome": r"resolves? (?:to |as )?(?:\"|“|')?other\b"
                     r"|none of the above",
    "replacement": r"\breplacement\b|\breplaced\b|\bsubstitut|\bwithdraw",
}

#: Wie weit die beiden Termine auseinanderliegen duerfen, bevor die
#: Differenz selbst ein Lesehinweis ist. Dieselbe Toleranz wie der
#: Titel-Screen (app/cross_pairs.py, MAX_RESOLUTION_GAP_DAYS).
EXPIRATION_GAP_FLAG_DAYS = 7.0


def expiration_gap_days(kalshi_expiration, polymarket_end) -> float | None:
    """Abstand der beiden Termine in Tagen, None wenn einer fehlt."""

    stamps = []
    for value in (kalshi_expiration, polymarket_end):
        try:
            stamp = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        except ValueError:
            return None
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        stamps.append(stamp)
    return round(abs((stamps[0] - stamps[1]).total_seconds()) / 86400.0, 3)


def _get(url: str, params: dict, timeout: int = 25):
    resp = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def normalise_text(value) -> str:
    """Collapse whitespace so two rulebooks are comparable at a glance."""
    return re.sub(r"\s+", " ", str(value or "")).strip()


def kalshi_rules(ticker: str, get_json=_get) -> dict:
    """Primary and secondary rule text for one Kalshi market."""
    try:
        payload = get_json(f"{KALSHI_MARKET_URL}/{ticker}", {})
    except Exception as exc:  # noqa: BLE001 - fehlender Text ist ein Ergebnis
        return {"ticker": ticker, "error": f"{type(exc).__name__}"}
    market = (payload or {}).get("market") or {}
    return {
        "ticker": ticker,
        "primary": normalise_text(market.get("rules_primary")),
        "secondary": normalise_text(market.get("rules_secondary")),
        "expiration": market.get("expiration_time"),
    }


def polymarket_rules(market_id: str, get_json=_get) -> dict:
    """Description and resolution source for one Polymarket market."""
    try:
        payload = get_json(GAMMA_MARKETS_URL, {"id": market_id})
    except Exception as exc:  # noqa: BLE001
        return {"market_id": market_id, "error": f"{type(exc).__name__}"}
    market = (payload or [{}])[0] if payload else {}
    return {
        "market_id": market_id,
        "description": normalise_text(market.get("description")),
        "resolution_source": normalise_text(market.get("resolutionSource")),
        "end_date": market.get("endDate"),
    }


def flags(text: str) -> list[str]:
    """Which reading prompts a rulebook trips. Never a verdict."""
    lowered = (text or "").lower()
    return sorted(name for name, pattern in FLAG_PATTERNS.items()
                  if re.search(pattern, lowered))


def compare_pair(pair: dict, get_json=_get) -> dict:
    """Both rulebooks for one pair, plus what a reader should check first."""
    kalshi = kalshi_rules(str(pair.get("kalshi_ticker") or ""), get_json)
    poly = polymarket_rules(str(pair.get("polymarket_market_id") or ""), get_json)
    kalshi_text = " ".join(filter(None, [kalshi.get("primary", ""),
                                         kalshi.get("secondary", "")]))
    poly_text = " ".join(filter(None, [poly.get("description", ""),
                                       poly.get("resolution_source", "")]))
    kalshi_flags, poly_flags = flags(kalshi_text), flags(poly_text)
    gap = expiration_gap_days(kalshi.get("expiration"), poly.get("end_date"))
    return {
        "pair": kalshi.get("ticker"),
        "question": str(pair.get("question") or "")[:100],
        "kalshi": kalshi,
        "polymarket": poly,
        "kalshi_flags": kalshi_flags,
        "polymarket_flags": poly_flags,
        # Nur eine Seite dokumentiert etwas: der Punkt, an dem zwei Boersen
        # bei demselben Sachverhalt auseinanderlaufen koennen.
        "one_sided_flags": sorted(set(kalshi_flags) ^ set(poly_flags)),
        "both_texts_present": bool(kalshi_text and poly_text),
        # Beide Termine nebeneinander: wer spaeter settelt, bindet das
        # Kapital bis dahin, und ein Jahr Abstand (Trump 2028) ist selbst
        # ein Hinweis, dass die beiden Seiten nicht dasselbe fragen.
        "expiration_gap_days": gap,
        "expiration_gap_flagged": gap is not None and gap > EXPIRATION_GAP_FLAG_DAYS,
    }


def run_study(watchlist_path: Path | str = watchlist.DEFAULT_PATH,
              get_json=_get) -> dict:
    pairs = watchlist.load(watchlist_path).get("paare", [])
    rows = [compare_pair(pair, get_json) for pair in pairs]
    return {
        "pairs": len(rows),
        "with_both_texts": sum(1 for r in rows if r["both_texts_present"]),
        "with_one_sided_flags": sum(1 for r in rows if r["one_sided_flags"]),
        "rows": rows,
    }


def _markdown(results: dict, tag: str) -> str:
    lines = [
        f"# Resolution rules side by side ({tag})",
        "",
        f"{results['pairs']} pairs, of which {results['with_both_texts']} carry "
        f"rule text on both sides. For "
        f"{results['with_one_sided_flags']} pairs only one side documents "
        f"something the other never mentions.",
        "",
        "**Found in the run of 2026-07-31:** on the 2028 US presidential pair, "
        "Kalshi resolves on who is next *inaugurated* as president, Polymarket "
        "on who *wins the election* according to Associated Press, Fox News "
        "and NBC. Those are two different conditions. A candidate who wins the "
        "election and is not inaugurated - death, withdrawal, a disputed "
        "certification - pays YES on Polymarket and NO on Kalshi. A basket "
        "over that pair then loses both legs instead of hedging. The titles "
        "are near identical; the difference lives only in the rule text.",
        "",
        "**This document does not judge.** It places the rulebooks side by "
        "side and marks what to read first. The dangerous difference is never "
        "the linguistic one but the substantive one under an edge case, and no "
        "text comparison finds that reliably. A pair without a mark has not "
        "been cleared, it has merely not stood out.",
        "",
    ]
    for row in results["rows"]:
        lines += [
            f"## {row['pair']}",
            "",
            f"{row['question']}",
            "",
            f"Documented on one side only: "
            f"{', '.join(row['one_sided_flags']) or 'nothing stood out'}",
            "",
            (f"Resolution times {row['expiration_gap_days']:.0f} days apart"
             + (" (more than a week: read both deadlines first)"
                if row.get("expiration_gap_flagged") else "")
             if row.get("expiration_gap_days") is not None
             else "Resolution times: one side missing"),
            "",
            "**Kalshi**",
            "",
            "> " + (row["kalshi"].get("primary") or "no text available")[:700],
            "",
        ]
        if row["kalshi"].get("secondary"):
            lines += ["> " + row["kalshi"]["secondary"][:400], ""]
        lines += [
            "**Polymarket**",
            "",
            "> " + (row["polymarket"].get("description") or "no text available")[:700],
            "",
        ]
        if row["polymarket"].get("resolution_source"):
            lines += [f"Source per Polymarket: "
                      f"{row['polymarket']['resolution_source'][:200]}", ""]
    lines += [
        "## Why this exists",
        "",
        "On the Super Bowl market asking whether Cardi B performed, Kalshi "
        "judged the outcome ambiguous and settled at the last traded price, "
        "while Polymarket paid YES in full. Same footage, different rulebooks. "
        "Across a pair like that a basket is not hedged, it is two open bets - "
        "and that only surfaces at resolution, when both legs have long been "
        "on.",
        "",
        "Read-only research. Not trading advice.",
    ]
    return "\n".join(lines)


def write_outputs(results: dict, tag: str,
                  research_dir: Path = RESEARCH_DIR) -> dict[str, Path]:
    research_dir.mkdir(parents=True, exist_ok=True)
    json_path = research_dir / f"resolution_rules_{tag}.json"
    json_path.write_text(json.dumps(results, indent=2, ensure_ascii=False),
                         encoding="utf-8")
    md_path = research_dir / f"resolution_rules_{tag}.md"
    md_path.write_text(_markdown(results, tag), encoding="utf-8")
    return {"json": json_path, "md": md_path}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tag", required=True)
    args = parser.parse_args(argv)
    results = run_study()
    paths = write_outputs(results, args.tag)
    print({k: v for k, v in results.items() if k != "rows"})
    for row in results["rows"]:
        print(" ", row["pair"], "->", row["one_sided_flags"] or "nothing")
    print({key: str(path) for key, path in paths.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
