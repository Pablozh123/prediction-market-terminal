"""Scan Polygon for a wallet's USDC transfers and write them to CSV.

Read-only: eth_getLogs against public RPCs, no keys, no order path, no signing.

    python scripts/fetch_wallet_flows.py --wallet 0x204f... --from-block 75000000

Public archive RPCs cap the block span per call, so the range is walked in
chunks with failover between endpoints. Chunks that fail on every endpoint are
reported rather than skipped silently: a gap in the scan is a gap in the answer.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import pandas as pd  # noqa: E402
import requests  # noqa: E402

from app import onchain_flows as flows  # noqa: E402

# Public endpoints that answered archive eth_getLogs over a 500k span.
RPC_ENDPOINTS = (
    "https://gateway.tenderly.co/public/polygon",
    "https://polygon.api.onfinality.io/public",
)
SESSION = requests.Session()


def rpc_call(url: str, method: str, params: list, timeout: int = 90) -> dict:
    response = SESSION.post(
        url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=timeout
    )
    response.raise_for_status()
    return response.json()


def latest_block() -> int:
    for url in RPC_ENDPOINTS:
        try:
            return int(rpc_call(url, "eth_blockNumber", [], timeout=25)["result"], 16)
        except Exception:  # noqa: BLE001
            continue
    raise RuntimeError("kein RPC erreichbar")


def fetch_chunk(from_block: int, to_block: int, topics: list) -> list[dict] | None:
    """One chunk across every endpoint; None when all of them failed."""
    params = [{
        "fromBlock": hex(from_block), "toBlock": hex(to_block),
        "address": list(flows.USDC_CONTRACTS), "topics": topics,
    }]
    for url in RPC_ENDPOINTS:
        try:
            payload = rpc_call(url, "eth_getLogs", params)
        except Exception:  # noqa: BLE001
            continue
        if "error" in payload:
            continue
        return payload.get("result") or []
    return None


def scan(wallet: str, start: int, end: int, chunk: int, pause: float) -> tuple[pd.DataFrame, list[tuple[int, int]]]:
    padded = flows.topic_address(wallet)
    directions = {
        "in": [flows.TRANSFER_TOPIC, None, padded],
        "out": [flows.TRANSFER_TOPIC, padded, None],
    }
    frames: list[pd.DataFrame] = []
    gaps: list[tuple[int, int]] = []
    total = 0
    for label, topics in directions.items():
        block = start
        while block < end:
            upper = min(block + chunk, end)
            logs = fetch_chunk(block, upper, topics)
            if logs is None:
                gaps.append((block, upper))
                print(f"  [{label}] {block:,}-{upper:,}: FEHLGESCHLAGEN")
            elif logs:
                frame = flows.decode_transfer_logs(logs)
                frames.append(frame)
                total += len(frame)
                print(f"  [{label}] {block:,}-{upper:,}: {len(frame)} Transfers (gesamt {total})")
            block = upper
            time.sleep(pause)
    if not frames:
        return pd.DataFrame(columns=["block", "tx", "contract", "sender", "recipient", "amount"]), gaps
    merged = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["tx", "sender", "recipient", "amount"])
    return merged.sort_values("block").reset_index(drop=True), gaps


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wallet", required=True)
    parser.add_argument("--from-block", type=int, default=75_000_000)
    parser.add_argument("--to-block", type=int, default=0, help="0 = aktueller Block")
    parser.add_argument("--chunk", type=int, default=500_000)
    parser.add_argument("--pause", type=float, default=0.3)
    parser.add_argument("--out", default=str(REPO_ROOT / "data" / "wallet_flows.csv"))
    args = parser.parse_args()

    end = args.to_block or latest_block()
    print(f"Wallet {args.wallet}\nBloecke {args.from_block:,} bis {end:,} "
          f"({(end - args.from_block) / args.chunk:.0f} Chunks je Richtung)\n")

    transfers, gaps = scan(args.wallet, args.from_block, end, args.chunk, args.pause)
    classified = flows.classify_flows(transfers, args.wallet)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    classified.to_csv(out_path, index=False)

    summary = flows.flow_summary(classified)
    print(f"\nTransfers gesamt: {len(classified):,}   gespeichert -> {out_path}")
    if gaps:
        print(f"WARNUNG: {len(gaps)} Chunks nicht abrufbar, Zahlen sind Untergrenzen: {gaps[:5]}")
    print("\n=== EXTERNE FLUESSE (echte Ein- und Auszahlungen) ===")
    print(f"  Einzahlungen   : ${summary['deposits_external']:>16,.2f}")
    print(f"  Auszahlungen   : ${summary['withdrawals_external']:>16,.2f}")
    print(f"  NETTO im System: ${summary['net_external']:>16,.2f}")
    print(f"  Hoechststand   : ${flows.peak_external_exposure(classified):>16,.2f}")
    print("\n=== PROTOKOLL-FLUESSE (Settlement/Merge, keine Finanzierung) ===")
    print(f"  eingehend      : ${summary['deposits_protocol']:>16,.2f}")
    print(f"  ausgehend      : ${summary['withdrawals_protocol']:>16,.2f}")

    external = classified[~classified["is_protocol"].astype(bool)]
    if not external.empty:
        print("\n=== groesste externe Gegenparteien ===")
        top = external.groupby(["counterparty", "direction"])["amount"].agg(["sum", "count"])
        print(top.sort_values("sum", ascending=False).head(10).to_string(float_format=lambda v: f"{v:,.2f}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
