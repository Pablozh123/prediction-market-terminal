# Handoff — Prediction Market Terminal

Single entry point for continuing this project from another machine.
Last updated 2026-08-18.

> This is a data and analysis product for public Polymarket and Kalshi data.
> The legal sections in the planning documents are compliance research for a
> memo — nothing there is implemented, and nothing should be without a lawyer.

---

## 1. What the project is

A Streamlit research terminal for Polymarket and Kalshi: market discovery,
trader and wallet research, live public flow, whale and insider risk screening,
backtesting, alerts, tracking, portfolio research and **paper-only**
copy-trading, plus the microstructure research that runs on top of it. All data
comes from public APIs. No live trading, no custody, and no order path exists
in this codebase.

- **Stack:** Python 3.12+, Streamlit (monolith `prediction_terminal.py`),
  pandas, plotly, networkx, websocket-client. A second frontend lives under
  `web/` as plain ES modules behind the read-only JSON API in `api/server.py`.
- **Local:** http://127.0.0.1:8503 (Streamlit), http://127.0.0.1:8787 (web).
- **Repo:** GitHub `Pablozh123/prediction-market-terminal`, default branch `main`.
- **Live:** https://marketintel.dev (Cloudflare Pages, static build of `web/`) +
  https://api.marketintel.dev (Railway, `api/server.py`, hosts the paper copy desk).
- **State:** 1,629 unit tests green (`python -m unittest discover -s tests`).

## 2. Quick start on a new machine

```bash
git clone https://github.com/Pablozh123/prediction-market-terminal.git
cd prediction-market-terminal
python -m pip install -r requirements.txt
python -m streamlit run prediction_terminal.py --server.address=127.0.0.1 --server.port=8503
```

On the current development machine only `.venv\Scripts\python.exe` is a real
interpreter (`python` on PATH is the Windows Store stub); every command below
means that one. Keep PowerShell scripts ASCII.

Background runners (optional, paper only):

```bash
python scripts/run_copy_trader.py     # copy daemon: WS detection, on-chain reconciliation, settlement
python scripts/run_alert_scanner.py   # Telegram alert scanner (token via env, see .env.example)
scripts\start_paper_desk.ps1          # Windows: API on 127.0.0.1:8787 + copy daemon, opens #copy
```

Production: `docker compose up -d --build` starts the terminal, the alert
scanner and Caddy. See [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md).

Verification:

```bash
python -m py_compile prediction_terminal.py src/prediction_markets.py src/copy_trading.py
python -m unittest discover -s tests -p "test_*.py"
python scripts/lint_claims.py
python scripts/visual_smoke.py --base-url http://127.0.0.1:8503
```

The web frontend has its own render tests (`tests/test_web_leerzustand.py`),
which drive every page through a fresh module import with and without a
payload. They need Node and skip without it.

## 3. Planning documents

| Doc | Contents |
|---|---|
| [LAUNCH_PLAN.md](LAUNCH_PLAN.md) | Venue terms and limits, auth outsourcing, Swiss company structure, geoblocking |
| [LIVE_COPYTRADING_PLAN.md](LIVE_COPYTRADING_PLAN.md) | Speed (WS over on-chain), wallet connect and SIWE, non-custodial architecture, the legal blocker |
| [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) | Hosting, security checklist, Swiss law, API limits, costs |

## 4. Roadmap

Buildable now, no legal exposure:

1. ✅ **Speed step 1** — WebSocket detection (RTDS `activity/trades`). Done, see §6.
2. ⬜ **Speed step 2** — harden execution: keep-alive HTTPS to the CLOB, cached
   L2 credentials, preloaded tick sizes, FOK orders. Only relevant if live
   execution is ever built.
3. ⬜ **Speed step 3** — co-locate the worker in Dublin or London.
4. ✅ **Auth** — done, see §7: `st.login()` with Google OIDC, Settings fail
   closed behind an email allowlist, no-op without secrets.
5. ⬜ **Read-only wallet connect** — own React component (wagmi/WalletConnect)
   plus SIWE.
