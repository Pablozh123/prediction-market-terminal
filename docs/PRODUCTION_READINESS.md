# Production readiness — running the terminal publicly

Last updated 2026-09-04. Researched against the official documentation of
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

### Control room (primary public site)

Since 2026-08 the compose stack fronts the **control room** — `api/server.py`
(FastAPI, read-only JSON API) serving the `web/` frontend and the published
research payloads from `public/data/` — and keeps Streamlit as a secondary
service. Same image, two commands:

| Hostname | Service | Port (internal) | Health |
|---|---|---|---|
| `https://$DOMAIN` | `controlroom` — `python -m uvicorn api.server:app --host 0.0.0.0 --port 8787` | 8787 | `GET /healthz` |
| `https://app.$DOMAIN` | `terminal` — Streamlit | 8501 | `GET /healthz` or `/_stcore/health` |

What the bridge does for a public URL: CORS restricted to `CORS_ORIGINS`
(default: the two local addresses; the frontend is same-origin and needs
none), a per-IP token bucket on the two expensive routes `POST /api/backtest`
and `GET /api/risk` (`RATE_LIMIT_PER_MIN`, default 6/min with a burst of 3)
plus a wide one for everything under `/api/` (`RATE_LIMIT_GLOBAL_PER_MIN`,
default 120/min), 429 with `{"error":"rate_limited","retry_after_s":N}`, and a
capped in-process cache (`CACHE_MAX_ENTRIES`, default 512). Behind Cloudflare
set `RATE_LIMIT_IP_HEADER=CF-Connecting-IP`, otherwise every visitor shares
Cloudflare's edge address. Country blocking stays a Cloudflare WAF rule; the
Caddyfile says why. `DOMAIN` in `.env` fills `{$DOMAIN}` in the Caddyfile;
both hostnames need DNS records.

Research pages only, no server at all: `python scripts/build_static_site.py`
writes `dist/` (web/ plus `data/*.json`) for any static host; the live pages
show their empty state there.

**Deployment in six steps** on a fresh VPS:

