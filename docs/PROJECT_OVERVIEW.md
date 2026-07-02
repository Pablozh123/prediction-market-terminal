# Projekt-Gesamtüberblick — Prediction Market Terminal

Stand: 2026-06-12 · main @ `796a0cc` · 311 Unit-Tests grün · live lokal auf http://127.0.0.1:8503

Dieses Dokument ist **self-contained** und dafür gedacht, es einer neuen Claude-/Research-Session zu geben, damit sie ohne weiteren Kontext weiterarbeiten/-recherchieren kann. Es beschreibt: was das Produkt ist, was auf der Website gebaut wurde, wie es technisch umgesetzt ist, die Datengrenzen, die Strategie und die offenen Entscheidungen.

> Rechtlicher Rahmen: legales Daten-/Analyse-Produkt über **öffentliche** Polymarket-/Kalshi-Daten. Paper-only, keine Custody, kein Live-Handel. Alle Rechtsthemen in den Plan-Docs sind Compliance-Research (kein Handeln ohne Anwalt).

---

## 1. Was das Produkt ist

Ein **Prediction-Market-Intelligence-Terminal** für Polymarket + Kalshi: Marktentdeckung, Trader-/Wallet-Research, Live-Flow, Whale-/Insider-Risk-Screening, Backtesting, verifizierte Track-Records, Alerts, Tracking, Portfolio und **Paper-only** Copy-Trading. Streamlit-Monolith, läuft lokal, deploybar via Docker.

**Positionierung / Differenzierung (Kern):** Nicht noch ein Whale-Feed. Der Markt ist voll mit Polymarket-only-Klonen auf mathematisch falschen Leaderboards + Insider-Copy-Hype. Wir gewinnen mit **Ehrlichkeit + Rechen-Korrektheit + Cross-Venue-Breite + Research-Positionierung**. Details: [DIFFERENTIATION_STRATEGY.md](DIFFERENTIATION_STRATEGY.md).

---

## 2. Tech-Stack & Architektur

- **Sprache/Runtime:** Python 3.13/3.14.
- **UI:** Streamlit 1.5x — ein Monolith `prediction_terminal.py` (~11k Zeilen). Seiten über `WORKSPACES`-Liste + Query-Slug-Routing (`PAGE_QUERY_SLUGS`, Aliasse `picks→Traders`, `alerts→Monitor`).
- **Daten/Analytics:** `pandas`, `plotly` (Charts, `plotly_dark`), `networkx` (Louvain-Clustering), `requests`, `dnspython`, `websocket-client`.
- **Streamlit-freie Logik in `app/`** (testbar, wiederverwendbar von Hintergrund-Skripten): `backtester.py`, `suspicion.py`, `track_record.py`, `signals.py`, `app_settings.py`, `authz.py`, `notify.py`, `copy_follow.py`, `copy_fidelity.py`.
- **Datenquellen-Clients** in `src/prediction_markets.py` (Polymarket Gamma/Data/CLOB, Kalshi) + `src/copy_trading.py` (SQLite Paper-Engine + On-Chain-Lesen).
- **Design-System:** Lime-Akzent `#C8F542` auf dunklem BG, Instrument-Serif-Headlines, JetBrains-Mono-Daten, Inter-Sans; CSS in `inject_css()`.
- **Caching:** durchgehend `@st.cache_data` mit TTLs 30–900 s → Origin-API-Last unabhängig von Besucherzahl (einstellige % der dokumentierten Limits selbst bei 10k Besuchern/Tag).
- **Verifikation:** `unittest` (311 Tests, `tests/`), Playwright-Visual-Smoke via System-Chrome (`scripts/visual_smoke.py`), Streamlit AppTest headless.

---

## 3. Website-Features — alle 16 Workspaces