6. ⬜ **Crypto payment** — only if asked for after launch. Fiat first.
7. ✅ **Production deploy** — live as marketintel.dev (Cloudflare Pages) +
   api.marketintel.dev (Railway), see §9.1. Imprint / privacy policy and
   geoblocking are still open; the compose + Caddy path in
   PRODUCTION_READINESS.md remains the self-hosted alternative.

Strategic decision, not without a lawyer:

8. ⬜ **Live-money copy-trading** — the non-custodial architecture is designed,
   but Swiss BGS Art. 130 (providing technical means for gambling operations
   blocked by the regulator) carries a custodial sentence, and a Swiss resident
   has no foreign-entity shield. A legal memo, CH and US geoblocking,
   execution-only, and a named entity would all be mandatory before a first
   live trade. The insider screen is positioned as research and warning, not as
   a tail-the-insider product.

## 5. Key files

| File | Purpose |
|---|---|
| `prediction_terminal.py` | Streamlit app, all workspaces and UI |
| `web/`, `api/server.py` | Second frontend (plain ES modules) and its read-only JSON bridge |
| `src/prediction_markets.py` | Public API clients (Polymarket Gamma/Data/CLOB, Kalshi) and analytics |
| `src/copy_trading.py` | SQLite paper-copy engine and WS detection |
| `app/backtester.py` | Streamlit-free backtest engine (copy/fade, four sizing modes, exposure cap) |
| `app/venue_fees.py` | Fee models for both venues; the backtester charges the real curve |
| `app/suspicion.py` | Insider-risk scoring, clusters, Louvain co-trading network |
| `app/signals.py` | Monitor signal and rule logic (shared with the scanner) |
| `app/app_settings.py` | Persisted settings with env-var overrides for secrets |
| `app/authz.py` | Streamlit-free admin-gate logic (fail closed) |
| `app/copy_daemon.py` | The copy daemon loop (`scripts/run_copy_trader.py` is a thin CLI over it; the API runs it in-process with `COPY_DAEMON=1`) |
| `app/copy_admin.py` | Paper copy desk: write gate (loopback or `COPY_ADMIN_TOKEN`), follow + per-wallet baseline seed, settings, overview, daemon status, one-shot sync, `ensure_desk` |
| `app/wallet_book.py` | Risk cards: what a flagged wallet holds in the flagged market now (hedge vs new bet), `/api/risk/book` |
| `app/wallet_similar.py` | Wallet page: top holders of the wallet's largest open markets, `/api/wallet/{w}/similar` |
| `web/js/pages/copy_page.js` | Copy desk page (traders, sizing modes, orders with kinds, settings) |
| `web/js/pages/wallet_page.js`, `web/js/treemap.js` | Wallet page (identity strip, KPI strip, aside, tabs, squarified positions treemap, Risk and Similar tabs) |
| `scripts/run_copy_trader.py` | Copy daemon CLI |
| `scripts/run_alert_scanner.py` | Alert scanner with Telegram delivery |
| `Dockerfile`, `docker-compose.yml`, `deploy/Caddyfile` | Production deploy |

## 6. WebSocket fast copy

**Why:** polling on-chain `OrderFilled` logs was the slowest possible
detection — the log appears about two seconds after the off-chain match. The
RTDS WebSocket sees the match immediately.

- `src/copy_trading.py`: `RTDS_WS_URL`, `rtds_subscribe_payload()` (empty
  filter, because the upstream wallet filter is broken), `decode_rtds_trade()`
  (matches `proxyWallet` client-side and normalises to the same shape the
  on-chain decoder produces), `RtdsTradeListener`, `apply_ws_trades()`.
- **Cross-path dedup:** `_fill_already_recorded()` keys on stable identity
  (wallet, tx, asset, side) and deliberately not on timestamp or price, which
  drift between the WS match time and the block time. The slower on-chain
  reconciliation therefore cannot double-copy a fill the socket already took.
- **`WsApplyWorker`:** the first design drained the socket in the main loop,
  where blocking reconciliation syncs queued it up behind rate-limited RPC
  calls. Measured live, the "fast" path ran at a 105-second median and the
  30-second API fallback overtook it. A dedicated thread with its own SQLite
  connection now drains every 0.5s; WAL plus a 30s busy timeout make the
  cross-thread writes safe, and the dedup keys keep both paths idempotent.
