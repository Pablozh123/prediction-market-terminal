"""Complete USDC ledger for one wallet: every transfer, no pre-filtering.

The earlier scan discarded protocol counterparties while paging, which made the
outflow side incomplete and left a $15.6M hole between the measured net flow and
the accounting identity (balance = deposits - withdrawals + profit). This walks
the same history keeping everything, and aggregates as it goes so the full 3.4M
rows never have to fit in memory.

    python scripts/full_wallet_ledger.py --wallet 0x204f...

State is checkpointed to disk after every batch, so an interrupted run resumes
instead of starting over. Read-only: public API, no order path, no signing.
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

from app import onchain_flows as ocf  # noqa: E402

API_URL = "https://api.etherscan.io/v2/api"
POLYGON_CHAIN_ID = 137
SESSION = requests.Session()
LARGE_TRANSFER_USD = 10_000.0  # kept row-by-row; everything else only aggregates


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


class Ledger:
    """Running aggregate over transfers, so nothing has to be held in memory."""

    def __init__(self) -> None:
        self.by_counterparty: dict[tuple[str, str], dict] = defaultdict(
            lambda: {"amount": 0.0, "count": 0, "first_block": None, "last_block": None,
                     "first_ts": None, "last_ts": None})
        self.by_month: dict[str, dict] = defaultdict(lambda: {"in": 0.0, "out": 0.0, "n": 0})
        self.large: list[dict] = []
        self.total_in = 0.0
        self.total_out = 0.0
        self.rows = 0

    def add(self, wallet: str, row: dict) -> None:
        try:
            decimals = int(row.get("tokenDecimal") or 6)
            amount = float(row.get("value", 0)) / (10 ** decimals)
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

        entry = self.by_counterparty[(counterparty, direction)]
        entry["amount"] += amount
        entry["count"] += 1
        if entry["first_block"] is None or block < entry["first_block"]:
            entry["first_block"], entry["first_ts"] = block, stamp
        if entry["last_block"] is None or block > entry["last_block"]:
            entry["last_block"], entry["last_ts"] = block, stamp

        month = time.strftime("%Y-%m", time.gmtime(stamp)) if stamp else "unknown"
        self.by_month[month][direction] += amount
        self.by_month[month]["n"] += 1

        if incoming:
            self.total_in += amount
        else:
            self.total_out += amount
        self.rows += 1
        if amount >= LARGE_TRANSFER_USD:
            self.large.append({"block": block, "timestamp": stamp, "direction": direction,
                               "counterparty": counterparty, "amount": amount,
                               "tx": str(row.get("hash", ""))})

    def to_state(self) -> dict:
        return {
            "by_counterparty": {f"{cp}|{d}": v for (cp, d), v in self.by_counterparty.items()},
            "by_month": dict(self.by_month),
            "large": self.large,
            "total_in": self.total_in, "total_out": self.total_out, "rows": self.rows,
        }

    @classmethod
    def from_state(cls, state: dict) -> "Ledger":
        ledger = cls()
        for key, value in (state.get("by_counterparty") or {}).items():
            counterparty, _, direction = key.rpartition("|")
            ledger.by_counterparty[(counterparty, direction)] = value
        for month, value in (state.get("by_month") or {}).items():
            ledger.by_month[month] = value
        ledger.large = state.get("large") or []
        ledger.total_in = float(state.get("total_in") or 0.0)
        ledger.total_out = float(state.get("total_out") or 0.0)
        ledger.rows = int(state.get("rows") or 0)
        return ledger


def fetch_page(wallet: str, api_key: str, contract: str, start_block: int) -> list | None:
    params = {"chainid": POLYGON_CHAIN_ID, "module": "account", "action": "tokentx",
              "address": wallet, "contractaddress": contract, "startblock": start_block,
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


def scan(wallet: str, api_key: str, pause: float, state_path: Path,
         contracts: tuple[str, ...] = ocf.USDC_CONTRACTS) -> tuple[Ledger, bool]:
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    ledger = Ledger.from_state(state.get("ledger", {})) if state else Ledger()
    cursors = state.get("cursors", {})
    seen: set[str] = set(state.get("seen_tail", []))
    complete = True

    for contract in contracts:
        label = {"0x2791": "USDC.e", "0x3c49": "USDC", "0xc011": "pUSD"}.get(contract[:6], contract[:10])
        block = int(cursors.get(contract, 0))
        if cursors.get(f"{contract}_done"):
            print(f"  {label}: bereits fertig (Resume)", flush=True)
            continue
        print(f"  {label} ab Block {block:,}", flush=True)
        pages = 0
        while True:
            result = fetch_page(wallet, api_key, contract, block)
            if result is None:
                print(f"    ABBRUCH bei Block {block:,} nach Wiederholungen", flush=True)
                complete = False
                break
            if not result:
                cursors[f"{contract}_done"] = True
                break
            fresh = 0
            for row in result:
                marker = f"{row.get('hash')}|{row.get('from')}|{row.get('to')}|{row.get('value')}"
                if marker in seen:
                    continue
                seen.add(marker)
                ledger.add(wallet, row)
                fresh += 1
            last_block = int(result[-1].get("blockNumber", block))
            pages += 1
            if fresh == 0:
                cursors[f"{contract}_done"] = True
                break
            block = last_block
            cursors[contract] = block
            if pages % 50 == 0:
                print(f"    Seite {pages}: Block {block:,}, Zeilen {ledger.rows:,}, "
                      f"IN ${ledger.total_in:,.0f} OUT ${ledger.total_out:,.0f}", flush=True)
                # Keep only a recent slice of markers: pages are block-ordered, so
                # older markers can no longer collide with an incoming page.
                state_path.write_text(json.dumps({
                    "ledger": ledger.to_state(), "cursors": cursors,
                    "seen_tail": list(seen)[-40_000:]}), encoding="utf-8")
            time.sleep(pause)
        state_path.write_text(json.dumps({
            "ledger": ledger.to_state(), "cursors": cursors,
            "seen_tail": list(seen)[-40_000:]}), encoding="utf-8")
    return ledger, complete


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wallet", required=True)
    parser.add_argument("--pause", type=float, default=0.21)
    parser.add_argument("--tokens", default="usdc", choices=("usdc", "pusd", "all"),
                        help="Welche Collateral-Waehrung scannen")
    parser.add_argument("--out-dir", default=str(REPO_ROOT / "data"))
    args = parser.parse_args()

    api_key = load_api_key()
    if not api_key:
        print("Kein ETHERSCAN_API_KEY gefunden.")
        return 1
    wallet = args.wallet.lower()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    state_path = out_dir / f"ledger_scan_state_{args.tokens}.json"

    print(f"Vollstaendiger Scan (ohne Vorfilter) fuer {wallet}\n")
    contracts = {"usdc": ocf.USDC_CONTRACTS, "pusd": (ocf.PUSD_CONTRACT,),
                 "all": ocf.COLLATERAL_CONTRACTS}[args.tokens]
    ledger, complete = scan(wallet, api_key, args.pause, state_path, contracts)

    counterparties = pd.DataFrame([
        {"counterparty": cp, "direction": d, **v} for (cp, d), v in ledger.by_counterparty.items()
    ])
    if not counterparties.empty:
        counterparties = counterparties.sort_values("amount", ascending=False)
        counterparties.to_csv(out_dir / f"ledger_counterparties_{args.tokens}.csv", index=False)
    months = pd.DataFrame([{"month": m, **v} for m, v in sorted(ledger.by_month.items())])
    months.to_csv(out_dir / f"ledger_monthly_{args.tokens}.csv", index=False)
    pd.DataFrame(ledger.large).to_csv(out_dir / f"ledger_large_transfers_{args.tokens}.csv", index=False)

    print(f"\n{'='*80}\nVOLLSTAENDIGE USDC-BILANZ   (vollstaendig: {complete})\n{'='*80}")
    print(f"  Transfers gesamt : {ledger.rows:>16,}")
    print(f"  Zufluss gesamt   : ${ledger.total_in:>16,.2f}")
    print(f"  Abfluss gesamt   : ${ledger.total_out:>16,.2f}")
    print(f"  NETTO            : ${ledger.total_in - ledger.total_out:>16,.2f}")
    print(f"  Gegenparteien    : {counterparties['counterparty'].nunique() if not counterparties.empty else 0:>16,}")
    print(f"  Grosstransfers   : {len(ledger.large):>16,}  (>= ${LARGE_TRANSFER_USD:,.0f})")
    if not counterparties.empty:
        print("\n=== TOP 15 GEGENPARTEIEN ===")
        top = counterparties.head(15)[["counterparty", "direction", "amount", "count"]]
        print(top.to_string(index=False, float_format=lambda v: f"{v:,.2f}"))
    print(f"\ngespeichert -> {out_dir}/ledger_*.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
