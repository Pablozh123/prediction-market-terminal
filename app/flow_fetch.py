"""Bounded on-chain flow fetch for one wallet, sized for an API route.

``scripts/fetch_wallet_flows_api.py`` walks a wallet's complete transfer
history and is allowed to take minutes: a heavy wallet has millions of
settlement transfers. An API route is not — it answers within seconds or it is
not a route. This module walks the same Etherscan V2 pages under a hard page
budget per collateral contract and carries a ``complete`` flag, so a capped
walk can never pass itself off as a full one. All money figures from an
incomplete walk are lower bounds and are labelled as such by the caller.

One thing survives the cap unconditionally: the walk pages from block 0
upward, so the first row it sees IS the wallet's first collateral transfer.
``first_transfer_at`` is therefore a real on-chain first-seen even when the
budget cuts the rest — subject only to every scanned contract having answered
at all, which is what ``complete`` per contract guards.

Decimals come per row from the API (``tokenDecimal``), so the pinned-exponent
question of ``app.onchain_flows`` does not reopen here; classification,
summary and peak exposure reuse that module unchanged.

Network access is injectable (``get``), so everything is testable offline;
the default uses ``requests`` with retries and a polite pause.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

import pandas as pd

from app import onchain_flows as ocf

API_URL = "https://api.etherscan.io/v2/api"
POLYGON_CHAIN_ID = 137
PAGE_SIZE = 10_000
#: Pages per contract before the walk stops. Four pages are 40k transfers per
#: contract — generous for a normal wallet, a fraction of a market maker. The
#: budget exists so the route has a worst case; ``complete`` says when it hit.
DEFAULT_PAGE_BUDGET = 4


class FlowFetchError(RuntimeError):
    """The walk could not run at all (no key, no usable answer)."""


def load_api_key(repo_root: Path | str | None = None) -> str | None:
    """Etherscan key from the environment, else from a local .env. Never logged."""

    for name in ("ETHERSCAN_API_KEY", "POLYGONSCAN_API_KEY"):
        value = os.environ.get(name)
        if value:
            return value.strip()
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[1]
    env_path = Path(repo_root) / ".env"
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


def _default_get(params: Mapping[str, Any]) -> Any:
    import requests

    return requests.get(API_URL, params=dict(params), timeout=30).json()


def fetch_contract_transfers(
    wallet: str,
    api_key: str,
    contract: str,
    *,
    page_budget: int = DEFAULT_PAGE_BUDGET,
    page_size: int = PAGE_SIZE,
    pause: float = 0.2,
    retries: int = 3,
    get: Callable[[Mapping[str, Any]], Any] | None = None,
) -> tuple[list[dict], bool]:
    """One contract's transfers for one wallet, oldest first, budget-capped.

    Returns (rows, complete). ``complete`` is False when the budget cut the
    walk or a page never answered; the rows read so far are still returned,
    because a labelled lower bound beats nothing. Pagination resumes at the
    last block seen (the server caps page sizes silently, so only an empty or
    fully-known page proves the history ended); the dedup marker absorbs the
    re-read of that block.
    """

    fetch = get or _default_get
    rows: list[dict] = []
    seen: set[tuple] = set()
    block = 0
    pages = 0
    while pages < max(1, int(page_budget)):
        params = {
            "chainid": POLYGON_CHAIN_ID, "module": "account", "action": "tokentx",
            "address": wallet, "contractaddress": contract, "startblock": block,
            "endblock": 99_999_999, "page": 1, "offset": int(page_size), "sort": "asc",
            "apikey": api_key,
        }
        result = None
        for attempt in range(max(1, int(retries))):
            try:
                payload = fetch(params)
            except Exception:  # noqa: BLE001 - network errors are the retry case
                time.sleep(pause * (attempt + 1))
                continue
            candidate = payload.get("result") if isinstance(payload, Mapping) else None
            if isinstance(candidate, list):
                result = candidate
                break
            message = str((payload or {}).get("message", "") if isinstance(payload, Mapping) else "")
            if "No transactions found" in message or "No records found" in str(candidate):
                result = []
                break
            time.sleep(pause * (attempt + 1))
        if result is None:
            return rows, False
        if not result:
            return rows, True
        fresh = 0
        for row in result:
            marker = (row.get("hash"), row.get("from"), row.get("to"), row.get("value"))
            if marker in seen:
                continue
            seen.add(marker)
            fresh += 1
            rows.append(row)
        if fresh == 0:
            return rows, True
        try:
            block = int(result[-1].get("blockNumber", block))
        except (TypeError, ValueError):
            return rows, False
        # A short page is NOT proof the history ended: the server caps page
        # sizes below the requested offset. Only an empty page or a page that
        # adds nothing new is proof, so the loop walks on and lets the dedup
        # marker end it one cheap request later.
        pages += 1
        if pause:
            time.sleep(pause)
    # The budget ended the loop while pages were still full: capped, not done.
    return rows, False


def to_transfer_frame(rows: Iterable[Mapping[str, Any]]) -> pd.DataFrame:
    """Etherscan rows -> the frame shape ``app.onchain_flows`` expects."""

    columns = ["block", "tx", "contract", "sender", "recipient", "amount", "timestamp"]
    rows = list(rows or [])
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
        "amount": pd.to_numeric(frame.get("value"), errors="coerce").fillna(0.0) / (10.0 ** decimals),
        "timestamp": pd.to_datetime(pd.to_numeric(frame.get("timeStamp"), errors="coerce"),
                                    unit="s", utc=True, errors="coerce"),
    })
    return out.drop_duplicates(subset=["tx", "sender", "recipient", "amount"]).reset_index(drop=True)


def wallet_flow_report(
    wallet: str,
    api_key: str,
    *,
    contracts: Iterable[str] = ocf.COLLATERAL_CONTRACTS,
    page_budget: int = DEFAULT_PAGE_BUDGET,
    page_size: int = PAGE_SIZE,
    pause: float = 0.2,
    top_counterparties: int = 12,
    get: Callable[[Mapping[str, Any]], Any] | None = None,
) -> dict[str, Any]:
    """Classified flows, funding summary and peak exposure for one wallet.

    The summary keys are those of ``ocf.flow_summary``; on an incomplete walk
    every one of them is a lower bound and ``complete`` is False. The peak
    figures come as the (low, high) pair around the ambiguous counterparties,
    exactly as the flows module defines them.
    """

    wallet = str(wallet or "").strip().lower()
    if not wallet:
        raise FlowFetchError("no wallet given")
    if not api_key:
        raise FlowFetchError("no Etherscan API key configured (ETHERSCAN_API_KEY)")

    all_rows: list[dict] = []
    complete = True
    per_contract: list[dict[str, Any]] = []
    for contract in contracts:
        rows, ok = fetch_contract_transfers(
            wallet, api_key, contract,
            page_budget=page_budget, page_size=page_size, pause=pause, get=get,
        )
        all_rows += rows
        complete = complete and ok
        per_contract.append({"contract": contract, "transfers": len(rows), "complete": ok})

    transfers = to_transfer_frame(all_rows)
    stamps = transfers[["tx", "sender", "recipient", "amount", "timestamp"]].copy()
    classified = ocf.classify_flows(transfers.drop(columns=["timestamp"], errors="ignore"), wallet)
    if not classified.empty:
        # One transaction can carry several transfers, so tx alone is not a
        # unique key; the merge uses the full transfer identity.
        classified = classified.merge(stamps, on=["tx", "sender", "recipient", "amount"], how="left")
    summary = ocf.flow_summary(classified)

    first_transfer = None
    if not transfers.empty and transfers["timestamp"].notna().any():
        first_transfer = transfers["timestamp"].min().isoformat()

    counterparties: list[dict[str, Any]] = []
    if not classified.empty:
        external = classified[~classified["classification"].astype(str).eq("protocol")]
        if not external.empty:
            table = (
                external.groupby(["counterparty", "direction", "classification"])["amount"]
                .agg(["sum", "count"]).reset_index()
                .sort_values("sum", ascending=False).head(int(top_counterparties))
            )
            counterparties = [
                {
                    "counterparty": str(row["counterparty"]),
                    "direction": str(row["direction"]),
                    "classification": str(row["classification"]),
                    "amount": float(row["sum"]),
                    "transfers": int(row["count"]),
                }
                for _, row in table.iterrows()
            ]

    return {
        "wallet": wallet,
        "complete": bool(complete),
        "contracts": per_contract,
        "n_transfers": int(len(classified)),
        "first_transfer_at": first_transfer,
        "summary": summary,
        "counterparties": counterparties,
        "peak_external_exposure": float(ocf.peak_external_exposure(classified)),
        "peak_external_exposure_high": float(ocf.peak_external_exposure(classified, include_ambiguous=True)),
        "note": (
            "Complete collateral transfer history."
            if complete else
            f"Bounded scan: at most {int(page_budget)} pages of {int(page_size)} transfers per "
            "contract were read. Totals are lower bounds; the first-transfer date is exact "
            "for the contracts that answered."
        ),
    }
