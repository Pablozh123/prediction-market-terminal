# Differenzierungs-Strategie — Prediction-Market Intelligence

Stand: 2026-06-12. Basis: 11 parallele Recherchen (Wettbewerber-Deep-Dives, User-Segmente, Pain-Points, Trust/Custody, Unmet-Needs, Zahlungsbereitschaft, Kalshi-Ökosystem) mit Primärquellen (WSJ, Bloomberg, Columbia-Studie, OrcaLayer, CNBC, YC, Vendor-Selbstauskünfte). Ziel: **nicht noch ein Whale-Feed** — verteidigbare Position im überfüllten Markt.

---

## 0. Kernthese (ein Satz)

Der Markt ist voll mit Polymarket-only Whale-Feed + Insider-Score + Copy-Bot-Klonen, die alle auf **irreführenden Vanity-Leaderboards** und **Insider-Copy-Hype** aufbauen — beides mathematisch nachweislich falsch und für Nutzer verlustbringend. Wir gewinnen durch **Ehrlichkeit + mathematische Korrektheit + Cross-Venue-Breite**: das neutrale **Prediction-Market-Intelligence-Terminal mit verifizierbaren, settled-only, survivorship-korrigierten Track-Records**, Research-Positionierung statt Glücksspiel-Copy-Funnel.

---

## 1. Marktrealität (belegt)

- **Barbell:** ~2 % der User = ~90 % Volumen; **Top 0.04–0.1 % = ~67–70 % der Gewinne**; **84 % der Trader verlieren Geld** (WSJ 1.7M Adressen; on-chain-Studie 2.5M Wallets, April 2026). Gewinner = Bots/Arbitrage/MM, **nicht kopierbare Menschen**. Bots: 89 Trades/Tag vs. 2.2 für Menschen; 14 der Top-20-Wallets sind Bots.
- **Zahlende Segmente:** Degens (Copy, churny), Sharps (hohe WTP, bauen oft selbst), **Quant/Builder** (recurring, $99/Mo Data-API bewiesen). Researcher/Journalisten/Forecaster = niedrige WTP, aber **Credibility-Funnel**. Casuals = riesig, preissensibel.
- **Nachfrage spiky:** Wahlnacht-Peak Kalshi ~400k DAU → Mitte 2025 ~27k. Novelty-Churn real → Retention braucht Workflow-Lock-in.
- **60 % der PM-User sind Krypto-Neulinge** — Onboarding/Klarheit zählt.

## 2. Wettbewerber

| Tool | Positionierung | Venues | Stärke | Schwäche/Lücke |
|---|---|---|---|---|
| **Unusual Whales** (Unusual Predictions, Jan 2026) | Insider-Detection, **3M+ X-Follower** | **Polymarket-only** | Distribution, "Unusual Score", Marke | Monitoring-only (kein Copy/Alert/API/Backtest für PM), **kein Kalshi**, PM = Bolt-on |
| **Verso** (YC-backed) | "Bloomberg Terminal for prediction markets" | PM + Kalshi | **Best-finanzierter Independent**, AI-News-Engine (30k Artikel→Contracts), Mobile, 15k+ Contracts | Neu, kein Copy/Backtest bekannt — **direkter Konkurrent** |
| **Kreo** | "find insiders before the rest" | PM + Kalshi | Non-custodial-ish (Privy/Gnosis), AI-Matcher, echte Copy | **Opake Fee, kein Backtest, keine API, nur Telegram**, unter Polymarket-Audit |
| **Oddpool** (YC S26) | "institutional data layer" | PM + Kalshi | Cross-venue, API, Whale-Feed | Free=1 Event, keine Lizenz, jung |
| **PredictFolio / OrcaLayer** | Daten-Genauigkeits-Referenz | PM | **Korrekte Mathematik** (NegRisk-Korrektur, Farmer-Filter), Journalisten zitieren | Nische, PM-only |
| **polywhaler** | Whale/Insider $9/$99 | PM | Insider-Scoring | Copy ausgelagert an PolyGun (Referral), anonym, Domain 5 Mt. alt |
| **Stand.trade** | Pro-Terminal, Copy | PM (+Kalshi) | $0, im Polymarket-Newsletter (COPYCAT) | Monetarisierung unklar |
| **PolyCopy / PolyGun / Polycule** | Copy-Bots | PM | Copy-Execution | **Custody-Risiko** (Polycule ~$230k gehackt), Referral-Spam |
| **adj.news / Dome** | Multi-Venue **API** | Alle | Breiteste Daten | **API, kein UI**; Dome von Polymarket **gekauft** |

