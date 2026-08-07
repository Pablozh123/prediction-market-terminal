# Handoff — Prediction Market Terminal

Single entry point for continuing this project from another machine.
Last updated 2026-08-07.

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
- **State:** 1,312 unit tests green (`python -m unittest discover -s tests`).

## 2. Quick start on a new machine

```bash
git clone https://github.com/Pablozh123/prediction-market-terminal.git
cd prediction-market-terminal
python -m pip install -r requirements.txt
python -m streamlit run prediction_terminal.py --server.address=127.0.0.1 --server.port=8503
```

Background runners (optional, paper only):

```bash
python scripts/run_copy_trader.py     # copy daemon: WS detection, on-chain reconciliation, settlement
python scripts/run_alert_scanner.py   # Telegram alert scanner (token via env, see .env.example)
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
7. ⬜ **Production deploy** — domain plus VPS (needs a purchase decision),
   `docker compose up`, CDN in front, imprint and privacy policy, geoblocking.

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
| `scripts/run_copy_trader.py` | Copy daemon loop |
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

- Three Windows scheduled tasks (registered by `scripts/install_autostart.ps1`):
  the terminal on 8503, the copy daemon, the alert scanner.
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

## 11. Next concrete step

Two candidates from the roadmap in §4:

- **Production deploy (7)** — the actual launch: domain and VPS (a purchase
  decision), `docker compose up`, CDN in front, imprint and privacy policy. The
  auth precondition is met; the guide is in
  [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md).
- **Read-only wallet connect (5)** — buildable without any purchase: a React
  component (wagmi/WalletConnect) plus SIWE. Details in
  [LIVE_COPYTRADING_PLAN.md](LIVE_COPYTRADING_PLAN.md) §2.