```bash
# 1. Install Docker (Ubuntu 24.04): curl -fsSL https://get.docker.com | sh
# 2. Clone the repo, fill .env from .env.example — at least DOMAIN
# 3. DNS: A/AAAA records for $DOMAIN and app.$DOMAIN pointing at the server
# 4. docker compose up -d --build
# 5. Cloudflare: DNS "Proxied", SSL mode "Full (strict)"
# 6. Point a monitor at https://$DOMAIN/healthz (Streamlit: https://app.$DOMAIN/_stcore/health)
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

### 8a. The live deployment (Cloudflare Pages + Railway)

marketintel.dev is served by Cloudflare Pages: `scripts/build_static_site.py`
copies `web/` to `dist/`, so `web/_headers` (CSP, HSTS, frame and permissions
headers), `robots.txt`, `sitemap.xml` and `404.html` ship with every build.
api.marketintel.dev is the Railway service (`api/server.py`) behind the
Cloudflare proxy; it sets its own headers on `/api/*` and prefers
`CF-Connecting-IP` for the per-IP limiter. Checked with `curl -sI` on
2026-09-04: both hosts answer through Cloudflare (`Server: cloudflare`,
anycast A records), `http://` is redirected with 301, `GET /healthz` on the
API answers 200 (`HEAD` answered 404 until the route accepted it; deploy
step 7 ships that). What is left is clicked in the two dashboards. Steps 1–5
and 9 are written as a paste sheet — the menu path, then the exact value for
each field — and `scripts/cloudflare_zone_setup.py` (after step 11) sets the
same values through the API; the rule names in the sheet are the names the
script looks for, so the two ways can be mixed without duplicates.

1. [ ] **SSL/TLS → Overview**, encryption mode (the Configure button), for
   the whole zone including `api.marketintel.dev`:
   ```
   Full (strict)
   ```
   "Full" alone would accept any certificate at the origin, "Flexible" would
   let Cloudflare reach it over plain HTTP. Not verifiable from outside.
2. [x] Always Use HTTPS is on (the 301 from `http://` shows it; the switch
   sits on the same page as the next field and stays on).
   [ ] **SSL/TLS → Edge Certificates → Minimum TLS Version**
   ```
   TLS 1.2
   ```
   Leave the HSTS switch off: `web/_headers` already sends
   `Strict-Transport-Security` (one year, includeSubDomains, no preload), and
   two sources with different values only confuse. Preload is a one-way
   decision — removal from the browser lists takes months — and stays off
   until it is wanted on purpose.
   [ ] **Caching → Configuration → Browser Cache TTL**
   ```
   Respect Existing Headers
   ```
   Until this is set, the zone default of four hours wins over `web/_headers`:
   on 2026-09-04 `/js/app.js` was served with `max-age=14400` although the
   file asks for `max-age=0`, so a deploy could stay invisible for hours.
3. [ ] **Optional — a business decision, off by default: the Swiss geoblock**
   from §4. It makes the site unreachable from Switzerland, operator
   included (check through a VPN, or add a skip rule for one IP first).
   Decide consciously; **Save as Draft** keeps the rule visible but inactive.
   **Security → Security rules → Create rule → Custom rules**
   ```
   Rule name:    Block Switzerland (cloudflare_zone_setup.py)
   Expression:   (ip.src.country eq "CH")
   Action:       Block
   ```
   The script creates this rule only when called with `--geoblock-ch`.
4. [ ] **Security → Settings → filter "Bot traffic" → Bot Fight Mode**
   ```
   On
   ```
   It covers the whole zone, `api.marketintel.dev` included, and can
   challenge clients that are not browsers (an uptime monitor, `curl`); after
   switching it on, confirm the monitor from step 10 still sees a 200.
5. [ ] **Security → Security rules → Create rule → Rate limiting rules** (the
   Free plan includes one rule):
   ```
   Rule name:                      API rate limit (cloudflare_zone_setup.py)
   If incoming requests match:     Field "URI Path" · Operator "starts with" · Value /api/
   With the same characteristics:  IP
   When rate exceeds:              60 requests · 10 seconds
   Then take action:               Block
   Duration:                       10 seconds
   ```
   Behind the builder that is `(starts_with(http.request.uri.path, "/api/"))`.
   A hostname clause is not available on the Free plan (its rate limiting
   expressions know only "Path" and "Verified Bot"); `/api/` exists only on
   `api.marketintel.dev`, so the rule already means "the API". The in-process
   token buckets in `api/server.py` stay as the second line behind it.
6. [ ] **Railway → service → Variables:** `RATE_LIMIT_IP_HEADER=CF-Connecting-IP`
   (the server prefers that header on its own when present; the variable
   makes the intent explicit) and `ROUTE_WARM_MIN=4`, which keeps `/api/cross`
   and `/api/risk` warm in the background instead of making the first visitor
   wait 20–25 s. **Settings → Networking:** remove the generated
   `*.up.railway.app` domain, otherwise requests to it bypass Cloudflare, the
   WAF rules and the limiter's trust in `CF-Connecting-IP`.
7. [x] **Railway deploy:** the service builds from `main` on its own (its
   source is the GitHub repository) once the commit's checks are green, and
   `.github/workflows/smoke-api.yml` verifies the live API every half hour
   with `scripts/smoke_live_api.py`, red when `main` stays ahead of the API
   for more than 20 minutes (a skipped deploy is not retried by Railway;
   `railway up --detach` redoes it). Ad hoc:
   `python scripts/smoke_live_api.py https://api.marketintel.dev` (ten lines
   `ok` on 2026-09-04 after the register shipped).
8. [x] **Pages → project → Settings → Builds:** production branch `main`, build
   command `python scripts/build_static_site.py --api-base
   https://api.marketintel.dev`, output directory `dist`. Deploys follow
   pushes to `main` today; confirm the three fields once when opening the page.
9. [ ] **www.marketintel.dev** answers 200 as a second Pages domain today. The
   canonical form is a 301 to the apex. **Rules → Overview → Create rule →
   Redirect Rule**, "When incoming requests match" set to *Custom filter
   expression*:
   ```
   Rule name:               www to apex 301 (cloudflare_zone_setup.py)
   Expression:              (http.host eq "www.marketintel.dev")
   URL redirect → Type:     Dynamic
   Expression:              concat("https://marketintel.dev", http.request.uri.path)
   Status code:             301
   Preserve query string:   on
   ```
   Verify with `curl -sI https://www.marketintel.dev/` (expect 301 and
   `Location: https://marketintel.dev/`).
   The project alias `prediction-market-terminal.pages.dev` also answers 200.
   It is not part of this zone, so no redirect rule reaches it; `web/_headers`
   sends `X-Robots-Tag: noindex` for that host, which keeps it out of search
   results, and a Cloudflare Access policy on the Pages project (**Workers &
   Pages → project → Settings → Enable access policy**, extended to the
   `pages.dev` hostname as described in the Pages "known issues" page) is the
   way to gate it fully. A `_redirects` file cannot do either: Pages matches
   paths only, never hostnames (tried on 2026-09-04, both hosts kept answering
   200).
10. [x] **Uptime:** `.github/workflows/uptime.yml` asks both hosts every
    15 minutes and opens an issue labelled `outage` when one stops answering,
    closed again on recovery; watching the repository (the owner does by
    default) turns that into an e-mail. An external monitor (Better Stack,
    UptimeRobot) stays optional for detection under a minute.
11. [ ] After the next Pages deploy, verify the file-level part:
    `curl -sI https://marketintel.dev/` shows `Content-Security-Policy`,
    `Strict-Transport-Security` and `X-Frame-Options: DENY`;
    `curl -sI https://marketintel.dev/robots.txt` is `text/plain`;
    `curl -sI https://marketintel.dev/no-such-page` is 404.

**Steps 1–5 and 9 in one go.** `scripts/cloudflare_zone_setup.py` (standard
library only) sets the same values through the Cloudflare API. It reads
before it writes, skips what is already set and recognises its rules by
name, so it can be run again at any time:

```
$env:CLOUDFLARE_API_TOKEN = "..."                     # PowerShell; bash: export CLOUDFLARE_API_TOKEN=...
python scripts/cloudflare_zone_setup.py --dry-run     # prints every request it would send, sends none
python scripts/cloudflare_zone_setup.py               # steps 1, 2, 4, 5 and 9
python scripts/cloudflare_zone_setup.py --geoblock-ch # additionally step 3
python scripts/cloudflare_zone_setup.py --verify      # reads only, prints every current value
```

Each step prints one line, `ok`, `skip` or `FAIL`; a failed step does not
stop the others, and the exit code is 1 if anything failed. The token comes
from the environment only, never from an argument. Creating it: **My Profile
→ API Tokens → Create Token → Custom token**, permissions (all in the Zone
group) `Zone: Read`, `Zone Settings: Edit`, `Zone WAF: Edit`,
`Bot Management: Edit`, `Single Redirect: Edit`; **Zone Resources: Include →
Specific zone → marketintel.dev**. The token is shown once and can be
deleted after the run.

Open beyond the dashboards, in rough order of value:

- **Backup of the Railway volume** — `.github/workflows/backup-volume.yml`
  pulls `GET /api/admin/backup` (a zip of the copy-desk SQLite, settings,
  entity graph and flag log, built with the SQLite backup API) once a day and
  keeps it as a workflow artifact for 90 days. Set the repository secrets
  `COPY_ADMIN_TOKEN` (the desk's write token) and `BACKUP_PASSPHRASE` (the
  artifact is encrypted with it; artifacts of a public repository are
  downloadable by anyone signed in). Nothing runs until the first secret is
  set.
- **API deploys follow `main`** already (Railway builds from the GitHub
  source after the checks pass); `.github/workflows/smoke-api.yml` compares
  the live commit with `main` every half hour and smokes the API. No token
  is involved.
- **Cold routes**: `ROUTE_WARM_MIN=4` (step 6) keeps `/api/risk` (~25 s)
  and `/api/cross` (~21 s) warm between visitors; a persisted precompute
  would make the first request after a restart fast as well.
- **Self-hosted IBM Plex** — removes the only third-party request the browser
  makes (Google Fonts) and the paragraph the privacy policy spends on it.
- **Cache rule check** — once the Browser Cache TTL from step 2 is set and
  the next deploy is through, `curl -sI https://marketintel.dev/js/app.js`
  must show `max-age=0, must-revalidate` (on 2026-09-04 it still showed
  `max-age=14400`: the zone-level TTL overrides `web/_headers`).

### 8b. The self-hosted alternative (VPS + Caddy)

The original plan, kept for the compose + Caddy path. If the site ever moves
off Pages and Railway, steps 3 to 10 apply unchanged.

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
