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

Two units questions decide whether any of this is money at all, and both are
answered here rather than left to the caller: only collateral contracts are
summed (a raw log scan returns every token that ever touched the wallet, and
one foreign 18-decimal token read with USDC's 6 decimals is a twelve-order-of-
magnitude error), and a transfer is identified by its log position rather than
by its payload, so two equal transfers inside one batched payout stay two.
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

# Polymarket migrated its trading collateral from USDC to pUSD in April 2026.
# A USDC-only ledger therefore goes silent mid-2026 while trading continues, and
# the missing volume looks like an unexplained profit gap. Any full accounting of
# a wallet spanning that date has to read both currencies.
PUSD_CONTRACT = "0xc011a7e12a19f7b1f670d46f03b03f3342e82dfb"  # CollateralToken
PUSD_MIGRATION_DATE = "2026-04-28"
COLLATERAL_CONTRACTS: tuple[str, ...] = USDC_CONTRACTS + (PUSD_CONTRACT,)

# Protocol addresses whose transfers are trading mechanics, not external funding.
# The CTF exchange and the conditional-token contract settle, split and merge.
# WrappedCollateral is the single biggest trap: a heavy wallet receives USDC from
# it on every winning settlement (tens of thousands of transfers), so leaving it
# out makes trading proceeds masquerade as deposits and inflates funding by the
# entire volume. Identified via Etherscan getsourcecode; contract names in comments.
PROTOCOL_ADDRESSES: frozenset[str] = frozenset({
    "0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e",  # CTF Exchange
    "0xc5d563a36ae78145c45a50134d48a1215220f80a",  # NegRisk CTF Exchange
    "0x4d97dcd97ec945f40cf65f87097ace5ea0476045",  # Conditional Tokens
    "0x3a3bd7bb9528e159577f7c2e685cc81a765002e2",  # WrappedCollateral (settlement payouts)
    "0xd91e80cf2e7be2e162c6513ced06f1dd0da35296",  # NegRisk Adapter
    "0xada2005600dec949baf300f4c6120000bdb6eaab",  # NegRisk CTF Collateral Adapter
    "0xc417fd8e9661c0d2120b64a04bb3278c17e99db1",  # pUSD reserve (holds the USDC backing)
    "0xc011a7e12a19f7b1f670d46f03b03f3342e82dfb",  # pUSD CollateralToken (mint/redeem)
    "0x0000000000000000000000000000000000000000",  # mint / burn
})

# Cross-chain bridge / relay contracts. Transfers here ARE external funding
# movements — this wallet family funds and withdraws over Relay rather than by
# plain wallet-to-wallet USDC, so these are the closest thing to deposits.
BRIDGE_ADDRESSES: frozenset[str] = frozenset({
    "0x4cd00e387622c35bddb9b4c962c136462338bc31",  # RelayDepository (withdrawals out)
    "0xc417fd8e9661c0d2120b64a04bb3278c17e99db1",  # ERC1967Proxy (deposits in)
})

# Addresses both lists claim. ``0xc417fd8e…`` is the case that motivated this:
# it was read once as the pUSD reserve (trading mechanics, excluded from
# funding) and once as the deposit proxy (funding, included). Both readings
# come from the same generic ERC1967Proxy source, and a contract can genuinely
# do both. Silently letting ``PROTOCOL_ADDRESSES`` win booked every deposit
# through that route as protocol traffic, so ``deposits_external`` and
# ``peak_external_exposure`` answered 0 for a wallet that had been funded.
# These transfers now get their own bucket and the funding figure becomes the
# range the module docstring always promised, instead of one of its two ends.
AMBIGUOUS_ADDRESSES: frozenset[str] = PROTOCOL_ADDRESSES & BRIDGE_ADDRESSES

