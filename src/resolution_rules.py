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
    "mehrdeutigkeit": r"\bambiguous|\bunclear|\bdispute|\bcannot be determined"
                      r"|\bnicht eindeutig|last traded price|\bvoid\b",
    "quelle": r"\bsource\b|\baccording to\b|\bconsensus\b|credible report"
              r"|official\b|\bannounce",
    "frist": r"\bdeadline|\bby \d|\bbefore \d|expiration|\bcutoff|\bet\b"
             r"|\butc\b|\bdate\b",
    "teilweise": r"\bpartial|\bpro rata|\bprorat|\bsplit\b",
}


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
        f"# Aufloesungsregeln im Vergleich ({tag})",
        "",
        f"{results['pairs']} Paare, davon mit Regeltext auf beiden Seiten "
        f"{results['with_both_texts']}. Bei "
        f"{results['with_one_sided_flags']} Paaren dokumentiert nur eine Seite "
        f"etwas, das die andere nicht erwaehnt.",
        "",
        "**Gefunden im Lauf vom 2026-07-31:** beim Paar zur "
        "US-Praesidentschaftswahl 2028 loest Kalshi darauf auf, wer als "
        "naechster als Praesident *vereidigt* wird, Polymarket darauf, wer die "
        "*Wahl gewinnt*, laut Associated Press, Fox News und NBC. Das sind "
        "zwei verschiedene Bedingungen. Wer die Wahl gewinnt und nicht "
        "vereidigt wird - Tod, Rueckzug, strittige Feststellung - loest auf "
        "Polymarket YES aus und auf Kalshi NO. Ein Basket ueber dieses Paar "
        "verliert dann beide Beine statt sich abzusichern. Die Titel sind "
        "praktisch identisch; der Unterschied steht nur im Regeltext.",
        "",
        "**Dieses Dokument urteilt nicht.** Es legt die Regelwerke "
        "nebeneinander und markiert, was zuerst zu lesen ist. Der gefaehrliche "
        "Unterschied ist nie der sprachliche, sondern der inhaltliche unter "
        "einem Randfall, und den findet kein Textvergleich zuverlaessig. Ein "
        "Paar ohne Markierung ist nicht freigegeben, es ist nur nicht "
        "aufgefallen.",
        "",
    ]
    for row in results["rows"]:
        lines += [
            f"## {row['pair']}",
            "",
            f"{row['question']}",
            "",
            f"Nur auf einer Seite dokumentiert: "
            f"{', '.join(row['one_sided_flags']) or 'nichts aufgefallen'}",
            "",
            "**Kalshi**",
            "",
            "> " + (row["kalshi"].get("primary") or "kein Text abrufbar")[:700],
            "",
        ]
        if row["kalshi"].get("secondary"):
            lines += ["> " + row["kalshi"]["secondary"][:400], ""]
        lines += [
            "**Polymarket**",
            "",
            "> " + (row["polymarket"].get("description") or "kein Text abrufbar")[:700],
            "",
        ]
        if row["polymarket"].get("resolution_source"):
            lines += [f"Quelle laut Polymarket: "
                      f"{row['polymarket']['resolution_source'][:200]}", ""]
    lines += [
        "## Warum das hier steht",
        "",
        "Beim Super-Bowl-Markt zur Frage, ob Cardi B auftrat, wertete Kalshi "
        "den Ausgang als mehrdeutig und rechnete zum letzten Handelspreis ab, "
        "waehrend Polymarket YES voll auszahlte. Gleiches Bildmaterial, "
        "verschiedene Regelwerke. Ueber so ein Paar ist ein Basket nicht "
        "abgesichert, sondern sind es zwei offene Wetten - und das faellt erst "
        "bei der Aufloesung auf, wenn beide Beine laengst stehen.",
        "",
        "Read-only-Forschung, keine Handelsempfehlung.",
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
        print(" ", row["pair"], "->", row["one_sided_flags"] or "nichts")
    print({key: str(path) for key, path in paths.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
