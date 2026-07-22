"""External cash flows of a wallet, reconstructed from ERC-20 Transfer logs.

Polymarket's profit figure is trade-based: it nets cost basis against payouts and
never sees a deposit. To answer "what did this wallet put in, and what did it take
out" you have to read the chain. This module holds the decoding and aggregation
so the network scan stays a thin script and the arithmetic is testable.

Deposits and withdrawals are USDC transfers into and out of the proxy wallet. The
caveat that matters for interpretation: a proxy wallet also receives USDC from
market settlements and merges, which are *internal* to trading rather than
external funding. Counterparty classification is therefore part of the result,
not an afterthought, and the headline number is always a range.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import pandas as pd

# keccak("Transfer(address,address,uint256)")
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

# Polygon USDC. Both are 6-decimal.
USDC_CONTRACTS: tuple[str, ...] = (
    "0x2791bca1f2de4661ed88a30c99a7a9449aa84174",  # USDC.e (bridged)
    "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359",  # native USDC
)
USDC_DECIMALS = 6

# Protocol addresses whose transfers are trading mechanics, not external funding.
# The CTF exchange and the conditional-token contract settle, split and merge.
PROTOCOL_ADDRESSES: frozenset[str] = frozenset({
    "0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e",  # CTF Exchange
    "0xc5d563a36ae78145c45a50134d48a1215220f80a",  # NegRisk CTF Exchange
    "0x4d97dcd97ec945f40cf65f87097ace5ea0476045",  # Conditional Tokens
    "0x0000000000000000000000000000000000000000",  # mint / burn
})


def topic_address(address: str) -> str:
    """Left-pad a 20-byte address into a 32-byte log topic."""
    clean = str(address or "").lower().removeprefix("0x")
    return "0x" + clean.rjust(64, "0")


def address_from_topic(topic: Any) -> str:
    """Recover the 20-byte address from a padded 32-byte topic."""
    text = str(topic or "").lower().removeprefix("0x")
    return "0x" + text[-40:] if len(text) >= 40 else ""


def decode_transfer_log(log: Mapping[str, Any], decimals: int = USDC_DECIMALS) -> dict[str, Any] | None:
    """One ``eth_getLogs`` entry -> {block, tx, contract, sender, recipient, amount}.

    Returns None for anything that is not a well-formed Transfer, so a malformed
    entry drops out of the sample instead of poisoning a sum.
    """

    topics = list(log.get("topics") or [])
    if len(topics) < 3 or str(topics[0]).lower() != TRANSFER_TOPIC:
        return None
    raw = str(log.get("data") or "0x")
    try:
        value = int(raw, 16)
        block = int(str(log.get("blockNumber") or "0x0"), 16)
    except (TypeError, ValueError):
        return None
    return {
        "block": block,
        "tx": str(log.get("transactionHash") or ""),
        "contract": str(log.get("address") or "").lower(),
        "sender": address_from_topic(topics[1]),
        "recipient": address_from_topic(topics[2]),
        "amount": value / (10 ** decimals),
    }


def decode_transfer_logs(logs: Iterable[Mapping[str, Any]], decimals: int = USDC_DECIMALS) -> pd.DataFrame:
    rows = [decoded for log in logs or [] if (decoded := decode_transfer_log(log, decimals)) is not None]
    columns = ["block", "tx", "contract", "sender", "recipient", "amount"]
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows, columns=columns).drop_duplicates().reset_index(drop=True)


def classify_flows(transfers: pd.DataFrame, wallet: str,
                   protocol: frozenset[str] = PROTOCOL_ADDRESSES) -> pd.DataFrame:
    """Label each transfer as in/out and as protocol or external.

    Protocol transfers are settlement and merge proceeds moving between the wallet
    and Polymarket's own contracts. Counting those as deposits would inflate
    funding by the entire trading volume, which is exactly the mistake that makes
    naive on-chain "deposit" figures useless.

    Adds columns: direction (in/out), counterparty, is_protocol.
    """

    columns = ["block", "tx", "contract", "sender", "recipient", "amount", "direction",
               "counterparty", "is_protocol"]
    if transfers is None or transfers.empty:
        return pd.DataFrame(columns=columns)
    target = str(wallet or "").lower()
    frame = transfers.copy()
    frame["sender"] = frame["sender"].astype(str).str.lower()
    frame["recipient"] = frame["recipient"].astype(str).str.lower()
    frame = frame[(frame["sender"] == target) | (frame["recipient"] == target)]
    if frame.empty:
        return pd.DataFrame(columns=columns)
    frame["direction"] = frame["recipient"].eq(target).map({True: "in", False: "out"})
    frame["counterparty"] = frame["sender"].where(frame["direction"].eq("in"), frame["recipient"])
    frame["is_protocol"] = frame["counterparty"].isin(protocol)
    return frame[columns].reset_index(drop=True)


def flow_summary(flows: pd.DataFrame) -> dict[str, float]:
    """Totals for the funding question, split by protocol vs external counterparty.

    ``net_external`` is deposits minus withdrawals: what the operator actually
    left in the system. It is the denominator a return on capital should use,
    while ``deposits_external`` alone overstates commitment whenever profits were
    cycled back out.
    """

    keys = ["deposits_external", "withdrawals_external", "net_external",
            "deposits_protocol", "withdrawals_protocol", "n_transfers"]
    if flows is None or flows.empty:
        return dict.fromkeys(keys, 0.0)
    amount = pd.to_numeric(flows["amount"], errors="coerce").fillna(0.0)
    incoming = flows["direction"].eq("in")
    protocol = flows["is_protocol"].astype(bool)
    deposits = float(amount[incoming & ~protocol].sum())
    withdrawals = float(amount[~incoming & ~protocol].sum())
    return {
        "deposits_external": deposits,
        "withdrawals_external": withdrawals,
        "net_external": deposits - withdrawals,
        "deposits_protocol": float(amount[incoming & protocol].sum()),
        "withdrawals_protocol": float(amount[~incoming & protocol].sum()),
        "n_transfers": float(len(flows)),
    }


def peak_external_exposure(flows: pd.DataFrame) -> float:
    """Largest cumulative net external funding ever outstanding, in block order.

    This is the tightest honest answer to "how much capital did this operation
    require": the high-water mark of money put in and not yet taken out. Total
    deposits overstate it whenever the operator recycled the same dollars.
    """

    if flows is None or flows.empty:
        return 0.0
    external = flows[~flows["is_protocol"].astype(bool)].copy()
    if external.empty:
        return 0.0
    external["signed"] = pd.to_numeric(external["amount"], errors="coerce").fillna(0.0)
    external.loc[external["direction"].ne("in"), "signed"] *= -1
    ordered = external.sort_values("block")["signed"].cumsum()
    return float(max(ordered.max(), 0.0))