| Workspace | Was + wie umgesetzt |
|---|---|
| **Overview** | Animierte Landing (Serif-Hero, LIVE-Pulse-Badge, 3 CTAs, Marquee-Ticker inkl. Volume-Anomalie-Item). CSS-Keyframes. |
| **Search** | Command-Palette: globale Suche über Märkte/Trader/Trades/News/Alerts; `build_monitor_signals` gespeist. |
| **Markets** | Tabelle/Karten/Kalender; Highlights (Volume-Anomalie ×ratio, Big-Mover, Ending-soon); "Who's-trading"-Quickview (PM + Kalshi, Whale-Prints + Top-Wallets mit Backtest/Track-Buttons). |
| **Traders** | Polymarket-Leaderboard (data-api), Podium Top-3, Smart-Score-Ranking (`ct.rank_traders_by_smart_score`), Kategorie-Chips, Speed-Trader, Insider-Picks-Feed; On-Demand-Enrichment (Positionen/Win-Rates/Balances) aus öffentlichen Wallet-Daten. |
| **Track** | Getrackte Märkte/Wallets, Live-Feed, Import, Action-Buttons. |
| **Live Trades** | Echtzeit-Trade-Tape (PM + Kalshi mit **echten** Markttiteln via Ticker-Anreicherung), Flow-Chart, Wallet/Markt-Aggregation. |
| **Wallets** | Wallet-Profil: Positionen, PnL-Kurve/Kalender, Activity, First-Funding, Account-Age, **Verified-Track-Record-Panel** (siehe §4.3). |
| **Backtester** | Wallet-Replay Copy/Fade, 4 Sizing-Modi, Exposure-Cap, Mid-Window-Resolutions, Beste-Sizing-Simulation im Chart. (siehe §4.1) |
| **Copy Trade** | Paper-Copy-Command-Center (Ziel-Wallet Swisstony), Daemon-Status, Sub-Accounts, ehrliche PnL. |
| **Whale Flow** | Großdruck-Scanner, Wallet-Aggregation, Outcome-Bias, Track-Actions (4 Tabs). |
| **Suspicious** | Insider-Risk-Screen (siehe §4.2): kategorie-bewusste Event-/Wallet-Scores, Fresh-Wallet-/Coordinated-Cluster, Louvain-Co-Trading-Netzwerk mit Klick-Isolation. |
| **Cross-Venue** | Polymarket↔Kalshi Preislücken-Finder. |
| **Monitor** | Signal-Scanner (Fast-Mover, Volume-Anomalie, Whale-Print, Tight-Spread, Holder-Konzentration, Ending, Watched) + gespeicherte Alert-Regeln + Telegram-Zustellung. |
| **Resolved** | Closed-Market-Archiv, Accuracy, finale Yes-Preise, CSV-Export. |
| **Portfolio** | Research-Portfolio, Copy-Portfolio, Exposure, Cash-Events, Paper-Historie, Watchlist. |
| **Settings** | Daten-Knöpfe (market/trade/whale-Limits), Backtester-Defaults, Telegram-Config, Copy-Daemon-Start/Stop. |

Die meisten Seiten akzeptieren URL-Query-Filter (z.B. `/markets?q=bitcoin&probMin=0.05`, `/live-trades?side=buy&minNotional=2500`, `/traders?bot=true`).

---

## 4. Kern-Engines (technisch)

### 4.1 Backtester — `app/backtester.py`
Streamlit-frei, injectable Fetchers. Replayt Wallet-Trades über 7/30/90 Tage. `BacktestConfig`: sizing_mode (`SIZING_FIXED`/`PERCENT`/`MIRROR`/`PORTFOLIO`), stake_value, max_stake, fee_bps, slippage_bps, `strategy` (`STRATEGY_COPY`/`FADE` — Fade kauft Gegenseite zu 1−p), `max_exposure_pct` (Cap auf offene Copies, Default 50%), `trader_portfolio_value` (für Match-Modus). `replay()` mit `schedule_resolution`/`settle_due`: Mid-Window-Auflösungen recyceln Cash/Exposure (RESOLVE-Zeilen zur echten end_time). `token_values` für alle traded market_keys vorgeladen. `strategy_comparison` simuliert, welches Sizing am besten gewesen wäre → im Equity-Chart als gepunktete Amber-Linie + Label. Ehrliche Flat-Curves (kein Schönfärben): bei hyperaktiven Wallets schrumpft das Fenster via API-Cap → amber Skip-Breakdown-Hinweis.

