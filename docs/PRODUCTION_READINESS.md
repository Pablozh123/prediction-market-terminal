# Production readiness — running the terminal publicly

Last updated 2026-08-07. Researched against the official documentation of
Streamlit, Hetzner, Cloudflare, Polymarket, Kalshi and the Swiss data
protection authority, with sources linked inline. The point of this document:
everything that lives in the repository is prepared, and what remains is the
set of services someone has to **buy or register**.

---

## 1. Recommended architecture

**Docker Compose on a VPS behind Caddy, with Cloudflare Free in front.** This
is the standard pattern for a Streamlit app that also runs background jobs.

```
Browser ──HTTPS──▶ Cloudflare (Free: DDoS, WAF, one rate-limit rule)
                      │
                      ▼
                Caddy (TLS via Let's Encrypt, security headers, optional basic auth)
                      │ reverse_proxy (including WebSocket)
                      ▼
            terminal (Streamlit, internal port only)   alert-scanner (same codebase)
                      │
                  ./data volume (settings, watchlists, paper-trading DB)
```

**Why not Streamlit Community Cloud?** Roughly a 1 GB memory limit, no custom
domain (only `*.streamlit.app`), US hosting, and above all no background
workers — the alert scanner and the copy daemon cannot run there.
([limits](https://docs.streamlit.io/knowledge-base/deploy/resource-limits),
[domains](https://docs.streamlit.io/knowledge-base/deploy/custom-subdomains))

**Why not Railway, Render or Fly?** They work, but app plus scanner plus daemon
means several services and therefore several line items (Railway Hobby $5/month
plus usage; Render Starter $7/month per service, and the free tier sleeps after
15 minutes). One VPS runs all of it for less.

**Streamlit properties that drive the sizing:**

- One persistent WebSocket per browser tab, so the proxy has to pass WebSocket
  upgrades through. Caddy does that without configuration.
  ([architecture](https://docs.streamlit.io/develop/concepts/architecture/architecture))
- A single Python process, so CPU-heavy work blocks other sessions. For 100 to
  1000 visitors a day that is fine: `st.cache_data` is used throughout with
  TTLs between 30 and 900 seconds and shares API responses across **all**
  users, which means the load on Polymarket and Kalshi does not grow with the
  number of visitors.
  ([caching](https://docs.streamlit.io/develop/concepts/architecture/caching))
- Health endpoint for monitors: `GET /_stcore/health` returns "ok"
  (`/healthz` also works).

**Sizing:** a Hetzner **CX23** (2 vCPU, 4 GB, €3.99/month) is enough to start;
**CX33** (4 vCPU, 8 GB, €6.49/month) if many concurrent sessions with large
dataframes are expected. Prices reflect the Hetzner adjustment of 2026-04-01
([official](https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/)).

## 2. What the repository already ships

| Artifact | Purpose |
|---|---|
| `Dockerfile` | Python 3.13-slim image, non-root user, healthcheck, hardened Streamlit flags (XSRF on, CORS off, 1 MB upload limit, telemetry off) |
| `docker-compose.yml` | Three services: `terminal` (internal only), `alert-scanner`, `caddy` (the single public entry point, ports 80 and 443) |
| `deploy/Caddyfile` | Automatic TLS, HSTS, nosniff, frame/referrer/permissions headers, a commented-out `basic_auth` block |
| `.env.example` | Every secret as an environment variable; `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` override the settings file and are never written back |
| `.dockerignore` | Keeps tests, documentation and artifacts out of the image |
| `requirements.txt` | Includes `networkx`, without which the Louvain clustering silently runs its fallback |
| Sidebar disclaimer | "Research tool only — no investment advice … data provided as-is" on every page |

**Deployment in six steps** on a fresh VPS:

```bash
# 1. Install Docker (Ubuntu 24.04): curl -fsSL https://get.docker.com | sh
# 2. Clone the repo, fill .env from .env.example
# 3. Put the domain in deploy/Caddyfile (A/AAAA record pointing at the server)
# 4. docker compose up -d --build
# 5. Cloudflare: DNS "Proxied", SSL mode "Full (strict)"
# 6. Point a monitor at https://domain/_stcore/health
```

## 3. Security checklist

- [x] **TLS:** Caddy obtains and renews Let's Encrypt certificates as soon as
  the domain resolves to the server.
- [x] **Security headers:** HSTS, `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy` and `Permissions-Policy` in
  the Caddyfile. **CSP is deliberately absent:** Streamlit's React frontend
  breaks under a strict policy (open issues
  [#6417](https://github.com/streamlit/streamlit/issues/6417),
  [#8524](https://github.com/streamlit/streamlit/issues/8524)). If it is
  wanted, start with `Content-Security-Policy-Report-Only`.
- [x] **Streamlit hardening:** `enableXsrfProtection=true`, `enableCORS=false`,
  `maxUploadSize=1`, telemetry off, and the app port not published — only
  Caddy exposes 80 and 443.
- [x] **Secrets:** the Telegram token comes from the environment (`.env`,
  gitignored) and never from the JSON settings or the repository. Reading
  Polymarket and Kalshi needs no key at all.
- [ ] **Rate limiting and DDoS:** put Cloudflare Free in front — unmetered DDoS
  protection, Bot Fight Mode and one rate-limit rule are included
  ([plan](https://www.cloudflare.com/plans/free/)). Suggested rule: at most
  ~30 requests per 10 seconds per IP against `/_stcore/*`.
- [x] **Protecting the admin surface:** done, through Streamlit's native
  `st.login()` with Google OIDC. Once `.streamlit/secrets.toml [auth]` exists
  (template: `.streamlit/secrets.toml.example`) the Settings page fails closed
  — only signed-in accounts on the admin allowlist (`ADMIN_EMAILS` env or
  `[admin].emails`) get through, while every research page stays public.
  Without those secrets the app runs in local research mode with no login
  surface at all. For Docker the read-only secrets mount sits commented out in
  `docker-compose.yml`. To gate the whole site instead, use **Cloudflare
  Access** (Zero Trust Free, up to 50 users) or the `basic_auth` block in the
  Caddyfile.
- [ ] **Updates:** `docker compose pull && build` monthly for patch releases,
  and enable Ubuntu unattended-upgrades.

## 4. Legal (Switzerland) — before launch

1. **Imprint** (UWG Art. 3 para. 1 lit. s): name, a postal address that accepts
   service (not a PO box), email. Strictly the duty applies to e-commerce
   offerings, but every Swiss source recommends it for any public site — and it
   becomes mandatory the moment donations, a subscription or affiliate income
   appear. Violations are punishable (UWG Art. 23).
   ([activemind](https://www.activemind.ch/blog/impressumspflicht/))
2. **Privacy policy** (revDSG, in force since 09/2023): required regardless of
   cookies — controller, purposes, categories of recipients, export countries,
   easily reachable.
   ([SME portal](https://www.kmu.admin.ch/kmu/en/home/facts-and-trends/digitization/data-protection/new-federal-act-on-data-protection-nfadp.html))
3. **No cookie banner needed** as long as only technically necessary cookies
   are set (Streamlit uses session and XSRF cookies) and no advertising or
   tracking stack runs. Not adding Google Analytics keeps it that way.
   (Swiss data protection authority cookie guidance v1.1, 10/2025)
4. **GDPR:** applies only when deliberately targeting EU users or doing
   behavioural tracking. Without ads, tracking or EU marketing it does not
   engage.
5. **Financial disclaimer:** "research only, not investment advice, not a
   recommendation" — already in the sidebar footer, and worth repeating on the
   imprint or disclaimer page. No personalised recommendations are shown, and
   the app does not produce any.
6. **⚠️ Gambling law — the decisive point:** both Polymarket and Kalshi appear
   on the **GESPA blocklist** (verified against the list of 2025-11-25).
   **Advertising unlicensed gambling is prohibited** (BGS Art. 74 para. 3,
   fines up to CHF 500,000), and even **linking can count as advertising** —
   criminal proceedings ran against influencers for online casino promotion in
   2025. What follows for this site:
   - Neutral data and research presentation is information, not advertising —
     Swiss outlets publish Polymarket odds routinely — but **no** referral or
     affiliate links, no "trade now" calls to action, and no sign-up funnels.
   - **Swiss geoblocking** through a Cloudflare country rule is the accepted
     industry pattern and the strongest protection available. A foreign company
     does not help: personal criminal liability remains, and "place of
     effective management" creates a tax problem on top. Structure and revenue
     planning: [LAUNCH_PLAN.md](LAUNCH_PLAN.md).
   - Before monetising: **two to four hours with a Swiss lawyer** on BGS
     Art. 74, to sign off the link policy and the geoblocking setup. A short
     opinion costs roughly CHF 1,000 to 3,000.
7. **Attribution:** "market data: public Polymarket and Kalshi APIs, without
   warranty", already in the sidebar footer.

## 5. API terms and limits

| Source | Official limits | Terms |
|---|---|---|
| Polymarket Gamma | 4,000 req/10 s overall; `/markets` 300/10 s; `/events` 500/10 s | Dashboards, research and analytics are allowed including commercial use; only bulk resale as a data feed is prohibited. No API key needed. ([rate limits](https://docs.polymarket.com/api-reference/rate-limits)) |
| Polymarket Data API | 1,000 req/10 s; `/trades` 200/10 s; `/positions` 150/10 s | Same, plus the known offset cap around 3000, which the code handles |
| Polymarket CLOB | 9,000 req/10 s; `/book` and `/price` 1,500/10 s | Same |
| Kalshi trade-api/v2 | Basic tier 20 reads/s (token bucket); public reads need no auth | The written terms are strict (personal, non-commercial) while practice is the opposite: YC-funded aggregators, integrations at major outlets, and Kalshi's own builders programme courting "analytics dashboards" with $2M in grants. No enforcement case is known. **Mitigation: apply to the builders programme for written authorisation, and keep the Kalshi feature flag so it can be switched off cleanly.** Details: [LAUNCH_PLAN.md](LAUNCH_PLAN.md). ([data terms PDF](https://kalshi-public-docs.s3.amazonaws.com/kalshi-data-terms-of-service.pdf), [rate limits](https://docs.kalshi.com/getting_started/rate_limits)) |
| Telegram Bot API | ~1 msg/s per chat, ~30 msg/s broadcast, 20 msg/min per group | Free; the scanner already deduplicates and stays far below |

The application caches (TTL 30 to 900 seconds) hold the real API load at
roughly one to two requests per second independently of visitor count, which is
far under every limit above.

## 6. Operations

- **Uptime:** Better Stack Free (10 monitors, three-minute checks, one status
  page) against `https://domain/_stcore/health`. UptimeRobot's free tier has
  prohibited commercial use since 12/2024.
- **Error tracking:** Sentry Developer (free, 5,000 events/month) — initialise
  `sentry-sdk` and guard the init against Streamlit reruns. Optional, later.
- **Backups:** nightly `restic` of `./data` (settings, watchlists, SQLite) to
  Hetzner Object Storage (€6.49/month) or any S3, plus a weekly server snapshot
  (€0.0143/GB/month).
- **Logs:** Docker `json-file` driver with `max-size: 10m` and `max-file: 3`,
  addable in Compose.
- **Optional auto-deploy:** GitHub Actions builds the image to GHCR, then
  `appleboy/ssh-action` runs `docker compose pull && up -d`.
- **Leftover Windows tasks:** when moving to the VPS, remove the local
  scheduled tasks with `scripts/uninstall_autostart.ps1`.

## 7. Shopping list (the only thing still missing)

| # | Item | Provider | Cost |
|---|---|---|---|
| 1 | **Domain** (.ch) | Infomaniak | ~CHF 9–12/year (one mailbox included) |
| 2 | **VPS** | Hetzner CX23 (Falkenstein or Helsinki) plus IPv4 | ~€4.50/month ex VAT (CX33: ~€7/month) |
| 3 | Cloudflare Free plus Zero Trust Free | Cloudflare | CHF 0 |
| 4 | TLS (Caddy, Let's Encrypt) | — | CHF 0 |
| 5 | Uptime (Better Stack Free) | — | CHF 0 |
| 6 | Error tracking (Sentry Developer) | — | CHF 0 |
| 7 | Backups (object storage, optional) | Hetzner | €0–6.50/month |
| 8 | Legal consultation on BGS and the Kalshi terms (once, recommended) | Swiss firm | ~CHF 300–600 |

**Running cost: roughly CHF 6–8 per month** for the minimal setup, or
**CHF 15–25 per month** with an 8 GB VPS and object-storage backups.

## 8. Launch checklist, in order

1. Register the domain, point the nameservers at Cloudflare.
2. Order the VPS, install Docker, deploy the repository
   (`docker compose up -d --build`), set the domain in the Caddyfile.
3. Cloudflare: proxy on, SSL "Full (strict)", rate-limit rule, Bot Fight Mode.
4. Put Cloudflare Access (or Caddy basic auth) in front of the site for as long
   as Settings and the copy daemon are unprotected.
5. Add the imprint and privacy policy as their own page or section (draft from
   a generator, then have them read).
6. **Read the Kalshi developer agreement** and get the BGS question answered by
   a lawyer; depending on the outcome, adjust the "open market" links or
   clarify Kalshi re-display.
7. Enable the Better Stack monitor and, optionally, Sentry.
8. Load-test with 10 to 20 parallel tabs and watch memory on the VPS
   (`docker stats`).
9. Set up the backup cron and test a restore once.
10. Go live, then uninstall the local Windows scheduled tasks.
