# Claude Codebase-Audit

Stand: 2026-06-10
Basis: Branch `codex/follow-traders-ui-split-fixes` (17 Commits vor `main`)
Autor: Claude (Cowork), Branch `claude/codebase-audit`

Hinweis: Die im Sandbox-Mount sichtbaren "modified"-Dateien sind reine CRLF/LF-Artefakte (Insertions == Deletions). Es wurden keine Code-Dateien angefasst.

## 1. Was existiert

### Architektur

Zwei getrennte Schichten im selben Repo:

1. **Terminal:** `prediction_terminal.py` (12.047 Zeilen, Streamlit-Monolith) + `src/prediction_markets.py` (API/Analytics) + `src/copy_trading.py` (Paper-Engine, SQLite) + `app/` (extrahierte, Streamlit-freie Helper: `format.py`, `filters.py`, `copy_follow.py`).
2. **Thesis-Sentiment-Pipeline (separat, ohne Bezug zum Terminal):** `app.py`, `run_analysis.py`, `run_bulk.py` mit `src/sentiment.py`, `src/reddit.py`, `src/polymarket.py`, `src/market_metadata.py`. Deren Dependencies (transformers etc.) fehlen bewusst in `requirements.txt`.

### Seiten (alle 14 funktional, Routing via Query-Slugs, `PAGES`-Dict ab Z. 12021)

Overview, Search, Markets, Traders, Wallets, Track, Live Trades, Whale Flow, Cross-Venue, Monitor, Alerts, Resolved, Portfolio, Copy Trade. Datenquellen: Polymarket (Gamma/Data/CLOB) und Kalshi. Caching durchgehend `@st.cache_data` mit TTLs 30–900s.

### API-Endpoints (konsumiert, nicht angeboten)

- Polymarket Gamma (Markets/Events), Data-API (Trades, Positions, Holders, Leaderboard), CLOB (Orderbooks)
- Kalshi Public API (Markets, Trades)
- Polygon RPC (OrderFilled-Events, Fast-Path des Copy-Daemons)

### DB-Schema (SQLite, `src/copy_trading.py` ab Z. 198)

`meta`, `paper_orders`, `positions`, `tony_positions` (legacy), `cash_events`, `traders`, `source_positions`, `trader_stats` (+ Migrationspfad `positions_migrated`). Bemerkenswert: Die Multi-Trader-Tabellen aus der Spec existieren bereits — Engine und UI arbeiten aber noch single-target (Swisstony).

### Tests & Tooling

- ~1.800 Unit-Tests in 4 Dateien (Routing/Filter/Analytics, Copy-Engine-Sizing, Formatter/Filter-Helper)
- `scripts/smoke_routes.py`: 25 Routen, nur HTTP-Status
- `scripts/visual_smoke.py`: 10 Routen, Playwright, Text + Screenshot + Blank-Detection
- `scripts/run_copy_trader.py`: Paper-Daemon (Polygon-RPC 1s / API-Fallback 30s / Settlement 180s), Stop-File, Status-JSON; PowerShell-Watchdog

## 2. Feature-Status-Tabelle

| Feature | Status | Datei/Pfad |
|---|---|---|
| Overview / Search / Markets / Traders / Wallets | fertig | `prediction_terminal.py` Z. 3121–6840 |
| Track (Wallet-Trade-Tape) | fertig | `prediction_terminal.py` Z. 6840–7022 |
| Live Trades / Whale Flow (inkl. Insider-Risk) | fertig | `prediction_terminal.py` Z. 7744–8871 |
| Cross-Venue / Monitor / Alerts / Resolved | fertig | `prediction_terminal.py` Z. 8871–10956 |
| Copy Trade (paper-only, Single-Target) | fertig | `prediction_terminal.py` Z. 10956–11432, `src/copy_trading.py` |
| Portfolio (Research + Copy-Equity + Watchlist) | fertig | `prediction_terminal.py` Z. 11432–12020 |
| API-Layer (Polymarket/Kalshi) | fertig | `src/prediction_markets.py` |
| Copy-Daemon + Watchdog | fertig | `scripts/run_copy_trader.py`, `scripts/start_copy_trader_watchdog.ps1` |
| Auth (Sign-in/Sign-up) | halb (UI-Shell, alle Buttons `disabled=True`) | `prediction_terminal.py` Z. 1802–1820 |
| Multi-Trader-Copytrading | halb (DB-Tabellen da, Engine/UI single-target, Spec v2 liegt vor) | `src/copy_trading.py` Z. 265–301, `docs/spec_multitrader_copytrading.md` |
| UI-Tests für Seitenrenderer | fehlt (nur HTTP-/Visual-Smoke) | `tests/`, `scripts/` |
| v1-clone-Merge nach `main` + Tag | fehlt | Git (`main` 17 Commits hinterher) |
| Track-Legacy-Seite | Dead Code (~720 Zeilen, nicht in `PAGES`) | `prediction_terminal.py` Z. 7022–7744 |
| Sentiment-Pipeline (Thesis) | separat, funktional, nicht ins Terminal integriert | `app.py`, `run_analysis.py`, `run_bulk.py`, `src/sentiment.py` u. a. |

## 3. Top 5 kritische Lücken

1. **`main` ist veraltet (17 Commits):** Der eigentliche Phase-1-Abschluss (Review → PR → Merge → Tag `v1-clone`) steht aus. Alles andere hängt laut COLLAB.md daran.
2. **Multi-Trader halb angelegt:** Schema-Tabellen (`traders`, `source_positions`, `trader_stats`) existieren bereits im Code, aber Engine, Sizing, ROI-Ranking und UI sind single-target. Inkonsistenz-Risiko zwischen Schema und Logik; Spec-Phasen 2–7 offen.
3. **12k-Zeilen-Monolith mit massiver Duplikation:** 36 fast identische `reset_*_filter_widgets()`- und 13 `apply_*_filter_view_widgets()`-Funktionen, ~720 Zeilen Dead Code (`page_track_legacy`), 14 leere `except: pass`. Haupt-Merge-Konfliktpunkt laut COLLAB.
4. **UI-Renderer ungetestet:** Unit-Tests decken nur reine Logik ab; `smoke_routes.py` prüft nur HTTP 200 ohne Inhalt. Regressionen in Seitenrendern fallen erst im Visual-Smoke (manuell, Playwright) auf.
5. **Doppelte/überlappende Module:** `cents()` doppelt mit unterschiedlicher Semantik (`app/format.py:37` vs. `src/prediction_markets.py:168`), `market_title_family_key()` doppelt, `src/polymarket.py`/`market_metadata.py` überlappen mit `prediction_markets.py` (gehören zur Thesis-Pipeline — Trennung nirgends dokumentiert). Dazu Auth als tote UI-Shell.

## 4. Schnellster Weg zur ersten lauffähigen Version

Die App ist auf diesem Branch bereits lauffähig: `pip install -r requirements.txt && python -m streamlit run prediction_terminal.py --server.address=127.0.0.1 --server.port=8503` — für eine "fertige" v1 fehlt nur Review + PR dieses Branches nach `main` und das Tag `v1-clone`.
