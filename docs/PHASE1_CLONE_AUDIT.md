# Phase 1 PredictParity Clone Audit

Status: in progress on `codex/website`.

This audit tracks the clone layer only. Multi-trader copy-trading is out of scope until the `v1-clone` tag exists on `main`.

Live surface comparison notes are tracked in `docs/PHASE1_LIVE_SURFACE_COMPARE.md`.

## Implemented Surfaces

| PredictParity surface | Local status | Evidence |
|---|---|---|
| Top navigation | Implemented | `Markets`, `Traders`, `Track`, `Live Trades`, `Monitor`, `Portfolio` top nav with path links |
| Path routes | Implemented | `/markets`, `/traders`, `/track`, `/live-trades`, `/monitor`, `/alerts`, `/resolved`, `/portfolio` route into Streamlit state |
| Market deep links | Implemented | `/markets/<slug>` routes into market search/detail prefill |
| Market URL filters | Implemented | PredictParity-style scanner filters including query, platform, status, probability, volume, liquidity, spread, ending, age, sort, and rows |
| Trader profile deep links | Implemented | `/traders/p/@handle` and `/wallets/0x...` route into the local wallet/profile workspace |
| Search Parity | Implemented | Command palette plus Search workspace for markets, traders, trades, news, alerts, tracked items |
| Search URL filters | Implemented | PredictParity-style global search filters including query, platform, result types, min value, active/tracked flags, broad-pair fallback, and rows |
| Home / featured market | Implemented | Overview workspace with featured market, price chart, news, trending and ending sections |
| Markets | Implemented | Table/card/calendar views, filters, categories, saved filter presets, market drilldown |
| Market detail | Implemented | Header metrics, charts, order book, holders, traders, recent trades, paper ticket, news, comments |
| Traders | Implemented | PredictParity public trader source with fallback, filters, saved views, profile links |
| Trader URL filters | Implemented | PredictParity-style query filters including `/traders?bot=true&apMin=101` |
| Trader / wallet profile | Implemented | Wallet analytics with positions, activity, counterparties, PnL chart/calendar, tracking actions |
| Track | Implemented | Tracked markets and wallets hub with imports, filters, feed, action buttons |
| Live Trades | Implemented | Public trade tape, filters, wallet/market aggregation, flow chart, tracking actions |
| Live Trades URL filters | Implemented | PredictParity-style tape filters including query, platform, side/outcome, min notional, whale-only, tracked markets/wallets, and rows |
| Monitor | Implemented | Movers, whale prints, spreads, holder risk, ending markets, signal rules |
| Monitor URL filters | Implemented | PredictParity-style signal filters including query, platform, signal types, watched-only, volume, liquidity, move, spread, whale notional, ending, and holder-risk controls |
| Alerts | Implemented | Signal feed, alert hits, rule builder, saved rules, coverage |
| Alerts URL filters | Implemented | PredictParity-style alert-center filters including query, signal types, hits-only, thresholds, ending, and holder-risk controls |
| Historical accuracy / Resolved | Implemented | Closed-market archive with final Yes price, inferred resolved outcome, category history, resolution mix, decisive-close stats, and CSV export |
| Resolved URL filters | Implemented | PredictParity-style accuracy archive filters including query, outcomes, decisive-only, volume/liquidity, category, closed window, final Yes range, sort, and rows |
| Portfolio | Implemented | Research portfolio, wallet import, copy portfolio, exposure, cash events, history, watchlist |
| Sign In / Sign Up shell | Implemented | Research-mode auth facade only, no credentials or live orders |
| Existing Swisstony paper copy-trading | Preserved | SQLite paper engine, skipped/baseline visibility, settlements/redeems, cash top-ups |

## Verified So Far

| Check | Result |
|---|---|
| `python -m py_compile prediction_terminal.py src\prediction_markets.py src\copy_trading.py scripts\smoke_routes.py` | Pass |
| `python -m unittest discover -s tests -p test_*.py` | Pass, 100 tests |
| `git diff --check main..codex/website` | Pass |
| HTTP route smoke for `/`, `/search?q=bitcoin&platform=polymarket&type=markets,traders,cross-venue&minValue=10000`, `/markets`, `/markets/will-bitcoin-hit-100k`, `/markets?q=bitcoin&platform=polymarket&status=active&probMin=0.05&probMax=0.95&volumeMin=10000`, `/traders`, `/track`, `/live-trades`, `/live-trades?q=swisstony&platform=polymarket&side=buy&minNotional=2500&whale=true`, `/monitor`, `/monitor?q=bitcoin&platform=polymarket&signal=whale-print,tight-spread&minWhale=2500&maxSpread=0.07`, `/alerts?q=iran&signal=fast-mover&hitsOnly=true&minWhale=5000`, `/resolved?q=iran&outcome=yes,no&decisiveOnly=true&minVolume=10000&closedWindow=30d&finalYesMin=0.95`, `/portfolio`, `/copy-trade`, `/traders/p/@swisstony`, `/traders?bot=true&apMin=101`, `/wallets/0x204f72f35326db932158cba6adff0b9a1da95e14` | Pass, 200 responses |
| Query route browser smoke for `?page=traders` and nav to markets | Pass in prior Playwright run |

## Open Gates Before `v1-clone`

1. Browser smoke on true path routes, especially `/traders`, `/markets`, `/track`, `/live-trades`, `/monitor`, `/portfolio`.
2. Visual sanity check in the in-app browser: no Traceback, no broken top nav, no obvious layout overlap.
3. Final comparison pass against the live PredictParity public surface if network/browser access is available.
4. Merge `codex/website` into `main`.
5. Re-run compile, unit tests, and browser smoke on `main`.
6. Tag and push `v1-clone`.

## Non-Goals In Phase 1

- No Multi-Trader-Copytrading implementation.
- No live trading.
- No Polymarket credential usage.
- No removal of the existing Swisstony paper copy-trader.
