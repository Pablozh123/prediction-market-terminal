# Plan: Wallet-Connect, Live-Copytrading, Krypto-Zahlung, Speed

Stand: 2026-06-12. Vier Recherchen mit Primärquellen. Research-Unterstützung, **keine Rechtsberatung** — die Stellen mit **[ANWALT ZWINGEND]** sind nicht verhandelbar, bevor ein einziger Live-Trade läuft.

---

## Die wichtigste Erkenntnis zuerst

Es gibt **zwei völlig verschiedene Risiko-Stufen**, und sie dürfen nicht vermischt werden:

| Stufe | Was | Rechtsrisiko | Aufwand |
|---|---|---|---|
| **A. Wallet-Connect read-only** (wie polywhaler) | Adresse verbinden → Positionen/PnL anzeigen | ~null (nur öffentliche Chain-Daten lesen) | 2–4 Tage |
| **B. Speed-Upgrade Fast-Copy** (Paper bleibt Paper) | WebSocket statt On-Chain-Polling | null (interne Technik) | Stunden–1 Tag |
| **C. Live-Geld-Copytrading** (wie polyhuntr) | Echte Orders mit Nutzer-Wallet ausführen | **HOCH — Geldspielrecht-Eskalation** | Wochen + Anwalt |
| **D. Krypto-Zahlung** | USDC-Abo neben Karte | gering (Gateway = Intermediär) | 2–6 Tage |

**A, B und D kannst du jederzeit bauen. C ist eine strategische Entscheidung mit echtem strafrechtlichem Risiko für dich als Schweizer Resident** — Details in Abschnitt 3.

---

## 1. Speed: unser Fast-Copy ist aktuell die langsamste brauchbare Methode

**Befund (bestätigt deine Vermutung):** Unser Worker pollt einen gratis Polygon-RPC mit `eth_getLogs` auf `OrderFilled`-Events. Der On-Chain-Log ist aber das **letzte** Ereignis im Trade-Lebenszyklus: Polymarket matcht off-chain **sofort**, settled erst ~2 s später on-chain (ein Bor-Block). Wir zahlen also ~2 s + unser 1-s-Poll-Intervall Strafe — langsamer geht es kaum.

**Trade-Lebenszyklus, früheste → späteste Sichtbarkeit:**
1. Nutzer signiert Order → CLOB-Operator matcht in-memory (~ms)
2. **CLOB-WebSocket broadcastet den Trade** ← hier ist das früheste öffentliche Signal
3. Settlement-Tx wird gebaut, an Relayer
4. **On-Chain `OrderFilled` gemined (~2 s später) ← HIER hören wir aktuell zu**

