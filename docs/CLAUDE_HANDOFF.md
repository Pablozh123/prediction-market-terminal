# Claude Desktop Handoff

Stand: 2026-06-10
Projekt: `C:\Users\chole\Projects\prediction-market-terminal`
Remote: `https://github.com/Pablozh123/prediction-market-terminal.git`
Aktueller Branch: `codex/follow-traders-ui-split-fixes`

## Wichtigster Zustand

Der Arbeitsbaum war vor diesem Handoff sauber. Der aktuelle Branch ist 16 Commits vor `main` und auf `origin/codex/follow-traders-ui-split-fixes` vorhanden. `main` ist daher nicht der neueste Entwicklungsstand.

Claude soll fuer die naechste Arbeit entweder direkt diesen Branch auschecken oder einen neuen Branch davon ableiten:

```powershell
cd C:\Users\chole\Projects\prediction-market-terminal
git fetch origin
git switch codex/follow-traders-ui-split-fixes
git pull --ff-only
```

Optional fuer eigene Arbeit:

```powershell
git switch -c claude/<kurzer-task-name> codex/follow-traders-ui-split-fixes
```

## Was seit `main` dazugekommen ist

Die folgenden Commits liegen auf dem aktuellen Branch ueber `main`:

- `070e795 feat: add smart trader ranking`
- `6d6a8df feat: add whale flow advanced behavior filters`
- `5fd36f4 feat: finalize whale flow insider risk scoring`
- `9c821c2 feat: add whale flow risk scoring`
- `5b6214d feat: add portfolio-relative copy sizing controls`
- `c789615 feat: focus track page on wallet trade tape`
- `778815c fix: reduce placeholder actions on trader and market pages`
- `305f65b feat: add copy trading command center`
- `7794a2a fix: make workspace navigation buttons switch pages`
- `d2d4a64 feat: allow tiny paper copy orders`
- `f20d66b fix: avoid bool fill warning in related markets`
- `496cb2f fix: simplify live trades filter row`
- `db615f3 chore: add copy trader watchdog starter`
- `4950af1 refactor: extract copy follow app helpers`
- `589ea5c feat: add copy follow controls to trader views`
- `518281d fix: normalize boolean masks without pandas warning`

## Current Product Surface

Die App ist ein Streamlit-PredictParity-Clone mit lokalen Forschungsfunktionen:

- Overview, Search, Markets, Traders, Track, Live Trades, Whale Flow, Cross-Venue, Monitor, Alerts, Resolved, Portfolio, Copy Trade.
- Copy Trade bleibt paper-only. Keine echten Orders, keine Private Keys, keine Secrets.
- Swisstony Wallet: `0x204f72f35326db932158cba6adff0b9a1da95e14`.
- Copy-Trading hat SQLite-Persistenz, Baseline-Seeding, Settlements/Redeems, Auto-Topups, Follow/Unfollow-Controls und dynamische Portfolio-relative Sizing-Controls.
- Whale Flow enthaelt Insider-Risk/Behavior-Filter wie Contrarian, Trend Follower, Lottery Ticket und Whale Splash.
- Track fokussiert inzwischen auf Wallet-Trade-Tape mit Eingabe einer Wallet und tabellarischer Trade-Uebersicht.

## Nicht anfassen ohne explizite Entscheidung

- Kein Live-Trading aktivieren.
- Keine Private Keys oder API-Secrets in Dateien schreiben.
- `data/`, `outputs/`, `artifacts/`, `.venv_tracking/`, `.git_kaputt_backup/` und alte Analyseartefakte nicht committen.
- `prediction_terminal.py` nur mit klar begrenztem Scope bearbeiten; diese Datei ist der Haupt-Konfliktpunkt.
- Keine grossen Refactors im Monolithen starten, wenn eigentlich ein Produkt-/UI-Fix gefragt ist.

## Wichtige Dateien

- `prediction_terminal.py` - Streamlit UI und Seitenrenderer.
- `src/prediction_markets.py` - Polymarket/Kalshi/PredictParity Public API und Analytics.
- `src/copy_trading.py` - Paper-Copy-Trading Engine und SQLite-Modell.
- `app/format.py` - extrahierte Formatter.
- `app/filters.py` - extrahierte Filter-Helfer.
- `scripts/run_copy_trader.py` - optionaler Paper-Copy-Daemon.
- `scripts/start_copy_trader_watchdog.ps1` - Watchdog-Starter fuer Paper-Copy-Sync.
- `docs/COLLAB.md` - Kollaborationsregeln.
- `docs/PHASE1_CLONE_AUDIT.md` - Phase-1-Audit.
- `docs/spec_multitrader_copytrading.md` - Multi-Trader-Spec.

## App starten

```powershell
cd C:\Users\chole\Projects\prediction-market-terminal
python -m streamlit run prediction_terminal.py --server.address=127.0.0.1 --server.port=8503
```

Browser:

```text
http://127.0.0.1:8503/
```

Optionaler Paper-Copy-Daemon:

```powershell
python scripts/run_copy_trader.py --interval 1 --api-interval 30 --settlement-interval 180
```

## Verification Gates

Vor jedem Commit mit Codeaenderungen mindestens:

```powershell
python -m py_compile prediction_terminal.py src\prediction_markets.py src\copy_trading.py
python -m unittest discover -s tests -p test_*.py
```

Bei UI-/Routing-Aenderungen zusaetzlich, waehrend Streamlit laeuft:

```powershell
python scripts/smoke_routes.py
python -m scripts.visual_smoke --base-url http://127.0.0.1:8503 --output-dir artifacts\visual_smoke --timeout-ms 45000
```

## Empfohlene naechste Aufgaben fuer Claude

1. Review des aktuellen Branches gegen `main`: Sind die 16 Commits produktreif und sinnvoll in einem PR zusammenzufassen?
2. UI-Review der Copy-Trade-Seite: Stats, PnL-Kurve, Followed-Trader-Panel, Dynamic-Sizing-Controls und Paper-only-Wording pruefen.
3. Whale-Flow-Review: Pruefen, ob Insider-Risk-Scores und Behavior-Filter verstaendlich und nicht ueberladen sind.
4. Testspezifikation erweitern: Welche UI-Smokes fehlen fuer Track, Copy Trade und Whale Flow?
5. Danach erst Implementierung: kleine Branches, kleine Commits, keine parallelen Edits an `prediction_terminal.py` durch mehrere Agenten.

## Git-Regeln fuer Claude Desktop

Vor Arbeitsbeginn:

```powershell
git status --short
git branch --show-current
git fetch origin
git pull --ff-only
```

Vor Commit:

```powershell
git status --short
git diff --stat
python -m py_compile prediction_terminal.py src\prediction_markets.py src\copy_trading.py
python -m unittest discover -s tests -p test_*.py
```

Commit-Beispiel:

```powershell
git add docs/<datei>.md
git commit -m "docs: update Claude handoff"
git push -u origin claude/<kurzer-task-name>
```

Wenn Claude nur reviewt, soll Claude Findings in `docs/` schreiben und nicht direkt grosse Code-Dateien anfassen.