## 3. Table-Stakes vs. White-Space

**Table-Stakes (haben alle):** Whale-Feed, Insider-/Smart-Score, Leaderboard, Copy-Trade, "Backtest"-Label, Telegram-Alerts.

**White-Space (nachweislich schlecht/gar nicht gelöst) — nach Nachfrage × Ungelöstheit:**

1. **Verifizierbare, korrekte Track-Records statt Vanity-Leaderboards** (größter Wedge). Belegte Defekte, die JEDES Leaderboard hat:
   - **NegRisk-Doppelzählung:** Multi-Outcome-Märkte werden pro Outcome gezählt → **Win-Rates bis 2× aufgebläht** (OrcaLayer).
   - **Falsches/vorzeichen-verkehrtes PnL:** gewonnene Positionen werden auto-redeemed und verschwinden aus der API → naive Tools zeigen Verlust statt Gewinn (Leo Labs: **−$3.5M angezeigt vs. +$11.4M real**).
   - **Survivorship + Zombie-Orders:** naive WR 70-80 %, **settled-only echte WR nur 55-62 %** (SeriouslySirius real 53.3 %). ~16 % der Leaderboard-Spitze sind Airdrop-Farmer; **~25 % des Volumens ist Wash-Trading** (Columbia; 45 % im Sport).
   - Niemand außer PredictFolio/OrcaLayer rechnet korrekt. → **Unser Moat: settled-only, NegRisk-korrigiert, Farmer-gefiltert, exit-liquiditäts-adjustiert, kalibrierungs-bewertet, Verhaltens-gelabelt (direktional/Hedge/MM/Arb), Multi-Wallet-verknüpft (Louvain haben wir), mit publizierter Methodik.**

2. **Echtes Cross-Venue-UI** (PM + Kalshi, später Limitless/Manifold): konsolidierte Quoten, Arbitrage, **venue-übergreifend abgestimmte PnL**. adj.news=nur API, Dome von PM gekauft, UW/polywhaler=PM-only. Das manuelle Diffen macht heute jeder selbst. **Cross-Venue-Neutralität ist der Moat, den PM & Kalshi selbst nie bauen** (zeigen nie die Konkurrenz-Quoten).

3. **Ehrlichkeit über Copy-Decay.** Kern-Defekt: Whale bewegt mit eigenem Einstieg den dünnen Book → Copier kauft die Spitze (Whale ~127 % vs. Copier ~100 %). Plus MEV-Frontrun (ms), Cat-and-Mouse (Zweit-Accounts, Iceberging, Merge-Exits → "du wirst Exit-Liquidity"). **Niemand disclosed das.** Wir: "Median-Copier X¢ schlechter gefüllt", nur wo Copy viabel ist.

4. **Prediction-Market-native Steuer + Cross-Venue-Reconciliation.** Kein Anbieter löst es ("None observed"). PM gibt keine Steuerformulare; jeder Trade = Krypto-Event (Form 8949); Cross-Venue = zwei Steuer-Frameworks. **Hohe WTP, wide open.**

5. **Persönliches Kalibrierungs-Dashboard für Echtgeld-Trader.** Manifold/Metaculus (Spielgeld) haben Brier-Score/Kalibrierung; PM/Kalshi **nicht**. "Bin ich wirklich kalibriert / habe ich Edge?" — sauberer, unbesetzter Gap. Perfekter Free-Tier/Credibility-Funnel.

6. **Resolution-/UMA-Dispute-Risiko-Alerts.** Echte Verluste ($7M Ukraine-Markt falsch aufgelöst, 25 % UMA-Voting-Power). Kein Mainstream-Tool warnt "deine offene Position ist in Dispute". Verteidigbar via Resolution-Präzedenz-Datensatz.

7. **Kategorie-bewusstes, erklärbares Insider-Screening.** UW & Co. scoren Sport-Odds als "Insider" (Rauschen). Wir: Sport/Wetter raus, Politik/Geopolitik rein, "warum geflaggt". **Nur wir machen das.**

## 4. Unsere Assets (schon gebaut)