#: Decimals per collateral contract. Both USDC deployments are 6 (verified via
#: the token contracts). pUSD is carried but not pinned here: no source in this
#: repo states its decimals, so its rows are flagged ``decimals_assumed`` and
#: counted rather than quietly scaled by a guessed exponent.
TOKEN_DECIMALS: dict[str, int] = {contract: USDC_DECIMALS for contract in USDC_CONTRACTS}


def topic_address(address: str) -> str:
    """Left-pad a 20-byte address into a 32-byte log topic."""
    clean = str(address or "").lower().removeprefix("0x")
    return "0x" + clean.rjust(64, "0")


def address_from_topic(topic: Any) -> str:
    """Recover the 20-byte address from a padded 32-byte topic."""
    text = str(topic or "").lower().removeprefix("0x")
    return "0x" + text[-40:] if len(text) >= 40 else ""


def _decimals_for(contract: str, decimals: int | Mapping[str, int]) -> int | None:
    """Decimals for one contract, or None when the row must be dropped.

    A scalar applies to every contract (the old behaviour, kept for callers that
    fetched a single token). A mapping is the safe mode: a contract that is not
    a known collateral contract returns None, because decoding a foreign token
    with USDC's exponent turns 1 WETH into a $1,000,000,000,000 deposit.
    """

    if not isinstance(decimals, Mapping):
        return int(decimals)
    known = decimals.get(contract)
    if known is not None:
        return int(known)
    return USDC_DECIMALS if contract in COLLATERAL_CONTRACTS else None


def decode_transfer_log(
    log: Mapping[str, Any], decimals: int | Mapping[str, int] = USDC_DECIMALS
) -> dict[str, Any] | None:
    """One ``eth_getLogs`` entry -> {block, log_index, tx, contract, …, amount}.

    Returns None for anything that is not a well-formed Transfer, so a malformed
    entry drops out of the sample instead of poisoning a sum. ``log_index`` rides
    along because it is the only field that separates two identical transfers in
    one transaction; without it a batched settlement paying the same amount twice
    collapses into one row and the ledger silently loses half of it.
    """

    topics = list(log.get("topics") or [])
    if len(topics) < 3 or str(topics[0]).lower() != TRANSFER_TOPIC:
        return None
    raw = str(log.get("data") or "0x")
    contract = str(log.get("address") or "").lower()
    exponent = _decimals_for(contract, decimals)
    if exponent is None:
        return None
    try:
        value = int(raw, 16)
        block = int(str(log.get("blockNumber") or "0x0"), 16)
    except (TypeError, ValueError):
        return None
    raw_index = log.get("logIndex", log.get("log_index"))
    try:
        log_index = int(str(raw_index), 16) if isinstance(raw_index, str) else int(raw_index)
    except (TypeError, ValueError):
        log_index = -1
    return {
        "block": block,
        "log_index": log_index,
        "tx": str(log.get("transactionHash") or ""),
        "contract": contract,
        "sender": address_from_topic(topics[1]),
        "recipient": address_from_topic(topics[2]),
        "amount": value / (10 ** exponent),
        "decimals_assumed": isinstance(decimals, Mapping) and contract not in decimals,
    }


TRANSFER_COLUMNS = ["block", "log_index", "tx", "contract", "sender", "recipient",
                    "amount", "decimals_assumed"]


def decode_transfer_logs(
    logs: Iterable[Mapping[str, Any]], decimals: int | Mapping[str, int] = USDC_DECIMALS
) -> pd.DataFrame:
    """Decode a batch of Transfer logs, de-duplicated by (tx, log_index).

    The chain identifies a log by its transaction and its position inside it.
    De-duplicating on the payload instead — the same sender, recipient and
    amount — throws away genuine repeated transfers of a batched payout, so the
    position is what decides here. Logs without a usable index (``log_index``
    -1) fall back to the payload key, which is all that can be done for them.
    """

    rows = [decoded for log in logs or [] if (decoded := decode_transfer_log(log, decimals)) is not None]
    if not rows:
        return pd.DataFrame(columns=TRANSFER_COLUMNS)
    frame = pd.DataFrame(rows, columns=TRANSFER_COLUMNS)
    indexed = frame[frame["log_index"] >= 0].drop_duplicates(subset=["tx", "log_index"])
    unindexed = frame[frame["log_index"] < 0].drop_duplicates()
    return pd.concat([indexed, unindexed], ignore_index=True).reset_index(drop=True)


