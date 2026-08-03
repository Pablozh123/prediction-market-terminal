# Prediction Market Terminal

[![CI](https://github.com/Pablozh123/prediction-market-terminal/actions/workflows/ci.yml/badge.svg)](https://github.com/Pablozh123/prediction-market-terminal/actions/workflows/ci.yml)

Microstructure research on Polymarket and Kalshi from self-recorded data, and the research terminal it runs on. Read-only throughout: no order path exists in this codebase, and the authenticated Kalshi socket signs `GET` only.

## Research

Four recorders run continuously across both venues — REST pollers on a 120-second grid, event-driven WebSocket recorders writing on every top-of-book change — feeding eight analysis modules. Every finding below has a report and a tested module behind it, and every cost is subtracted separately for spread and fee.

- **Book imbalance predicts direction and is still not tradable as a taker.** 55.2% hit rate over 1,011,556 observations, Wilson lower bound 55.0%. Gross edge +0.03 to +0.13 cents against a 2.58 cent round trip. 34 cuts knowable before the trade fail to rescue it; the one survivor has a confidence interval containing zero, which is the expected false-positive count at 34 tests.
- **Market making loses to staleness, not to spread width — and whether it pays is not identified.** Same code and parameters on five days of seconds-resolution data instead of a 120-second grid: markout per fill falls from 362 to 70 cents while spread earned per fill barely moves, 138 against 148. The decomposition is an identity, not an estimate — spread capture plus markout plus late drift reconstructs terminal mark-to-mid exactly, asserted to nine decimal places in the tests. Five days is also the first sample where the daily block bootstrap runs, and it puts the two fill models on opposite sides of zero with neither interval touching it: touch (-12,121, -2,413) USD per day, tape (+881, +5,889). More data sharpened the ambiguity instead of resolving it; settling the sign needs queue position, not more days.
- **Cross-venue gaps are carry, not arbitrage, and they prove it by staying open.** Net of both fee curves, 3 of 5 verified pairs clear: best 3.07 cents, all settling in 2027 or 2028, so 0.5 to 1.8% annualised. Reconstructed over 11.6 hours from both recorders, 3 of the 5 were open at every moment observed.
- **Two venues can price the same event and settle it differently.** Kalshi resolves the 2028 presidential market on who is next inaugurated, Polymarket on who wins the election. A basket over that pair loses both legs instead of hedging — and that pair had passed this project's own title-based mismatch screen as clean.

Discarded along the way, and documented as such: signal-conditioned quoting (better total PnL, unchanged markout per fill — the gain was only from trading less), signed order flow as a signal (51.3%), and two apparent cross-venue edges of 79 and 64 cents that turned out to be mismatched pairs.

**Start here:** [one-page summary](docs/research/ONE_PAGER.md) · [full index of studies](docs/research/README.md)

## The terminal

Streamlit research terminal: market discovery, trader/wallet research, live public flow, whale/insider risk screening, backtesting, alerts, tracking, portfolio research, and paper-only copy-trading. It is the platform the research above runs on, and the place where wallet-level findings are checked against out-of-sample outcomes.

All market data comes from the public Polymarket (Gamma/Data/CLOB) and Kalshi APIs. Live trading is disabled — the copy-trading module is paper-only. The app is a research tool, not investment advice.

> **Continuing the project / picking up on another machine?** Start with [docs/HANDOFF.md](docs/HANDOFF.md) — current state, roadmap, conventions, and the next concrete step.

## Run locally

```powershell
python -m streamlit run prediction_terminal.py --server.address=127.0.0.1 --server.port=8503
```

Open `http://127.0.0.1:8503/`.

### Control-room frontend (new)

A standalone dark-terminal frontend lives under `web/`, served together with a
read-only JSON API by `api/server.py`:

```powershell
python api/server.py
```

Open `http://127.0.0.1:8787/`. The page starts on a labelled demo dataset and
switches to `LIVE · POLYMARKET + KALSHI` as soon as the API answers; the badge
in the top bar always states which one you are looking at. All fifteen
workspaces (markets, live tape, cross-venue, leaderboard, whale flow, risk
screen, backtester, paper copy-trading, alerts, the eight research studies,
settings) reuse the exact same logic modules in `app/` and `src/` as the
Streamlit app — the API only orchestrates and maps to JSON (`app/api_views.py`).
Sample sizes, confidence intervals, `capped`/`window_truncated` flags and
snapshot timestamps are part of every score-bearing response. The Streamlit
app is unchanged and keeps working as before.

Optional background runners:

```powershell
python scripts/run_copy_trader.py --interval 1 --api-interval 30 --settlement-interval 180   # paper copy daemon
python scripts/run_alert_scanner.py                                                          # Telegram alert scanner
```

## Deploy publicly

The repo ships production artifacts — see [docs/PRODUCTION_READINESS.md](docs/PRODUCTION_READINESS.md) for the full guide (hosting, security, Swiss legal checklist, API terms, costs).

```bash
cp .env.example .env       # fill in Telegram secrets (env overrides the settings file)
# set your domain in deploy/Caddyfile
docker compose up -d --build
```

This starts the terminal, the alert scanner, and Caddy (automatic TLS + security headers) as the only public entry point.

### Optional: Google sign-in for the Settings page

Without auth secrets the app runs in open local-research mode — no sign-in surface, Settings unrestricted. To restrict Settings on a public deployment, copy [.streamlit/secrets.toml.example](.streamlit/secrets.toml.example) to `.streamlit/secrets.toml` (gitignored), fill in the Google OIDC credentials, and set the admin allowlist (`[admin] emails` in secrets, or the `ADMIN_EMAILS` env var which takes precedence). With auth configured, Settings fail closed: only signed-in, allowlisted accounts can change configuration, while all research workspaces stay public. For Docker, uncomment the secrets volume in `docker-compose.yml`.

## Workspaces

Overview, Search, Markets, Traders, Track, Live Trades, Wallets, Backtester, Copy Trade, Whale Flow, Suspicious, Cross-Venue, Monitor, Resolved, Portfolio, Settings.

Highlights:

- **Backtester** — replay any wallet's trades over 7/30/90 days with Copy or Fade strategy, four sizing modes, exposure cap, mid-window resolution recycling, and a best-sizing simulation drawn into the equity chart.
- **Suspicious** — event/wallet insider-risk scores from public whale flow with category context (sports odds and weather are excluded — nothing to know early there), fresh-wallet clusters, coordinated-timing clusters, and a Louvain co-trading network with click-to-isolate cluster stories.
- **Traders** — Polymarket leaderboard with podium, smart-score ranking, speed traders, insider-picks feed, and on-demand enrichment (open positions, win rates, balances) from public wallet data.
- **Monitor** — signal scanner (fast movers, volume anomaly, whale prints, tight spreads, holder concentration, endings) with saved alert rules and Telegram delivery.
- **Kalshi integration** — markets, trades (with real market titles), cross-venue gaps, and event-level whale/insider signals; Kalshi publishes no wallet identities, so wallet-level scoring skips those rows and the UI says so.

Most pages accept URL query filters, e.g. `/markets?q=bitcoin&platform=polymarket&probMin=0.05`, `/live-trades?side=buy&minNotional=2500&whale=true`, `/traders?bot=true&apMin=101`.

## Data boundaries

- Polymarket exposes public proxy-wallet, position, activity, trade, holder, and leaderboard data.
- Kalshi public feeds expose market and trade data, but no trader identities.
- Wallet labels, bot-like labels, whale labels, and flow traits are heuristics from public data.
- The app does not place real orders on any venue.

## Paper copy-trading

The Copy Trade page follows a target wallet (default Swisstony, `0x204f72f35326db932158cba6adff0b9a1da95e14`) with local SQLite persistence (`data/copy_trading.sqlite`), paper-only accounting, baseline seeding, settlement recycling, CSV exports, and URL filters such as `/copy-trade?status=copied,baseline`.

Accounting is contribution-aware: every cash injection (start cash, manual or auto top-up) is tracked separately from trading PnL, the equity chart draws equity against the contributions step line, and auto top-up is **off by default** — when a sub-account runs out of cash, buys skip visibly until settlements recycle funds.

Sizing aims for a faithful scaled mirror of the source wallet: the default scale is the uncapped neutral portfolio ratio (your sub-account equity / source equity), a cash throttle shrinks all orders uniformly during cash droughts instead of skipping later trades, and the Copy fidelity tab quantifies every deviation — config fidelity (settings vs neutral), execution fidelity (filled vs desired, with loss breakdown), and a %-PnL overlay of the paper curve against the source wallet's official PnL curve.

## Main files

| File | Purpose |
|---|---|
| `prediction_terminal.py` | Streamlit app (all workspaces + UI) |
| `src/prediction_markets.py` | Public API clients and analytics helpers |
| `src/copy_trading.py` | SQLite-backed paper copy-trading engine |
| `app/backtester.py` | Streamlit-free backtest engine |
| `app/suspicion.py` | Insider-risk scoring, clusters, co-trading network |
| `app/signals.py` | Monitor signal/rule logic (shared with the scanner) |
| `app/app_settings.py` | Persisted settings with env-var secret overrides |
| `app/authz.py` | Admin-gate logic for the Settings page (`st.login()` + allowlist, fail closed) |
| `scripts/run_alert_scanner.py` | Background alert scanner with Telegram delivery |
| `scripts/run_copy_trader.py` | Background paper-copy sync runner |
| `Dockerfile` / `docker-compose.yml` / `deploy/Caddyfile` | Production deployment |
| `docs/PRODUCTION_READINESS.md` | Public-launch guide (hosting, security, legal, costs) |

## Verification

```powershell
python -m py_compile prediction_terminal.py src\prediction_markets.py src\copy_trading.py
python -m unittest discover -s tests -p test_*.py
python scripts/smoke_routes.py
python -m scripts.visual_smoke --base-url http://127.0.0.1:8503 --output-dir artifacts\visual_smoke --timeout-ms 45000
```

The full Streamlit page smoke (network-dependent) runs with `RUN_APP_SMOKE=1 python -m unittest tests.test_app_smoke -v`.
