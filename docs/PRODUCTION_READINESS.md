# Production Readiness — öffentlicher Betrieb des Terminals

Stand: 2026-06-12. Recherchebasis: offizielle Doku von Streamlit, Hetzner, Cloudflare, Polymarket, Kalshi, EDÖB/KMU-Portal u. a. (Quellen jeweils verlinkt). Ziel: Alles im Repo ist vorbereitet — es fehlen nur noch die Dienste, die man **kaufen/registrieren** muss.

---

## 1. Empfohlene Architektur

**Docker Compose auf einem VPS hinter Caddy, Cloudflare Free davor.** Das ist 2026 das Standardmuster für Streamlit-Apps mit Hintergrundjobs.

```
Browser ──HTTPS──▶ Cloudflare (Free: DDoS, WAF, 1 Rate-Limit-Regel)
                      │
                      ▼
                Caddy (TLS via Let's Encrypt, Security-Header, optional Basic-Auth)
                      │ reverse_proxy (inkl. WebSocket)
                      ▼
            terminal (Streamlit, Port nur intern)   alert-scanner (gleiche Codebasis)
                      │
                  ./data Volume (Settings, Watchlists, Paper-Trading-DB)
```

**Warum nicht Streamlit Community Cloud?** ~1 GB RAM-Limit, keine Custom Domain (nur `*.streamlit.app`), US-Hosting, und vor allem: keine Hintergrund-Worker — der Alert-Scanner und der Copy-Daemon können dort nicht laufen. ([Limits](https://docs.streamlit.io/knowledge-base/deploy/resource-limits), [Domains](https://docs.streamlit.io/knowledge-base/deploy/custom-subdomains))

**Warum nicht Railway/Render/Fly?** Funktioniert, aber App + Scanner + Bot = mehrere Services = mehrere Posten (Railway Hobby $5/Mo + Verbrauch; Render Starter $7/Mo pro Service, Free-Tier schläft nach 15 min ein). Ein VPS fährt alles zusammen günstiger.

**Streamlit-Eigenheiten, die die Auslegung bestimmen:**
- Eine persistente WebSocket-Verbindung pro Browser-Tab; der Proxy muss WebSocket-Upgrades durchreichen (Caddy macht das automatisch). ([Architektur](https://docs.streamlit.io/develop/concepts/architecture/architecture))
- Ein einziger Python-Prozess; CPU-lastige Berechnungen blockieren andere Sessions. Für 100–1000 Besucher/Tag reicht das — `st.cache_data` (im Code durchgehend mit TTLs 30–900 s) teilt API-Antworten über **alle** Nutzer, d. h. die Polymarket/Kalshi-Last wächst nicht mit der Nutzerzahl. ([Caching](https://docs.streamlit.io/develop/concepts/architecture/caching))
- Health-Endpoint für Monitore: `GET /_stcore/health` → "ok" (alternativ `/healthz`).

**Dimensionierung:** Hetzner **CX23** (2 vCPU/4 GB, €3.99/Mo) reicht zum Start; **CX33** (4 vCPU/8 GB, €6.49/Mo) wenn viele gleichzeitige Sessions mit großen DataFrames erwartet werden. (Preise nach Hetzner-Preisanpassung vom 01.04.2026, [offiziell](https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/))

## 2. Was im Repo bereits vorbereitet ist

| Artefakt | Zweck |
|---|---|
| `Dockerfile` | Python-3.13-slim-Image, non-root User, Healthcheck, gehärtete Streamlit-Flags (XSRF an, CORS aus, Upload-Limit 1 MB, Telemetrie aus) |
| `docker-compose.yml` | 3 Services: `terminal` (nur intern exponiert), `alert-scanner`, `caddy` (einziger öffentlicher Einstieg, Ports 80/443) |
| `deploy/Caddyfile` | Automatisches TLS, HSTS, nosniff, Frame/Referrer/Permissions-Header, auskommentierter `basic_auth`-Block |
| `.env.example` | Alle Secrets als Env-Variablen; `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` übersteuern die Settings-Datei und werden nie zurückgeschrieben |
| `.dockerignore` | Hält Tests/Doku/Artefakte aus dem Image |
| `requirements.txt` | inkl. `networkx` (Louvain-Clustering läuft sonst nur im Fallback) |
| Sidebar-Disclaimer | "Research tool only — no investment advice … data provided as-is" auf jeder Seite |

**Deployment in 6 Schritten** (auf dem frischen VPS):
```bash
# 1. Docker installieren (Ubuntu 24.04): curl -fsSL https://get.docker.com | sh
# 2. Repo klonen, .env aus .env.example befüllen
# 3. Domain in deploy/Caddyfile eintragen (A/AAAA-Record zeigt auf den Server)
# 4. docker compose up -d --build
# 5. Cloudflare: DNS auf "Proxied", SSL-Modus "Full (strict)"
# 6. Monitor auf https://domain/_stcore/health richten
```

## 3. Security-Checkliste

- [x] **TLS:** Caddy holt/erneuert Let's-Encrypt-Zertifikate automatisch, sobald die Domain auf den Server zeigt.
- [x] **Security-Header:** HSTS, `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy`, `Permissions-Policy` im Caddyfile. **CSP bewusst nicht gesetzt:** Streamlits React-Frontend bricht unter strikter CSP (offene Issues [#6417](https://github.com/streamlit/streamlit/issues/6417), [#8524](https://github.com/streamlit/streamlit/issues/8524)) — falls gewünscht, zuerst nur als `Content-Security-Policy-Report-Only` testen.
- [x] **Streamlit-Härtung:** `enableXsrfProtection=true`, `enableCORS=false`, `maxUploadSize=1`, Telemetrie aus, App-Port nicht öffentlich (nur Caddy exponiert 80/443).
- [x] **Secrets:** Telegram-Token per Env (`.env`, gitignored); nie im JSON/Repo. Polymarket/Kalshi-Reads brauchen keinen Key.
- [ ] **Rate-Limiting/DDoS:** Cloudflare Free davor schalten — unmetered DDoS-Schutz, Bot Fight Mode, 1 Rate-Limit-Regel inklusive ([Plan](https://www.cloudflare.com/plans/free/)). Empfohlene Regel: max. ~30 Requests/10 s pro IP auf `/_stcore/*`.
- [x] **Admin-Bereiche schützen (wichtig):** ✅ Umgesetzt via Streamlit-nativem `st.login()` + Google-OIDC: sobald `.streamlit/secrets.toml [auth]` existiert (Template: `.streamlit/secrets.toml.example`), failt die Settings-Seite closed — nur eingeloggte Accounts auf der Admin-Allowlist (`ADMIN_EMAILS`-Env oder `[admin].emails` in secrets.toml) kommen durch; alle Research-Seiten bleiben öffentlich. Ohne Secrets: lokaler Research-Modus ohne Login-UI. Für Docker liegt der read-only-Secrets-Mount auskommentiert in `docker-compose.yml`. Zusätzlich möglich (ganze Site): **Cloudflare Access** (Zero Trust Free, bis 50 Nutzer) oder `basic_auth` im Caddyfile (Block auskommentiert bereit).
- [ ] **Updates:** monatlich `docker compose pull/build` (Patch-Releases), Ubuntu unattended-upgrades aktivieren.

## 4. Rechtliches (Schweiz) — vor dem Launch erledigen

1. **Impressum** (UWG Art. 3 Abs. 1 lit. s): Name, ladungsfähige Postadresse (kein Postfach), E-Mail. Pflicht gilt streng genommen für E-Commerce-Angebote; jede CH-Quelle empfiehlt es trotzdem für alle öffentlichen Sites — und sobald Spenden/Abo/Affiliate dazukommt, ist es zwingend. Verstöße sind strafbewehrt (UWG Art. 23). ([activemind](https://www.activemind.ch/blog/impressumspflicht/))
2. **Datenschutzerklärung** (revDSG, seit 09/2023): unabhängig von Cookies Pflicht — Verantwortlicher, Zwecke, Empfängerkategorien, Exportländer, einfach zugänglich. ([KMU-Portal](https://www.kmu.admin.ch/kmu/en/home/facts-and-trends/digitization/data-protection/new-federal-act-on-data-protection-nfadp.html))
3. **Kein Cookie-Banner nötig**, solange nur technisch notwendige Cookies gesetzt werden (Streamlit: Session/XSRF) und kein Ad-/Tracking-Stack läuft. Kein Google Analytics einbauen → Thema bleibt erledigt. (EDÖB-Cookie-Leitfaden v1.1, 10/2025)
4. **GDPR/EU:** greift nur bei gezieltem Ausrichten auf EU-Nutzer oder Behavioral Tracking. Ohne Ads/Tracking und ohne EU-Marketing: außen vor.
5. **Finanz-Disclaimer:** "Research only, keine Anlageberatung, keine Empfehlung" — im Sidebar-Footer bereits eingebaut; zusätzlich in Impressum/Disclaimer-Seite wiederholen. Keine personalisierten Empfehlungen anzeigen (tut die App nicht).
6. **⚠️ Geldspielrecht — der wichtigste Punkt:** Polymarket UND Kalshi stehen auf der **GESPA-Sperrliste** (verifiziert in der Blocklist vom 25.11.2025). **Werbung für nicht bewilligte Geldspiele ist verboten** (BGS Art. 74 Abs. 3, Bussen bis CHF 500'000), und schon **Verlinkung kann als Werbung gelten** — 2025 liefen Strafverfahren gegen Influencer wegen Online-Casino-Promo. Konsequenz für die Site:
   - Neutrale Daten-/Research-Darstellung ist Information, nicht Werbung (SRF/20min publizieren laufend Polymarket-Quoten) — aber **keine** Referral-/Affiliate-Links, keine "Trade now"-CTAs, keine Sign-up-Funnels.
   - **CH-Geoblocking** (Cloudflare-Country-Rule) ist das anerkannte Branchenmuster und die stärkste Absicherung; eine Auslandsfirma bringt dagegen nichts (persönliche strafrechtliche Haftung + Steuerfalle "Ort der tatsächlichen Verwaltung"). Struktur-/Einnahmen-Plan: [LAUNCH_PLAN.md](LAUNCH_PLAN.md).
   - Vor Monetarisierung: **2–4 h Beratung bei einem Schweizer Anwalt** zu BGS Art. 74 (Link-Policy + Geoblocking-Setup absegnen) — Kurzgutachten ca. CHF 1'000–3'000.
7. **Quellenangabe:** "Marktdaten: öffentliche Polymarket- und Kalshi-APIs, ohne Gewähr" (im Sidebar-Footer eingebaut).

## 5. API-Bedingungen & Limits

| Quelle | Limits (offiziell) | Bedingungen |
|---|---|---|
| Polymarket Gamma | 4'000 Req/10 s gesamt; `/markets` 300/10 s; `/events` 500/10 s | Dashboards/Research/Analytics inkl. kommerzieller Nutzung erlaubt; verboten ist nur Bulk-Weiterverkauf als Datenfeed. Kein API-Key nötig. ([Rate Limits](https://docs.polymarket.com/api-reference/rate-limits)) |
| Polymarket Data-API | 1'000 Req/10 s; `/trades` 200/10 s; `/positions` 150/10 s | dito; zusätzlich bekannter Offset-Cap ~3000 (im Code behandelt) |
| Polymarket CLOB | 9'000 Req/10 s; `/book`,`/price` 1'500/10 s | dito |
| Kalshi trade-api/v2 | Basic-Tier 20 Reads/s (Token-Bucket); public Reads ohne Auth | Papier-ToS streng (personal/non-commercial), Praxis gegenteilig: YC-finanzierte Aggregatoren (Oddpool), Google/CNN-Integrationen, Kalshis eigenes Builders-Programm wirbt um "analytics dashboards" ($2M Grants), kein Enforcement-Fall bekannt. **Maßnahme: Kalshi-Builders-Bewerbung = schriftliche Autorisierung; Kalshi-Feature-Flag für sauberes Abschalten.** Details + Playbook: [LAUNCH_PLAN.md](LAUNCH_PLAN.md). ([Data Terms PDF](https://kalshi-public-docs.s3.amazonaws.com/kalshi-data-terms-of-service.pdf), [Rate Limits](https://docs.kalshi.com/getting_started/rate_limits)) |
| Telegram Bot API | ~1 Msg/s pro Chat, ~30 Msg/s broadcast, 20 Msg/min pro Gruppe | Free; der Scanner dedupliziert bereits und bleibt weit darunter |

Die App-Caches (TTL 30–900 s) halten die tatsächliche API-Last unabhängig von der Besucherzahl in der Größenordnung von ~1–2 Req/s — weit unter allen Limits.

## 6. Betrieb

- **Uptime:** Better Stack Free (10 Monitore, 3-min-Checks, 1 Statuspage) auf `https://domain/_stcore/health`. (UptimeRobot Free verbietet seit 12/2024 kommerzielle Nutzung.)
- **Fehler-Tracking:** Sentry Developer (free, 5'000 Events/Mo) — `sentry-sdk` initialisieren, Init gegen Streamlit-Reruns guarden. Optionaler späterer Einbau.
- **Backups:** Nächtlich `restic` von `./data` (Settings, Watchlists, SQLite) auf Hetzner Object Storage (€6.49/Mo) oder beliebiges S3; zusätzlich wöchentlicher Server-Snapshot (€0.0143/GB/Mo).
- **Logs:** Docker-Logging-Driver `json-file` mit `max-size: 10m`, `max-file: 3` (in Compose ergänzbar).
- **Auto-Deploy (optional):** GitHub Actions → Image nach GHCR → `appleboy/ssh-action` → `docker compose pull && up -d`.
- **Windows-Task-Altlast:** Beim Umzug auf den VPS die lokalen Scheduled Tasks (`MarketIntelTerminal` etc.) via `scripts/uninstall_autostart.ps1` entfernen.

## 7. Einkaufsliste (das Einzige, was noch fehlt)

| # | Posten | Anbieter/Empfehlung | Kosten |
|---|---|---|---|
| 1 | **Domain** (.ch) | Infomaniak | ~CHF 9–12/Jahr (1 Mail-Adresse inklusive) |
| 2 | **VPS** | Hetzner CX23 (Falkenstein/Helsinki) + IPv4 | ~€4.50/Mo ex MwSt (CX33: ~€7/Mo) |
| 3 | Cloudflare Free + Zero Trust Free | Cloudflare | CHF 0 |
| 4 | TLS (Caddy/Let's Encrypt) | — | CHF 0 |
| 5 | Uptime (Better Stack Free) | — | CHF 0 |
| 6 | Fehler-Tracking (Sentry Developer) | — | CHF 0 |
| 7 | Backups (Object Storage, optional) | Hetzner | €0–6.50/Mo |
| 8 | Anwalts-Konsultation BGS/Kalshi-ToS (einmalig, empfohlen) | CH-Kanzlei | ~CHF 300–600 einmalig |

**Laufende Kosten: ~CHF 6–8/Monat** (Minimal-Setup) bzw. **~CHF 15–25/Monat** (mit 8-GB-VPS + Object-Storage-Backups).

## 8. Launch-Checkliste (Reihenfolge)

1. Domain registrieren, Nameserver auf Cloudflare.
2. VPS bestellen, Docker installieren, Repo deployen (`docker compose up -d --build`), Domain im Caddyfile setzen.
3. Cloudflare: Proxy an, SSL "Full (strict)", Rate-Limit-Regel, Bot Fight Mode.
4. Cloudflare Access (oder Caddy basic_auth) vor die Site, solange Settings/Copy-Daemon ungeschützt sind.
5. Impressum + Datenschutzerklärung als eigene Seite/Sektion einfügen (Texte aus Generator, z. B. activemind.ch, gegenlesen).
6. **Kalshi Developer Agreement lesen** (Browser) und BGS-Frage anwaltlich klären; je nach Ergebnis "Open market"-Links anpassen oder Kalshi-Re-Display klären.
7. Better-Stack-Monitor + (optional) Sentry aktivieren.
8. Lasttest mit 10–20 parallelen Tabs; RAM auf dem VPS beobachten (`docker stats`).
9. Backup-Cron einrichten, Restore einmal testen.
10. Go-live; lokale Windows-Scheduled-Tasks deinstallieren.