def classify_flows(transfers: pd.DataFrame, wallet: str,
                   protocol: frozenset[str] = PROTOCOL_ADDRESSES,
                   contracts: Iterable[str] | None = COLLATERAL_CONTRACTS) -> pd.DataFrame:
    """Label each transfer as in/out and as protocol, ambiguous or external.

    Protocol transfers are settlement and merge proceeds moving between the wallet
    and Polymarket's own contracts. Counting those as deposits would inflate
    funding by the entire trading volume, which is exactly the mistake that makes
    naive on-chain "deposit" figures useless.

    ``contracts`` restricts the frame to the collateral tokens whose unit is a
    dollar. The raw scan asks the node for every Transfer that touches the
    wallet, so without this filter an airdropped token lands in the same sum as
    USDC and is read as money. Pass None to keep every contract.

    Counterparties that both address lists claim (``AMBIGUOUS_ADDRESSES``) are
    labelled ``ambiguous`` rather than resolved by list order: they are the
    difference between the low and the high end of the funding range.

    Adds columns: direction (in/out), counterparty, classification, is_protocol.
    """

    columns = ["block", "log_index", "tx", "contract", "sender", "recipient", "amount",
               "direction", "counterparty", "classification", "is_protocol"]
    if transfers is None or transfers.empty:
        return pd.DataFrame(columns=columns)
    target = str(wallet or "").lower()
    frame = transfers.copy()
    if "log_index" not in frame:
        frame["log_index"] = -1
    for column in ("sender", "recipient", "contract"):
        if column in frame:
            frame[column] = frame[column].astype(str).str.lower()
    if contracts is not None and "contract" in frame:
        frame = frame[frame["contract"].isin({str(c).lower() for c in contracts})]
    frame = frame[(frame["sender"] == target) | (frame["recipient"] == target)]
    if frame.empty:
        return pd.DataFrame(columns=columns)
    frame["direction"] = frame["recipient"].eq(target).map({True: "in", False: "out"})
    frame["counterparty"] = frame["sender"].where(frame["direction"].eq("in"), frame["recipient"])
    ambiguous = frame["counterparty"].isin(AMBIGUOUS_ADDRESSES)
    frame["classification"] = "external"
    frame.loc[frame["counterparty"].isin(protocol), "classification"] = "protocol"
    frame.loc[ambiguous, "classification"] = "ambiguous"
    # Kept for callers that only ask "is this trading mechanics": an ambiguous
    # counterparty is not settled either way, so it is not claimed as protocol.
    frame["is_protocol"] = frame["classification"].eq("protocol")
    return frame[columns].reset_index(drop=True)


