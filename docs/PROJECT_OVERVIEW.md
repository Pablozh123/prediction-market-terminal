# Project overview — Prediction Market Terminal

Last updated 2026-08-07 · 1,370 unit tests green · local at http://127.0.0.1:8503

This document is **self-contained**: without further context it describes what
the product is, what was built, how it works technically, where the data
boundaries are, what strategy sits behind it and which decisions are open.
Written for anyone picking the project up cold.

> Legal framing: a lawful data and analysis product over **public** Polymarket
> and Kalshi data. Paper only, no custody, no live trading. Every legal topic
> in the planning documents is compliance research, and none of it is acted on
> without a lawyer.

---

## 1. What the product is

A **prediction-market intelligence terminal** for Polymarket and Kalshi: market
discovery, trader and wallet research, live flow, whale and insider risk
screening, backtesting, verified track records, alerts, tracking, portfolio
research and **paper-only** copy-trading — plus the microstructure research
that runs on the recorded data.

**Positioning:** not another whale feed. The market is full of Polymarket-only
clones built on mathematically wrong leaderboards and insider-copy hype. The
differentiators are **honesty, computational correctness, cross-venue breadth
and a research posture**. Details:
[DIFFERENTIATION_STRATEGY.md](DIFFERENTIATION_STRATEGY.md).

---

## 2. Stack and architecture

- **Runtime:** Python 3.12 or newer. CI runs 3.12 and 3.13; the container image
  ships 3.13.
- **Interfaces:** a Streamlit monolith `prediction_terminal.py` holding all
  workspaces, and a second frontend under `web/` (plain ES modules) served by
  the read-only JSON bridge in `api/server.py`.
- **Data and analytics:** `pandas`, `plotly`, `networkx` (Louvain clustering),
  `requests`, `dnspython`, `websocket-client`.
- **Streamlit-free logic in `app/`**, testable and reused by the background
  scripts: `backtester.py`, `suspicion.py`, `track_record.py`, `signals.py`,
  `venue_fees.py`, `scorecard.py`, `app_settings.py`, `authz.py`, `notify.py`,
  `copy_follow.py`, `copy_fidelity.py`, `filters.py`, `format.py`.
- **Source clients** in `src/prediction_markets.py` (Polymarket Gamma, Data and
  CLOB; Kalshi) plus `src/copy_trading.py` (SQLite paper engine and on-chain
  reads), and the recorders `book_recorder.py`, `book_stream.py`,
  `kalshi_recorder.py`, `kalshi_stream.py`.
- **Design system:** a lime accent `#C8F542` on a dark background, serif
  headlines, monospaced data, sans body; CSS in `inject_css()`.
- **Caching:** `@st.cache_data` throughout with TTLs of 30 to 900 seconds, so
  origin API load is independent of visitor count — single-digit percentages of
  the documented limits even at 10,000 visitors a day.
- **Verification:** `unittest` (1,370 tests), ruff in CI, a Playwright visual
  smoke (`scripts/visual_smoke.py`), Streamlit AppTest headless, and a
  Node-driven render test for the web frontend
  (`tests/test_web_leerzustand.py`).

---

## 3. Workspaces

