# Phase 1 Live Surface Comparison

Date: 2026-05-31

Primary public references used:

- [PredictParity live app](https://predictparity.com/)
- [PolyMart Predict Parity listing](https://polymart.app/predict-parity)

The direct PredictParity app is a JavaScript app. Browser probing on 2026-05-31 loaded the public root, Markets, and Traders surfaces directly. Track, Live Trades, Monitor, and Portfolio resolved to the live app's login/sign-up screen, so those areas are compared by public route/navigation intent plus local implemented functionality.

## Public Surface Signals

| Public PredictParity signal | Local Phase 1 coverage | Notes |
|---|---|---|
| Consolidated prediction-market dashboard | Covered | Markets, Overview, Cross-Venue, market drilldowns for Polymarket and Kalshi public data |
| Dashboard deep links | Covered | Root `/?...` links can prefill overview query, platforms, categories, volume/liquidity, flow thresholds, featured source, active-only, and news visibility |
| Wallet performance tracking | Covered | Traders page, Wallets page, PnL, win rate, open/closed positions, profile links |
| Watchlist / tracking hub links | Covered | `/track?...` links can prefill market/wallet tracking filters, signal filter, watch volume, and wallet open-value thresholds |
| Portfolio dashboard links | Covered | `/portfolio?...` links can prefill research/copy/watchlist/history sources, PnL/value thresholds, outcomes, and copy statuses |
| Market data visualizations | Covered | Price charts, order book, volume charts, holder split, flow charts, portfolio/exposure charts |
| Smart-money alerts and monitoring | Covered | Monitor, Alerts, whale flow, tracked wallets, signal rules |
| Smart-money and venue-gap deep links | Covered | `/whale-flow?...` and `/cross-venue?...` links can prefill smart-money and cross-market gap scanners |
| Historical accuracy statistics / finished events | Covered | Resolved page, closed market archive, resolution mix, category history |
| Historical accuracy deep links | Covered | `/resolved?...` links can prefill query, outcome, decisive-only, volume/liquidity, closed-window, final-price, sort, and row filters |
| Top traders for any Polymarket | Covered | Market detail includes holders/top traders/recent tape leaders |
| Counterparty visibility | Best-effort covered | Public APIs do not expose exact counterparties; local app estimates counterparty hints from public tape proximity |
| Bot filtering via `/traders?bot=true&apMin=101` | Covered | Local trader URL filters now parse bot and active-position minimum params |
| Wallet connection / direct trading | Shell only | Live order placement is intentionally disabled; local app provides research-mode auth/wallet shell, auth deep links, and paper trade tickets |

## Live Browser Probe 2026-05-31

| Live route | Observed public surface | Local Phase 1 match |
|---|---|---|
| `/` | Top navigation, `Search Parity...`, Sign In/Sign Up, featured market carousel, Yes/No prices, newsfeed, time-window controls, trending markets | Covered by Overview, featured market, news, trend/ending sections, top nav, auth shell |
| `/markets` | Top navigation, saved/trending/my positions/ending/new filters, active status, probability/spread/end-date filters, market table with probability, spread, volume, liquidity, end date | Covered by Markets scanner, filters, table/card/calendar views, saved filter presets |
| `/traders` | Top navigation, active filter, position minimum filter, trader leaderboard with PnL, volume, win rate, positions; `swisstony` visible | Covered by Traders leaderboard, bot/position filters, PredictParity public trader source/fallback, profile links |
| `/track` | Login/sign-up screen behind top navigation | Covered locally as a research tracking hub without login blocker |
| `/live-trades` | Login/sign-up screen behind top navigation | Covered locally as public trade tape without login blocker |
| `/monitor` | Login/sign-up screen behind top navigation | Covered locally as signal monitor and alert-rule workspace without login blocker |
| `/portfolio` | Login/sign-up screen behind top navigation | Covered locally as research/copy portfolio without live credential use |

Screenshots from this probe are intentionally untracked under `artifacts\predictparity_live`.

## Remaining Evidence Needed Before `v1-clone`

1. Final merge of `codex/website` into `main`.
2. Re-run compile, unit, HTTP route smoke, and browser visual smoke on `main`.
3. Tag and push `v1-clone`.

## Intentional Phase 1 Boundary

The local clone keeps live trading disabled. Any real-order mode belongs outside the current clone milestone and must not be mixed into Multi-Trader Phase 2 until `v1-clone` is merged and tagged.
