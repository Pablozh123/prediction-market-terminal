"""Complete ERC-1155 (conditional token) ledger for one wallet on Polygon.

The USDC scan only sees ERC-20. Polymarket position tokens are ERC-1155, so a
transfer of positions to a third party would be invisible there. This walks
Etherscan V2 action=token1155tx for the wallet, keeps everything, and aggregates
per counterparty so the millions of rows never have to fit in memory.

    python scripts/scan_erc1155_ledger.py --wallet 0x204f...

Shares carry no dollar value on chain. tokenValue has 6 decimals and one share
pays at most $1, so the share sum is an upper bound on the dollar value.
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
LARGE_SHARES = 100_000.0  # rows kept individually, in shares


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


class Ledger1155:
    def __init__(self) -> None:
        self.by_counterparty: dict[tuple[str, str, str], dict] = defaultdict(
            lambda: {"shares": 0.0, "count": 0, "tokens": 0,
                     "first_block": None, "last_block": None,
                     "first_ts": None, "last_ts": None})
        self.by_month: dict[str, dict] = defaultdict(lambda: {"in": 0.0, "out": 0.0, "n": 0})
        self.large: list[dict] = []
        self.total_in = 0.0
        self.total_out = 0.0
        self.rows = 0
        self._token_seen: dict[tuple[str, str, str], set] = defaultdict(set)

    def add(self, wallet: str, row: dict) -> None:
        try:
            shares = float(row.get("tokenValue", 0)) / 1_000_000.0
            block = int(row.get("blockNumber", 0))
            stamp = int(row.get("timeStamp", 0))
        except (TypeError, ValueError):
            return
        sender = str(row.get("from", "")).lower()
        recipient = str(row.get("to", "")).lower()
        if wallet not in (sender, recipient):
            return
        incoming = recipient == wallet
        counterparty = sender if incoming else recipient
        direction = "in" if incoming else "out"
        token_contract = str(row.get("contractAddress", "")).lower()
        key = (counterparty, direction, token_contract)

        entry = self.by_counterparty[key]
        entry["shares"] += shares
        entry["count"] += 1
        if entry["first_block"] is None or block < entry["first_block"]:
            entry["first_block"], entry["first_ts"] = block, stamp
        if entry["last_block"] is None or block > entry["last_block"]:
            entry["last_block"], entry["last_ts"] = block, stamp
        # distinct token ids, but only tracked for small (non-protocol-scale) flows
        bucket = self._token_seen[key]
        if len(bucket) < 20_000:
            bucket.add(str(row.get("tokenID", "")))
            entry["tokens"] = len(bucket)

        month = time.strftime("%Y-%m", time.gmtime(stamp)) if stamp else "unknown"
        self.by_month[month][direction] += shares
        self.by_month[month]["n"] += 1
        if incoming:
            self.total_in += shares
        else:
            self.total_out += shares
        self.rows += 1
        if shares >= LARGE_SHARES:
            self.large.append({"block": block, "timestamp": stamp, "direction": direction,
                               "counterparty": counterparty, "token_contract": token_contract,
                               "shares": shares, "token_id": str(row.get("tokenID", "")),
                               "tx": str(row.get("hash", "")),
                               "method": str(row.get("functionName", ""))[:60]})

    def to_state(self) -> dict:
        return {
            "by_counterparty": {"|".join(k): v for k, v in self.by_counterparty.items()},
            "by_month": dict(self.by_month), "large": self.large,
            "total_in": self.total_in, "total_out": self.total_out, "rows": self.rows,
        }

    @classmethod
    def from_state(cls, state: dict) -> "Ledger1155":
        ledger = cls()
        for key, value in (state.get("by_counterparty") or {}).items():
            parts = key.split("|")
            if len(parts) == 3:
                ledger.by_counterparty[(parts[0], parts[1], parts[2])] = value
        for month, value in (state.get("by_month") or {}).items():
            ledger.by_month[month] = value
        ledger.large = state.get("large") or []
        ledger.total_in = float(state.get("total_in") or 0.0)
        ledger.total_out = float(state.get("total_out") or 0.0)
        ledger.rows = int(state.get("rows") or 0)
        return ledger


def fetch_page(wallet: str, api_key: str, start_block: int) -> list | None:
    params = {"chainid": POLYGON_CHAIN_ID, "module": "account", "action": "token1155tx",
              "address": wallet, "startblock": start_block, "endblock": 99_999_999,
              "page": 1, "offset": 10_000, "sort": "asc", "apikey": api_key}
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


def scan(wallet: str, api_key: str, pause: float, state_path: Path) -> tuple[Ledger1155, bool]:
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    ledger = Ledger1155.from_state(state.get("ledger", {})) if state else Ledger1155()
    block = int(state.get("cursor", 0))
    seen: set[str] = set(state.get("seen_tail", []))
    complete = True
    if state.get("done"):
        print("  bereits fertig (Resume)", flush=True)
        return ledger, True

    print(f"  ERC-1155 ab Block {block:,}", flush=True)
    pages = 0
    while True:
        result = fetch_page(wallet, api_key, block)
        if result is None:
            print(f"    ABBRUCH bei Block {block:,}", flush=True)
            complete = False
            break
        if not result:
            state["done"] = True
            break
        fresh = 0
        for row in result:
            marker = (f"{row.get('hash')}|{row.get('from')}|{row.get('to')}"
                      f"|{row.get('tokenID')}|{row.get('tokenValue')}")
            if marker in seen:
                continue
            seen.add(marker)
            ledger.add(wallet, row)
            fresh += 1
        last_block = int(result[-1].get("blockNumber", block))
        pages += 1
        if fresh == 0:
            state["done"] = True
            break
        block = last_block
        if pages % 25 == 0:
            print(f"    Seite {pages}: Block {block:,}, Zeilen {ledger.rows:,}, "
                  f"IN {ledger.total_in:,.0f} OUT {ledger.total_out:,.0f} Shares", flush=True)
            state_path.write_text(json.dumps({
                "ledger": ledger.to_state(), "cursor": block,
                "seen_tail": list(seen)[-40_000:]}), encoding="utf-8")
        time.sleep(pause)
    state_path.write_text(json.dumps({
        "ledger": ledger.to_state(), "cursor": block, "done": state.get("done", False),
        "seen_tail": list(seen)[-40_000:]}), encoding="utf-8")
    return ledger, complete


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wallet", required=True)
    parser.add_argument("--pause", type=float, default=0.21)
    parser.add_argument("--out-dir", default=str(REPO_ROOT / "data"))
    args = parser.parse_args()

    api_key = load_api_key()
    if not api_key:
        print("No ETHERSCAN_API_KEY found (env or .env).")
        return 1
    wallet = args.wallet.lower()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    state_path = out_dir / "ledger1155_scan_state.json"

    print(f"ERC-1155-Scan fuer {wallet}\n")
    ledger, complete = scan(wallet, api_key, args.pause, state_path)

    rows = [{"counterparty": cp, "direction": d, "token_contract": tc, **v}
            for (cp, d, tc), v in ledger.by_counterparty.items()]
    counterparties = pd.DataFrame(rows)
    if not counterparties.empty:
        counterparties = counterparties.sort_values("shares", ascending=False)
        counterparties.to_csv(out_dir / "ledger1155_counterparties.csv", index=False)
    months = pd.DataFrame([{"month": m, **v} for m, v in sorted(ledger.by_month.items())])
    months.to_csv(out_dir / "ledger1155_monthly.csv", index=False)
    pd.DataFrame(ledger.large).to_csv(out_dir / "ledger1155_large_transfers.csv", index=False)

    print(f"\n{'='*80}\nERC-1155-BILANZ   (vollstaendig: {complete})\n{'='*80}")
    print(f"  Transfers gesamt : {ledger.rows:>18,}")
    print(f"  Shares IN        : {ledger.total_in:>18,.2f}")
    print(f"  Shares OUT       : {ledger.total_out:>18,.2f}")
    print(f"  NETTO Shares     : {ledger.total_in - ledger.total_out:>18,.2f}")
    if not counterparties.empty:
        print("\n=== ALLE GEGENPARTEIEN ===")
        print(counterparties.to_string(index=False, float_format=lambda v: f"{v:,.2f}"))
    print(f"\ngespeichert -> {out_dir}/ledger1155_*.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
