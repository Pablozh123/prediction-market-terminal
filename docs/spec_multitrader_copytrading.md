# Spec: Multi-Trader-Copytrading (Paper)

Status: Entwurf v2 (Entscheidungen eingearbeitet) · Owner: Claude · Branch: `claude/multitrader-spec` · Umsetzung: Codex

## 1. Ziel und Abgrenzung

Das bestehende Paper-Copytrading kopiert genau **ein** Polymarket-Wallet (Swisstony). Ziel ist die Erweiterung auf **mehrere Trader**, mit zwei Nutzungsarten:

- **Beliebiges Wallet folgen** (Kernfunktion): der Nutzer gibt irgendein Polymarket-Wallet an und kopiert es.
- **Entdeckungs-Liste**: ein nach ROI geranktes Leaderboard schlägt am Anfang die besten Wallets vor, damit man nicht bei null anfängt.

Jeder gefolgte Trader bekommt ein **eigenes simuliertes Konto** (Sub-Portfolio). So lässt sich jeder Trader fair und einzeln auswerten.

Im Scope: Polymarket (on-chain + Public API), Paper-Modus, beliebiges Folgen + ROI-Ranking, Sub-Portfolios, Gleichverteilung, Pro-Trader-Reporting. Nicht im Scope: echtes Order-Routing (`live_trading_enabled` bleibt `false`) und Kalshi-Wallet-Copy (siehe Abschnitt 4).

## 2. Getroffene Entscheidungen

1. **Konto-Modell:** eigener Topf je Trader (Sub-Portfolio), nicht gemeinsam.
2. **Ranking:** beliebiges Wallet folgen ist möglich; zum Start werden die besten nach **ROI + Mindestaktivität** vorgeschlagen.
3. **Allokation:** gleich verteilt — jeder Trader startet mit demselben Spielgeld-Betrag.
4. **Migration:** Swisstony wird als erster Trader übernommen.

## 3. Ist-Zustand (Basis: `src/copy_trading.py`)

Die Engine ist SQLite-gestützt und teils schon wallet-bewusst:

- `CopySettings` hält ein einzelnes `target_wallet`, `copy_scale` (1 %), `max_order_equity_pct` (5 %), `paper_start_cash` plus dynamisches Sizing, an den Ziel-Wallet gekoppelt.
- Tabelle `paper_orders` enthält bereits **`source_wallet`** — Orders sind pro Quelle zuordenbar.
- Tabelle `positions` ist ein **gemeinsames** Depot (Schlüssel `asset`).
- Tabelle `tony_positions` spiegelt die Positionen des einen Ziel-Wallets.
- `cash` und Wallet-Stats liegen einzeln im `meta`-Store; `cash_events` kennt keine Wallet-Spalte.

Für Sub-Portfolios muss also das **Geld- und Positions-Modell pro Wallet getrennt** werden.

## 4. Soll-Architektur

### 4.1 Datenmodell (Sub-Portfolio je Trader)

Neue Tabelle `traders` (eine Zeile je gefolgtem Wallet, je mit eigenem Konto):

| Spalte | Typ | Bedeutung |
|---|---|---|
| `wallet` | TEXT PK | Polymarket-Proxy-Wallet |
| `label` | TEXT | Anzeigename (z. B. X-Handle) |
| `active` | INTEGER | 1 = wird kopiert |
| `start_cash` | REAL | Startkapital dieses Sub-Kontos |
| `cash` | REAL | aktueller Barbestand des Sub-Kontos |
| `copy_scale_override` | REAL NULL | überschreibt globales `copy_scale` |
| `rank_score` | REAL | zuletzt berechneter ROI-Score |
| `added_at` / `updated_at` | TEXT | Zeitstempel |

Generalisierungen am bestehenden Schema, damit jedes Sub-Konto getrennt geführt wird:

- `positions` → Schlüssel von `asset` auf **`(trader_wallet, asset)`** umstellen (jedes Sub-Konto hat eigene Positionen).
- `cash_events` → Spalte `trader_wallet` ergänzen (Cash-Bewegungen je Sub-Konto).
- `tony_positions` → **`source_positions(wallet, asset, …)`** (Spiegel der realen Positionen jeder gefolgten Quelle).
- Wallet-Stats aus dem `meta`-Store in **`trader_stats(wallet, roi, pnl, win_rate, trades, volume, last_refresh)`**.
- `paper_orders.source_wallet` bleibt der Anker für Orders und Attribution.

Gesamt-Equity = Summe der Sub-Konto-Equities.

### 4.2 Beliebiges Wallet folgen + ROI-Ranking

- **Folgen:** UI-Aktion „Wallet folgen" (Eingabe einer Adresse **oder** Knopf im Leaderboard/Wallet-Analyzer) → neue Zeile in `traders` mit `start_cash`, Sync startet.
- **Ranking (Vorschläge):** Datenquelle existiert (`src/prediction_markets.py`: PnL, Win-Rate, Trades, Volumen). Score primär nach **ROI** (Rendite in %, misst Können statt Kapitalgrösse), mit Mindestschwellen gegen Glückstreffer.
- Schwellen (Vorschlag, anpassbar): min. 50 abgeschlossene Trades, positiver ROI, in den letzten 30 Tagen aktiv.

