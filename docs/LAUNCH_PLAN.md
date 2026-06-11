# Launch-Plan: Daten-Rechte, Auth, Standort & Einnahmen

Stand: 2026-06-12. Vier Recherchen (Kalshi/Oddpool, Polymarket, Auth-Provider, CH-Recht/Firmenstruktur) mit Primärquellen — Details und Links in den jeweiligen Abschnitten. Research-Unterstützung, keine Rechtsberatung; wo ein Anwalt nötig ist, steht es explizit.

---

## Die Antworten auf die offenen Fragen (Kurzfassung)

| Frage | Antwort |
|---|---|
| **Müssen wir Kalshi entfernen?** | **Nein.** Behalten + Attribution + **Kalshi-Builders-Bewerbung** einreichen (verwandelt geduldete Nutzung in schriftlich autorisierte). Architektur so bauen, dass Kalshi per Schalter abschaltbar ist. |
| **Wie "darf" Oddpool das?** | Sie haben **keine offengelegte Lizenz** — sie operieren in der geduldeten Zone, wie das ganze Ökosystem. YC finanziert sie öffentlich; Kalshi hat noch nie einen Aggregator abgemahnt und vergibt selbst $2M-Grants an "analytics dashboards". |
| **Auth auslagern?** | **Ja.** Sofort: Streamlit-natives `st.login()` + Google-OIDC (gratis, 2–4 h) für Admin-Gating. Später Freemium: **Auth0 Free-Tier** (25k MAU, EU-Tenant) hinter demselben `st.login()` + Stripe (8–16 h). Nichts selbst hosten. |
| **Polymarket-Limits — reicht das?** | **Locker.** Unser Server-Cache nutzt einstellige Prozent der dokumentierten Limits (Gamma 4'000 Req/10 s …). Rote Linie der ToS ist nur institutionelle Daten-Distribution (ICE-Exklusivdeal) — Retail-Dashboards sind die geduldete, teils offiziell beworbene Kategorie. Aktion: **Builder-Profil + Mail an builder@polymarket.com**. |
| **Standort/Firma — Ausland wegen CH-Sperre?** | **Ausländische Firma bringt nichts**: Die Strafbarkeit (BGS-Werbeverbot) haftet an der handelnden Person, nicht am Firmenmantel, und eine aus CH geführte US-LLC/estnische OÜ wird steuerlich zur Schweizer Gesellschaft ("Ort der tatsächlichen Verwaltung"). Der echte Hebel: **CH-Geoblocking + keine Referral-/Sign-up-Links**. Einnahmen: Einzelfirma → ab ~CHF 100k GmbH. |

---

## 1. Kalshi: Befund und Playbook

**Die Papierlage ist streng:** Das Developer Agreement (v1.1, von Kalshis eigenem S3-Bucket) beschränkt API-Nutzung auf "facilitating a member's own trading" (§3) und verbietet Caching/Weitergabe ohne "prior written authorization" (§3.1); die Data Terms erlauben nur "personal use for non-commercial purposes". Kündigung jederzeit möglich (§8), Haftungsdeckel $50.

**Die Praxis ist das Gegenteil:**
- **Oddpool, Inc.** (Delaware, YC Spring 2026, Ex-Microsoft/Bloomberg-Gründer) verkauft Kalshi+Polymarket-Daten als Abo (Pro $30/Premium $100/Mo) — ohne jede offengelegte Lizenz, nur mit Disclaimer "Informational only".
- **Dome** (YC, $5.2M) verkaufte eine kommerzielle Kalshi+Polymarket-API — und wurde im Feb 2026 **von Polymarket gekauft**, ohne dass Kalshi je interveniert hätte.
- **Google** zeigt Kalshi-Odds in Search/Finance (seit 11/2025), **CNN** hat einen Kalshi-Live-Ticker (12/2025), **Pyth** publiziert Kalshi-Preise on-chain, electionbettingodds.com aggregiert seit Jahren.
- **Kalshi selbst wirbt um Builder**: [kalshi.com/builders](https://kalshi.com/builders) mit "$2M in Grants & Developer Support"; der KalshiEco Hub (12/2025) nennt explizit "analytics dashboards" als gewünschte Kategorie und listet "Kalshinomics, a dashboard for market analytics" als Kollaborateur.
- **Kein einziger Enforcement-Fall** gegen einen Daten-Re-Publisher auffindbar. Kalshis Rechtsenergie geht in Regulator-Streitigkeiten; ihr Marketing zahlt Influencer.

**Realistisches Worst-Case** für eine kleine Research-Site: API-Key-/Konto-Kündigung plus Takedown-Mail — keine Klage (öffentliche Preise sind als Fakten urheberrechtlich schwach, *Feist*; der Vertrag ist das einzige Instrument, und dessen Schaden ist auf $50 gedeckelt).

**Ein Zukunftsrisiko:** Kalshi baut selbst ein "Bloomberg Terminal for prediction markets" (CNBC, 04.06.2026) — sie könnten Datenzugang später formalisieren/monetarisieren (CME-Playbook). Darum: Abschaltbarkeit einbauen.

**Playbook (in dieser Reihenfolge):**
1. **Kalshi-Builders-Bewerbung einreichen** (kalshi.com/builders) — Annahme ist faktisch die "written authorization", die beide ToS-Dokumente als Heilung nennen; dazu Grant-Chance und Marketing-Support. Parallel im Developer-Discord (#dev) fragen.
2. Attribution im Footer (bereits drin): "Data: Kalshi, Polymarket — not affiliated with or endorsed by either exchange."
3. **Nie "Kalshi" im Produktnamen/Domain** (Trademark ist das Einzige, was Kalshi aktiv verteidigt).
4. Keine Roh-/Bulk-Daten-Exporte verkaufen (meistverbotene Handlung in beiden Dokumenten); UI/Analyse verkaufen, nicht Daten.
5. Keine Member-Deanonymisierung (§3.6 — passt: Kalshi liefert eh keine Identitäten), Rate-Limits respektieren (tun wir), keine AI-Trainings-Claims auf Kalshi-Daten.
6. **Feature-Flag für Kalshi**: ein Settings-Schalter, der alle Kalshi-Feeds sauber deaktiviert, falls je eine Aufforderung kommt (Kündigungs-at-will ist das echte operative Risiko).

## 2. Polymarket: Befund und Maßnahmen

**ToS (Effective 01.06.2026, via eingebettetes Google-Doc gelesen):** Die Lizenz ist "personal, limited, revocable" — **ohne** Non-Commercial-Klausel. Die neue Daten-Klausel verbietet Nutzung/Weiterverkauf nur an **"Capital Market Clients"** (Broker, Hedgefonds, Market Maker, ETF-Emittenten …) und **"market data distributors"** ohne schriftliche Vereinbarung — das schützt den exklusiven institutionellen Feed von **ICE** ($2-Mrd-Investment 10/2025, "Polymarket Signals and Sentiment" seit 02/2026). Retail-Dashboards sind nicht das Ziel der Klausel.

**Ökosystem:** polymarketanalytics.com (Goldsky-On-Chain-Indexing + Gamma-API) wurde in **Polymarkets eigenem Newsletter** vorgestellt; QuickNode listet 10+ Whale-Tracker; polywhaler/polyloly verkaufen Abos; **kein C&D gegen eine Analytics-Site bekannt**. Der ToS-Carve-out behält sich ausdrücklich vor, "access to public on-chain infrastructure and the Company's builder program" zu gewähren — On-Chain-Indexing ist die explizit saubere Spur.

**Limits (verifiziert, weiterhin aktuell):** Global 15'000 Req/10 s; Gamma 4'000/10 s (Markets 300, Events 500); Data-API 1'000/10 s (Trades 200); CLOB 9'000/10 s (Book/Price 1'500). Drosselung = Cloudflare-Queueing statt Fehler. **WebSocket-Marktkanal ist öffentlich und ohne Auth** — ersetzt Polling. Mit unserem geteilten Server-Cache (TTL 30–900 s) ist die Origin-Last unabhängig von der Besucherzahl: ~einstellige Prozent der Kapazität selbst bei 10k Besuchern/Tag.

**Maßnahmen:**
1. **Builder-Profil anlegen** (polymarket.com/settings → Builder) und **builder@polymarket.com** anschreiben (API-Key, Use Case, erwartetes Volumen) → Verified-Tier. Kostet nichts, schafft die schriftliche Spur, und macht das Copy-Trading-Feature zukunftsfähig (Builder-Code = Volumen-Credit, wöchentliche USDC-Rewards, Grant-Eligibility).
2. Eigene ToS der Site: Anzeige/Analyse ja, kein Roh-Feed-Verkauf, insbesondere nicht an Finanzinstitute.
3. Bei Wachstum: WSS statt REST-Fan-out; historische Backfills über On-Chain (Achtung: seit 28.04.2026 v2-Datasets bei Goldsky, alte Public-Subgraphs liefern falsche Daten).
4. Kein "Polymarket" im Produktnamen/Domain.

## 3. Auth: Auslagern — ja, so

**Sofort (Launch, Admin-Schutz, 2–4 h):** Streamlit-natives **`st.login()` + Google-OIDC direkt** — gratis, kein MAU-Limit, kein Anbieter-Lock-in. Settings-/Admin-Seite oben mit `st.user.is_logged_in` + E-Mail-Allowlist gaten, Fake-Sign-in-Shell löschen. Stolperfallen: Cookie fix 30 Tage; Streamlit ≥ gepatchte Version wegen der 1.57-Cookie-Regression pinnen; ggf. `client_kwargs = { "prompt" = "login" }` gegen den Logout-Account-Chooser.

**Später (Freemium mit Accounts + Stripe, 12–24 h gesamt):** **Auth0 Free-Tier** — seit Ende 2024 **25'000 MAU gratis**, EU-Tenant (Frankfurt/Dublin) wählbar, gehostete Login-/Signup-Seite, E-Mail-Verifizierung, Magic Links, Social Logins; eigener Mail-Provider statt Auth0-Dev-Mailer vor Launch. Integration: derselbe `st.login()`-Aufruf, nur secrets.toml ändern — der Gating-Code bleibt identisch. Zahlung: Stripe + [st-paywall](https://github.com/tylerjrichards/st-paywall) oder ~100 Zeilen eigener Entitlement-Check (`st.user.email` → Stripe-Subscription → Session-Cache).

**Alternativen, falls relevant:** **WorkOS AuthKit** (1 Mio. MAU gratis — größtes Free-Tier, $99/Mo für Custom Domain) wenn 25k MAU je knapp werden; **Zitadel** (Schweizer Firma, EU-Regionen) wenn CH/EU-Datenhaltung Pflicht wird. **Nicht nehmen:** Clerk (React-zentriert, OIDC-Umweg bringt nichts), Supabase Auth (keine gehostete Login-UI), Firebase (kein OIDC-Server für st.login), Keycloak self-hosted (Ops-Last solo unverhältnismäßig). Cloudflare Access (50 User gratis, E-Mail-OTP) bleibt die richtige Wahl für eine private Beta oder eine separate Admin-Instanz — nicht für "öffentlich mit geschütztem Settings-Tab" (eine Streamlit-Origin lässt sich nicht pfadweise gaten).

## 4. Standort, Firma, Einnahmen

**Territorialität des BGS-Werbeverbots (Art. 74 Abs. 3):** Geschützt wird der Schweizer Markt; Kommentar-Literatur stellt auf Werbung ab, die **in der Schweiz wahrnehmbar/auf die Schweiz gerichtet** ist. Ausländische Anbieter nutzen **CH-Geoblocking**, um von der GESPA-Liste zu kommen — das ist das anerkannte, systemkonforme Muster. Aber: Wer **von Schweizer Boden aus handelt**, handelt strafrechtlich in der Schweiz, auch bei ausländischem Publikum — darum schützt weder Auslands-Hosting noch eine Auslandsfirma die Person. GESPA-Praxis 2024/25: 12–25 Strafanzeigen, Fokus auf Betreiber und **CH-gerichtete Promotion** (Influencer-/Affiliate-Fälle). **Kein Fall** gegen eine englischsprachige, CH-geoblockte Informations-Site gefunden. Wichtig: Neutrale Datendarstellung ist Information, nicht Werbung — SRF/20min publizieren laufend Polymarket-Quoten. Die Grenze verläuft bei Referral-Codes, Bonus-Inhalten, "Trade now"-CTAs.

**Konsequenz Standortfrage:** Nicht der Firmensitz, sondern das **Site-Design** entscheidet. Empfehlung: international launchen, **Schweiz geo-blocken** (Cloudflare-Regel, 5 Minuten) oder mindestens CH-Besuchern die Outbound-Links zu polymarket.com/kalshi.com ausblenden; keinerlei Referral-Monetarisierung.

**Firmenstruktur (Kosten 2026):**

| Struktur | Einmalig | Laufend | Urteil |
|---|---|---|---|
| Privatperson (Phase 0) | CHF 0 | CHF 0 | Reicht ohne Einnahmen. Impressum + DSE trotzdem jetzt. |
| **Einzelfirma (Phase 1)** | ~CHF 0 (HR-Eintrag erst ab CHF 100k Pflicht) | ~10 % AHV auf Nettoeinkommen (ab CHF 2'300/Jahr anmelden) | **Standard für erste Einnahmen.** Verschlechtert die BGS-Lage nicht — die haftet eh an der Person. |
| **GmbH (Phase 2)** | CHF 20k Kapital + CHF 800–3'500 Gründung | CHF 2'500–5'000/Jahr (Buchhaltung etc.) | Ab ~CHF 100k Umsatz oder B2B-/Werbeverträgen. |
| US-LLC / estnische OÜ | $100–300 bzw. €400+ | + IRS-Form 5472 ($25k Busse bei Versäumnis) bzw. €59–179/Mo Accounting | **Falle:** aus CH geführt = steuerlich Schweizer Gesellschaft (doppelte Pflichten), und null Schutz beim Werbeverbot. Nur bei echtem Wegzug sinnvoll. |

**Einnahmen-Mechanik:**
- **Abos:** Unter ~CHF 100–200k Umsatz **Merchant of Record** (Paddle/Lemon Squeezy, ~5 % + $0.50) — übernimmt als Verkäufer die gesamte EU/UK-MwSt. Alternative mit mehr Marge: Stripe (2.9 % + 0.30) + **Non-Union-OSS**-Registrierung in einem EU-Land (Pflicht ab dem ersten Euro B2C-Digitalumsatz in die EU — kein Schwellenwert für Nicht-EU-Anbieter!).
- **Schweizer MWST:** Registrierung ab CHF 100k **Weltumsatz** (30 Tage Frist); Abos an Auslandskunden = 0 % CH-MWST.
- **Ads (AdSense):** Vertragspartner Google Ireland, 0 % CH-MWST, zählt aber zur 100k-Schwelle; W-8BEN hinterlegen. Achtung: AdSense könnte eine Prediction-Market-Site als Gambling-nah einstufen und Ads limitieren — Abos sind das robustere Modell.

**Der eine Anwaltstermin, der sich lohnt** (Phase 1, vor Monetarisierung): 2–4 h bei einer Gaming-/ICT-Kanzlei (CHF 250–450/h, schriftliche Kurzeinschätzung CHF 1'000–3'000) zu genau zwei Fragen: (a) Link-Policy/CH-Posture unter Art. 74 Abs. 3 BGS, (b) Absegnung des Geoblocking-Setups. Mehr Anwalt braucht es nicht.

## 5. Roadmap (konkrete Reihenfolge)

**Sofort (CHF 0):**
1. Kalshi-Builders-Bewerbung + Polymarket-Builder-Profil/-Mail — beide schriftlichen Spuren anstoßen.
2. Kalshi-Feature-Flag in Settings (sauberes Abschalten).
3. `st.login()` + Google-OIDC fürs Admin-Gating; Fake-Auth-Shell raus.
4. CH-Geoblocking-Entscheid umsetzen (Cloudflare-Country-Rule) + Referral-/CTA-Verbot als feste Site-Policy.
5. Impressum + Datenschutzerklärung (revDSG) als Seite.

**Launch (~CHF 6–8/Mo, siehe PRODUCTION_READINESS.md):**
6. Domain + VPS + Cloudflare + Deploy (Artefakte liegen bereit).
7. Eigene Site-ToS (Anzeige/Analyse ja, kein Datenfeed-Verkauf).

**Erste Einnahmen (< CHF 100k):**
8. Einzelfirma/AHV-Anmeldung (ab CHF 2'300 Nettoeinkommen), Paddle/Lemon Squeezy als MoR, Auth0 vor `st.login()`, Stripe-Entitlements.
9. Anwalts-Kurzgutachten (CHF 1'000–3'000) zur Link-Policy/Geoblocking.

**Skalierung (> CHF 100k):**
10. GmbH-Umwandlung; MWST-Registrierung (30-Tage-Frist beachten); ggf. Stripe+OSS statt MoR; WSS/On-Chain-Indexing statt REST-Fan-out; Kalshi-Lage neu bewerten (deren eigenes Terminal beobachten).