- **Cross-Venue PM + Kalshi in einer UI** (nicht nur API).
- **Kategorie-bewusstes Insider-Screening** (Sport/Wetter ausgeschlossen — macht sonst keiner).
- **Rigoroser Backtester** (Copy/Fade, 4 Sizing-Modi, Exposure-Cap, Mid-Window-Resolutions, **ehrliche Flat-Curves**).
- **Louvain-Co-Trading-Netzwerk** (Multi-Wallet-Cluster — genau das Werkzeug gegen Cat-and-Mouse).
- **Non-custodial by architecture** (Paper-only) — Custody ist DER Trust-Bottleneck (Polycule $230k, PolyGun-Keys serverseitig trotz "non-custodial"-Marketing).
- **WS-Fast-Copy** (sub-Sekunde).

## 5. Differenzierungs-These — vier Säulen

**Säule 1 — Korrekte, verifizierbare Track-Records ("die Mathematik stimmt").** Das ist der #1-Trust-Hebel der ganzen Kategorie (belegt: Sport-Wetten Blogabet/Pyckio-Modell = vorab-committed, unlöschbar). Settled-only, NegRisk-korrigiert, survivorship-bereinigt, kalibriert, on-chain nachprüfbar, Methodik publiziert. **Prove before you copy:** unser Backtester bewertet eine Wallet ehrlich (echte Fees/Slippage/Decay) BEVOR man folgt. Moat gegen UW (monitoring-only) und Copy-Bots (blindes Mirroring).

**Säule 2 — Cross-Venue Truth Layer.** DAS neutrale unified Terminal PM + Kalshi: Quoten, Arb, abgestimmte PnL/Tax. Verteidigbar, weil die Venues es aus Interessenkonflikt nie bauen.

**Säule 3 — Research/Intelligence statt Copy-Funnel.** Insider-Screen = erklärbare **Warnung** (kategorie-bewusst), nicht "tail the insider". Umgeht Audit-/BGS-Art.-130-Falle (Kreo/Polycool), gewinnt Sharps/Researcher/Journalisten (gratis Kalibrierungs-Layer → Zitate → Marketing).

**Säule 4 — Ehrliche, non-custodial Positionierung.** "Wir fassen deine Funds nie an" + "du hättest beim Kopieren Geld verloren" — genau die Analytics, die die konfliktbehafteten Incumbents (PM/Kalshi/Copy-Bots) NICHT bauen können.

## 6. Bedrohungen & Konsolidierung

- **Konsolidierung läuft:** Polymarket kaufte **Dome** (unified API), betreibt COPYCAT/Stand-Copy. Kalshi baut **eigenes Bloomberg-Terminal** (CNBC 04.06.2026, Alpha). → Rohdaten-Normalisierung + native Copy werden commoditized/first-party. **Nicht dort kämpfen.**
- **Verso (YC):** best-finanzierter Independent-Multi-Venue-Terminal → schneller sein bei Trust-Rigor + Backtest + Kategorie-Intelligenz + ehrlichem Copy-Decay (haben sie nicht).
- **Unusual Whales (3M Follower):** Distribution unerreichbar → nicht auf PM-Insider-Terrain kämpfen; gewinnen auf Cross-Venue + Rigor + Actionability.
- **Kalshi-Anonymität:** Insider/Copy/verifizierte-Leaderboards sind auf Kalshi **strukturell unmöglich** (keine Wallets) — ehrlich sein: unser Kalshi-Layer = event-level; Wallet-Rigor = Polymarket-nativ.
- **Funding-Welle = Zeitdruck:** Kalshi raist ~$40B, Polymarket ~$15B, ICE $2B rein; **5c(c) Capital (~$35M, erster PM-VC-Fonds)** wird ~20 weitere Tooling-Startups finanzieren. Der Raum wird schnell voller und besser finanziert → **jetzt Position besetzen, nicht später.**

**Am wenigsten umkämpfte Achsen (fast leer, echte Nischen):**
- **Non-English-Märkte** — jedes gefundene Tool ist English-only. Unbesetzt.
- **Mobile** — praktisch niemand (nur Verso/Kalshi-Terminal deuten es an).
- **Counter-Trading** — auto-faden von nachweislich schlechten Wallets (nur Stand macht es). **Wir haben die FADE-Strategie im Backtester bereits** — direkt ausbaubar.
- **Prosumer-Tier (~$20-40)** — seriöses Retail will Institutional-Analytics zu fairem Preis; dünn bedient.