- `reconcile_backoff_seconds` backs the on-chain sweep off exponentially on RPC
  429 streaks (30s to a 600s cap) instead of blocking every 30 seconds.

## 7. Auth and admin gating

**Why:** before any public deployment the Settings page (data controls,
Telegram secrets, daemon control) has to be protected.

- **Without `.streamlit/secrets.toml [auth]`** everything runs as before: no
  login surface, Settings open, local research mode. Completely no-op.
- **With `[auth]` secrets** the sidebar offers Google sign-in and the Settings
  page **fails closed** — only signed-in accounts on the admin allowlist
  (`ADMIN_EMAILS` env takes precedence over `[admin].emails`) can reach it.
  Every research workspace stays public. Signed in but not allowlisted is
  refused as well.
- The logic is Streamlit-free in `app/authz.py`, with the gate itself asserted
  in `tests/test_app_smoke.py`.

## 8. Conventions

- Logic stays Streamlit-free under `app/` and `src/`; the monolith holds only
  `render_*` and `page_*` functions. Scripts under `scripts/` import the same
  modules.
- Tests are stdlib `unittest` in `tests/test_<module>.py`. Every new logic
  module gets its own test file.
- Money in dollars, prices and probabilities in (0, 1), `market_key` is the
  Polymarket `conditionId`.
- Settings live in `app/app_settings.py` (JSON-backed, env wins). Secrets never
  enter the repository.
- Every score-bearing display carries its sample size, confidence interval and
  snapshot timestamp. `data/claims.yaml` lists the phrasings that are not
  allowed, and `scripts/lint_claims.py` enforces it in CI.

## 9. Operations

### 9.1 Deploying the live site

Two hosts, two mechanisms — this cost a session once, so it is spelled out:

- **marketintel.dev** (Cloudflare Pages) rebuilds from a push to `origin/main`
  within a few minutes (`scripts/build_static_site.py --api-base
  https://api.marketintel.dev` writes `dist/`).
- **api.marketintel.dev** (Railway project `victorious-strength`, service
  `attractive-truth`, Dockerfile) does **not** follow GitHub. After the push run
  `railway up --detach` from the repo root and poll a new route until it
  answers (build ~1 min; the in-process copy daemon pauses for that minute).
  `railway up` uploads the working tree minus `.gitignore` — `data/` never
  ships. Under Git Bash prefix `MSYS_NO_PATHCONV=1` when setting a variable
  whose value starts with `/` (`/data/...` was mangled to `C:/Program Files/Git/data/...`).
- Railway variables (read with `railway variables`, never in the repo):
  `COPY_DATA_DIR=/data/copy_desk` (the mounted volume `attractive-truth-volume`
  at `/data`, 500 MB), `COPY_DAEMON=1`, `COPY_ADMIN_TOKEN=<secret>`,
  `CORS_ORIGINS=https://marketintel.dev,https://www.marketintel.dev`,
  `API_HOST=0.0.0.0`, `PORT=8787`. Optional `COPY_DESK_PRIVATE=1` gates reads too.
- Frontend-only changes need only the push (Pages); anything under `api/`,
  `app/`, `src/` needs `railway up` as well.

### 9.2 The paper copy desk (live)

- Page: https://marketintel.dev/#copy. Reads are public; writes need the admin
  token pasted once into the page (kept in that browser's localStorage, sent as
  `X-Admin-Token`). Locally (`127.0.0.1:8787`) writes are open from loopback.
- Books: `copy_trading.sqlite`, `copy_settings.json`, `copy_trader_status.json`
  in `COPY_DATA_DIR`. A fresh desk starts with the migration's Swisstony row
  **paused**; nothing is copied until a wallet is followed. Follow = row +
  per-wallet baseline (positions mirrored, recent trades marked observed,
  cutoff = newest of them); resume re-seeds.
