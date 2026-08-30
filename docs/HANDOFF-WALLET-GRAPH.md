# Handover: Wallet-Graph (Recherche & Produktvorschlag)

> Übergabe-Dokument aus der Claude-Code-Session „Wallet-Graph-Recherche" vom 27.08.2026
> (Session-Name für Peer-Nachrichten, solange sie läuft: `prediction-market-terminal-78`).
> Zweck: Claude auf einem anderen Rechner kann hiermit ohne die Original-Session weiterarbeiten.

## Auftrag

Das Copy-Trading-Terminal soll zu einem vollumfänglichen **Screening-Tool** ausgebaut werden,
das auffällige Wallets **verknüpft** (Cluster statt Einzelbewertung). Vorbild-Recherche:
Bubblemaps u.a. Ergebnis der Session ist ein Dossier mit Marktanalyse und Produktvorschlag.

**Das vollständige Dossier (Artefakt, kontogebunden, auf jedem Gerät abrufbar):**
https://claude.ai/code/artifact/1559e64a-979d-4c14-a8aa-ec6e2ac8ac3f

## Rechercheergebnisse (Kurzfassung)

1. **Bubblemaps**: Token-zentrierte Holder-Cluster (Top 250), „Magic Nodes" (verbindende
   Zwischenadressen: gemeinsame Funder, geteilte Deposit-Adressen), Time Travel, 14 Chains
   inkl. Polygon, REST-API + iFrame-Widget, ~6h Refresh. Deckte mit *60 Minutes* den
   **Polymarket-US-Iran-Insider-Ring** auf: 9 Konten, ~$2,4M Profit, ~98 % Trefferquote —
   einzeln unauffällig, nur als Cluster sichtbar.
2. **Arkham** hat eine eigene Prediction-Market-Suite (PnL-Leaderboard aller Polymarket-Trader,
   20+ Labels, Identitäts-Zuordnung; API neuerdings usage-based). **Nansen** hat
   Prediction-Markets-Endpoints ($10/10k Credits). **Beide clustern nicht.**
3. **Polymarket-Nische** (Polymarket Analytics $20/Mon., Hashdive→„Unusual Predictions",
   Polywhaler, OrcaLayer, PredictFolio mit freier API, Telegram-Copy-Bots): alle bewerten
   Wallets **einzeln**. Trader-zentriertes Clustering macht niemand → das ist die Lücke.
4. **Verknüpfungs-Spur auf Polygon liegt offen**: jedes Konto hat eine eigene
   Deposit-Adresse (Contract → leitet USDC an die Proxy-Wallet weiter), Proxies kommen aus
   Factories (Safe Proxy Factory `0xaacf…3541b`), Fills laufen über einen Relayer (EOA-basiertes
   Clustering funktioniert nicht, Funding-/Positions-Spuren dafür umso besser), Positionen sind
   ERC-1155. Präzedenz „Théo" (US-Wahl 2024): bis zu 11 Konten via gemeinsamer
   Kraken-Finanzierung + Order-Splitting-Fingerprint (71 Wetten/Min.) verknüpft.
   Methodik-Papers: Columbia (Wash-Trading über gerichtete Zyklen ≤5 Hops im
   Maker-Taker-Graph), LBS/Yale (Insider-Flow, Sign-Randomisierung, 1,72M Konten).
5. **Codebasis-Inventur** (Details in den Dateien selbst):
   - `app/suspicion.py:471` — Co-Trading-Graph + Louvain-Communities, fertig, aber nur auf
     ~1 Tag Live-Tape; deshalb die dreistufige Lockerungs-Leiter (`CO_TRADING_LADDER` und
     `co_trading_ladder` in `api/server.py`, bekannte Schwäche). Die Leiter steht seit
     PR #126 vollständig in der Nutzlast (`graph.regel_leiter`): je Sprosse die Regel im
     Klartext, ob sie versucht wurde und was sie gefunden hat. Vorher nannte das Bild nur
     die Sprosse, die getragen hat, und las sich damit als Ergebnis der strengsten Regel.
   - `app/onchain_flows.py` — getesteter USDC-Funding-Kernel (Protokoll- vs. externe Flüsse,
     Bridge-Erkennung, pUSD-Migration, Bilanz-Identität) — **nicht** an API/Frontend angeschlossen.
     Dezimalstellen sind seit PR #126 je Kontrakt gepinnt; pUSD steht mit `None` in
     `TOKEN_DECIMALS`, ein Transfer darüber wirft `UnknownTokenDecimals`. Wer die Stellen
     am Token-Kontrakt nachgelesen hat, reicht sie als
     `TOKEN_DECIMALS | {PUSD_CONTRACT: n}` durch.
   - `scripts/scan_erc1155_ledger.py` — einziger Code, der Positions-Transfers zwischen Wallets
     sieht (härtestes Cluster-Signal), nur Einmal-Skript.
   - Unterschätzter Endpoint: `/v1/market-positions` (`src/prediction_markets.py:2199`) —
     komplette Teilnehmerliste pro Markt mit PnL.
   - **Strukturelle Schwäche: keine Persistenz** (kein Trades-/Wallets-/Kanten-Store;
     Railway-Volume nur 500 MB).

## Der Vorschlag („Wallet-Graph")

Grundeinheit **Entity** (Akteur) statt Wallet. Verknüpfung über drei Evidenz-Stufen,
jede Kante trägt Belege (Tx-Hashes, Zeitfenster, Konfidenz):

