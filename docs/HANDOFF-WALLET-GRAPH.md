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
     Railway-Volume nur 500 MB). Behoben in Phase 1, siehe "Stand der Umsetzung".

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

Phase 1 wurde parallel auf beiden Rechnern gebaut; der Merge behielt den Store von
main (`src/trade_store.py`) und traegt die Stuecke des PR-Zweigs nach, die dort
fehlten. Ergebnis:

- `src/trade_store.py` — SQLite-Speicher (WAL, Dedup-Schluessel wie `load_deep_tape`:
  `transaction_hash, wallet, asset`), Lesefenster `TRADE_STORE_WINDOW_DAYS` (Standard
  14 Tage), `extend_tape` reichert das Live-Band des Risk-Screens an, `store_note`
  liefert den zweiten Satz der Bildunterschrift (Prints, Tage-mit-Daten, letzter
  Ingest, Dedup-Summe; bei mehr als einem Tag Ingest-Stillstand benennt er die
  Luecke zwischen Speicherfenster und Live-Band). Ohne Datei aendert sich nichts,
  fail-soft in jede Richtung. Neu dazu: `wallets`-Tabelle (First/Last-Seen je
  Wallet, MIN/MAX-idempotent, uebersteht `prune`) und `first_seen_map`.
- `scripts/run_trade_ingest.py` — Runner (Schleife alle 15 min, `--once`, Stop-Datei
  `data/trade_ingest.stop`, Aufbewahrung 45 Tage via `prune`, Einzelinstanz via
  `app/proc_lock`). Als geplante Task `MarketIntelTradeIngest` in
  `scripts/install_autostart.ps1` registrierbar.
- `api/server.py` — `load_deep_tape` vereinigt Live-Band + Speicherfenster;
  `TRADE_STORE_RECORD=1` laesst den API-Prozess seine ohnehin geholten Seiten
  eintragen (Standard aus). Die Regelleiter bleibt unveraendert und berichtet
  ehrlich weiter; die lockeren Sprossen fliegen erst raus, wenn der Store
  verlaesslich Wochen haelt.
- `app/flow_fetch.py` + Route `GET /api/wallet/{wallet}/flows` — der getestete
  Funding-Kernel aus `onchain_flows.py` haengt jetzt an der API. Begrenzter
  Etherscan-V2-Walk (Budget je Kontrakt, `complete`-Flag, gekappte Summen heissen
  Untergrenzen), liefert Funding-Spanne, Peak-Exposure, Top-Gegenparteien und das
  on-chain First-Transfer-Datum. Braucht `ETHERSCAN_API_KEY`, sonst 503.
- Echter First-Seen: `md.whale_wallet_risk_scores` nimmt `known_since`
  (First-Seen-Map aus dem Store, via `store_known_since` in `api/server.py`).
  Eine Wallet, die der Store schon vor dem Tagesfenster kannte, ist nicht mehr
  "sample-fresh"; Risk-Screen und Wallet-Seite nutzen dieselbe Map, und das
  Etikett nutzt dieselbe Maske wie die Punkte. Wallet-Detail traegt zusaetzlich
  `store_first_seen`.

**Betriebsbefunde:**

- Heimrechner (anderer PC): Der Provider (Salt) blockt `*.polymarket.com` per DNS
  (NXDOMAIN vom Router; 1.1.1.1/8.8.8.8 loesen normal auf, Schweizer
  Geldspiel-Blockliste). Der lokale Runner braucht dort einen anderen Resolver,
  ODER man laesst den Store auf Railway wachsen: `TRADE_STORE_RECORD=1` +
  `TRADE_STORE_PATH=/data/trade_store.sqlite` (Volume!) + `RISK_LOG_INTERVAL_MIN>0`,
  dann fuettert der Flag-Sampler den Store im Vorbeigehen. ~1-2 MB/Tag bei
  $1k-Floor, 45 Tage unter 100 MB, passt ins 500-MB-Volume.
