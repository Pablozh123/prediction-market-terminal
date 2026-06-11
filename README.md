# Prediction Market Terminal

Streamlit research terminal for Polymarket and Kalshi: market discovery, trader/wallet research, live public flow, whale/insider risk screening, backtesting, alerts, tracking, portfolio research, and paper-only copy-trading.

All market data comes from the public Polymarket (Gamma/Data/CLOB) and Kalshi APIs. Live trading is disabled — the copy-trading module is paper-only. The app is a research tool, not investment advice.

## Run locally

```powershell
python -m streamlit run prediction_terminal.py --server.address=127.0.0.1 --server.port=8503
```

Open `http://127.0.0.1:8503/`.

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
