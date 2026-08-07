"""Full ERC-20 ledger for one wallet and one token contract on Polygon.

Generalises scripts/full_wallet_ledger.py, which hard-codes the two USDC
contracts. Polymarket switched collateral to pUSD in 2026, so a USDC-only scan
goes blind exactly when the wallet keeps trading.

    python scripts/scan_token_ledger.py --wallet 0x204f... --token 0xc011a7e1...

Read-only: public API, no order path, no signing.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import pandas as pd  # noqa: E402
import requests  # noqa: E402

API_URL = "https://api.etherscan.io/v2/api"
POLYGON_CHAIN_ID = 137
SESSION = requests.Session()
LARGE = 10_000.0


def load_api_key(repo_root: Path = REPO_ROOT) -> str | None:
    import os
    for name in ("ETHERSCAN_API_KEY", "POLYGONSCAN_API_KEY"):
        if os.environ.get(name):
            return os.environ[name].strip()
    env_path = repo_root / ".env"
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            if key.strip() in ("ETHERSCAN_API_KEY", "POLYGONSCAN_API_KEY"):
                return value.strip().strip('"').strip("'")
    return None


def fetch_page(wallet: str, api_key: str, token: str, start_block: int) -> list | None:
    params = {"chainid": POLYGON_CHAIN_ID, "module": "account", "action": "tokentx",
              "address": wallet, "contractaddress": token, "startblock": start_block,
              "endblock": 99_999_999, "page": 1, "offset": 10_000, "sort": "asc",
              "apikey": api_key}
    for attempt in range(8):
        try:
            payload = SESSION.get(API_URL, params=params, timeout=90).json()
        except Exception:  # noqa: BLE001
            time.sleep(2 * (attempt + 1))
            continue
        result = payload.get("result")
        if isinstance(result, list):
            return result
        message = str(payload.get("message") or result)
        if "No transactions found" in message or "No records found" in message:
            return []
        time.sleep(3 * (attempt + 1))
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wallet", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--tag", default="token")
    parser.add_argument("--pause", type=float, default=0.35)
    parser.add_argument("--out-dir", default=str(REPO_ROOT / "data"))
    args = parser.parse_args()

    api_key = load_api_key()
    if not api_key:
        print("No ETHERSCAN_API_KEY found (env or .env).")
        return 1
    wallet, token = args.wallet.lower(), args.token.lower()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    state_path = out_dir / f"ledger_{args.tag}_state.json"

    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    by_cp: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"amount": 0.0, "count": 0, "first_block": None, "last_block": None,
                 "first_ts": None, "last_ts": None})
    for key, value in (state.get("by_counterparty") or {}).items():
        cp, _, d = key.rpartition("|")
        by_cp[(cp, d)] = value
    by_month: dict[str, dict] = defaultdict(lambda: {"in": 0.0, "out": 0.0, "n": 0})
    for month, value in (state.get("by_month") or {}).items():
        by_month[month] = value
    large: list[dict] = state.get("large") or []
    total_in = float(state.get("total_in") or 0.0)
    total_out = float(state.get("total_out") or 0.0)
    rows = int(state.get("rows") or 0)
    block = int(state.get("cursor") or 0)
    seen: set[str] = set(state.get("seen_tail") or [])
    symbol = state.get("symbol") or ""
    complete = True
    pages = 0

    print(f"Scan {args.tag} ({token}) fuer {wallet} ab Block {block:,}", flush=True)
    while not state.get("done"):
        result = fetch_page(wallet, api_key, token, block)
        if result is None:
            print(f"  ABBRUCH bei Block {block:,}", flush=True)
            complete = False
            break
        if not result:
            state["done"] = True
            break
        fresh = 0
        for row in result:
            marker = f"{row.get('hash')}|{row.get('from')}|{row.get('to')}|{row.get('value')}"
            if marker in seen:
                continue
            seen.add(marker)
            try:
                dec = int(row.get("tokenDecimal") or 6)
                amount = float(row.get("value", 0)) / (10 ** dec)
                blk = int(row.get("blockNumber", 0))
                stamp = int(row.get("timeStamp", 0))
            except (TypeError, ValueError):
                continue
            symbol = symbol or str(row.get("tokenSymbol") or "")
            sender, recipient = str(row.get("from", "")).lower(), str(row.get("to", "")).lower()
            if wallet not in (sender, recipient):
                continue
            incoming = recipient == wallet
            cp = sender if incoming else recipient
            d = "in" if incoming else "out"
            e = by_cp[(cp, d)]
            e["amount"] += amount
            e["count"] += 1
            if e["first_block"] is None or blk < e["first_block"]:
                e["first_block"], e["first_ts"] = blk, stamp
            if e["last_block"] is None or blk > e["last_block"]:
                e["last_block"], e["last_ts"] = blk, stamp
            month = time.strftime("%Y-%m", time.gmtime(stamp)) if stamp else "unknown"
            by_month[month][d] += amount
            by_month[month]["n"] += 1
            if incoming:
                total_in += amount
            else:
                total_out += amount
            rows += 1
            fresh += 1
            if amount >= LARGE:
                large.append({"block": blk, "timestamp": stamp, "direction": d,
                              "counterparty": cp, "amount": amount,
                              "tx": str(row.get("hash", "")),
                              "method": str(row.get("functionName", ""))[:60]})
        last_block = int(result[-1].get("blockNumber", block))
        pages += 1
        if fresh == 0:
            state["done"] = True
            break
        block = last_block
        if pages % 25 == 0:
            print(f"  Seite {pages}: Block {block:,} Zeilen {rows:,} "
                  f"IN {total_in:,.0f} OUT {total_out:,.0f}", flush=True)
        time.sleep(args.pause)

    state_path.write_text(json.dumps({
        "by_counterparty": {f"{cp}|{d}": v for (cp, d), v in by_cp.items()},
        "by_month": dict(by_month), "large": large, "total_in": total_in,
        "total_out": total_out, "rows": rows, "cursor": block, "symbol": symbol,
        "done": state.get("done", False), "seen_tail": list(seen)[-40_000:]}), encoding="utf-8")

    cps = pd.DataFrame([{"counterparty": cp, "direction": d, **v} for (cp, d), v in by_cp.items()])
    if not cps.empty:
        cps = cps.sort_values("amount", ascending=False)
        cps.to_csv(out_dir / f"ledger_{args.tag}_counterparties.csv", index=False)
    pd.DataFrame([{"month": m, **v} for m, v in sorted(by_month.items())]).to_csv(
        out_dir / f"ledger_{args.tag}_monthly.csv", index=False)
    pd.DataFrame(large).to_csv(out_dir / f"ledger_{args.tag}_large.csv", index=False)

    print(f"\n{'='*80}\n{args.tag.upper()} ({symbol}) BILANZ  (vollstaendig: {complete})\n{'='*80}")
    print(f"  Transfers : {rows:>18,}")
    print(f"  IN        : {total_in:>18,.2f}")
    print(f"  OUT       : {total_out:>18,.2f}")
    print(f"  NETTO     : {total_in - total_out:>18,.2f}")
    if not cps.empty:
        print("\n=== GEGENPARTEIEN (top 30) ===")
        print(cps.head(30).to_string(index=False, float_format=lambda v: f"{v:,.2f}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
