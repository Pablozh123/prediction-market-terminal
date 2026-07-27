"""Wallet USDC cash flows via the Etherscan V2 multichain API.

Read-only. Needs ETHERSCAN_API_KEY in the environment or in a local .env; the key
is never printed or written anywhere.

    python scripts/fetch_wallet_flows_api.py --wallet 0x204f...

The API returns at most 10,000 rows per query, so the history is walked forward
by block: each page resumes at the last block seen. A wallet whose transfers all
share one block would stall that loop, so the walk stops rather than spinning,
and reports how far it got.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import pandas as pd  # noqa: E402
import requests  # noqa: E402

from app import onchain_flows as ocf  # noqa: E402

API_URL = "https://api.etherscan.io/v2/api"
POLYGON_CHAIN_ID = 137
PAGE_SIZE = 10_000
SESSION = requests.Session()


def load_api_key(repo_root: Path = REPO_ROOT) -> str | None:
    """Key from the environment, else from a local .env. Never logged."""
    for name in ("ETHERSCAN_API_KEY", "POLYGONSCAN_API_KEY"):
        value = os.environ.get(name)
        if value:
            return value.strip()
    env_path = repo_root / ".env"
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() in ("ETHERSCAN_API_KEY", "POLYGONSCAN_API_KEY"):
            return value.strip().strip('"').strip("'")
    return None


def fetch_token_transfers(wallet: str, api_key: str, contract: str,
                          start_block: int = 0, pause: float = 0.25,
                          keep: "callable | None" = None) -> tuple[list[dict], bool]:
    """Every ERC-20 transfer of one contract for one wallet, paged by block.

    ``keep`` filters rows before they are retained. This wallet has millions of
    settlement transfers and a few dozen funding ones, so keeping everything
    wastes memory for no gain; the pagination cursor still advances over the
    discarded rows.

    Returns (rows, complete). ``complete`` is False when the walk had to stop
    early, so a caller never mistakes a truncated history for a full one.
    """
    rows: list[dict] = []
    seen: set[tuple] = set()
    block = start_block
    complete = True
    pages = 0
    scanned = 0
    while True:
        params = {
            "chainid": POLYGON_CHAIN_ID, "module": "account", "action": "tokentx",
            "address": wallet, "contractaddress": contract, "startblock": block,
            "endblock": 99_999_999, "page": 1, "offset": PAGE_SIZE, "sort": "asc",
            "apikey": api_key,
        }
        result = None
        for attempt in range(6):
            try:
                payload = SESSION.get(API_URL, params=params, timeout=90).json()
            except Exception:  # noqa: BLE001
                time.sleep(2 * (attempt + 1))
                continue
            candidate = payload.get("result")
            if isinstance(candidate, list):
                result = candidate
                break
            message = str(payload.get("message") or candidate)
            if "No transactions found" in message or "No records found" in message:
                result = []
                break
            # Transient server errors are the norm on a multi-million-row walk;
            # backing off beats abandoning the scan three quarters of the way in.
            time.sleep(3 * (attempt + 1))
        if result is None:
            print(f"    Abbruch nach Wiederholungen bei Block {block:,}")
            complete = False
            break
        if not result:
            break
        scanned += len(result)
        fresh = 0
        for row in result:
            marker = (row.get("hash"), row.get("from"), row.get("to"), row.get("value"))
            if marker in seen:
                continue
            seen.add(marker)
            fresh += 1
            if keep is None or keep(row):
                rows.append(row)
        last_block = int(result[-1].get("blockNumber", block))
        pages += 1
        if pages % 100 == 0 or fresh == 0:
            print(f"    Seite {pages}: Block {last_block:,}, gescannt {scanned:,}, "
                  f"extern behalten {len(rows):,}", flush=True)
        # The server caps the page size below the requested offset, so a short
        # page is NOT proof the history ended. Only an empty page, or a page that
        # adds nothing new, is. Resuming at last_block re-reads that block, which
        # the dedup marker absorbs.
        if fresh == 0:
            break
        block = last_block
        time.sleep(pause)
    return rows, complete


def to_transfer_frame(rows: list[dict]) -> pd.DataFrame:
    """Etherscan rows -> the frame shape app.onchain_flows expects."""
    columns = ["block", "tx", "contract", "sender", "recipient", "amount", "timestamp"]
    if not rows:
        return pd.DataFrame(columns=columns)
    frame = pd.DataFrame(rows)
    decimals = pd.to_numeric(frame.get("tokenDecimal"), errors="coerce").fillna(ocf.USDC_DECIMALS)
    out = pd.DataFrame({
        "block": pd.to_numeric(frame.get("blockNumber"), errors="coerce").fillna(0).astype("int64"),
        "tx": frame.get("hash", "").astype(str),
        "contract": frame.get("contractAddress", "").astype(str).str.lower(),
        "sender": frame.get("from", "").astype(str).str.lower(),
        "recipient": frame.get("to", "").astype(str).str.lower(),
        "amount": pd.to_numeric(frame.get("value"), errors="coerce").fillna(0.0) / (10 ** decimals),
        "timestamp": pd.to_datetime(pd.to_numeric(frame.get("timeStamp"), errors="coerce"),
                                    unit="s", utc=True, errors="coerce"),
    })
    return out.drop_duplicates(subset=["tx", "sender", "recipient", "amount"]).reset_index(drop=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wallet", required=True)
    parser.add_argument("--pause", type=float, default=0.25)
    parser.add_argument("--out", default=str(REPO_ROOT / "data" / "wallet_flows.csv"))
    args = parser.parse_args()

    api_key = load_api_key()
    if not api_key:
        print("Kein API-Key gefunden (ETHERSCAN_API_KEY in .env oder Umgebung).")
        return 1

    wallet = args.wallet.lower()

    def is_external(row: dict) -> bool:
        """Drop protocol counterparties at page level; they are trading, not funding."""
        sender = str(row.get("from", "")).lower()
        recipient = str(row.get("to", "")).lower()
        other = sender if recipient == wallet else recipient
        return other not in ocf.PROTOCOL_ADDRESSES

    all_rows: list[dict] = []
    complete = True
    for contract in ocf.USDC_CONTRACTS:
        label = "USDC.e" if contract.startswith("0x2791") else "USDC"
        print(f"  {label} ({contract[:10]}..):", flush=True)
        rows, ok = fetch_token_transfers(wallet, api_key, contract, pause=args.pause,
                                         keep=is_external)
        all_rows += rows
        complete = complete and ok

    transfers = to_transfer_frame(all_rows)
    stamps = transfers[["tx", "sender", "recipient", "amount", "timestamp"]] if "timestamp" in transfers else None
    classified = ocf.classify_flows(transfers.drop(columns=["timestamp"], errors="ignore"), wallet)
    if stamps is not None and not classified.empty:
        # A single transaction can carry several transfers, so tx alone is not a
        # unique key; merging on the full transfer identity avoids a bad reindex.
        classified = classified.merge(stamps, on=["tx", "sender", "recipient", "amount"], how="left")
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    classified.to_csv(out_path, index=False)

    summary = ocf.flow_summary(classified)
    print(f"\nTransfers gesamt: {len(classified):,}   Historie vollstaendig: {complete}")
    print(f"gespeichert -> {out_path}\n")
    print("=== EXTERNE FLUESSE (echte Ein- und Auszahlungen) ===")
    print(f"  Einzahlungen    : ${summary['deposits_external']:>16,.2f}")
    print(f"  Auszahlungen    : ${summary['withdrawals_external']:>16,.2f}")
    print(f"  NETTO im System : ${summary['net_external']:>16,.2f}")
    print(f"  Hoechststand    : ${ocf.peak_external_exposure(classified):>16,.2f}")
    print("\n=== PROTOKOLL-FLUESSE (Settlement/Merge, keine Finanzierung) ===")
    print(f"  eingehend       : ${summary['deposits_protocol']:>16,.2f}")
    print(f"  ausgehend       : ${summary['withdrawals_protocol']:>16,.2f}")

    external = classified[~classified["is_protocol"].astype(bool)]
    if not external.empty:
        print(f"\n=== EXTERNE GEGENPARTEIEN ({external['counterparty'].nunique()}) ===")
        table = external.groupby(["counterparty", "direction"])["amount"].agg(["sum", "count"])
        print(table.sort_values("sum", ascending=False).to_string(float_format=lambda v: f"{v:,.2f}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