| Workspace | What it does |
|---|---|
| **Overview** | Landing page: hero, live badge, marquee ticker including the volume-anomaly item. |
| **Search** | Command palette: global search across markets, traders, trades, news and alerts, fed by `build_monitor_signals`. |
| **Markets** | Table, cards and calendar; highlights (volume anomaly by ratio, big movers, ending soon); a "who is trading" quick view across both venues with whale prints and top wallets. |
| **Traders** | Polymarket leaderboard, top-three podium, smart-score ranking, category chips, speed traders, insider-picks feed, and on-demand enrichment (positions, win rates, balances) from public wallet data. |
| **Track** | Tracked markets and wallets, live feed, import, action buttons. |
| **Live Trades** | Real-time trade tape across both venues with **real** market titles through ticker enrichment, flow chart, wallet and market aggregation. |
| **Wallets** | Wallet profile: positions, PnL curve and calendar, activity, first funding, account age, and the **verified track-record panel** (§4.3). |
| **Backtester** | Wallet replay, copy or fade, four sizing modes, exposure cap, mid-window resolutions, best-sizing simulation drawn into the chart (§4.1). |
| **Copy Trade** | Paper-copy command centre, daemon status, sub-accounts, honest PnL. |
| **Whale Flow** | Large-print scanner, wallet aggregation, outcome bias, track actions. |
| **Suspicious** | Insider risk screen (§4.2): category-aware event and wallet scores, fresh-wallet and coordinated clusters, and a Louvain co-trading network with click-to-isolate. |
| **Cross-Venue** | Price-gap finder between the two venues. |
| **Monitor** | Signal scanner (fast movers, volume anomaly, whale prints, tight spreads, holder concentration, endings, watched) plus saved alert rules and Telegram delivery. |
| **Resolved** | Closed-market archive, accuracy, final yes prices, CSV export. |
| **Portfolio** | Research portfolio, copy portfolio, exposure, cash events, paper history, watchlist. |
| **Settings** | Data limits, backtester defaults, Telegram config, copy-daemon start and stop. |

Most pages accept URL query filters, for example
`/markets?q=bitcoin&probMin=0.05`, `/live-trades?side=buy&minNotional=2500`,
`/traders?bot=true`.

---

## 4. Core engines

### 4.1 Backtester — `app/backtester.py`

Streamlit-free with injectable fetchers. Replays a wallet's trades over 7, 30
or 90 days. `BacktestConfig` carries the sizing mode (fixed, percent, mirror,
portfolio share, Kelly), stake value, cap, slippage, strategy (copy or fade,
where fade buys the opposite side at 1−p), `max_exposure_pct` and
`trader_portfolio_value`.

**Fees follow the venue.** The engine charges Polymarket's own curve —
`fee = shares · rate · p · (1 − p)`, which works out to `stake · rate · (1 − p)`
and therefore depends on the price: about 250 bps at 0.50 and about 50 bps at
0.90. A flat rate stays reachable as `fee_model="flat"` for comparison. On 90
days of a real wallet the switch moved fees from $49.90 to $646.70 and the
return from −3.21% to −5.41%, which is how much a flat 20 bps was flattering
the result.

`replay()` with `schedule_resolution` and `settle_due` recycles cash and
exposure on mid-window resolutions. `strategy_comparison` simulates which
sizing would have been best and draws it into the equity chart. Curves stay
honest: for hyperactive wallets the window shrinks against the API cap, and the
interface says so instead of hiding it.

### 4.2 Insider and suspicion layer — `app/suspicion.py`

Event and wallet insider scores from whale flow, banded at 40, 55 and 70.
**Category context** (`classify_insider_context`) excludes sports odds and
weather **entirely** — game results and weather models cannot be traded on
early — damps crypto and market prices behind a toggle, and focuses politics,
geopolitics, awards and corporate events. Parent event titles from Gamma give
neutral sub-market names. Bonuses for fresh-wallet clusters and coordinated
clusters in a five-minute window.

The **Louvain co-trading network** (`co_trading_network`, `networkx`,
`seed=42`) draws an edge where two wallets took the same side of at least
`min_shared` markets with at least $10k of paired volume, then lays out islands
with click-to-isolate and plain-language cluster stories. Kalshi stays
event-level, because no wallet identities are published; the wallet-level logic
skips those rows and the interface explains why.

### 4.3 Track-record engine — `app/track_record.py`

The core trust differentiator. Naive leaderboards mislead in four ways, and
each is corrected here with the naive figure shown next to the corrected one:

1. **NegRisk leg netting** — `market_records()` nets per condition id and
   `event_records()` per event slug. Naive tools count every outcome leg
   separately, inflating win rates by up to 2×.
2. **Settled-only PnL** — real realised PnL per resolved market.
3. **Wash and farmer flag** — high volume with roughly zero edge per dollar.
4. **Survivorship** — a sample gate (at least 10 markets and 14 days), profit
   concentration for one-hit wonders, a Sharpe-like `risk_adjusted` figure, and
   a composite 0–100 mapped to grades A–F.

