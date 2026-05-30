# Prediction Market Terminal

Streamlit research terminal for Polymarket and Kalshi, built as a Phase 1 clone of the public PredictParity experience. The app focuses on market discovery, trader/wallet research, live-style public flow, alerts, tracking, portfolio research, and paper-only Swisstony copy-trading.

Live trading is disabled. The copy-trading module is paper-only and must not be expanded into Multi-Trader work until Phase 2.

## Run

```powershell
python -m streamlit run prediction_terminal.py --server.address=127.0.0.1 --server.port=8503
```

Open:

```text
http://127.0.0.1:8503/
```

Optional fast paper-copy daemon:

```powershell
python scripts/run_copy_trader.py --interval 1 --api-interval 30 --settlement-interval 180
```

Optional local route smoke while the app is running:

```powershell
python scripts/smoke_routes.py
```

## Phase Plan

Phase 1 is the PredictParity clone layer. It covers PredictParity-like navigation, search, markets, traders, tracking, live trades, monitor, portfolio, filters, saved views, market detail tools, wallet analytics, and the existing paper Swisstony copy-trader.

Phase 2 is Multi-Trader-Copytrading as a separate layer. Do not start it before the Phase 1 `v1-clone` tag. See [docs/COLLAB.md](docs/COLLAB.md) and `docs/spec_multitrader_copytrading.md` on the Claude branch.

## PredictParity Clone Map

| PredictParity surface | Local implementation |
|---|---|
| Top nav: Markets, Traders, Track, Live Trades, Monitor, Portfolio | Top navigation plus sidebar workspaces in `prediction_terminal.py` |
| Search Parity `/` | Command palette with global markets, traders, trades, alerts, news, tracked items |
| Trader profile routes `/traders/p/@handle` | Local route into the wallet/profile workspace with profile-handle resolution |
| Home / featured market | Overview page with featured carousel, Yes/No buttons, chart windows, line/candlestick, news, trending markets |
| Markets | Table/Card/Calendar views, quick filters, category chips, saved filters, market drilldown |
| Market detail | Header metrics, charts, order book, holders, top traders, recent trades, paper ticket, news, comments |
| Traders | PredictParity public GraphQL leaderboard, table/list/card views, filters, saved views, profile links |
| Trader URL filters | Supports PredictParity-style trader query filters such as `/traders?bot=true&apMin=101` |
| Trader / wallet profile | Wallet page with profile resolver, PnL chart/calendar, positions, activity, counterparties, tracking actions |
| Track | Local tracked markets and wallets hub with import, filters, live feed, action buttons |
| Live Trades | Public trade tape with filters, wallet/market aggregation, flow chart, track actions |
| Monitor | Signal monitor for fast movers, whale prints, spreads, holder risk, endings, saved alert rules |
| Alerts | Alert hits, signal feed, rule builder, saved rules, coverage |
| Portfolio | Research portfolio, wallet import, copy portfolio, exposure, cash events, paper history, watchlist |
| Sign In / Sign Up shell | Local research-mode auth facade mirroring PredictParity UI; no credential transmission |

## Data Boundaries

- Polymarket exposes public proxy-wallet, position, activity, trade, holder, and leaderboard data.
- PredictParity public GraphQL is used for public trader leaderboard/profile/chart data where available.
- Kalshi public feeds expose market and trade data, but not public trader wallet identities.
- Wallet labels, bot-like labels, whale labels, and flow traits are heuristics from public data.
- The app is research-only. It does not place real Polymarket or Kalshi orders.

## Paper Copy-Trading

The existing Copy Trade page follows Swisstony:

```text
0x204f72f35326db932158cba6adff0b9a1da95e14
```

Current behavior:

- Local SQLite persistence in `data/copy_trading.sqlite`
- Paper-only portfolio accounting
- Baseline seeding from the target wallet
- New observed BUY/SELL copies after baseline
- Settlement/redeem recycling from unrealized to realized PnL
- Manual paper cash top-ups
- CSV exports and skipped/baseline visibility

Do not replace or remove this during Phase 1.

## Main Files

| File | Purpose |
|---|---|
| `prediction_terminal.py` | Streamlit website and PredictParity-style UI |
| `src/prediction_markets.py` | Public API clients and analytics helpers |
| `src/copy_trading.py` | SQLite-backed paper copy-trading engine |
| `scripts/run_copy_trader.py` | Background paper-copy sync runner |
| `scripts/smoke_routes.py` | Lightweight local HTTP route smoke |
| `tests/test_prediction_markets.py` | Prediction-market helper tests |
| `tests/test_copy_trading.py` | Paper copy-trading tests |
| `docs/COLLAB.md` | Codex/Claude collaboration rules and phase boundary |
| `docs/PHASE1_CLONE_AUDIT.md` | Phase 1 clone completion checklist and remaining gates |

## Verification

```powershell
python -m py_compile prediction_terminal.py src\prediction_markets.py src\copy_trading.py
python -m unittest discover -s tests -p test_*.py
python scripts/smoke_routes.py
```

Before tagging `v1-clone`, also run a browser smoke against `http://127.0.0.1:8503/`:

- App loads without Traceback
- Top PredictParity navigation works
- Trader profile deep links route into the local profile view
- Search Parity opens
- Markets page loads Table/Card/Calendar controls
- Traders page loads leaderboard controls
- Track, Live Trades, Monitor, Portfolio load without login blockers
- Copy Trade page still shows paper-only Swisstony state

## Git Workflow

Active Phase 1 branch:

```text
codex/website
```

Phase 1 completion requires:

1. Merge `codex/website` into `main`
2. Verify tests and browser smoke on `main`
3. Tag the stable clone milestone:

```powershell
git tag v1-clone
git push origin main
git push origin v1-clone
```
