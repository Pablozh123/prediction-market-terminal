# Spec: multi-trader copy-trading (paper)

Status: draft v2, decisions incorporated. Last updated 2026-08-07.

## 1. Goal and scope

The existing paper copy-trading follows exactly **one** Polymarket wallet. The
goal is to extend it to **several traders**, in two modes:

- **Follow any wallet** (the core function): the user names any Polymarket
  wallet and copies it.
- **A discovery list**: a leaderboard ranked by ROI suggests strong wallets at
  the start, so nobody begins from nothing.

Every followed trader gets its **own simulated account** (a sub-portfolio), so
each can be evaluated fairly and separately.

In scope: Polymarket (on-chain plus public API), paper mode, following any
wallet plus ROI ranking, sub-portfolios, equal allocation, per-trader
reporting. Out of scope: real order routing (`live_trading_enabled` stays
`false`) and Kalshi wallet copy (section 5).

## 2. Decisions taken

1. **Account model:** one pot per trader (sub-portfolio), not shared.
2. **Ranking:** following any wallet is possible; the starting suggestions rank
   by **ROI plus a minimum activity bar**.
3. **Allocation:** equal — every trader starts with the same paper capital.
4. **Migration:** the current target wallet becomes the first trader.

## 3. Current state (`src/copy_trading.py`)

The engine is SQLite-backed and already partly wallet-aware:

- `CopySettings` holds a single `target_wallet`, `copy_scale`,
  `max_order_equity_pct` and `paper_start_cash`, plus dynamic sizing tied to
  that one wallet.
- The `paper_orders` table already carries **`source_wallet`**, so orders are
  attributable per source.
- The `positions` table is a **shared** book, keyed on `asset`.
- One table mirrors the positions of the single target wallet.
- `cash` and wallet stats sit as single values in the `meta` store, and
  `cash_events` has no wallet column.

So sub-portfolios require the **cash and position model to be separated per
wallet**.

## 4. Target architecture

### 4.1 Data model (one sub-portfolio per trader)

New table `traders`, one row per followed wallet:

| Column | Type | Meaning |
|---|---|---|
| `wallet` | TEXT PK | Polymarket proxy wallet |
| `label` | TEXT | Display name |
| `active` | INTEGER | 1 means it is copied |
| `start_cash` | REAL | Starting capital of this sub-account |
| `cash` | REAL | Current cash balance of this sub-account |
| `copy_scale_override` | REAL NULL | Overrides the global `copy_scale` |
| `rank_score` | REAL | Last computed ROI score |
| `added_at` / `updated_at` | TEXT | Timestamps |

Generalisations to the existing schema, so every sub-account is kept
separately:

- `positions` → rekey from `asset` to **`(trader_wallet, asset)`**.
- `cash_events` → add a `trader_wallet` column.
- The single-wallet mirror table → **`source_positions(wallet, asset, …)`**.
- Wallet stats move out of `meta` into
  **`trader_stats(wallet, roi, pnl, win_rate, trades, volume, last_refresh)`**.
- `paper_orders.source_wallet` stays the anchor for orders and attribution.

Total equity is the sum of the sub-account equities.

### 4.2 Following any wallet, and the ROI ranking

- **Following:** a "follow wallet" action, either by entering an address or by
  a button in the leaderboard or wallet analyzer, writes a new row in `traders`
  with its `start_cash` and starts the sync.
- **Ranking (suggestions):** the data source already exists in
  `src/prediction_markets.py` (PnL, win rate, trades, volume). Score primarily
  by **ROI**, since a percentage return measures skill rather than capital
  size, with minimum thresholds against lucky one-offs.
- Suggested thresholds, adjustable: at least 50 closed trades, positive ROI,
  active within the last 30 days.

### 4.3 Allocation and sizing

Equal allocation through **identical starting capital per sub-account**: one
configurable `per_trader_start_cash`, the same for everyone. The benefit is a
common starting line for fair per-trader comparison, and adding or removing a
trader does not disturb the others.

Per order, inside its own sub-account:

```
order_notional = source_notional * effective_copy_scale(trader)
capped by max_order_equity_pct * equity(sub_account)
```

Risk limits per sub-account: a market cap for diversification, and no purchase
when cash is short. The existing dynamic sizing generalises from "tied to the
one wallet" to "per sub-account".

### 4.4 Sync engine

- `sync_copy_trades` and `sync_onchain_copy_trades` iterate over all active
  traders and book into the right sub-account.
- `trade_dedup_key` has to include the wallet — verify, and add it if missing.
- The single-wallet seeding function becomes `seed_source_positions(wallet, …)`.
- `scripts/run_copy_trader.py` reads the wallet list from `traders`
  (`active=1`) instead of a constant.

### 4.5 Interface

- "Follow" and "unfollow" in the leaderboard and the wallet analyzer.
- A copy-trading page with the trader list, sub-account figures (cash, equity,
  ROI), an active switch and the starting-capital setting.
- Reuse the existing filters and components.

### 4.6 Reporting and attribution

Because every trader has its own sub-account, per-trader performance is
directly readable as an equity curve per wallet. A detail drilldown goes
through `paper_orders` by `source_wallet`.

## 5. The Kalshi boundary

Kalshi's public feeds expose **no** wallet or trader identities, so copying a
trader from public data is impossible there in principle. What remains is the
existing cross-venue signal, the price gap between the two venues. This is
worth documenting as a data boundary rather than working around.

## 6. Migration

The current target wallet becomes the **first trader**: a row in `traders` with
its own `start_cash`, the existing mirror positions moved to
`source_positions`, the existing `paper_orders` (which already carry
`source_wallet`) attributed to its sub-account, and cash and equity set
consistently. The existing history is preserved.

## 7. Implementation steps, in order

1. Schema migration: `traders`, `source_positions`, `trader_stats`; add
   `trader_wallet` to `positions` and `cash_events`; extend `init_db` with a
   migration path for the existing wallet.
2. Move the engine from one `target_wallet` to the active trader list with
   sub-accounts.
3. Sizing and cash per sub-account; generalise the dynamic sizing.
4. ROI ranking and thresholds for the suggestion list.
5. Interface: follow and unfollow, sub-account reporting, starting capital.
6. Move `run_copy_trader.py` to multi-wallet.
7. Extend `tests/test_copy_trading.py` (multi-wallet dedup, sub-account
   booking, ROI ranking, migration).

After each step: compile, run the tests, commit.

## 8. Relation to the research question

Separate sub-accounts per trader produce directly comparable equity curves,
which is empirical material for the question behind the research: are there
persistent, copyable excess returns on Polymarket, or does the advantage of
profitable wallets disappear once it is followed (informational efficiency)?
The Kalshi boundary in section 5 is a methodological limitation that can be
stated cleanly rather than hidden.
