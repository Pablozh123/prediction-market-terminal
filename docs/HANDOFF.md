# Handoff — Prediction Market Terminal

Single entry point to continue this project from any machine. Stand: 2026-06-12.

> Hinweis: Dies ist ein **legales Daten-/Analyse-Produkt** für öffentliche Polymarket-/Kalshi-Daten. Alle Rechtsthemen in den Plan-Dokumenten sind reine Compliance-Recherche für ein Memo — keine Umsetzung ohne Anwalt.

---

## 1. Was das Projekt ist

Streamlit-Research-Terminal für Polymarket & Kalshi: Marktentdeckung, Trader-/Wallet-Research, Live-Flow, Whale/Insider-Risk-Screening, Backtesting, Alerts, Tracking, Portfolio und **Paper-only** Copy-Trading. Alle Daten aus öffentlichen APIs. Kein Live-Handel, keine Custody.

- **Sprache/Stack:** Python 3.13/3.14, Streamlit 1.5x (Monolith `prediction_terminal.py`, ~11k Zeilen), pandas, plotly, networkx, websocket-client.
- **Live lokal:** http://127.0.0.1:8503 (Windows Scheduled Task `MarketIntelTerminal`).
- **Repo:** GitHub `Pablozh123/prediction-market-terminal`, Default-Branch `main`.
- **Aktueller Stand:** **259 Unit-Tests grün** (`python -m unittest discover -s tests`), voll gepusht (lokal == origin).

## 2. Schnellstart auf einer neuen Maschine

```bash
git clone https://github.com/Pablozh123/prediction-market-terminal.git
cd prediction-market-terminal
python -m pip install -r requirements.txt          # streamlit, requests, pandas, plotly, dnspython, networkx, websocket-client
python -m streamlit run prediction_terminal.py --server.address=127.0.0.1 --server.port=8503
```

Hintergrund-Runner (optional, Paper-only):
```bash
python scripts/run_copy_trader.py     # Copy-Daemon: WS-Detection + On-Chain-Reconciliation + API/Settlement
python scripts/run_alert_scanner.py   # Telegram-Alert-Scanner (Token via Env, siehe .env.example)
```

Produktion: `docker compose up -d --build` (Terminal + Alert-Scanner + Caddy). Siehe [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md).

Verifikation:
```bash
python -m py_compile prediction_terminal.py src/prediction_markets.py src/copy_trading.py
python -m unittest discover -s tests          # ~241 Tests
python scripts/visual_smoke.py --base-url http://127.0.0.1:8503   # Playwright via System-Chrome
```

## 3. Strategie-/Plan-Dokumente (alles recherchiert, mit Quellen)

| Doc | Inhalt |
|---|---|
| [LAUNCH_PLAN.md](LAUNCH_PLAN.md) | Kalshi behalten (Builders-Bewerbung), Polymarket-ToS/Limits (Builder-Profil), **Auth-Outsourcing** (st.login + Google → Auth0), CH-Firmenstruktur (Einzelfirma→GmbH, Geoblocking, kein Auslands-Wrapper) |
| [LIVE_COPYTRADING_PLAN.md](LIVE_COPYTRADING_PLAN.md) | **Speed** (WS statt On-Chain), Wallet-Connect (React-Komponente + SIWE), Live-Copy non-custodial (Builder-Program, maker/signer, **BGS Art. 130 → Anwalt zwingend**), Krypto-Zahlung |
| [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) | Hosting (Hetzner VPS + Docker + Caddy + Cloudflare ~CHF 6-8/Mo), Security-Checkliste, CH-Recht, API-Limits, Einkaufsliste |

## 4. Roadmap — was fehlt noch