- Dieser Rechner: kein DNS-Block, der Live-Smoke des Ingest lief direkt gegen den
  Feed (3000 Prints ab $500 in einem Pass, zweiter Pass fand korrekt 0 Neue).
  Gemessene Zeilengroesse ~850 Bytes inkl. Indizes.

## Stand Phase 2 (2026-08-30)

Funding-Graph und Entity-Aufloesung sind gebaut (Branch
`claude/wallet-graph-phase2-entities`):

- `app/entity_graph.py` — eigener Store `data/entity_graph.sqlite` (WAL) mit
  `scans` / `funding_links` / `position_links` / `edges(typ, stufe, konfidenz,
  evidenz, first_seen)` / `wallet_entity`. Stufe 1 (direkte Collateral-Transfers
  zwischen gescannten Wallets, gemeinsamer externer Funder, gemeinsames
  Auszahlungsziel, direkte ERC-1155-Positionstransfers) fuehrt per Union-Find
  zusammen; Stufe 2 (Gegenpartei verhaelt sich wie eine Boerse, `degree_cap`
  Standard 4; engeres 48-h-Fenster hebt nur die Konfidenz) bleibt
  Kandidatenliste und merged nie. Jede Kante traegt Belege (Tx-Hashes,
  Betraege, Zeitfenster); Entity-Ids sind deterministisch (kleinste Wallet
  der Komponente); `rebuild_edges`/`assign_entities` sind idempotent, der
  Graph ist eine Ableitung der Link-Tabellen, keine zweite Wahrheit.
- `app/flow_fetch.py` — erweitert um `fetch_classified_flows` (gemeinsamer
  Kern fuer Flows-Route und Entity-Scan) und `fetch_position_transfers`
  (token1155tx am Conditional-Tokens-Kontrakt, Protokoll- und
  Bridge-Gegenparteien fallen raus: uebrig bleiben Transfers von Wallet zu
  Wallet, die es im normalen Handel nicht gibt).
- `scripts/run_entity_scan.py` — selektiver Runner: `--wallet` und/oder
  `--top-store N` (groesste Wallets im Tape-Store-Fenster), Seitenbudget je
  Kontrakt, Rescan-Drossel, danach kompletter Rebuild. Read-only.
- `GET /api/wallet/{wallet}/entity` — liest nur den lokalen Graphen (keine
  Chain-Abrufe), unterscheidet "kein Graph auf diesem Host", "nicht
  gescannt" und die Entity samt `linked_wallets` (Stufe 1) und `candidates`
  (Stufe 2); jede Antwort mit Inhalt traegt den `screen_not_proof`-Satz aus
  dem Claims-Register. Keine Deanonymisierung: verknuepft werden Konten
  ueber belegte Transfers, nie Personen.
- Tests: `tests/test_entity_graph.py` (Stufen-Vertrag, Idempotenz, Route).

**Befunde der ersten Live-Laeufe (3 groesste Tape-Store-Wallets, Budget 2 Seiten):**

- Der erste Lauf verband alle drei Wallets ueber EIN gemeinsames Auszahlungsziel zu
  einer Entity. Die Adresse war `0xe2222d27...`, ein neueres
  Polymarket-Exchange-Deployment, das `src/copy_trading.py` laengst kannte,
  `app/onchain_flows.py::PROTOCOL_ADDRESSES` aber nicht: Settlement-Verkehr wurde
  als externes Funding gebucht (betraf auch die Funding-Summen der Flows-Route).
  Beide 2026er-Exchange-Adressen stehen jetzt in der Protokoll-Liste.
- Daraus abgeleitete Regel: eine Gegenpartei, die JEDE gescannte Wallet verbindet
  (ab 3 Scans), ist nur Kandidat; in einem kleinen Scan-Set kann der Degree-Cap
  nie greifen, und geteilte Infrastruktur sieht dann exakt wie gemeinsame
  Kontrolle aus.