### 4.2 Insider-/Suspicion-Layer — `app/suspicion.py` + `src` Scorer
Event-/Wallet-Insider-Scores aus Whale-Flow (`whale_event_risk_scores`/`whale_wallet_risk_scores`, Bänder 40/55/70). **Kategorie-Kontext** (`classify_insider_context`): Sport-Odds und Wetter werden **ganz ausgeschlossen** (Spielergebnisse/Wettermodelle nicht insider-handelbar), Crypto/Market-Prices gedämpft (Toggle), Politik/Geopolitik/Awards/Corporate fokussiert; nutzt Parent-Event-Titel (Gamma) für neutrale Sub-Markt-Titel. Bonusse: Fresh-Wallet-Cluster, Coordinated-Cluster (5-min-Fenster). **Louvain-Co-Trading-Netzwerk** (`co_trading_network`, networkx `louvain_communities`, seed=42): Kanten = gleiche Seite ≥min_shared Märkte + ≥$10k Paar-Volumen; Insel-Layout + Klick-Isolation (plotly `on_select`), Klartext-Cluster-Stories. Kalshi: event-level (keine Wallet-Identitäten public → wallet-level Logik überspringt Kalshi-Zeilen, UI erklärt es).

### 4.3 Track-Record-Engine — `app/track_record.py` (WICHTIG: die vier Leaderboard-Korrekturen)
Kern-Trust-Differenzierer. Naive Leaderboards täuschen 4-fach; wir korrigieren jede und zeigen naive vs. korrigiert:
1. **NegRisk/Leg-Netting** — `market_records()` nettet pro conditionId, `event_records()` pro Event-Slug. Naive Tools zählen jedes Outcome-Leg separat → Win-Rate bis 2× aufgebläht.
2. **Settled-only PnL** — echte realized_pnl pro resolved Markt.
3. **Wash/Farmer-Flag** — hohes Volumen + ~0 Edge/Dollar.
4. **Survivorship** — Sample-Gate (≥10 Märkte/≥14 Tage), Profit-Konzentration (one-hit-wonder), Sharpe-artiger `risk_adjusted`, Composite 0–100 → Grade A–F.

**Echte Win-Rate + Datengrenze (zentral verstehen):** Polymarkets `/closed-positions` defaultet auf die **Top-50-Gewinner** (PnL-sortiert, hart bei 50 gekappt, offset ignoriert) → naiv sieht jede Wallet ~100% aus. Lösung: `get_polymarket_resolved_positions()` holt **beide Sort-Richtungen** (DESC-Gewinner ∪ ASC-Verlierer, dedup by market_key+outcome). Für **normale Wallets (≤50 je Seite) = vollständig → echte, verlässliche Win-Rate**. Für **hyperaktive (>50 Gewinne UND >50 Verluste) = `capped=True`** → ehrliches "EXTREMES ONLY"-Badge statt Fake-Zahl. Die Verteilungsmitte solcher Whales ist über die REST-Feeds **nicht** erreichbar. **Vollständige Lösung für ALLE = On-Chain-Indexing** (jeder Trade liegt auf Polygon, kein Cap; wie polymarketanalytics via Goldsky/Dune) — offener Skalierungsschritt, siehe §7.

### 4.4 WebSocket-Fast-Copy — `src/copy_trading.py` + `scripts/run_copy_trader.py`
On-Chain-`OrderFilled`-Polling war die langsamste Detection (Log ~2s nach off-chain Match). Jetzt: **RTDS-WebSocket** (`RTDS_WS_URL = wss://ws-live-data.polymarket.com`, `rtds_subscribe_payload()` = globaler Firehose weil Wallet-Filter upstream kaputt, `decode_rtds_trade` matcht `proxyWallet` clientseitig). `RtdsTradeListener` (Thread + websocket-client, PING, Queue, graceful ohne lib), `WsApplyWorker` (dedizierter Thread, WAL + busy_timeout, drain 0.5s). On-Chain bleibt Reconciliation; `_fill_already_recorded()` dedupt cross-path auf (wallet,tx,asset,side) — WS-Match-Zeit ≠ Block-Zeit, also greift der timestamp-dedup_key nicht. `reconcile_backoff_seconds` bei RPC-429. Latenz sub-Sekunde statt ~2s. Nächste Speed-Schritte (im Plan): Execution härten, Worker nach Dublin/London co-locaten (Polymarket-CLOB = AWS eu-west-2).

### 4.5 Signals/Alerts — `app/signals.py`
`build_monitor_signals` (inkl. "Volume anomaly": volume_1h ≥3× volume_24h/24, vol24≥$10k). Wiederverwendet von Monitor-Seite + Telegram-Scanner (`scripts/run_alert_scanner.py`, Dedup-State, Stop-File).

---