**Sofort baubar, kein Rechtsrisiko:**
1. ✅ **Speed Schritt 1** — WS-Detection (RTDS `activity/trades`) — ERLEDIGT (PR #26/#27, siehe §6).
2. ⬜ **Speed Schritt 2** — Execution härten: keep-alive HTTPS zu clob.polymarket.com, gecachte L2-Creds, vorgeladene tick sizes, FOK-Orders via py-clob-client. (Erst relevant bei Live-Execution.)
3. ⬜ **Speed Schritt 3** — Worker nach Dublin/London co-locaten (AWS eu-west-2). Beim öffentlichen Deploy ohnehin EU-VPS.
4. ✅ **Auth** — ERLEDIGT (siehe §7): echtes `st.login()` + Google-OIDC, Settings fail-closed hinter E-Mail-Allowlist, Fake-Auth-Shell entfernt; ohne Secrets komplett no-op. Setup: `.streamlit/secrets.toml.example`.
5. ⬜ **Wallet-Connect read-only** (polywhaler-Stil) — eigene React-Komponente (wagmi/WalletConnect iframe) + SIWE. ~2-4 Tage. **← nächster autonom baubarer Schritt.**
6. ⬜ **Krypto-Zahlung** — erst nach Launch wenn nachgefragt: USDC-on-Polygon 30-Tage-Prepaid oder NOWPayments/CoinGate. Fiat (Stripe/MoR) zuerst.
7. ⬜ **Production-Deploy** — Domain + Hetzner-VPS kaufen (**User-Entscheidung/Kauf nötig**), `docker compose up`, Cloudflare davor, Impressum + DSE, CH-Geoblocking-Regel. Auth-Voraussetzung ist jetzt erfüllt.

**Strategische Entscheidung — NICHT ohne Anwalt:**
8. ⬜ **Live-Geld-Copytrading** — non-custodial Architektur steht im Plan, aber **BGS Art. 130** (Bereitstellung technischer Mittel für GESPA-gesperrte Geldspiele, bis 3-5 J. Gefängnis; als CH-Resident kein Auslands-Schutz). Anwalts-Memo (CHF 5-25k), CH+US-Geoblock, execution-only, benannte Entität zwingend VOR dem ersten Live-Trade. Insider-Screen als Research/Warnung positionieren, nicht als "tail-the-insider"-Copy (Polymarket auditiert solche Apps seit 04/2026).

## 5. Schlüsseldateien

| Datei | Zweck |
|---|---|
| `prediction_terminal.py` | Streamlit-App, alle 15 Workspaces + UI |
| `src/prediction_markets.py` | Öffentliche API-Clients (Polymarket Gamma/Data/CLOB, Kalshi) + Analytics |
| `src/copy_trading.py` | SQLite Paper-Copy-Engine + **WS-Detection** (RtdsTradeListener, decode_rtds_trade, apply_ws_trades) |
| `app/backtester.py` | Streamlit-freie Backtest-Engine (copy/fade, 4 Sizing-Modi, Exposure-Cap) |
| `app/suspicion.py` | Insider-Risk-Scoring, Cluster, Louvain-Co-Trading-Netzwerk |
| `app/signals.py` | Monitor-Signal-/Regel-Logik (geteilt mit Scanner) |
| `app/app_settings.py` | Persistente Settings (`data/app_settings.json`) + Env-Override für Secrets |
| `app/authz.py` | Streamlit-freie Admin-Gating-Logik (Provider-Detection, Allowlist, fail-closed) |
| `.streamlit/secrets.toml.example` | Google-OIDC + Admin-Allowlist Template für `st.login()` |
| `scripts/run_copy_trader.py` | Copy-Daemon-Loop (WS-Drain → On-Chain-Reconcile → API/Settlement) |
| `scripts/run_alert_scanner.py` | Alert-Scanner mit Telegram |
| `scripts/install_autostart.ps1` | Registriert die 3 Windows Scheduled Tasks |
| `Dockerfile` / `docker-compose.yml` / `deploy/Caddyfile` | Produktions-Deploy |

## 6. WebSocket-Fast-Copy (PR #26 + #27)

**Warum:** On-Chain `OrderFilled`-Polling war die langsamste Detection (Log erscheint ~2s nach dem off-chain Match). Lösung: RTDS-WebSocket sieht den Match sofort.

- `src/copy_trading.py`: `RTDS_WS_URL`, `rtds_subscribe_payload()` (leerer Filter = globaler Firehose, da Wallet-Filter upstream kaputt), `decode_rtds_trade(message, target_wallets)` (matcht `proxyWallet` clientseitig, normalisiert auf dieselbe source_trade-Form wie der On-Chain-Decoder), `RtdsTradeListener` (Thread + websocket-client, PING, Queue, graceful wenn lib fehlt), `apply_ws_trades(trades, settings, db_path)`.
- **Cross-Path-Dedup:** `_fill_already_recorded()` in `apply_paper_trade` dedupt auf stabiler Identität (wallet, tx, asset, side) — ohne timestamp/price, die zwischen WS-Match-Zeit und Block-Zeit driften. So kopiert die langsamere On-Chain-Reconciliation einen vom WS bereits kopierten Fill nicht doppelt.
- `scripts/run_copy_trader.py`: Listener-Lifecycle, `--disable-ws` Flag, ws-Status-Felder. On-Chain bleibt als Fallback/Reconciliation.
- **`WsApplyWorker` (Nachbesserung):** Das ursprüngliche Design drainte den WS im Main-Loop — dessen blockierende Reconciliation-Syncs (On-Chain gegen rate-limitenden RPC, API-Sweeps, Settlements) stauten die Queue, live: **WS-Median 105s, der 30s-API-Fallback überholte den "schnellen" Pfad**. Jetzt bucht ein dedizierter Thread (`ct.WsApplyWorker`, drain alle 0.5s, eigene SQLite-Connection; WAL + busy_timeout 30s machen Cross-Thread-Writes sicher, Dedup-Keys halten die Pfade idempotent). Status-Feld `ws_worker` (last_result/latency/totals). Dazu `reconcile_backoff_seconds`: On-Chain-Sweep backt bei RPC-429-Serien exponentiell aus (30s→…→600s cap) statt alle 30s sinnlos zu blocken (`rpc_fail_streak` im Status).
- Tests: `tests/test_copy_trading.py::WsDetectionTests` (7) — decode, wallet-matching, flat/nested messages, baseline, unseeded-skip, Cross-Path-Dedup — plus `WsApplyWorkerTests` (3) und `ReconcileBackoffTests` (3).

## 7. Auth & Admin-Gating (zuletzt gebaut)

**Warum:** Vor dem Public-Deploy müssen Settings (Datenknöpfe, Telegram-Secrets, Copy-Daemon-Steuerung) geschützt sein; die alte Sign-in/Sign-up-Shell war reine Attrappe.

- **Ohne `.streamlit/secrets.toml [auth]`** läuft alles wie bisher: kein Login-UI, Settings offen (lokaler Research-Modus). Komplett no-op — Tests und lokale Nutzung unverändert.
- **Mit `[auth]`-Secrets** (Template: `.streamlit/secrets.toml.example`, Google-Cloud-Anleitung inline): Sidebar zeigt "Sign in with Google"/"Sign out" (`st.login()`/`st.logout()`), und die Settings-Seite **failt closed** — nur eingeloggte Accounts auf der Admin-Allowlist (`ADMIN_EMAILS`-Env hat Vorrang, sonst `[admin].emails` in secrets.toml) sehen die Seite. Alle anderen Workspaces bleiben öffentlich. Eingeloggt-aber-ohne-Allowlist ⇒ ebenfalls gesperrt (reason `no_allowlist`).
- Logik Streamlit-frei in `app/authz.py` (19 Tests): `auth_provider_from_secrets` (None=aus, `""`=flacher Default-Provider, Name=`[auth.<name>]`-Subsection), `normalize_emails`, `admin_emails` (Env > Secrets), `settings_access` → reasons `open`/`login_required`/`no_allowlist`/`not_allowed`/`ok`.
- Terminal-Seite: `current_auth_provider`/`current_user_email`/`settings_admin_emails`/`trigger_login` + `render_settings_gate`; Gate-AppTests in `tests/test_app_smoke.py::AuthGateSmokeTests` (Settings offen ohne Secrets, gesperrt mit Secrets + anonym).
- Entfernt: Fake-Auth-Dialog, `/sign-in`-/`/sign-up`-Routen (`md.local_auth_route_mode` inkl. Test), Sidebar-Fake-Buttons, `.auth-note`-CSS; Smoke-Skripte bereinigt.
- Deploy: secrets.toml ist git- UND docker-ignored; `docker-compose.yml` hat einen auskommentierten read-only-Mount. `Authlib` in requirements (st.login-Dependency). Cookie fix 30 Tage; requirements pinnen streamlit ≥1.58 (1.57-Cookie-Regression).

## 8. Dev-Workflow & Konventionen (WICHTIG)

- **Immer Branch VOR Änderungen** (nach jedem Merge): `git checkout -b claude/<slug> main`.
- **Verifizieren** vor Commit: `py_compile` + `unittest discover` + ggf. AppTest-Smoke (temp Streamlit auf Port **8504**, nie die Produktion 8503).
- **Commit-Message via Datei** (PowerShell verhackt `-m` mit Quotes/Newlines): in `.git_commit_msg.txt` schreiben → `git commit -F .git_commit_msg.txt` → Datei löschen. Message endet mit `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- **PR via GitHub REST API** (gh CLI ist nicht authentifiziert): Token in **Bash** holen — `TOKEN=$(printf 'protocol=https\nhost=github.com\n' | git credential fill | grep '^password=' | cut -d= -f2)`; JSON-Payload via python json.dumps in eine Datei **IM Repo-Dir** (nicht /tmp); `curl --data-binary @file .../pulls` dann PUT `.../merge {"merge_method":"merge"}`.
- **Nach Merge:** `git checkout main && git pull --ff-only`; Live-App neu starten: `Stop-ScheduledTask MarketIntelTerminal; sleep 3; Start-ScheduledTask MarketIntelTerminal; sleep 15`; `http://127.0.0.1:8503/healthz` == 200.
- **PowerShell-Gotcha:** kein Heredoc (`python - <<'PY'` ist Parser-Fehler) — temp-Datei via Write, dann ausführen.

## 9. Betrieb

- **3 Windows Scheduled Tasks** (User-Logon, via `scripts/install_autostart.ps1`): `MarketIntelTerminal` (8503), `MarketIntelCopyDaemon`, `MarketIntelAlertScanner`. Neustart-Muster: Stop-/Start-ScheduledTask.
- **Secrets** via Env (`.env`, gitignored): `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` übersteuern `data/app_settings.json`, nie zurückgeschrieben. Copy-Daemon-Env in `.env.example`.
- **Daten** (`data/`, gitignored): `app_settings.json`, `copy_trading.sqlite`, Watchlists, Scanner-State.

## 10. Offene Punkte / Gotchas

- Polymarket data-api `/activity` lehnt offset+limit > ~3000 ab → `fetch_window_trades` cappt bei 3000.
- Hyperaktive Wallets (z.B. Swisstony `0x204f72f35326db932158cba6adff0b9a1da95e14`, ~3000 Trades/Tag) → "30d"-Backtest-Fenster schrumpft via API-Cap auf Stunden; das ist ehrlich, im UI erklärt.
- Kalshi liefert keine Wallet-Identitäten → wallet-level Logik überspringt Kalshi-Zeilen, UI sagt es.
- **Copy-Trading-Ökonomie:** Swisstony VERKAUFT nie (487 Buys / 0 Sells in 45 min) — er recycelt über Resolution/Redeem/Merge und ist ~100% investiert. Die Kopie ist deshalb strukturell fast voll deployed; Cash kommt nur über Settlements zurück. `auto_top_up_enabled` ist seit PR #30 **default OFF** (hatte still 13×$1000 nachgeschossen); Einzahlungen trackt `ct.total_contributions()` (traders.start_cash + cash_events); echte Equity-Kurve via `equity_snapshots`-Tabelle (Daemon schreibt ~60s-Snapshots, Page throttled 300s). Trader-PnL-Kurven kommen vom offiziellen `user-pnl-api.polymarket.com` (`md.get_polymarket_user_pnl`).
- **Copy-Fidelity (Ziel: skalierte 1:1-Spiegelung der Source-Kurve):** `dynamic_scale_max` default **0 = uncapped** (der alte 1%-Deckel kostete ~21% Treue bei neutraler Ratio 1.27%); `cash_throttle_pct` default 0.25 = eine Order darf max. 25% des Rest-Cash ausgeben → in Engpässen schrumpfen ALLE Kopien gleichmäßig statt dass spätere komplett skippen (eine harte Cash-Reserve verschiebt nur die Wand und bringt nichts); Settlement-Sync 180s→90s. Jede Order speichert `desired_notional` (gewollt bei konfigurierter Skala) → `app/copy_fidelity.py` rechnet Config-Fidelity (effektiv vs. neutral, Faktoren je Knopf), Execution-Fidelity (filled/desired 24h, Verlust-Breakdown) und das PnL%-Overlay Paper vs. Source (aus equity_snapshots − contributions vs. user-pnl-api). UI: Tab "Copy fidelity" auf der Copy-Trade-Seite + Config-Fidelity-Metrik/Warnung im Sizing-Expander. Legacy `tony_*`-Meta-Keys schreibt nur noch der `target_wallet` (andere Trader clobberten sie — edenmoons 44.7k stand als "Tony Equity" da).
- `preview_screenshot` MCP timeoutet auf dieser App → Playwright via System-Chrome nutzen (`scripts/visual_smoke.py`).
- Memory liegt unter `~/.claude/projects/.../memory/` und ist **gitignored** — reist NICHT mit dem Repo. Dieses Handoff-Doc ist die repo-gebundene Wahrheit. Die volle Projekt-Historie (Runde 1-25 + Gotchas) steht dort in `backtester-polyhuntr-ui-milestone.md`.

## 11. Nächster konkreter Schritt

Zwei Kandidaten (Roadmap §4):

- **Production-Deploy (#7)** — der eigentliche Launch: Domain + Hetzner-VPS kaufen (**User-Entscheidung, kostet Geld**), `docker compose up`, Cloudflare davor (inkl. CH-Geoblocking-Regel), Impressum + DSE. Auth-Voraussetzung ist erfüllt; Anleitung in [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md).
- **Wallet-Connect read-only (#5)** — autonom baubar ohne Käufe: eigene React-Komponente (wagmi/WalletConnect) + SIWE, ~2-4 Tage. Details in [LIVE_COPYTRADING_PLAN.md](LIVE_COPYTRADING_PLAN.md) §2.