- Nach dem Fix bleibt eine Stufe-1-Kante: zwei der drei Top-Wallets zahlen an
  dasselbe externe Ziel (`0x115f48dc2a731aa16251c6d6e1befc42f92accc9`) aus,
  mit Tx-Belegen im Graphen. Einordnung: zusammen nur rund $108, also ein
  Muster-Beleg (gleiches Ziel), kein Geldstrom; ob das Gebuehren-, Test- oder
  Operator-Verkehr ist, muesste ein Scan der Zieladresse selbst zeigen.

## Stand Phase 3 (2026-08-30)

Der Verhaltens-Layer ist gebaut (Stufe 3: wird angezeigt, fuehrt nie zusammen):

- `app/behavior.py` — zwei Detektoren ueber dem Tape-Frame, bewusst OHNE neuen
  0-100-Score (Lektion insider_score_unvalidated): `order_splitting_fingerprints`
  (dichtester Burst je Wallet und Marktseite, Theo-Muster; Standard 8 Prints je
  60 s) und `complementary_books` (Paare wiederholt zeitnah auf Gegenseiten
  desselben Buchs, Wash-Verdacht als "verhaelt sich wie"). Die Columbia-Methode
  (gerichtete Zyklen im Maker-Taker-Graphen) braucht die Gegenpartei je Fill,
  die das oeffentliche Band nicht traegt; das Paar-Muster ist die ehrliche
  Naeherung. Kappung auf die groessten Wallets, `focus_wallets` ueberleben sie.
- `GET /api/wallet/{wallet}/entity` traegt fuer gescannte Wallets einen
  `behavior`-Block aus dem Store-Fenster (Ergebnis gefiltert auf die Entity,
  Band ungefiltert, damit Partner ausserhalb der Entity sichtbar bleiben).
- `scripts/run_cluster_probe.py` — der Iran-Test als Werkzeug: benannte
  Wallet-Menge (`--wallet`/`--file`), Handelshistorie je Wallet ueber die
  Data-API (`/trades?user=`, auch fuer Zeitraeume vor dem eigenen Store),
  dann strenge UND lockerste Co-Trading-Regel, beide Detektoren, optional
  `--onchain` (Funding/Positionen in eine eigene Probe-DB). Ausgabe: welche
  Signalklassen auf der Menge feuern.
- Erster Live-Lauf (die zwei Wallets mit der gemeinsamen Auszahlungs-Kante):
  kein Co-Trading, keine Komplementaer-Paare, aber ein sauberer
  Order-Splitting-Fingerprint (24 Prints in 24 s auf einem Sportmarkt, klares
  Bot-Muster). Die Signalklassen trennen also wirklich.
- Tests: `tests/test_behavior.py`, `tests/test_cluster_probe.py`, Route-Test.

**Iran-Test, erster Durchlauf (2026-08-30):** Die Adressliste des Feb-28-Clusters
wurde aus oeffentlichen Quellen rekonstruiert (Bubblemaps-Thread, The Block,
Forbes, Decrypt; zwei Adressen woertlich publiziert, sieben ueber die
Polymarket-Namenssuche aufgeloest, Verwechslungsrisiko durch Renames bleibt und
ist je Adresse vermerkt). Probe ueber die 9 Wallets:

- Band: alle 9 mit kurzer Historie (1 bis 373 Prints), passend zum
  "fresh wallets"-Befund der Berichterstattung.
- Co-Trading: 6 von 9 verbunden (5 Kanten unter der lockersten Regel), 1 Paar
  selbst unter der strengsten Sprosse (3+ Maerkte in 5 min, $10k gepaart).
- On-Chain Stufe 1: whopperlover und Skoobidoobnj teilen eine
  Finanzierungsquelle (`0xc536633f...`, 22 Transfers) und werden eine Entity.