- **Stufe 1 (hart, on-chain, führt automatisch zusammen)**: direkte USDC-Transfers zwischen
  Proxies, gleiche Funding-EOA, ERC-1155-Positionstransfer, gleiches Auszahlungsziel.
- **Stufe 2 (mittel, nur Kandidatenliste)**: gleiche CEX-Hotwallet in engem Zeitfenster,
  Proxy-Erstellung in Serie, Einzahlungs-Muster.
- **Stufe 3 (Verhalten, wird nur angezeigt, führt nie zusammen)**: Co-Trading (Louvain),
  Order-Splitting-Fingerprint, Timing-Korrelation, komplementäre Bücher (Wash-Verdacht).

Darauf aufbauend: Cluster-Scores (aggregierte Win-Rate/PnL/Insider-Score), Cluster-Alerts
(Telegram/Ledger-Infra existiert), Copy-Desk auf Akteurs-Ebene („Entity folgen"),
öffentliche Methodik-Seite. Sprachregelung strikt nach `data/claims.yaml`
(`screen_not_proof`): Stufe 2/3 heißt „Kandidat"/„verhält sich wie", nie „ist".
Keine Deanonymisierung (Konten verknüpfen, keine Personen identifizieren).

## Ausbaustufen & Empfehlung

1. **Phase 1 (zuerst, und nur diese): Persistenz.** Eigener Ingest-Prozess (lokal, geplante
   Task; getrennt vom API-Prozess und vom 500-MB-Volume): Whale-Tape via `data-api /trades`
   fortlaufend + Goldsky-Subgraphs (`pnl`, `activity`); SQLite/WAL; `onchain_flows.py` hinter
   eine API-Route; echter On-Chain-First-Seen. → Louvain über Wochen, Lockerungs-Leiter löschen.
2. **Phase 2: Funding-Graph & Entity-Auflösung** — selektiv (nur auffällige Wallets), Etherscan
   V2 (Scanner existiert), Union-Find, Schema `entities` / `wallet_entity` / `edges(typ, evidenz,
   konfidenz, first_seen)`.
3. **Phase 3: Verhaltens-Layer** — Fingerprints, Wash-Zyklen (Columbia-Methode), Entity-Insider-
   Score. Erfolgskriterium: der „Iran-Test" (hätte das System den Ring gefunden?).
4. **Phase 4: Produktfläche** — Seite „Wallet-Graph" (`web/js/app.js`-PAGES,
   `cluster_graphics.js` ausbauen), Wallet-Tab „Verknüpft", Alerts, Copy-Anbindung.

Kosten: $0–50/Monat. Kalshi bleibt außen vor (keine öffentlichen Wallets).

## Stand der Umsetzung (2026-08-30)

Phase 1 (Persistenz) ist gebaut:

- `src/trade_store.py` — SQLite-Speicher (WAL, Dedup-Schlüssel wie `load_deep_tape`:
  `transaction_hash, wallet, asset`), Lesefenster `TRADE_STORE_WINDOW_DAYS` (Standard 14 Tage),
  `extend_tape` reichert das Live-Band des Risk-Screens an, `store_note` liefert den zweiten
  Satz der Bildunterschrift (Prints, Tage-mit-Daten, letzter Ingest, Dedup-Summe). Ohne
  Datei ändert sich nichts — fail-soft in jede Richtung.
- `scripts/run_trade_ingest.py` — Runner (Schleife alle 15 min, `--once`, Stop-Datei
  `data/trade_ingest.stop`, Aufbewahrung 45 Tage via `prune`).
- `api/server.py` — `load_deep_tape` vereinigt Live-Band + Speicherfenster;
  `TRADE_STORE_RECORD=1` lässt den API-Prozess seine ohnehin geholten Seiten eintragen
  (Standard aus). Die Regelleiter bleibt unverändert und berichtet ehrlich weiter.
- Tests: `tests/test_trade_store.py`; volle Suite grün (2.337 Tests).

**Betriebsbefund:** Auf dem Heimrechner blockt der Provider (Salt) `*.polymarket.com`
per DNS (NXDOMAIN vom Router; 1.1.1.1/8.8.8.8 lösen normal auf — Schweizer
Geldspiel-Blockliste). Der lokale Ingest-Runner braucht daher einen anderen Resolver,
ODER man lässt den Store auf Railway wachsen: `TRADE_STORE_RECORD=1` +
`TRADE_STORE_PATH=/data/trade_store.sqlite` (Volume!) + `RISK_LOG_INTERVAL_MIN>0`,
dann füttert der Flag-Sampler den Store im Vorbeigehen. ~1–2 MB/Tag bei $1k-Floor,
45 Tage ≈ unter 100 MB — passt ins 500-MB-Volume.

## Offene Punkte

- Betriebsentscheidung: Ingest via Railway (Env-Variablen setzen + `railway up`) oder
  lokal mit öffentlichem DNS. Railway ist der Weg des geringsten Widerstands.
- Nach ~2 Wochen Bestand: prüfen, ob die strengen Leiter-Sprossen jetzt tragen; dann
  Phase 2 (Funding-Graph & Entity-Auflösung, `entities`/`wallet_entity`/`edges`).
- Beobachten: `_tape_categories` schlägt bei breiterem Tape mehr Märkte nach
  (gebatcht + fail-soft, aber Kaltstart von /api/risk wird träger).
- Optional: Arkham-API-Labels als Anreicherung (Buy), Bubblemaps-iFrame als Sanity-Check.