**Der 80/20-Gewinn (größter Effekt, ~Stunden Arbeit, $0):** Detection auf den **CLOB-WebSocket** umstellen.
- **RTDS `activity/trades`-Feed** (`wss://ws-live-data.polymarket.com`): liefert `proxyWallet`, `side`, `size`, `price`, `asset`, `conditionId`, `transactionHash` — **inklusive Wallet**, zum Match-Zeitpunkt. Gotcha: Einzel-Wallet-Filter ist kaputt (Issue #34) → mit leerem Filter den globalen Firehose abonnieren und `proxyWallet` clientseitig gegen die Ziel-Liste matchen. Alle 5 s `PING` senden.
- Entfernt sofort ~2 s Latenz; On-Chain-Polling bleibt als **Reconciliation/Fallback** (fängt, was der WS verpasst, bestätigt Settlement).

**Ranked Upgrade-Pfad:**
| # | Schritt | Latenz-Gewinn | Aufwand | Kosten |
|---|---|---|---|---|
| 1 | **WS-Detection statt On-Chain-Polling** | **~2 s → sub-Sekunde** | Stunden | $0 |
| 2 | Execution härten: keep-alive HTTPS zu clob.polymarket.com, gecachte L2-Creds, vorgeladene tick sizes/token IDs, **FOK**-Market-Orders via py-clob-client | ~100–200 ms Critical Path | ~1 Tag | $0 |
| 3 | **Worker nach Dublin/London co-locaten** (Polymarket-CLOB läuft in AWS eu-west-2 London) | ~70–130 ms → ~1–10 ms RTT | ~halber Tag | ~$5–40/Mo VPS |
| 4 | Paid WSS-RPC (Chainstack/Alchemy) mit `eth_subscribe` als On-Chain-Fallback | ersetzt unzuverlässigen Gratis-RPC | ~halber Tag | $0–50/Mo |
| 5 | ~~bloXroute/Mempool, Builder-Partner-Tier~~ | — | **überspringen**: Settlement ist Relayer-batched, Mempool bringt nichts; Partner-Tier nur für Skalierung relevant | — |

**Netto:** Schritte 1–3 bringen uns von "~2–3 s hinterher + US-RTT" auf "**sub-Sekunde, oft ~100–300 ms end-to-end, am frühesten Signal, neben der Matching-Engine**" — für eine kleine Dublin-VPS und 1–2 Tage Arbeit. **Schritt 1 ist der dominante Gewinn** und gilt auch für unser Paper-Copy (realistischere Fills) und die Live-Trades/Suspicious-Feeds.

## 2. Wallet-Connect (read-only): niedriges Risiko, hoher Wert

**polywhaler-Muster:** "Connect wallet" = nur Adresse lesen → Positionen/PnL anzeigen. Keine Signatur, keine Custody, kein Finanzdienstleistungs-/Geldspiel-Fußabdruck. Genau das, was unsere Engine schon kann (sie liest `OrderFilled` per Adresse).

**Technik in Streamlit (das ist nicht trivial):** Streamlit ist serverseitig; echtes Wallet-JS läuft nur in einer **eigenen React-Komponente (iframe)** mit wagmi/WalletConnect, die Adresse + optional Signatur via `Streamlit.setComponentValue` zurückgibt. Die fertigen Komponenten (`streamlit-wallet-connect` etc.) sind 2022er-Stand, MetaMask-only, ohne Message-Signing — **nicht brauchbar**, nur als Referenz.
- **Phase 1a (nur Adresse):** Nutzer tippt/verbindet Adresse → Engine liest öffentliche Daten. Minimal, null Risiko.
- **Phase 1b (authentifiziert):** **SIWE / EIP-4361** (2025 finalisiert) — eine Klartext-Signatur beweist Wallet-Besitz, gated Premium-Analytics. Keine Transaktion, keine Fonds. Backend verifiziert mit `eth_account`/`siwe`.
- **Aufwand:** ~2–4 Tage (Großteil = erster React-Komponenten-Build + iframe-Rerun-Handling).

## 3. Live-Copytrading: technisch machbar, rechtlich die rote Linie

### 3a. Wie polyhuntr es baut (non-custodial)
Wörtlich aus deren Terms: *"PolyHuntr does not hold, custody, or control your funds. All trades execute directly on Polymarket or Kalshi using your own wallet."* Privacy: *"exchange API secrets stay in your browser session only."* Gebühr: **10 % vom realisierten Gewinn, off-chain via Stripe abgerechnet** (kein On-Chain-Skim → konsistent mit non-custodial). **Betreiber/Jurisdiktion: NICHT offengelegt** (/about ist 404) — das ist ein Warnsignal, kein Vorbild für unsere Rechts-Hygiene.

### 3b. Polymarket unterstützt das technisch
Der Order-Struct hat getrennte `maker` (Geldquelle) und `signer` (wer signiert) — *"Optional; if not present the signer is the maker."* Das ist der non-custodial Delegations-Hook. Saubere Architektur:
1. Als **Polymarket Builder** registrieren (builderCode wird in die signierte Order serialisiert; Builder hält nie Fonds).
2. Nutzer verbindet Proxy-Wallet (Gnosis Safe / Deposit-Wallet), signiert **einmalig** eine gedeckelte USDC-Allowance an die 4 Exchange-Contracts (Relayer zahlt Gas, gasless).
3. Engine spiegelt Leader-Trades, indem sie Orders baut, die **die Nutzer-Wallet signiert** — entweder (A) Backend-**Session-Key** als `signer` mit On-Chain-Spend-Caps (beste UX für unbeaufsichtigtes Copy, aber Backend hält einen *beschränkten* Key) oder (B) **Browser signiert jede Order** (max non-custodial, aber Browser muss offen/zustimmen → kein "set and forget").
4. Gebühr off-chain via Stripe.
- **Technik-Stack-Delta:** kleiner **JS-Microservice** (Next.js, Polymarkets `wagmi-safe-builder-example` als Basis) fürs Onboarding (Wallet-Connect, Safe-Deploy, Approval-Batch, L2-Cred-Ableitung) + `py-clob-client` in der Engine. **Aufwand: Phase-2-Option-A ~2–4 Wochen** (Session-Key-Registrierung ist unter-dokumentiert → erst gegen Testnet/Kleinbeträge prototypen; v2-SDK-Signer-Bug #70 beachten).

### 3c. Das Rechtsbild — hier wird es ernst

**Finanzrecht (machbar mit richtiger Gestaltung):** Non-custodial + keine diskretionäre Verwaltung + keine personalisierte Beratung hält dich wahrscheinlich aus den schweren Lizenzen (Bank, Effektenhändler, FinIA). Aber "Copy-Trading" ist eine eigene regulierte Kategorie (ESMA/FinSA-Funktionstest):
- **Auto-Execute ohne Nutzeraktion → Portfolio-Management** (lizenzpflichtig). Vermeiden.
- **Nutzer bestätigt jeden Trade → Anlageberatung/Auftragsübermittlung** (Verhaltenspflichten, Berater­register). Leichter.
- **Execution-only (Nutzer löst aus, du übermittelst nur) → leichteste Stufe.** ← anzustrebende Gestaltung.
- Custody ist überall die helle Linie: **nie Fonds/Keys halten** → keine Bank-/AMLA-Pflicht.

**⚠️ Geldspielrecht (BGS) — DIE Eskalation und der Grund, warum das ≠ Daten-Site ist:**
- Polymarket ist GESPA-gesperrt (unbewilligtes Online-Geldspiel).
- **BGS Art. 130:** Wer vorsätzlich unbewilligte Großspiele organisiert **oder "die technischen Mittel dafür bereitstellt, im Wissen um die beabsichtigte Verwendung"**, an Personen ohne Bewilligung → **Freiheitsstrafe bis 3 Jahre (5 bei Gewerbsmäßigkeit)**.
- **BGS Art. 131:** Werbung für unbewilligte Spiele → Busse bis CHF 500'000.
- Eine **Daten-/Leaderboard-Site** zeigt nur öffentliche Information. Ein Tool, das **Schweizer Nutzer beim Live-Trading auf einem gesperrten Geldspiel-Markt routet/erleichtert**, ist viel näher an "Bereitstellung der technischen Mittel" — der qualitative Sprung von Information zu Facilitation.
- **Gegengewicht:** Schweizer Behörden zeigen *"wenig Appetit"* auf Strafverfahren gegen ausländische Sites, und die Auslands-Anwendbarkeit ist *"unsicher"* — Enforcement war bisher administrativ (Blocklist/DNS), nicht strafrechtlich. **ABER:** Diese "Handlung im Ausland"-Unsicherheit ist genau der Schutz, den du als **Schweizer Resident nicht hast**. Wer aus der Schweiz heraus die technischen Mittel bereitstellt, ist territorial klar erfasst.

**Konsequenz:** Für Live-Copy ist **[ANWALT ZWINGEND]** — nicht optional. Die genaue Frage (darf ein Schweizer Resident Live-Trades für *Nicht*-Schweizer auf einem GESPA-gesperrten Markt erleichtern?) kann nur eine Schweizer Fintech-+-Gaming-Kanzlei klären. Kostenrahmen Memo: **~CHF 5'000–15'000** (Klassifizierung), volles Gutachten FinSA+BGS+AMLA grenzüberschreitend **~CHF 15'000–25'000+**. Angesichts der Gefängnis-Exposition von Art. 130 ist das die billigste Versicherung.

### 3c-bis. Konkurrenz: Gebührenmodelle, Custody, Sicherheitsvorfälle

**Gebührenmodelle (zur Orientierung):**
- **polyhuntr**: 10 % vom realisierten Gewinn, off-chain via Stripe, kein Abo. Live nur nach manueller Admin-Freigabe.
- **PolyCopy**: $30/Mo + **1 % taker / 0.5 % maker als Polymarket-Builder-Fees** (on-chain) — der klarste offengelegte Einsatz der Builder-Fee-Schiene; Key-Custody via Turnkey HSM/TEE.
- **Poly Syncer**: $299/Mo (bis 250 Wallets, dedizierter RPC), non-custodial. **PolyCop**: ~0.5 %. **Stand.trade**: aktuell $0 (erst wenn Polymarket Fees aktiviert), im Polymarket-Newsletter profiliert.
- **Zwei Erlösschienen** also: (a) Builder-Fee on-chain (PolyCopy, 0.5–1 %) oder (b) Performance-Fee off-chain via Stripe (polyhuntr, 10 % Gewinn). (b) ist non-custodial-konformer und vermeidet die On-Chain-Fee-Mechanik-Frage.

**Sicherheitsvorfälle (untermauern die non-custodial-Pflicht):**
- **Polycule** (Jan 2026, ~$230k gestohlen): war **custodial** — Backend generierte und speicherte Private Keys pro Nutzer, signierte serverseitig. Vektor u. a. SSRF + reversibler Key-Store. → Genau das Modell, das wir **nicht** bauen.
- **PolyGun** (Feb 2026, ~$70k), und **bösartige GitHub-"copy-trading-bot"-Repos**, die Private Keys aus `.env` exfiltrieren. Lehre: Keys serverseitig = Angriffsfläche. Unser Vorteil: strikt non-custodial, nie Keys halten.

**Polymarkets Haltung — direkt relevant für unser Insider-Feature:** Im April 2026 begann Polymarket, Builder-Startups zu **auditieren, deren Apps Nutzern helfen, verdächtige Insider-Wallets zu kopieren** (genannt: Kreo, Polycool) — Auslöser: vier am selben Tag erstellte Wallets machten $663k auf einem US-Iran-Markt. Plus Palantir-Partnerschaft für On-Chain-Monitoring, neue Insider-Trading-Regeln. **Wichtig:** Es ist "embrace builders, police insider-copying", nicht anti-copy-trading (Polymarkets eigener Newsletter profiliert Copy-Tools positiv). **Konsequenz für uns:** Unser Suspicious/Insider-Screen ist wertvoll — aber ein Feature "kopiere diese Insider-Wallet automatisch" wäre genau das, was Polymarket gerade auditiert. Insider-Erkennung als **Research/Warnung** positionieren, nicht als "tail the insider"-Copy-Funnel.

**Counterparty-Beobachtung:** polyhuntr UND polywhaler legen **keine Rechtsentität, Adresse oder Governing Law** offen (nur E-Mail). Bei einem Tool, das Live-Trading-Credentials berührt, ist das ein Risikosignal — wir machen es anders (benannte Entität, echte Terms).

### 3d. Verteidigbare Gestaltung, falls C kommt
- **Strikt non-custodial** (nie Fonds/Keys/Secrets serverseitig), gedeckelte revoke-bare Allowance, Gebühr off-chain (Stripe).
- **Execution-only / Nutzer bestätigt** statt stilles Auto-Execute; Signale **generisch, nicht personalisiert** (keine Beratung).
- **Echtes Hartes Geoblocking: CH UND US blocken** (US = CFTC-IB/CPO/CTA-Minenfeld bei Event-Contracts), plus Polymarkets eigene Restricted-Liste — IP-Geofencing + Attestation + ToS, nicht nur Checkbox.
- **Echte Terms** mit Restricted-Jurisdictions, "not financial advice", "not affiliated", non-custodial-Statement, benannte Betreiber-Entität (anders als polyhuntr), Haftungsdeckel, Governing Law.
- **Anwalts-Memo vor dem ersten Live-Trade.**

## 4. Krypto-Zahlung

**Zwei brauchbare Wege neben Karte/MoR:**
1. **NOWPayments oder CoinGate** (Gateway, Auto-Konvertierung zu Fiat, ~0.5–1 %): Prozessor wird zum regulierten AMLA-Intermediär statt dir, du bekommst Fiat, keine Volatilität/Custody. CoinGate ist EU-/CH-konformer (EU-lizenziert, gratis SEPA). ~2–4 Tage. Recurring ist invoice-/reminder-basiert, kein echter Auto-Pull.
2. **Direkte USDC-on-Polygon-Adresse, als 30-Tage-Prepaid verkauft** (kein Auto-Renew): crypto-nativ für unsere Polygon-Nutzer, <$0.01 Gebühr, Sekunden. Pro-Nutzer-Deposit-Adresse für Attribution, RPC-Watcher bestätigt Zahlung. ~3–6 Tage, kein Prozessor-Cut, aber du handhabst Edge-Cases selbst.

**Tot/ungeeignet:** Coinbase Commerce (Shutdown 31.03.2026), Stripe-Stablecoin (nur US-Händler), Helio (Solana, falsche Chain), Loop/Sphere Auto-Pull (Over-Engineering bis Nutzer Auto-Renew verlangen).

**Steuer/Recht (CH):** Krypto-Annahme macht dich **nicht** zum Finanzintermediär (Verkauf eigener Leistung ≠ Intermediation); Auto-Konvertierung via Gateway hält FINMA fern. Umsatz wird zum CHF-Wert bei Eingang als Geschäftsertrag verbucht (keine private Kapitalgewinn-Befreiung). MWST folgt der SaaS-Leistung, nicht der Zahlart.

**Empfehlung:** **Fiat-only zum Launch** (Stripe/MoR bringt mehr Umsatz pro Stunde und löst die EU-MwSt). Krypto (Option 2, USDC-Polygon-Button) nachrüsten, sobald zahlende Nutzer danach fragen — für unsere crypto-native Zielgruppe dann ein echtes Differenzierungsmerkmal.

## 5. Empfohlene Reihenfolge

**Sofort baubar (null/geringes Risiko):**
1. **Speed Schritt 1**: WS-Detection (RTDS `activity/trades`) statt On-Chain-Polling — größter Gewinn, paar Stunden, verbessert auch Paper-Copy + Live-Feeds.
2. Speed 2–3: Execution härten + Worker nach Dublin (beim öffentlichen Deploy ohnehin EU-VPS).
3. Wallet-Connect read-only (React-Komponente + SIWE), ~2–4 Tage.
4. Krypto-Zahlung erst nach Launch, wenn nachgefragt.

**Strategische Entscheidung (nicht ohne Anwalt):**
5. Live-Copytrading nur nach **Anwalts-Memo (CHF 5–25k)** zur BGS-Art.-130-Frage + verteidigbarer Gestaltung (non-custodial, execution-only, CH+US-Geoblock, echte Terms, benannte Entität). Technik dann ~2–4 Wochen + JS-Onboarding-Microservice.

**Kernsatz:** Wir können sofort die schnellste *Paper*-Copy- und Analytics-Plattform werden (Speed Schritt 1 schlägt die meisten öffentlichen Bots) und Wallet-Connect-Analytics liefern — beides ohne Rechtsrisiko. Der Sprung zu **Live-Geld** ist eine separate, anwaltlich abzusichernde Entscheidung, weil er als Schweizer Resident die Geldspielrecht-Grenze berührt.
