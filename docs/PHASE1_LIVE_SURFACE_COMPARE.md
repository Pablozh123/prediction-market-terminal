# Phase 1 Live Surface Comparison

Date: 2026-05-30

Primary public reference used: [PolyMart Predict Parity listing](https://polymart.app/predict-parity). The direct PredictParity app is a JavaScript app, so this document is a feature-surface comparison, not a final visual sign-off.

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
| Wallet connection / direct trading | Shell only | Live order placement is intentionally disabled; local app provides research-mode auth/wallet shell and paper trade tickets |

## Remaining Evidence Needed Before `v1-clone`

1. Real browser smoke on the local app path routes.
2. Visual sanity pass for navigation, tables, filter panels, and profile/deep-link views.
3. If browser access to PredictParity succeeds, a final visual comparison of the landing/sidebar/top-nav/profile/trader surfaces.

## Intentional Phase 1 Boundary

The local clone keeps live trading disabled. Any real-order mode belongs outside the current clone milestone and must not be mixed into Multi-Trader Phase 2 until `v1-clone` is merged and tagged.