### 4.3 Allokation und Sizing

Gleichverteilung über **gleiches Startkapital je Sub-Konto**: ein konfigurierbares `per_trader_start_cash` (z. B. 1000 $), identisch für alle. Vorteil: gleiche Startlinie → faire Pro-Trader-Vergleiche, und das Hinzufügen/Entfernen eines Traders stört die anderen nicht.

Pro Order im jeweiligen Sub-Konto:

```
order_notional = quelle_notional * effektiver_copy_scale(trader)
gedeckelt durch max_order_equity_pct * equity(sub_konto)
```

Risikograenzen pro Sub-Konto: Markt-Cap (Diversifikation), kein Kauf bei zu wenig Cash. Das bisherige dynamische Sizing wird von „an Tony gekoppelt" auf „pro Sub-Konto" verallgemeinert.

### 4.4 Sync-Engine

- `sync_copy_trades` / `sync_onchain_copy_trades` über alle aktiven Trader iterieren; Buchung jeweils ins richtige Sub-Konto.
- `trade_dedup_key` muss den Wallet enthalten (prüfen, sonst ergänzen).
- `seed_tony_positions` → `seed_source_positions(wallet, …)`.
- `scripts/run_copy_trader.py` liest die Wallet-Liste aus `traders` (`active=1`) statt einer Konstante.

### 4.5 UI (`prediction_terminal.py`, Owner Codex — siehe Scope-Grenze unten)

- „Wallet folgen / entfolgen" im Leaderboard und Wallet-Analyzer.
- Copytrading-Seite mit Trader-Liste, Sub-Konto-Kennzahlen (Cash, Equity, ROI), Aktiv-Schalter und Startkapital-Einstellung.
- Bestehende Filter/Komponenten wiederverwenden.

### 4.6 Reporting und Attribution

Da jeder Trader ein eigenes Sub-Konto hat, ist die Pro-Trader-Performance direkt ablesbar (Equity-Kurve je Wallet). Zusätzlich Detail-Drilldown über `paper_orders` nach `source_wallet`.

## 5. Kalshi-Abgrenzung

Kalshi-Public-Feeds geben **keine** Wallet-/Trader-Identitäten preis. Trader-Copy aus Public Data ist auf Kalshi grundsätzlich nicht möglich. Stattdessen: bestehende Cross-Venue-Signale (Preis-Gaps Polymarket↔Kalshi). In der Thesis als Daten-Boundary dokumentieren.

## 6. Migration (Swisstony übernehmen)

Swisstony wird als **erster Trader** angelegt: Zeile in `traders` mit eigenem `start_cash`, bestehende `tony_positions` nach `source_positions` übertragen, bisherige `paper_orders` (haben schon `source_wallet`) seinem Sub-Konto zuordnen, Cash/Equity konsistent setzen. So bleibt der bisherige Verlauf erhalten.

## 7. Umsetzungsschritte für Codex (geordnet)

1. Schema-Migration: `traders`, `source_positions`, `trader_stats`; `positions`/`cash_events` um `trader_wallet`; `init_db` + Migrationspfad für Swisstony.
2. Engine von einem `target_wallet` auf die aktive Trader-Liste mit Sub-Konten umstellen.
3. Sizing/Cash pro Sub-Konto; dynamisches Sizing verallgemeinern.
4. ROI-Ranking + Schwellen (für die Vorschlagsliste).
5. UI: Folgen/Entfolgen, Sub-Konto-Reporting, Startkapital.
6. `run_copy_trader.py` auf Multi-Wallet.
7. Tests in `tests/test_copy_trading.py` erweitern (Mehr-Wallet-Dedup, Sub-Konto-Buchung, ROI-Ranking, Migration).

Nach jedem Schritt: `python -m py_compile`, Tests, committen.

## 8. Scope-Grenze gegenüber dem Phase-1-Terminal

Codex' Dauerauftrag ist der exakte Nachbau von Phase-1-Terminal.com. Multi-Trader-Copytrading ist eine **bewusste Erweiterung darüber hinaus**, kein Teil des Klons. Damit beide Ziele sich nicht widersprechen: die Copytrading-Funktion als eigene Schicht/Seite halten, möglichst getrennt von den Klon-Teilen in `prediction_terminal.py`, und die Umsetzung an einem stabilen Klon-Meilenstein oder im isolierten Modul einplanen. Codex' Ziel sollte diese Grenze explizit kennen, damit es das Copytrading nicht als „nicht in Phase-1-Terminal" zurückbaut.

## 9. Anknüpfung an die Bachelorarbeit

Eigene Sub-Konten je Trader liefern direkt vergleichbare Equity-Kurven — empirisches Material zur Forschungsfrage: Gibt es auf Polymarket persistente, kopierbare Überrenditen, oder verschwindet der Vorsprung profitabler Wallets (informationelle Effizienz)? Die Kalshi-Boundary (Abschnitt 5) ist eine sauber begründbare Methodik-Limitation.