- Sizing modes on the Settings tab map onto `CopySettings`: same share of
  account (dynamic sizing on, order = his notional × your equity / his equity ×
  multiplier), fixed % of his trade (dynamic off, `copy_scale`), dollar for
  dollar (dynamic off, `copy_scale = 1`). Settings are global — the sub-accounts
  are the comparison, so every trader runs the same rules.
- Orders carry a kind (BUY / SELL / MERGE / REDEEM / RESOLUTION), a sentence and
  the source wallet's mirrored YES/NO book; a MERGE is both sides handed back
  for cash, not a bet on the printed outcome.
- Local desk on the dev machine (`scripts\start_paper_desk.ps1`) has its own,
  separate books under `data/`; it was stopped so there is one desk.

### 9.3 Machine tasks

- Three Windows scheduled tasks (registered by `scripts/install_autostart.ps1`):
  the terminal on 8503, the copy daemon, the alert scanner. Not registered on
  the current dev machine; the scripts prefer `.venv\Scripts\python.exe`.
- Secrets come from the environment (`.env`, gitignored):
  `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` override `data/app_settings.json`
  and are never written back.
- Runtime data lives in `data/` (gitignored): settings, `copy_trading.sqlite`,
  watchlists, scanner state.

## 10. Open points and gotchas

- The Polymarket data API rejects `/activity` with offset plus limit above
  about 3000, so `fetch_window_trades` caps there. For hyperactive wallets
  (~3000 trades a day) a "30 day" backtest window therefore shrinks to hours.
  That is honest and the UI says so.
- Kalshi publishes no wallet identities, so wallet-level logic skips those rows
  and the UI states it rather than silently dropping them.
- **Copy-trading economics:** the default target wallet never sells — 487 buys
  and 0 sells in 45 minutes — because it recycles through resolution, redeem
  and merge and stays roughly fully invested. A copy is therefore structurally
  almost fully deployed and cash only returns through settlements.
  `auto_top_up_enabled` defaults to **off**; it had quietly injected
  13 × $1000 before that changed. Contributions are tracked separately from
  trading PnL so the equity curve cannot flatter itself.
- **Copy fidelity:** `dynamic_scale_max` defaults to 0, meaning uncapped — the
  old 1% cap cost about 21% fidelity against a neutral ratio of 1.27%.
  `cash_throttle_pct` at 0.25 lets one order spend at most a quarter of the
  remaining cash, so a cash drought shrinks every copy evenly instead of
  skipping later trades entirely. Every order stores `desired_notional`, and
  `app/copy_fidelity.py` turns that into config fidelity, execution fidelity
  and a PnL overlay against the source wallet's official curve.
- **System clock:** on the development machine W32Time was set to `NoSync` and
  never synchronised; the clock ran 68 seconds fast and corrupted every latency
  measurement taken through it. Fixed by configuring an explicit peer list and
  forcing a resync — a bare `/resync` fails under `NoSync` with "no time data
  available". Check `w32tm /query /status` on any new machine, because CLOB
  order signatures are timestamp sensitive. Independently, the daemon measures
  `ct.measure_clock_offset_seconds()` against the CLOB `/time` endpoint at
  startup and every 30 minutes and corrects the reported latency.

- **Multi-trader engine (fixed 2026-08-18):** baseline cutoff and on-chain
  scan cursor are per wallet now (`seeded_at:<w>`, `baseline_cutoff_ts:<w>`,
  `fast_last_block:<w>`, legacy global keys serve the primary wallet). Before,
  one global cutoff copied a later-followed wallet's history at stale prices and
  one global cursor left every wallet but the first unscanned on-chain. All
  traders paused now means copy nobody (the fallback to Swisstony applies only
  to a `traders` table with no rows). `copy_scale_override` is stored but not
  read by the sizing — remove it or wire it, do not expose it.
- **Daemon on Windows:** `write_status` retries the atomic rename (a reader
  holding the file made the daemon die on the first page refresh).
- **Wallet page basis lines:** the Similar tab is "top 20 holders per outcome of
  the 12 largest open markets", not "everyone who traded them"; PnL only where
  the wallet is on the cached leaderboard; conviction = avg $ bought on winners
  / losers. The Risk tab is PARTIAL whenever the closed tails are capped. Keep
  those sentences on the page when touching it.