## 5. Datenquellen & ihre Grenzen (kritisch für weitere Recherche)

- **Polymarket Gamma** (Märkte/Metadaten/Kategorien), **Data-API** (Trades/Positionen/Activity/Leaderboard), **CLOB** (Orderbook/Preise). Public, kein Key. Limits: Global 15'000/10s, Gamma 4'000/10s, Data-API 1'000/10s (/trades 200), CLOB 9'000/10s. Drosselung = Cloudflare-Queueing.
- **Bekannte Caps/Fallen:**
  - `/activity` lehnt offset+limit > ~3000 ab (`fetch_window_trades` cappt bei 3000). **ABER** offset paginiert sonst sauber (2494+ Events über Seiten verifiziert).
  - `/closed-positions` **kappt bei ~50 Zeilen, offset ignoriert**, defaultet auf Gewinner; sortDirection ASC/DESC flippt welche 50 → Union-Trick (§4.3).
  - Worthless-expiry-Verlierer erzeugen **kein Redeem-Event** → in /activity unsichtbar.
- **Kalshi** (trade-api/v2): Märkte + Trades, **keine Wallet-Identitäten** (event-level only). `get_kalshi_markets(tickers=...)` reichert Trade-Ticker mit echten Titeln/Kategorien/End-Times an.
- **On-Chain (Polygon)** — die vollständige Lane: `OrderFilled`-Logs (Decoder existiert in copy_trading.py), Redeem-Events. Kein Cap. Für komplette Track-Records nötig (via Goldsky-Subgraph/Dune/eigener Indexer). Noch nicht für Analytics genutzt, nur für Copy-Detection.
- **Test-Wallet:** Swisstony `0x204f72f35326db932158cba6adff0b9a1da95e14` (~3000 Trades/Tag, hyperaktiv → Worst-Case für alle Cap-Themen).

---

## 6. Ops, Deploy, Security

- **Lokal:** 3 Windows Scheduled Tasks (`MarketIntelTerminal` :8503, `MarketIntelCopyDaemon`, `MarketIntelAlertScanner`) via `scripts/install_autostart.ps1`. Neustart: Stop-/Start-ScheduledTask.
- **Produktion (bereit):** `Dockerfile` (non-root, healthcheck, gehärtete Streamlit-Flags), `docker-compose.yml` (terminal + alert-scanner + caddy), `deploy/Caddyfile` (Auto-TLS, Security-Header). Secrets via Env (`.env`, `.streamlit/secrets.toml` — gitignored).
- **Auth:** `st.login()` + Google-OIDC, Settings failt closed hinter E-Mail-Allowlist (`app/authz.py`); ohne Secrets no-op (lokaler Research-Modus). Template `.streamlit/secrets.toml.example`.
- **Kosten-Schätzung öffentlicher Betrieb:** ~CHF 6–8/Mo (Hetzner CX23 + Domain, Cloudflare/TLS/Monitoring gratis). Details: [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md).

---

## 7. Offene Entscheidungen & Roadmap

**Sofort baubar, kein Rechtsrisiko:**
- **On-Chain-Indexer / vollständige Track-Records** — die "komplett für alle Wallets"-Version (§4.3, §5). Eigener Polygon-Log-Scan (Decoder da) oder Goldsky/Dune-Anbindung. Löst das 50er-Cap für Whales. **Nächste offene Produktentscheidung** (Aufwand/Kosten: Gratis-RPC langsam, Paid-RPC/Subgraph ~$0–50/Mo).
- Speed-Schritt 2/3 (Execution härten, Worker co-locaten) — relevant bei Live-Execution.
- Wallet-Connect read-only (React-Komponente wagmi/WalletConnect iframe + SIWE) — ~2–4 Tage. Streamlit kann kein natives web3-Frontend → iframe-Komponente nötig.
- Weitere Differenzierungs-Features (aus DIFFERENTIATION_STRATEGY.md): Cross-Venue reconciled PnL/Tax, Copy-Decay-Ehrlichkeit, Kalibrierungs-Dashboard ("war 70% wirklich 70%?"), Resolution-/UMA-Dispute-Alerts.
- Krypto-Zahlung (nach Launch): USDC-on-Polygon-Prepaid oder NOWPayments/CoinGate. Fiat (Stripe/MoR) zuerst.

