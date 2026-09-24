# Equal-share paper execution against observed order-book depth

Date: 2026-09-24. Status: implemented and running locally.

## Context and decision

The user requested stopping SwissTony and testing whether the other followed
wallets can be copied at their actual share size after their public fills.
The previous paper engine reused the source price and scaled into USD 1,000
sub-accounts. That cannot measure executable copy capacity.

The explicit `realistic_copy_enabled` mode uses the existing WS and fallback
detectors, fetches the public CLOB book, then walks asks for buys and bids for
sells. The requested quantity equals source shares. Sells cannot short the
paper account. Initial historical holdings are not newly seeded in this mode.
Existing positions/orders remain and are visibly identified as legacy data.

Additional paper cash required by an executed buy is recorded in cash_events
as research_1to1_funding. It counts as contributed capital, never profit.
The legacy sizing/cash settings still apply when this mode is disabled.
Live trading stays disabled; no signing or order submission was added.

## Evidence and boundaries

The book must match the asset, follow the source fill and be at most five
seconds old against local UTC. Fractional source timestamps are retained;
second-only timestamps conservatively require the following second.
HTTP errors, malformed, crossed, stale or missing books produce no fill.
Order minimums and two-decimal requested share precision are respected.

Depth is shadow-consumed persistently by asset, side and price. Only observed
size increases replenish it. Older snapshots and inconsistent snapshots
with the same timestamp are rejected. This underestimates replacement
liquidity of unchanged size, which REST snapshots cannot establish.
Partial fills are final for that source event, like a fill-and-kill attempt.
Unfilled shares are not retried or invented.

HTTP fetching precedes the SQLite writer lock. Identity is rechecked under
BEGIN IMMEDIATE; source/position changes, funding, shadow depth, the full
book evidence and the paper order commit together. Cross-path dedup survives.
Execution coverage values copied shares at the source price so adverse
slippage does not masquerade as coverage above 100%.

This is an observed-depth counterfactual, not a guaranteed exchange fill.
Fees, submission/matching delays, intervening cancellations, counterfactual
market impact and same-size order replacements are not modelled. PnL is
explicitly gross of fees. Latency uses the local clock and is labelled;
source timestamps can have one-second uncertainty.

Reference: [Polymarket order semantics and book constraints](https://docs.polymarket.com/trading/place-orders).

## Positions and operation

`GET /api/copy/positions` reuses the desk access policy and reads source
research snapshots plus current paper holdings without loading the historical
order ledger. It exposes entry prices, shares, marked open PnL, mark source/
timestamp/staleness and the latest execution price, size and latency.
Research names and trader names open this view. Tables initially show 100
positions per wallet and allow loading more; feed caps are disclosed.

The task uses branch codex/copytrading-realistic in
C:/Users/chole/.codex/worktrees/copytrading-realistic/prediction-market-terminal.
It inherited the original uncommitted working state without altering it.
Runtime data remains in C:/Users/chole/Projects/prediction-market-terminal/data.
The prior settings and SwissTony row are backed up there in
copy_realistic_before_20260924.json. SwissTony active=0; nine others active.

Local UI: http://localhost:8788/#copy. The original port 8787 and its working
directory belong to the concurrent session. Do not use its old settings
writer for this experiment; it does not know the new execution mode.

The new daemon runs the worktree's scripts/run_copy_trader.py with the original
project as working directory (so its settings loader reads the shared data).
Arguments: --disable-fast --api-interval 30 --settlement-interval 180
--min-copy-notional 0, with --db/--status-file/--stop-file pointing to the
shared data directory. Restart this version explicitly after a reboot until
integration; the original watchdog still points to the original code.

The preview runs api/server.py from this worktree with COPY_DATA_DIR set to
the shared data directory, API_PORT=8788, COPY_DAEMON=0.

## Verification

204 copy tests, 259 web tests, 28 server tests passed. JS syntax checks,
Python compilation, git diff --check and both copy rendering/browser
harnesses passed. An independent reviewer reproduced and then rechecked
fractional timestamp, snapshot replay and transaction rollback cases.
Graphify was updated locally.

Live verification shortly after startup: one paused and nine active traders,
WS mode started, execution evidence stored, including two complete
8.62-share copies at 0.949 and 0.93 with measured delays of approximately
6.44 and 13.61 seconds. Other attempts were rejected for stale/pre-fill
books. These are observations, not a latency guarantee or profitability result.