- Stufe 2: eine Gegenpartei (`0xc2884805...`) verbindet 7 der 9, eine weitere
  (`0xf7cd89be...`) 6 der 9, jeweils Kandidat, nie Merge. Die
  Relay-Infrastruktur (`0xf70da978...`, `0x4cd00e38...`) verbindet alle 9 und
  wird von der Whole-Set-Regel korrekt als Infrastruktur-Kandidat einsortiert.
- Fingerprints und Wash-Paare: keine. Dieser Ring hat gross und einmal
  gewettet, nicht gestueckelt; das Splitting-Muster gehoert zum Theo-Fall.

Verdict der Verknuepfungs-Haelfte: als Menge zeigt das System den Ring klar als
Rechercheanlass (Co-Trading-Kanten, geteilte Funding-Kandidaten ueber den
Grossteil der Menge, eine harte Kante). Es verschmilzt die 9 bewusst NICHT zu
einer Entity, weil CEX-artige Gegenparteien nie mergen; genau dort ist
Bubblemaps' Methode mutiger als unsere Sprachregel erlaubt. Offen bleibt die
Findungs-Haelfte: ob der Risk-Screen die Wallets ohne Vorwissen nach oben
gespuelt haette (Fresh-Wallet- und Konzentrations-Flags existieren; der
Rueckblick-Test braucht historisches Band aus der Ereigniswoche).

## Offene Punkte

- Betriebsentscheidung Ingest-Host: dieser Rechner kann lokal sammeln (geplante Task
  `MarketIntelTradeIngest` via `scripts/install_autostart.ps1` registrieren,
  User-Aktion); auf dem Heimrechner nur mit anderem Resolver, sonst Railway.
  Ein Sammler reicht, jeder Rechner sammelt sonst in seinen eigenen lokalen Store.
- Entity-Scan regelmaessig fahren (z.B. woechentlich `--top-store 50` plus die
  Flag-Wallets des Risk-Screens); noch keine geplante Task, bewusst: erst sehen,
  was die ersten Laeufe an Kanten liefern und ob `degree_cap=4` traegt.
- Nach ~2 Wochen Bestand: pruefen, ob die strengen Leiter-Sprossen jetzt tragen; dann
  die lockeren Sprossen loeschen.
- Goldsky-Subgraphs (`pnl`, `activity`) als zweite Ingest-Quelle: noch offen.
- Beobachten: `_tape_categories` schlaegt bei breiterem Tape mehr Maerkte nach
  (gebatcht + fail-soft, aber Kaltstart von /api/risk wird traeger).
- Iran-Test, Findungs-Haelfte: Rueckblick ueber das Band der Ereigniswoche
  (Feb 2026), ob Fresh-Wallet- und Konzentrations-Flags den Ring ohne
  Vorwissen markiert haetten. Die Verknuepfungs-Haelfte ist gelaufen, siehe
  "Stand Phase 3".
- Kuratierte Infra-Liste fuer die Kandidaten-Ableitung: Relay/Relayer-Adressen
  (`0xf70da978...`, `0x4cd00e38...`) verbinden JEDEN und dominieren sonst jede
  Kandidatenliste; die Whole-Set-Regel faengt sie heute nur ab, solange sie
  das ganze Scan-Set beruehren.
- Bewusst offen im Verhaltens-Layer: Timing-Korrelation als eigener Detektor
  (das Co-Trading-Fenster deckt die Haelfte ab) und echte Wash-ZYKLEN nach
  Columbia (brauchen Maker-Taker-Zuordnung je Fill, die das oeffentliche Band
  nicht hergibt; moeglicher Weg: OrderFilled-Logs on-chain je Markt).
- Phase 4 (Produktflaeche: Seite "Wallet-Graph", Wallet-Tab "Verknuepft",
  Cluster-Alerts) steht aus; Entity-Route samt Verhaltens-Block ist der
  fertige Unterbau.
- Optional: Arkham-API-Labels als Anreicherung (Buy), Bubblemaps-iFrame als Sanity-Check.