- **PnL curve fallback (2026-08-18):** `user-pnl-api.polymarket.com` only has
  history from late November 2024 (`interval=all` = `max`; the API accepts
  `max/all/1m/1w/1d/12h/6h` × `1d/18h/12h/3h/1h`). Theo4 (0x5668…5839) traded
  Oct–Nov 2024, so its profile curve is 630 identical points at $22.05M — zero
  drawdown, no Sharpe. `api_views._wallet_pnl` now flags `flat`, always adds a
  `settled` curve (closed rows' realised PnL summed in resolution order, starting
  at $0 the day before the first resolution) and sets `shown` to `profile` /
  `settled` / `none`; the page charts the settled curve with an amber "PROFILE
  CURVE FLAT" line and the KPI strip names which curve Sharpe / drawdown come
  from. Capped tails make the settled curve the extremes only, and it says so.
  The block is laid out after predicts.guru's PnL Timeline: current PnL big at
  the right, `charts.pnlZeitkurve` (time axis, area fill, $ ticks), six stat
  tiles, definitions collapsed in a `<details>`. Sortino follows Sortino & van
  der Meer (downside RMS over all days) and is None under 3 losing days
  (`perf_metrics.MIN_DOWNSIDE_DAYS`) — the old losers-only denominator printed
  246,860 for Theo4 off one −$21 day.
- **Kalshi titles on the tape (2026-08-19):** the trade feed carries tickers
  only; `md.enrich_kalshi_tape` (memoised per ticker, `kalshi_market_meta`)
  swaps them for `kalshi_display_title` — question plus strike ("Bitcoin price
  on Aug 19? · $68,200 or above"), parlays as "Parlay · N legs: …". Kalshi
  prints now carry `market_key = ticker`, and `app/suspicion` feeds the ticker
  into the context classifier as context (`_context_with_ticker`), so the
  KX… exclusion patterns still fire when the title is the question. Before,
  KXSILVER15M/KXHIGHMIA/parlays sat on the risk screen as "General".
- **Risk event card (2026-08-19):** closed card = kind, score, market, flow
  chips, top wallets, one-line `BOOK NOW 1 adds · 2 not held`, four figures,
  "Why 63?" toggle (`state.riskOpen[market_key]`, not `<details>` — the
  30 s re-render would close it). Open = the score taken apart
  (`riskScoreBreakdown`): one row per scoring part with a plain label
  ("One wallet dominates", not "top-wallet concentration"), a bar against
  its cap, the points, and under it `fact` / `rule` from
  `suspicion.event_components` ("0x07be…5233 did 97% of the flow · full marks
  when one wallet did all of it"); zero parts in one NOT FOUND line; the
  context multiplier; the arithmetic "56.9 pts × 1.1 = 63" (flagged when the
  listed parts do not reach the score). `whale_base` rides on the event row
  so the rule can say "full marks at $100k". The toggle carries `data-stop`
  so the card's market-drawer click does not fire.

## 11. Next concrete step

Open from the 2026-08-18 session (the paper copy experiment on the live desk is
running with slow domain-expert wallets; the owner reviews sub-accounts there):

- Watch the live desk for a week; the per-trader equity curves
  (`trader_equity_snapshots`) are the comparison the experiment is about.
- Wallet page: mobile widths (the aside wraps, the treemap is fixed 440px);
  a range brush on the PnL curve and trade markers were left out.
- Similar wallets: PnL/volume are sparse because only the cached top-250
  leaderboard is consulted; a per-wallet PnL read would cost one call each.
- Streamlit copy page still says "Swisstony is the seed trader and stays
  followed" — the engine no longer requires that; align or retire that panel.

Earlier candidates from the roadmap in §4:

- **Launch hygiene (7, rest)** — imprint and privacy policy on marketintel.dev,
  geoblocking decision; the guide is in
  [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md).
- **Read-only wallet connect (5)** — buildable without any purchase: a React
  component (wagmi/WalletConnect) plus SIWE. Details in
  [LIVE_COPYTRADING_PLAN.md](LIVE_COPYTRADING_PLAN.md) §2.