**The real win rate and its data boundary, which is central:** Polymarket's
`/closed-positions` defaults to the **top 50 winners**, sorted by PnL, hard
capped at 50 with offset ignored — so naively every wallet looks perfect. The
fix is `get_polymarket_resolved_positions()`, which fetches **both sort
directions** (winners descending, losers ascending) and dedupes by market key
and outcome. For **normal wallets** (50 or fewer per side) that is complete and
the win rate is real. For **hyperactive wallets** (more than 50 wins *and* more
than 50 losses) it sets `capped=True` and the interface shows an "extremes
only" badge instead of a fabricated number: the middle of such a distribution
is simply not reachable through the REST feeds. The complete answer for every
wallet is **on-chain indexing**, since every trade sits on Polygon with no cap.
That remains an open scaling step, see §7.

### 4.4 WebSocket fast copy — `src/copy_trading.py`

Polling on-chain `OrderFilled` was the slowest detection available, since the
log lands about two seconds after the off-chain match. Detection now runs on
the **RTDS WebSocket** (a global firehose, because the upstream wallet filter
is broken, with `proxyWallet` matched client-side). `RtdsTradeListener` runs the
socket and `WsApplyWorker` books in a dedicated thread with its own SQLite
connection — the first version drained in the main loop and measured a
105-second median, worse than the 30-second API fallback it was supposed to
beat. On-chain polling stays as reconciliation, and `_fill_already_recorded()`
dedupes across paths on wallet, transaction, asset and side, deliberately not
on timestamp or price, which drift between match time and block time.
`reconcile_backoff_seconds` backs off on RPC 429 streaks.

### 4.5 Signals and alerts — `app/signals.py`

`build_monitor_signals` produces fast movers, volume anomalies (hourly volume
at least three times the 24-hour average with at least $10k daily), whale
prints, tight spreads, holder concentration, endings and watched markets. The
Monitor page and the Telegram scanner
(`scripts/run_alert_scanner.py`, with dedupe state and a stop file) consume the
same function.

---

## 5. Data sources and their limits

- **Polymarket Gamma** (markets, metadata, categories), **Data API** (trades,
  positions, activity, leaderboard), **CLOB** (order book, prices). Public, no
  key. Limits: 15,000 req/10 s globally, Gamma 4,000/10 s, Data API 1,000/10 s
  (trades 200), CLOB 9,000/10 s. Throttling surfaces as queueing, not errors.
- **Known caps and traps:**
  - `/activity` rejects offset plus limit above roughly 3000, so
    `fetch_window_trades` caps there. Offset otherwise paginates cleanly.
  - `/closed-positions` **caps at about 50 rows, ignores offset** and defaults
    to winners; the sort direction flips which 50 you get, hence the union
    trick in §4.3.
  - Losers that expire worthless produce **no redeem event** and are therefore
    invisible in `/activity`.
- **Kalshi** (trade-api/v2): markets and trades, **no wallet identities**, so
  event-level only. `get_kalshi_markets(tickers=...)` enriches trade tickers
  with real titles, categories and end times.
- **On-chain (Polygon)** — the complete lane: `OrderFilled` logs (the decoder
  exists) and redeem events, with no cap. Needed for complete track records.
  Currently used for copy detection only, not for analytics.
- **Test wallet:** `0x204f72f35326db932158cba6adff0b9a1da95e14`, roughly 3000
  trades a day, which is the worst case for every cap above.

---

## 6. Operations, deployment, security

- **Local:** three Windows scheduled tasks (terminal on 8503, copy daemon,
  alert scanner) registered by `scripts/install_autostart.ps1`.
- **Production (ready):** `Dockerfile` (non-root, healthcheck, hardened
  Streamlit flags), `docker-compose.yml` (terminal, alert scanner, Caddy),
  `deploy/Caddyfile` (automatic TLS, security headers). Secrets come from the
  environment; `.env` and `.streamlit/secrets.toml` are gitignored.
- **Auth:** `st.login()` with Google OIDC, Settings failing closed behind an
  email allowlist (`app/authz.py`); a complete no-op without secrets.
- **Cost of running publicly:** roughly CHF 6–8 per month. Details:
  [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md).

---

## 7. Open decisions and roadmap

**Buildable now, no legal exposure:**

