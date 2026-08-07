"""Parallel Etherscan V2 ledger scan for one wallet (ERC-20 or ERC-1155) on Polygon.

The serial scanners are latency-bound: for a wallet with millions of transfers a
single page takes ~4s server-side, and the page size is hard-capped at 1000 rows
no matter what `offset` says. Splitting the block range across threads turns a
four-hour walk into a few minutes while staying far below the 5 calls/s limit.

    python scripts/scan_wallet_ledger_parallel.py --wallet 0x204f... \
        --kind erc1155 --tag t1155 --workers 12

Windows are scanned independently and merged at the end. A window keeps only
rows with window_start <= block < window_end, so boundary pages cannot
double-count. If one block holds more rows than a page, the worker walks the
`page` parameter for that single block instead of stalling.

Read-only: public API, no order path, no signing.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import pandas as pd  # noqa: E402
import requests  # noqa: E402

API_URL = "https://api.etherscan.io/v2/api"
POLYGON_CHAIN_ID = 137
PAGE_CAP = 1000  # server-side hard cap, independent of the offset we send
PRINT_LOCK = threading.Lock()


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


class RateLimiter:
    """Global call pacer. Without it every worker races into the per-key limit,
    every request comes back as an error, and the backoff sleeps collapse
    throughput far below the limit itself."""

    def __init__(self, per_second: float) -> None:
        self.interval = 1.0 / per_second
        self.lock = threading.Lock()
        self.next_slot = 0.0

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            slot = max(now, self.next_slot)
            self.next_slot = slot + self.interval
        delay = slot - time.monotonic()
        if delay > 0:
            time.sleep(delay)

    def penalise(self, seconds: float) -> None:
        with self.lock:
            self.next_slot = max(self.next_slot, time.monotonic() + seconds)


LIMITER = RateLimiter(4.0)
RATE_HITS = [0]


def api_get(session: requests.Session, params: dict) -> list | None:
    for attempt in range(10):
        LIMITER.wait()
        try:
            payload = session.get(API_URL, params=params, timeout=120).json()
        except Exception:  # noqa: BLE001
            time.sleep(1.0 * (attempt + 1))
            continue
        result = payload.get("result")
        if isinstance(result, list):
            return result
        message = str(payload.get("message") or result)
        if "No transactions found" in message or "No records found" in message:
            return []
        RATE_HITS[0] += 1
        LIMITER.penalise(min(0.5 * (attempt + 1), 3.0))
    return None


class Bucket:
    """Per-window aggregate; merged into the global tally at the end."""

    def __init__(self) -> None:
        self.by_cp: dict[tuple, dict] = defaultdict(
            lambda: {"amount": 0.0, "count": 0, "first_block": None, "last_block": None,
                     "first_ts": None, "last_ts": None})
        self.by_method: dict[tuple, dict] = defaultdict(lambda: {"amount": 0.0, "count": 0})
        self.by_month: dict[str, dict] = defaultdict(lambda: {"in": 0.0, "out": 0.0, "n": 0})
        self.large: list[dict] = []
        self.total_in = 0.0
        self.total_out = 0.0
        self.rows = 0
        self.incomplete: list[int] = []

    def add(self, wallet: str, row: dict, kind: str, large_min: float) -> None:
        try:
            if kind == "erc1155":
                amount = float(row.get("tokenValue", 0)) / 1_000_000.0
            else:
                amount = float(row.get("value", 0)) / (10 ** int(row.get("tokenDecimal") or 6))
            block = int(row.get("blockNumber", 0))
            stamp = int(row.get("timeStamp", 0))
        except (TypeError, ValueError):
            return
        sender = str(row.get("from", "")).lower()
        recipient = str(row.get("to", "")).lower()
        if wallet not in (sender, recipient):
            return
        incoming = recipient == wallet
        cp = sender if incoming else recipient
        direction = "in" if incoming else "out"
        token = str(row.get("contractAddress", "")).lower()

        entry = self.by_cp[(cp, direction, token)]
        entry["amount"] += amount
        entry["count"] += 1
        if entry["first_block"] is None or block < entry["first_block"]:
            entry["first_block"], entry["first_ts"] = block, stamp
        if entry["last_block"] is None or block > entry["last_block"]:
            entry["last_block"], entry["last_ts"] = block, stamp

        method = (str(row.get("functionName") or "").split("(")[0]
                  or str(row.get("methodId") or ""))[:48]
        m = self.by_method[(direction, method)]
        m["amount"] += amount
        m["count"] += 1

        month = time.strftime("%Y-%m", time.gmtime(stamp)) if stamp else "unknown"
        self.by_month[month][direction] += amount
        self.by_month[month]["n"] += 1
        if incoming:
            self.total_in += amount
        else:
            self.total_out += amount
        self.rows += 1
        if amount >= large_min:
            self.large.append({"block": block, "timestamp": stamp, "direction": direction,
                               "counterparty": cp, "token": token, "amount": amount,
                               "token_id": str(row.get("tokenID", "")),
                               "method": method, "tx": str(row.get("hash", ""))})

    def merge(self, other: "Bucket") -> None:
        for key, value in other.by_cp.items():
            e = self.by_cp[key]
            e["amount"] += value["amount"]
            e["count"] += value["count"]
            if e["first_block"] is None or (value["first_block"] is not None
                                            and value["first_block"] < e["first_block"]):
                e["first_block"], e["first_ts"] = value["first_block"], value["first_ts"]
            if e["last_block"] is None or (value["last_block"] is not None
                                           and value["last_block"] > e["last_block"]):
                e["last_block"], e["last_ts"] = value["last_block"], value["last_ts"]
        for key, value in other.by_method.items():
            self.by_method[key]["amount"] += value["amount"]
            self.by_method[key]["count"] += value["count"]
        for month, value in other.by_month.items():
            self.by_month[month]["in"] += value["in"]
            self.by_month[month]["out"] += value["out"]
            self.by_month[month]["n"] += value["n"]
        self.large.extend(other.large)
        self.total_in += other.total_in
        self.total_out += other.total_out
        self.rows += other.rows
        self.incomplete.extend(other.incomplete)


def base_params(wallet: str, kind: str, token: str | None, api_key: str) -> dict:
    params = {"chainid": POLYGON_CHAIN_ID, "module": "account",
              "action": "token1155tx" if kind == "erc1155" else "tokentx",
              "address": wallet, "page": 1, "offset": PAGE_CAP, "sort": "asc",
              "apikey": api_key}
    if token:
        params["contractaddress"] = token
    return params


def scan_window(wallet: str, kind: str, token: str | None, api_key: str,
                start: int, end: int, large_min: float, idx: int) -> Bucket:
    """Collect rows with start <= block < end.

    Pages are capped at PAGE_CAP rows, so the last block of a full page is
    usually only partly delivered. Rather than spend a second request on that
    block, the next page restarts *at* it and skips the rows already counted
    (`carry`), which the ascending order makes deterministic.
    """
    session = requests.Session()
    bucket = Bucket()
    block = start
    carry = 0  # rows of `block` already counted by earlier pages
    calls = 0
    while block < end:
        params = base_params(wallet, kind, token, api_key)
        params.update({"startblock": block, "endblock": end - 1})
        rows = api_get(session, params)
        calls += 1
        if rows is None:
            bucket.incomplete.append(block)
            break
        if not rows:
            break
        skipped = 0
        for row in rows:
            try:
                blk = int(row.get("blockNumber", 0))
            except (TypeError, ValueError):
                continue
            if blk == block and skipped < carry:
                skipped += 1
                continue
            if start <= blk < end:
                bucket.add(wallet, row, kind, large_min)
        if len(rows) < PAGE_CAP:
            break
        last_block = int(rows[-1].get("blockNumber", block))
        tail_count = sum(1 for r in rows if int(r.get("blockNumber", 0)) == last_block)
        if last_block == block:
            # A single block fills a whole page, so the startblock cursor cannot
            # advance. Walk the page parameter for that one block instead.
            page = (carry // PAGE_CAP) + 2
            while page <= 10:
                params = base_params(wallet, kind, token, api_key)
                params.update({"startblock": block, "endblock": block, "page": page})
                extra = api_get(session, params)
                calls += 1
                if not extra:
                    break
                for row in extra:
                    bucket.add(wallet, row, kind, large_min)
                if len(extra) < PAGE_CAP:
                    break
                page += 1
            if page > 10:
                bucket.incomplete.append(block)
            block += 1
            carry = 0
        else:
            block = last_block
            carry = tail_count
    with PRINT_LOCK:
        print(f"  Fenster {idx:>3} [{start:,}..{end:,}) fertig: {bucket.rows:>9,} Zeilen "
              f"/ {calls:>5} Calls", flush=True)
    return bucket


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wallet", required=True)
    parser.add_argument("--kind", choices=["erc20", "erc1155"], default="erc1155")
    parser.add_argument("--token", default=None, help="ERC-20 contract to restrict to")
    parser.add_argument("--tag", default="scan")
    parser.add_argument("--start-block", type=int, default=74_000_000)
    parser.add_argument("--end-block", type=int, default=91_000_000)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--windows", type=int, default=0, help="default: 4x workers")
    parser.add_argument("--large-min", type=float, default=50_000.0)
    parser.add_argument("--rate", type=float, default=4.0, help="API calls per second")
    parser.add_argument("--out-dir", default=str(REPO_ROOT / "data"))
    args = parser.parse_args()

    api_key = load_api_key()
    if not api_key:
        print("No ETHERSCAN_API_KEY found (env or .env).")
        return 1
    wallet = args.wallet.lower()
    token = args.token.lower() if args.token else None
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    global LIMITER
    LIMITER = RateLimiter(args.rate)
    n_windows = args.windows or args.workers * 4
    span = args.end_block - args.start_block
    edges = [args.start_block + (span * i) // n_windows for i in range(n_windows + 1)]
    started = time.time()
    print(f"{args.kind} Scan {wallet} Blocks {args.start_block:,}..{args.end_block:,} "
          f"in {n_windows} Fenstern, {args.workers} Threads", flush=True)

    total = Bucket()

    def dump(done: int) -> pd.DataFrame:
        frame = pd.DataFrame([{"counterparty": cp, "direction": d, "token": t, **v}
                              for (cp, d, t), v in total.by_cp.items()])
        if not frame.empty:
            frame = frame.sort_values("amount", ascending=False)
            frame.to_csv(out_dir / f"ledger_{args.tag}_counterparties.csv", index=False)
        pd.DataFrame([{"direction": d, "method": m, **v}
                      for (d, m), v in total.by_method.items()]).to_csv(
            out_dir / f"ledger_{args.tag}_methods.csv", index=False)
        pd.DataFrame(total.large).to_csv(out_dir / f"ledger_{args.tag}_large.csv", index=False)
        (out_dir / f"ledger_{args.tag}_progress.json").write_text(json.dumps({
            "windows_done": done, "windows_total": n_windows, "rows": total.rows,
            "total_in": total.total_in, "total_out": total.total_out,
            "incomplete": total.incomplete[:50], "rate_hits": RATE_HITS[0],
            "elapsed_s": round(time.time() - started, 1)}), encoding="utf-8")
        return frame

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(scan_window, wallet, args.kind, token, api_key,
                               edges[i], edges[i + 1], args.large_min, i)
                   for i in range(n_windows)]
        for fut in as_completed(futures):
            total.merge(fut.result())
            done += 1
            if done % 20 == 0:
                dump(done)
    dump(n_windows)

    cps = pd.DataFrame([{"counterparty": cp, "direction": d, "token": t, **v}
                        for (cp, d, t), v in total.by_cp.items()])
    if not cps.empty:
        cps = cps.sort_values("amount", ascending=False)
        cps.to_csv(out_dir / f"ledger_{args.tag}_counterparties.csv", index=False)
    methods = pd.DataFrame([{"direction": d, "method": m, **v}
                            for (d, m), v in total.by_method.items()])
    if not methods.empty:
        methods = methods.sort_values("amount", ascending=False)
        methods.to_csv(out_dir / f"ledger_{args.tag}_methods.csv", index=False)
    pd.DataFrame([{"month": m, **v} for m, v in sorted(total.by_month.items())]).to_csv(
        out_dir / f"ledger_{args.tag}_monthly.csv", index=False)
    pd.DataFrame(total.large).to_csv(out_dir / f"ledger_{args.tag}_large.csv", index=False)

    unit = "Shares" if args.kind == "erc1155" else "Token"
    print(f"\n{'='*80}\n{args.tag.upper()} BILANZ ({args.kind})\n{'='*80}")
    print(f"  Laufzeit    : {time.time() - started:>16,.0f}s")
    print(f"  Transfers   : {total.rows:>16,}")
    print(f"  IN  ({unit}) : {total.total_in:>16,.2f}")
    print(f"  OUT ({unit}) : {total.total_out:>16,.2f}")
    print(f"  NETTO       : {total.total_in - total.total_out:>16,.2f}")
    print(f"  Luecken     : {len(total.incomplete)} (Bloecke: {total.incomplete[:10]})")
    print(f"  Rate-Limits : {RATE_HITS[0]:>16,}")
    if not cps.empty:
        print(f"\n=== GEGENPARTEIEN gesamt {cps['counterparty'].nunique():,} "
              f"| top 25 nach Volumen ===")
        print(cps.head(25).to_string(index=False, float_format=lambda v: f"{v:,.2f}"))
    if not methods.empty:
        print("\n=== METHODEN ===")
        print(methods.head(25).to_string(index=False, float_format=lambda v: f"{v:,.2f}"))
    print(f"\ngespeichert -> {out_dir}/ledger_{args.tag}_*.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
