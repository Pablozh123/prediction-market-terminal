"""Interpret the complete USDC ledger produced by full_wallet_ledger.py.

Answers three questions the raw totals cannot:
  1. Does the ledger reconcile with the platform's reported profit?
  2. Which counterparties are protocol infrastructure and which are funding?
  3. What was the largest amount of external capital outstanding at any time?

Every counterparty above a materiality threshold is classified by asking the
chain whether it holds code, and named via the explorer where a verified source
exists, so the split is evidence rather than assumption.
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

from app import onchain_flows as ocf  # noqa: E402

API_URL = "https://api.etherscan.io/v2/api"
SESSION = requests.Session()


def load_api_key() -> str | None:
    import os
    if os.environ.get("ETHERSCAN_API_KEY"):
        return os.environ["ETHERSCAN_API_KEY"].strip()
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.strip().startswith(("ETHERSCAN_API_KEY", "POLYGONSCAN_API_KEY")) and "=" in line:
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def describe_address(address: str, api_key: str) -> tuple[str, str]:
    """(kind, name) for one address: EOA or CONTRACT, plus its verified name."""
    kind, name = "?", ""
    for _ in range(3):
        try:
            payload = SESSION.get(API_URL, params={
                "chainid": 137, "module": "proxy", "action": "eth_getCode",
                "address": address, "tag": "latest", "apikey": api_key}, timeout=30).json()
            code = payload.get("result")
            if code is not None:
                kind = "CONTRACT" if code and code != "0x" else "EOA"
                break
        except Exception:  # noqa: BLE001
            time.sleep(1)
    if kind != "CONTRACT":
        return kind, name
    for _ in range(3):
        try:
            payload = SESSION.get(API_URL, params={
                "chainid": 137, "module": "contract", "action": "getsourcecode",
                "address": address, "apikey": api_key}, timeout=30).json()
            result = payload.get("result")
            if isinstance(result, list) and result:
                name = str(result[0].get("ContractName") or "")
                break
        except Exception:  # noqa: BLE001
            time.sleep(1)
    return kind, name


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=str(REPO_ROOT / "data"))
    parser.add_argument("--profit", type=float, required=True, help="berichteter Profit")
    parser.add_argument("--balance", type=float, required=True, help="aktueller Portfoliowert")
    parser.add_argument("--materiality", type=float, default=50_000.0)
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    counterparties = pd.read_csv(data_dir / "ledger_counterparties.csv")
    monthly = pd.read_csv(data_dir / "ledger_monthly.csv")
    large = pd.read_csv(data_dir / "ledger_large_transfers.csv")

    total_in = float(counterparties[counterparties["direction"] == "in"]["amount"].sum())
    total_out = float(counterparties[counterparties["direction"] == "out"]["amount"].sum())

    print("=" * 88)
    print("1. VOLLSTAENDIGE BILANZ")
    print("=" * 88)
    print(f"  Zufluss  : ${total_in:>18,.2f}")
    print(f"  Abfluss  : ${total_out:>18,.2f}")
    print(f"  NETTO    : ${total_in - total_out:>18,.2f}")
    print(f"  Transfers: {int(counterparties['count'].sum()):>18,}")
    print(f"  Adressen : {counterparties['counterparty'].nunique():>18,}")

    print("\n" + "=" * 88)
    print("2. ABGLEICH MIT DER BUCHHALTUNGS-IDENTITAET")
    print("=" * 88)
    check = ocf.reconcile_ledger(total_in, total_out, args.balance, args.profit)
    print(f"  Endbestand = Nettofluss + Profit")
    print(f"  erwartet   : ${check['implied_balance']:>18,.2f}")
    print(f"  tatsaechlich: ${check['actual_balance']:>17,.2f}")
    print(f"  RESIDUUM   : ${check['residual']:>18,.2f}"
          f"   ({check['residual_pct_of_profit']:.1f} % des Profits)"
          if check["residual_pct_of_profit"] is not None else "")
    print(f"  stimmt ueberein: {check['reconciles']}")

    api_key = load_api_key()
    material = counterparties[counterparties["amount"] >= args.materiality].copy()
    print("\n" + "=" * 88)
    print(f"3. GEGENPARTEIEN >= ${args.materiality:,.0f}  ({len(material)} Zeilen)")
    print("=" * 88)
    kinds, names = [], []
    for address in material["counterparty"]:
        kind, name = describe_address(address, api_key) if api_key else ("?", "")
        kinds.append(kind)
        names.append(name)
    material["kind"] = kinds
    material["name"] = names
    material["known"] = material["counterparty"].isin(ocf.PROTOCOL_ADDRESSES)
    for _, row in material.iterrows():
        flag = "PROTOKOLL" if row["known"] else row["kind"]
        print(f"  {row['counterparty'][:14]}.. {row['direction']:<3} ${row['amount']:>16,.0f} "
              f"{int(row['count']):>7}x  {flag:<9} {row['name'][:26]}")
    material.to_csv(data_dir / "ledger_counterparties_classified.csv", index=False)

    print("\n" + "=" * 88)
    print("4. MONATLICHER NETTOFLUSS")
    print("=" * 88)
    monthly = monthly.sort_values("month")
    monthly["net"] = monthly["in"] - monthly["out"]
    monthly["cum"] = monthly["net"].cumsum()
    for _, row in monthly.iterrows():
        print(f"  {row['month']}  rein ${row['in']:>15,.0f}  raus ${row['out']:>15,.0f}"
              f"  netto ${row['net']:>14,.0f}  kumuliert ${row['cum']:>14,.0f}")
    print(f"\n  Hoechststand kumuliert: ${monthly['cum'].max():,.2f}")

    if not large.empty:
        print("\n" + "=" * 88)
        print(f"5. GROSSTRANSFERS  ({len(large):,} Stueck)")
        print("=" * 88)
        large = large.sort_values("amount", ascending=False)
        top = large.head(12)[["timestamp", "direction", "counterparty", "amount"]].copy()
        top["datum"] = pd.to_datetime(top["timestamp"], unit="s", utc=True).dt.date
        print(top[["datum", "direction", "counterparty", "amount"]].to_string(
            index=False, float_format=lambda v: f"{v:,.0f}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
