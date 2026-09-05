#!/usr/bin/env python3
"""Resolve the arbitrage scanner's paper trades against Polymarket and publish
the result next to the scanner's own file.

    python scripts/resolve_arb_paper.py                       # bot DB if present, else the payload
    python scripts/resolve_arb_paper.py --bot-db <trades.db>  # read the scanner's SQLite, read-only
    python scripts/resolve_arb_paper.py --trades <export.json>

Writes public/data/arb_resolutions.json (schema arb_resolutions/1) and a
markdown report under docs/research/. Gamma and CLOB answers are cached
under data/cache/ so a re-run does not refetch settled markets.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import arb_resolution as ar  # noqa: E402

DEFAULT_BOT_DB = Path.home() / "Projects" / "prediction-alpha-bot" / "logs" / "trades.db"
PAYLOAD = ROOT / "public" / "data" / "arb_scan.json"
OUT = ROOT / "public" / "data" / "arb_resolutions.json"
CACHE = ROOT / "data" / "cache" / "arb_gamma_markets.json"
STRICH = "—"


def _lade_cache() -> dict:
    if CACHE.exists():
        try:
            return json.loads(CACHE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
    return {}


def _schreibe_cache(cache: dict) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def _tabelle(kopf: list[str], zeilen: list[list]) -> str:
    aus = ["| " + " | ".join(kopf) + " |", "|" + "|".join("---" for _ in kopf) + "|"]
    for z in zeilen:
        aus.append("| " + " | ".join(str(x) for x in z) + " |")
    return "\n".join(aus)


def _usd(v, vorzeichen: bool = False) -> str:
    if v is None:
        return STRICH
    return f"{v:+.2f}" if vorzeichen else f"{v:.2f}"


def _preis(v) -> str:
    return STRICH if v is None else f"{float(v):.3f}"


def _tag(v) -> str:
    return (v or "")[:10] or STRICH


def _gruende(d: dict) -> str:
    return ", ".join(f"{k} {v}" for k, v in sorted(d.items())) if d else "none"


def report_markdown(result: dict, quelle: str) -> str:
    s = result["summary"]
    trades = result["trades"]
    koerbe = result["baskets"]
    stand = result["generated_at"][:16].replace("T", " ") + " UTC"
    verkn = [t for t in trades if t["size_shares_recorded"]]
    journal = [t for t in trades if not t["size_shares_recorded"]]
    verkn_res = [t for t in verkn if t["status"] == "resolved"]
    verkn_pnl = [t for t in verkn_res if t["pnl_corrected_usd"] is not None]
    journal_res = [t for t in journal if t["status"] == "resolved"]
    journal_nach = [t for t in journal_res if t["filled_after_close"]]
    journal_vor = [t for t in journal_res if not t["filled_after_close"]]
    journal_pnl = [t for t in journal_vor if t["pnl_corrected_usd"] is not None]
    journal_ohne = [t for t in journal_vor if t["pnl_corrected_usd"] is None]
    korb_verkn = [k for k in koerbe if k["linked"]]

    def summe(rows, feld):
        return sum(float(r[feld]) for r in rows if r.get(feld) is not None)

    z = [
        "# Paper trades of the arbitrage scanner, resolved against Polymarket",
        "",
        f"Snapshot {stand}. Trades from {quelle}. Resolution source: {result['source']}.",
        "Modeled paper results, not realized returns: no order was placed and no capital moved.",
        "",
        "## In one paragraph",
        "",
        f"The scanner's journal holds {s['trades']} paper trades and reports none of them as resolved. "
        f"{s['resolved']} of them sit on markets Polymarket has settled; {s['open']} are still open"
        + (f", {s['unknown']} could not be found" if s['unknown'] else "") + ". "
        f"The scanner never sees a settlement because it asks Gamma for markets without `closed=true`, "
        f"and that endpoint returns settled markets only with the parameter. "
        f"Of the {s['resolved']} settled trades, {s['filled_after_close']} were filled after their market had already closed, "
        f"so they were never fills at all. Of the rest, {s['with_corrected_pnl']} have an entry price the CLOB's own day price supports; "
        f"those {s['with_corrected_pnl']} legs staked {_usd(s['cost_corrected_usd'])} USD, paid out {_usd(s['payout_corrected_usd'])} USD, "
        f"and made **{_usd(s['pnl_corrected_usd'], True)} USD** before fees ({s['won_corrected']} won, {s['lost_corrected']} lost, {s['flat_corrected']} flat). "
        f"Mean time from fill to settlement was {s['mean_days_held']} days (median {s['median_days_held']}, n = {s['days_held_n']}).",
        "",
        "## The four linked baskets (the ones the site shows)",
        "",
        f"{len(verkn)} trades carry an opportunity id and a share count; they are the baskets the scanner fired between "
        f"{_tag(min((t['opened_at'] for t in verkn), default=None))} and {_tag(max((t['opened_at'] for t in verkn), default=None))}. "
        f"All {len(verkn_res)} legs have settled. Every entry price matches the CLOB day price of the NO token "
        f"(entry checks: {_gruende(ar._zaehle(t['entry_check'] for t in verkn))}). "
        f"Together they staked {_usd(summe(verkn_pnl, 'size_usd'))} USD and made **{_usd(summe(verkn_pnl, 'pnl_corrected_usd'), True)} USD**.",
        "",
    ]
    kopf = ["basket", "exclusive", "legs", "stake USD", "payout USD", "PnL USD", "opened", "settled", "what happened"]
    zeilen = []
    for k in sorted(korb_verkn, key=lambda k: -(k["pnl_corrected_usd"] or 0)):
        legs = [t for t in trades if t["opportunity_id"] == k["key"]]
        gewonnen = sum(1 for t in legs if (t["settlement_price"] or 0) >= 1)
        halb = sum(1 for t in legs if t["resolution_kind"] == "split")
        verloren = sum(1 for t in legs if t["status"] == "resolved" and (t["settlement_price"] or 0) == 0)
        was = f"{gewonnen} NO leg{'s' if gewonnen != 1 else ''} paid 1.00" + (f", {halb} settled 0.50" if halb else "") + (f", {verloren} paid 0" if verloren else "")
        zeilen.append([
            k.get("event_slug") or k["key"], {True: "yes", False: "no", None: "?"}[k.get("mutually_exclusive")],
            k["legs"], _usd(k["cost_usd"]), _usd(k["payout_corrected_usd"]), _usd(k["pnl_corrected_usd"], True),
            _tag(k.get("opened_at")), _tag(k.get("resolved_at")), was,
        ])
    z.append(_tabelle(kopf, zeilen))
    z += [
        "",
        "A NO-on-every-outcome basket pays n minus 1 dollars only when exactly one outcome can happen; Gamma marks such events `negRisk`. "
        "The Weinstein basket is one, and it paid what the model said, eight tenths of a cent on five dollars. "
        "The Starmer and MicroStrategy baskets sat on staggered deadlines (by May 31, by June 30, by December 31): once the event happened, "
        "every later deadline resolved YES too and every NO on it paid nothing, so those baskets lost about half their stake. "
        "The GTA VI legs were independent events that Polymarket settled 0.50/0.50, and the basket came out seven cents ahead by chance, not by structure.",
        "",
        "## The journal's older rows",
        "",
        f"{len(journal)} rows have no opportunity id and no share count (`link_status` legacy_unlinked); they carry a one dollar notional each. "
        f"{len(journal_res)} sit on settled markets.",
        "",
        f"- **{len(journal_nach)} were filled after the market's closedTime**, {len([t for t in journal_nach if float(t['entry_price'] or 0) == 0])} of them at an entry of 0.000. "
        "The scanner was pricing markets that had already settled. These rows get no PnL.",
        f"- Of the {len(journal_vor)} filled while the market was open, the CLOB day price supports the recorded entry for "
        f"{sum(1 for t in journal_vor if t['entry_check'] == 'entry')} rows and supports it only as 1 minus entry for "
        f"{sum(1 for t in journal_vor if t['entry_check'] == 'complement')} rows: the journal stored the YES price on a NO trade. "
        f"For {sum(1 for t in journal_vor if t['entry_check'] == 'neither')} rows it supports neither"
        + (f", and {sum(1 for t in journal_vor if t['entry_check'] == 'no_data')} have no day price" if any(t['entry_check'] == 'no_data' for t in journal_vor) else "") + ".",
        f"- The {len(journal_pnl)} supported rows staked {_usd(summe(journal_pnl, 'size_usd'))} USD and made **{_usd(summe(journal_pnl, 'pnl_corrected_usd'), True)} USD** "
        f"({sum(1 for t in journal_pnl if t['pnl_corrected_usd'] > 0)} won, {sum(1 for t in journal_pnl if t['pnl_corrected_usd'] < 0)} lost). "
        f"Taken as recorded, the same rows would show {_usd(summe(journal_pnl, 'pnl_usd'), True)} USD, because a NO recorded at a few cents "
        "turns one dollar into hundreds of shares that no book ever offered.",
        f"- {len(journal_ohne)} settled rows get no corrected PnL: {_gruende(ar._zaehle(t['pnl_corrected_reason'] for t in journal_ohne))}.",
        "",
        "## Every basket",
        "",
    ]
    kopf = ["basket", "linked", "exclusive", "legs", "settled", "after close", "entry checks", "stake USD", "PnL USD (corrected)", "PnL USD (as recorded)"]
    zeilen = []
    for k in sorted(koerbe, key=lambda k: (not k["linked"], -(k["pnl_corrected_usd"] or 0))):
        zeilen.append([
            (k.get("event_slug") or k["key"])[:44], "yes" if k["linked"] else "no",
            {True: "yes", False: "no", None: "?"}[k.get("mutually_exclusive")],
            k["legs"], f"{k['resolved_legs']}/{k['legs']}", k["filled_after_close"], _gruende(k["entry_checks"]),
            _usd(k["cost_usd"]), _usd(k["pnl_corrected_usd"], True) + (f" (n = {k['legs_with_corrected_pnl']})" if k["pnl_corrected_usd"] is not None else ""),
            _usd(k["pnl_usd"], True),
        ])
    z.append(_tabelle(kopf, zeilen))
    z += ["", "## Every trade", "",
          "Entry is the journal's price; day is the CLOB price of the traded token nearest the fill; check says whether entry matches "
          "the day price as recorded, as 1 minus entry (complement), neither, or could not be checked. Days run from fill to closedTime; "
          "a negative number is a fill after the close.", ""]
    kopf = ["market", "linked", "entry", "day", "check", "stake", "status", "settle", "days", "PnL corrected", "PnL as recorded"]
    zeilen = []
    for t in trades:
        zeilen.append([
            t["slug"][:48], "yes" if t["size_shares_recorded"] else "no", _preis(t["entry_price"]), _preis(t["clob_day_price"]), t["entry_check"],
            _usd(float(t["size_usd"])) if t["size_usd"] is not None else STRICH, t["status"],
            STRICH if t["settlement_price"] is None else f"{t['settlement_price']:.2f}",
            STRICH if t["days_held"] is None else f"{t['days_held']:.0f}",
            _usd(t["pnl_corrected_usd"], True) if t["pnl_corrected_usd"] is not None else (t["pnl_corrected_reason"] if t["status"] == "resolved" else STRICH),
            _usd(t["pnl_usd"], True) if t["pnl_usd"] is not None else (t["pnl_reason"] if t["status"] == "resolved" else STRICH),
        ])
    z.append(_tabelle(kopf, zeilen))
    z += ["", "## Method", "", result["method"], "",
          "The scanner itself is unchanged. The one-line fix (`closed=true` on its Gamma lookup) belongs in the prediction-alpha-bot repository, "
          "together with a check that a market is still open before a paper fill is written."]
    return "\n".join(z) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--bot-db", type=Path, default=None, help="scanner SQLite (read-only); default: the alpha-bot journal if present")
    p.add_argument("--trades", type=Path, default=None, help="JSON list of trades instead of the DB")
    p.add_argument("--out", type=Path, default=OUT)
    p.add_argument("--report", type=Path, default=None, help="markdown report path (default: docs/research/arb_paper_resolution_<date>.md)")
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--no-clob", action="store_true", help="skip the entry check against the CLOB day price")
    args = p.parse_args(argv)

    if args.trades:
        trades = json.loads(args.trades.read_text(encoding="utf-8"))
        quelle = str(args.trades)
    else:
        db = args.bot_db or (DEFAULT_BOT_DB if DEFAULT_BOT_DB.exists() else None)
        if db:
            trades = ar.trades_from_bot_db(db)
            quelle = f"the scanner's journal (paper_trades in {db.name}, read-only)"
        else:
            if not PAYLOAD.exists():
                print(f"error: neither a scanner DB nor {PAYLOAD} is available", file=sys.stderr)
                return 2
            trades = ar.trades_from_payload(json.loads(PAYLOAD.read_text(encoding="utf-8")))
            quelle = str(PAYLOAD) + " (paper_positions; no entry prices, so no PnL)"
    cache = {} if args.no_cache else _lade_cache()
    vorher = len(cache)
    result = ar.resolve_all(trades, cache=cache, now=datetime.now(timezone.utc), with_clob=not args.no_clob)
    if not args.no_cache:
        _schreibe_cache(cache)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    report = args.report or (ROOT / "docs" / "research" / f"arb_paper_resolution_{result['generated_at'][:10]}.md")
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(report_markdown(result, quelle), encoding="utf-8")
    s = result["summary"]
    print(f"trades {s['trades']} · resolved {s['resolved']} · open {s['open']} · unknown {s['unknown']} · filled after close {s['filled_after_close']}")
    print(f"corrected: n {s['with_corrected_pnl']} · won {s['won_corrected']} lost {s['lost_corrected']} flat {s['flat_corrected']} · "
          f"stake {s['cost_corrected_usd']:.2f} · pnl {s['pnl_corrected_usd']:+.2f} USD · mean {s['mean_days_held']} d (n {s['days_held_n']})")
    print(f"as recorded: n {s['with_pnl']} · pnl {s['pnl_usd']:+.2f} USD · baskets {s['baskets']} · not exclusive {s['baskets_not_exclusive']}")
    print(f"cache {vorher} -> {len(cache)} entries · wrote {args.out.relative_to(ROOT) if args.out.is_relative_to(ROOT) else args.out} and {report.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
