# Market Intel Terminal

This workspace now includes a Streamlit website for researching prediction-market flow across Polymarket and Kalshi.

## Run

```bash
python -m streamlit run prediction_terminal.py --server.address=127.0.0.1 --server.port=8502
```

Then open http://127.0.0.1:8502.

## What is implemented

- Overview dashboard with high-volume markets, venue volume, and recent large trades.
- Markets scanner for Polymarket and Kalshi with price, volume, liquidity, rule text, order book, recent trades, and venue links.
- Polymarket trader leaderboard using public wallet data.
- Trader traits for recent-flow whale and bot-like behavior using public trade samples.
- Polymarket wallet analyzer with open positions, closed positions, realized PnL, win rate, trades, and activity.
- Paper copy-trading page for Swisstony (`0x204f72f35326db932158cba6adff0b9a1da95e14`) with a local $1,000 simulated portfolio, 1% trade-notional scaling, and a 5% equity cap per paper order.
- Whale-flow tape that aggregates large public Polymarket wallet trades and Kalshi ticker-level trades.
- Cross-venue matcher that compares similar Polymarket and Kalshi contract titles and ranks yes-price gaps.
- Monitor page for fast movers, whale prints, tight spreads, and Polymarket holder concentration.
- Resolved-market archive with binary outcome mix and category-level history from closed Polymarket markets.
- Manual research portfolio and market watchlist stored in Streamlit session state.

## Data boundaries

- Polymarket exposes public proxy-wallet data, positions, activity, trades, holders, and leaderboard endpoints.
- Kalshi public market and trade feeds do not expose public wallet identities, so Kalshi wallet analytics cannot be reproduced from public data alone.
- Bot-like and whale labels are heuristics from the currently loaded public trade sample; they are not identity claims.
- The Swisstony copy-trading workflow is paper-only. The first sync seeds a baseline from the current public wallet state, then later newly observed trades are copied into the local simulated account.
- For fast repeated copying, run `python scripts/run_copy_trader.py --interval 5 --limit 500`. It polls Swisstony every 5 seconds, writes status to `data/copy_trader_status.json`, and stops when `data/copy_trader.stop` exists.
- The app is research-only and does not place trades.

## Main files

- `prediction_terminal.py` - Streamlit website.
- `src/prediction_markets.py` - Public API clients and analytics helpers.
- `src/copy_trading.py` - SQLite-backed paper copy-trading engine.