- **On-chain indexer and complete track records** — the "complete for every
  wallet" version (§4.3, §5). Either a Polygon log scan of our own, the decoder
  already exists, or a hosted subgraph. Solves the 50-row cap for whales.
  **The next open product decision** (a free RPC is slow; a paid RPC or
  subgraph runs $0–50 a month).
- Speed steps 2 and 3 (harden execution, co-locate the worker) — relevant only
  with live execution.
- Read-only wallet connect (a React component with wagmi/WalletConnect in an
  iframe, plus SIWE), two to four days. Streamlit cannot host a native web3
  frontend, so the iframe component is required.
- Further differentiating features from
  [DIFFERENTIATION_STRATEGY.md](DIFFERENTIATION_STRATEGY.md): cross-venue
  reconciled PnL and tax, copy-decay honesty, the calibration dashboard, and
  resolution or dispute alerts.
- Crypto payment after launch; fiat first.

**Strategic decision, not without a lawyer:**

- **Live-money copy-trading** — the non-custodial architecture is designed
  (builder programme, separate maker and signer fields), but **BGS Art. 130**
  (providing technical means for gambling blocked by the regulator, up to three
  to five years' imprisonment, with no foreign shield for a Swiss resident)
  makes a legal memo (CHF 5–25k), CH and US geoblocking, execution-only and a
  named entity mandatory before a first live trade. Details:
  [LIVE_COPYTRADING_PLAN.md](LIVE_COPYTRADING_PLAN.md).

**Company and revenue:** private individual → sole proprietorship (first
revenue, a merchant of record for EU VAT) → GmbH from roughly CHF 100k. A
foreign company achieves nothing (personal liability plus a tax trap); the
lever is Swiss geoblocking and no referral links. Details:
[LAUNCH_PLAN.md](LAUNCH_PLAN.md).

---

## 8. Competition, in brief

Table stakes everyone has: whale feed, insider score, leaderboard, copy,
Telegram alerts. Main players: **Unusual Whales** (huge distribution,
Polymarket only, monitoring only), **Verso** (YC, multi-venue terminal),
**Kreo** (copy, under Polymarket audit), **Oddpool** (YC, cross-venue data),
several analytics and copy sites, **Dome** (acquired by Polymarket) and
**Stand**. Consolidation plus a funding wave means time pressure. White space:
a real cross-venue interface, correct verifiable track records, honest copy
decay, tax reconciliation, calibration, non-English, mobile. Full analysis:
[DIFFERENTIATION_STRATEGY.md](DIFFERENTIATION_STRATEGY.md).

---

## 9. Other documents

- [HANDOFF.md](HANDOFF.md) — quick start, conventions and state for continuing
  from any machine.
- [DIFFERENTIATION_STRATEGY.md](DIFFERENTIATION_STRATEGY.md) — competition,
  differentiation, build plan.
- [LAUNCH_PLAN.md](LAUNCH_PLAN.md) — data rights, auth outsourcing, company
  structure.
- [LIVE_COPYTRADING_PLAN.md](LIVE_COPYTRADING_PLAN.md) — wallet connect,
  non-custodial live copy, speed, crypto payment, law.
- [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) — hosting, security, Swiss
  law, API limits, shopping list.
- [research/README.md](research/README.md) — the microstructure studies and
  their reports.

**Repo:** GitHub `Pablozh123/prediction-market-terminal`, default branch
`main`. **Verification:** `python -m unittest discover -s tests -p "test_*.py"`
and `python -m ruff check .`

---

## 10. Research starting points

Questions this document raises that would be worth settling next:

1. **On-chain indexer:** hosted subgraph versus a query platform versus an
   indexer of our own — cost, latency, maintenance and completeness for full
   track records. Solves the 50-row cap.
2. **Cross-venue reconciled PnL and tax** — both venues in one portfolio, with
   a tax-form export.
3. **Calibration layer** — a Brier score and calibration curve per wallet from
   resolved markets, as the researcher and credibility funnel.
4. **Read-only wallet connect** — the concrete Streamlit React component and
   SIWE flow.
5. **Go to market** — target segment, pricing tiers, free funnel.
6. **Legal memo**, only if live copy is ever pursued.