def flow_summary(flows: pd.DataFrame) -> dict[str, float]:
    """Totals for the funding question, split by protocol vs external counterparty.

    ``net_external`` is deposits minus withdrawals: what the operator actually
    left in the system. It is the denominator a return on capital should use,
    while ``deposits_external`` alone overstates commitment whenever profits were
    cycled back out.
    """

    keys = ["deposits_external", "withdrawals_external", "net_external",
            "deposits_protocol", "withdrawals_protocol",
            "deposits_ambiguous", "withdrawals_ambiguous",
            "net_external_low", "net_external_high", "n_transfers"]
    if flows is None or flows.empty:
        return dict.fromkeys(keys, 0.0)
    amount = pd.to_numeric(flows["amount"], errors="coerce").fillna(0.0)
    incoming = flows["direction"].eq("in")
    if "classification" in flows:
        label = flows["classification"].astype(str)
    else:  # frames from an older classify_flows still carry only the flag
        label = flows["is_protocol"].astype(bool).map({True: "protocol", False: "external"})
    protocol = label.eq("protocol")
    unclear = label.eq("ambiguous")
    external = ~protocol & ~unclear
    deposits = float(amount[incoming & external].sum())
    withdrawals = float(amount[~incoming & external].sum())
    deposits_unclear = float(amount[incoming & unclear].sum())
    withdrawals_unclear = float(amount[~incoming & unclear].sum())
    return {
        "deposits_external": deposits,
        "withdrawals_external": withdrawals,
        "net_external": deposits - withdrawals,
        "deposits_protocol": float(amount[incoming & protocol].sum()),
        "withdrawals_protocol": float(amount[~incoming & protocol].sum()),
        "deposits_ambiguous": deposits_unclear,
        "withdrawals_ambiguous": withdrawals_unclear,
        # The range the docstring promises, as the two consistent readings of
        # the ambiguous counterparties: all of them protocol, or all of them
        # external funding. Anything in between is a mixture nobody verified.
        "net_external_low": min(deposits - withdrawals,
                                deposits + deposits_unclear - withdrawals - withdrawals_unclear),
        "net_external_high": max(deposits - withdrawals,
                                 deposits + deposits_unclear - withdrawals - withdrawals_unclear),
        "n_transfers": float(len(flows)),
    }


def reconcile_ledger(total_in: float, total_out: float, ending_balance: float,
                     reported_profit: float, tolerance: float = 0.02) -> dict[str, Any]:
    """Check a wallet's transfer ledger against the accounting identity.

    For any account: ``ending_balance = net_flow + profit``. If a complete USDC
    ledger disagrees with the platform's reported profit, exactly one of three
    things is true, and the size and sign of the gap says which:

    - the ledger is incomplete (transfers missed, or a non-USDC funding route),
    - the reported profit measures something else (mark-to-market on open
      positions rather than realised cash), or
    - value is held outside this wallet.

    ``residual`` is what the identity cannot explain. A positive residual means
    more money arrived than profit plus deposits can account for.
    """

    net_flow = float(total_in) - float(total_out)
    implied_balance = net_flow + float(reported_profit)
    residual = float(ending_balance) - implied_balance
    scale = max(abs(float(reported_profit)), abs(net_flow), 1.0)
    return {
        "net_flow": net_flow,
        "implied_balance": implied_balance,
        "actual_balance": float(ending_balance),
        "residual": residual,
        "residual_pct_of_profit": residual / float(reported_profit) * 100.0 if reported_profit else None,
        "reconciles": abs(residual) <= tolerance * scale,
    }


def peak_external_exposure(flows: pd.DataFrame, include_ambiguous: bool = False) -> float:
    """Largest cumulative net external funding ever outstanding, in block order.

    This is the tightest honest answer to "how much capital did this operation
    require": the high-water mark of money put in and not yet taken out. Total
    deposits overstate it whenever the operator recycled the same dollars.

    ``include_ambiguous`` gives the other end of the range: with it, transfers
    through counterparties that could be either funding or trading mechanics
    count as funding. Reading only the default end reports zero capital for a
    wallet funded exclusively through such a counterparty, which is how this
    was wrong before.
    """

    if flows is None or flows.empty:
        return 0.0
    if "classification" in flows:
        label = flows["classification"].astype(str)
        keep = label.ne("protocol") if include_ambiguous else label.eq("external")
    else:
        keep = ~flows["is_protocol"].astype(bool)
    external = flows[keep].copy()
    if external.empty:
        return 0.0
    external["signed"] = pd.to_numeric(external["amount"], errors="coerce").fillna(0.0)
    external.loc[external["direction"].ne("in"), "signed"] *= -1
    sort_keys = [k for k in ("block", "log_index") if k in external.columns]
    ordered = external.sort_values(sort_keys)["signed"].cumsum() if sort_keys else external["signed"].cumsum()
    return float(max(ordered.max(), 0.0))