**Strategische Entscheidung — NICHT ohne Anwalt:**
- **Live-Geld-Copytrading** — non-custodial Architektur geplant (Polymarket Builder-Program, getrennte maker/signer-Order-Felder), ABER **BGS Art. 130** (Bereitstellung technischer Mittel für GESPA-gesperrte Geldspiele, bis 3–5 J. Gefängnis; als CH-Resident kein Auslands-Schutz). Anwalts-Memo (CHF 5–25k) + CH+US-Geoblock + execution-only + benannte Entität zwingend VOR erstem Live-Trade. Details: [LIVE_COPYTRADING_PLAN.md](LIVE_COPYTRADING_PLAN.md).

**Firmenstruktur/Einnahmen:** Privatperson → Einzelfirma (erste Einnahmen, MoR für EU-MwSt) → GmbH (ab ~CHF 100k). Auslandsfirma bringt nichts (persönliche Strafbarkeit + Steuerfalle). Hebel = CH-Geoblocking + keine Referral-Links. Details: [LAUNCH_PLAN.md](LAUNCH_PLAN.md).

---

## 8. Wettbewerb (Kurzbild, für Research-Kontext)

Table-Stakes (haben alle): Whale-Feed, Insider-Score, Leaderboard, Copy, Telegram-Alerts. Hauptakteure: **Unusual Whales** (3M Follower, PM-only, monitoring-only), **Verso** (YC, Multi-Venue-Terminal), **Kreo** (Copy, unter Polymarket-Audit), **Oddpool** (YC, cross-venue Daten), **polymarketanalytics/polyloly/polywhaler**, **Dome** (von Polymarket gekauft), **Stand** (Polymarket-COPYCAT). Konsolidierung + Funding-Welle (5c(c) $35M-Fonds) → Zeitdruck. White-Space: echtes Cross-Venue-UI, korrekte verifizierbare Track-Records, ehrlicher Copy-Decay, Tax-Reconciliation, Kalibrierung, non-English, Mobile. Volle Analyse: [DIFFERENTIATION_STRATEGY.md](DIFFERENTIATION_STRATEGY.md).

---

## 9. Verweise (alle Docs im Repo)

- [HANDOFF.md](HANDOFF.md) — Schnellstart/Workflow/Konventionen zum Weiterbauen von jeder Maschine.
- [DIFFERENTIATION_STRATEGY.md](DIFFERENTIATION_STRATEGY.md) — Wettbewerb + Differenzierung + Bau-Plan.
- [LAUNCH_PLAN.md](LAUNCH_PLAN.md) — Kalshi-/Polymarket-Datenrechte, Auth-Outsourcing, CH-Firmenstruktur.
- [LIVE_COPYTRADING_PLAN.md](LIVE_COPYTRADING_PLAN.md) — Wallet-Connect, non-custodial Live-Copy, Speed, Krypto-Zahlung, Recht.
- [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) — Hosting, Security, CH-Recht, API-Limits, Einkaufsliste.

**Repo:** GitHub `Pablozh123/prediction-market-terminal`, Default-Branch `main`. **Verifikation:** `python -m unittest discover -s tests` (311), `python scripts/visual_smoke.py --base-url http://127.0.0.1:8503`.

---

## 10. Recherche-Startpunkte für die nächste Session

Sinnvolle Fragen, die dieses Dokument aufwirft und die als Nächstes recherchiert/entschieden werden könnten:
1. **On-Chain-Indexer:** Goldsky-Subgraph vs. Dune vs. eigener Polygon-Indexer — Kosten, Latenz, Wartung, Vollständigkeit für komplette Track-Records. (Löst die 50er-Cap-Grenze.)
2. **Cross-Venue reconciled PnL/Tax** — technische Umsetzung PM+Kalshi in einem Portfolio, Form-8949-Export.
3. **Kalibrierungs-Layer** — Brier-Score/Kalibrierungskurve pro Wallet aus resolved Märkten (Researcher-/Credibility-Funnel).
4. **Wallet-Connect (read-only)** — konkrete Streamlit-React-Komponente + SIWE-Flow.
5. **Go-to-Market** — Zielsegment (Sharps/Quant/Researcher), Pricing-Tier-Design, Free-Funnel.
6. **Rechts-Memo** (nur falls Live-Copy) — Schweizer Gaming-/Fintech-Anwalt zu BGS Art. 130 + Geoblocking.