## 7. Konkreter Bau-Plan (differenzierende Features, priorisiert)

1. **Track-Record-Engine v2** (größter Wedge, nutzt Louvain + Backtester): settled-only PnL (Auto-Redeem-korrekt), **NegRisk-Korrektur**, Farmer-Filter, Wash-Filter, exit-liquiditäts-Haircut, Kalibrierung, Verhaltens-Label, Multi-Wallet-Cluster, publizierte Methodik. Ersetzt das Vanity-Leaderboard auf Traders.
2. **Cross-Venue reconciled PnL + Tax-Export** (Form-8949-fähig) — Cross-Venue-Seite ausbauen. Hohe WTP, unbesetzt.
3. **Copy-Decay-Ehrlichkeit** aus WS-Detection-vs-Fill-Daten: "Median-Copier X¢ schlechter", pro Markt/Size-Band.
4. **Persönliches Kalibrierungs-Dashboard** ("war 70 % wirklich 70 %?") — Resolved-Seite + Brier/Kalibrierungs-Kurve. Free-Tier/Credibility-Funnel.
5. **Resolution-/Dispute-Risiko-Alerts** — "deine Position ist in UMA-Dispute" + Ambiguitäts-Score pro Markt.
6. **Alerts-mit-Kontext** (Hedge vs. neues Risiko), gegen "spammy alerts".

## 8. Monetarisierung (matcht die Segmente + Preis-Anker)

**Preis-Realität:** PM-Tools sind **niedrig geankert ($10-20/Mo)**, weil Daten öffentlich + Gratis-Konkurrenz. Analogie-Leiter: TradingView $15/**$30 (sweet spot)**/$60; Pikkit $40; Nansen $129; Dune $399 (nur Pro/High-Volume). Usage-based/Pay-per-use im Kommen ($0.25/10 Whales).

- **Free (Reichweite + Trust):** Kalibrierungs-Layer, Basis-Feeds, citier­bare Quoten → Researcher/Journalisten/Casuals als Funnel.
- **Pro (~$19-29/Mo, Sharps/Degens):** Cross-Venue-Flow, Track-Record-Engine, Copy-Decay, reconciled PnL/Tax, Alerts-mit-Kontext, Backtester.
- **Data/API (~$99/Mo, Builder/Quant):** historische Orderbook-Daten + API — bewiesene recurring WTP.
- **Optional Usage-Credits** für Gelegenheitsnutzer (statt $100+-Sub).
- **Frictionless self-serve Cancel + transparente Abrechnung** (Nansen verliert Kunden genau daran).
- **Nicht:** Vanity-Leaderboard, Insider-Copy-Hype, Custody, Referral-Links (BGS + Trust), Flat-Fee-für-Signale (Incentive-Misalignment).

## 9. Anti-Ziele (bewusst NICHT tun)

Kein blindes Copy ohne Decay-Warnung. Kein "tail-the-insider"-Funnel (Audit/BGS). Keine Custody. Kein Single-Venue-Denken. Kein wash-/NegRisk-verzerrtes Leaderboard. Kein Hype-Marketing ("900 % gewonnen") — verbrennt genau die zahlenden Sharp/Researcher. Keine undisclosed Referral-Deals (Trust-Killer).

## 10. Einzeiler-Pitch

> **"Bloomberg für Prediction Markets — cross-venue, ehrlich, non-custodial. Verifizierte settled-only Track-Records statt aufgeblähter Leaderboards. Prove before you copy."**

## 11. Sofort-Chancen (kostenlos, aus Recherche)

- **Kalshi Builders Grant** ($2M+ Pool, bis $10k/Grant, nennt "analytics dashboards" explizit) — Bewerbung = Funding + Distribution + schriftliche Autorisierung.
- **Polymarket Builder-Profil** (schriftliche Spur, Verified-Tier).
- **PredictFolio als Genauigkeits-Benchmark** nehmen (0.7 % Abweichung anpeilen) → Journalisten-Zitate = gratis Marketing.

Verwandte Docs: [LAUNCH_PLAN.md](LAUNCH_PLAN.md) (Recht/Auth/Firma), [LIVE_COPYTRADING_PLAN.md](LIVE_COPYTRADING_PLAN.md) (Speed/Wallet-Connect/Copy-Recht), [HANDOFF.md](HANDOFF.md) (Stand/Roadmap).
