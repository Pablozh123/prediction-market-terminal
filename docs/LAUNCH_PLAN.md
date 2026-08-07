# Launch plan: data rights, auth, jurisdiction and revenue

Last updated 2026-08-07. Four research threads (Kalshi and the aggregator
ecosystem, Polymarket, auth providers, Swiss law and company structure) with
primary sources linked in each section. This is research support, not legal
advice; where a lawyer is required it says so explicitly.

---

## Short answers to the open questions

| Question | Answer |
|---|---|
| **Do we have to drop Kalshi?** | **No.** Keep it, attribute it, and **apply to the Kalshi builders programme**, which turns tolerated use into use that is authorised in writing. Build so that Kalshi can be switched off with a flag. |
| **How is Oddpool allowed to do this?** | They have **no disclosed licence** — they operate in the tolerated zone, like the rest of the ecosystem. YC funds them publicly, Kalshi has never sent an aggregator a takedown, and Kalshi itself hands out $2M in grants to "analytics dashboards". |
| **Outsource auth?** | **Yes.** Immediately: Streamlit's native `st.login()` with Google OIDC (free, two to four hours) for admin gating. Later, for freemium: **Auth0's free tier** (25k MAU, EU tenant) behind the same `st.login()`, plus Stripe. Host none of it yourself. |
| **Polymarket limits — enough?** | **Comfortably.** The shared server cache uses single-digit percentages of the documented limits. The red line in the terms is institutional data distribution (the ICE exclusive), not retail dashboards. Action: **create a builder profile and email builder@polymarket.com**. |
| **Jurisdiction — go offshore because of the Swiss block?** | **A foreign company achieves nothing.** Criminal liability under the advertising ban attaches to the person acting, not to the corporate shell, and a US LLC or Estonian OÜ run from Switzerland becomes a Swiss company for tax purposes ("place of effective management"). The real lever is **Swiss geoblocking and no referral or sign-up links**. Revenue: sole proprietorship first, GmbH from roughly CHF 100k. |

---

## 1. Kalshi: findings and playbook

**The written position is strict.** The developer agreement (v1.1, from
Kalshi's own S3 bucket) limits API use to "facilitating a member's own trading"
(§3) and forbids caching or redistribution without "prior written
authorization" (§3.1); the data terms allow only "personal use for
non-commercial purposes". Termination is at will (§8) and liability is capped
at $50.

**Practice is the opposite:**

- **Oddpool, Inc.** (Delaware, YC Spring 2026) sells Kalshi and Polymarket data
  as a subscription (Pro $30, Premium $100 per month) with no disclosed licence
  at all, carrying only an "informational only" disclaimer.
- **Dome** (YC, $5.2M) sold a commercial Kalshi and Polymarket API and was
  **acquired by Polymarket** in February 2026 without Kalshi ever intervening.
- **Google** has shown Kalshi odds in Search and Finance since 11/2025, **CNN**
  has run a Kalshi live ticker since 12/2025, **Pyth** publishes Kalshi prices
  on-chain, and electionbettingodds.com has aggregated for years.
- **Kalshi actively courts builders**: [kalshi.com/builders](https://kalshi.com/builders)
  advertises "$2M in Grants & Developer Support", and the KalshiEco hub
  (12/2025) names "analytics dashboards" as a wanted category and lists a
  market-analytics dashboard as a collaborator.
- **No enforcement case** against a data re-publisher is findable. Kalshi's
  legal energy goes into regulatory disputes; its marketing pays influencers.

**Realistic worst case** for a small research site: API key or account
termination plus a takedown email. Not a lawsuit — public prices are facts and
weak under copyright (*Feist*), the contract is the only instrument, and its
damages are capped at $50.

**One forward risk:** Kalshi is building its own "Bloomberg terminal for
prediction markets" (CNBC, 2026-06-04), so it could formalise or monetise data
access later, following the CME playbook. Hence: build the off switch.

**Playbook, in order:**

1. **Apply to the Kalshi builders programme.** Acceptance is in effect the
   "written authorization" both documents name as the cure, and it comes with
   grant eligibility and marketing support. Ask in the developer Discord in
   parallel.
2. Attribution in the footer, already present: "Data: Kalshi, Polymarket — not
   affiliated with or endorsed by either exchange."
3. **Never put "Kalshi" in the product name or domain.** The trademark is the
   one thing Kalshi does defend actively.
4. Sell no raw or bulk data exports — the most explicitly forbidden act in both
   documents. Sell the interface and the analysis, not the data.
5. No member deanonymisation (§3.6, which fits: Kalshi publishes no identities
   anyway), respect the rate limits (we do), and make no AI-training claims on
   Kalshi data.
6. **Feature flag for Kalshi:** one settings switch that cleanly disables every
   Kalshi feed, in case a request ever arrives. Termination at will is the real
   operational risk.

## 2. Polymarket: findings and actions

**Terms (effective 2026-06-01):** the licence is "personal, limited,
revocable" — **with no** non-commercial clause. The data clause forbids use or
resale only to **"Capital Market Clients"** (brokers, hedge funds, market
makers, ETF issuers) and to **"market data distributors"** without a written
agreement. That protects the exclusive institutional feed at **ICE** ($2bn
investment in 10/2025, "Polymarket Signals and Sentiment" since 02/2026).
Retail dashboards are not what the clause targets.

**Ecosystem:** polymarketanalytics.com (Goldsky on-chain indexing plus the
Gamma API) was featured in **Polymarket's own newsletter**; QuickNode lists ten
or more whale trackers; several sites sell subscriptions; **no cease and desist
against an analytics site is known**. The terms explicitly reserve the right to
grant "access to public on-chain infrastructure and the Company's builder
program", which makes on-chain indexing the clean lane.

**Limits (verified):** 15,000 req/10 s globally; Gamma 4,000/10 s (markets 300,
events 500); Data API 1,000/10 s (trades 200); CLOB 9,000/10 s (book and price
1,500). Throttling shows up as Cloudflare queueing rather than errors. The
**WebSocket market channel is public and needs no auth**, which replaces
polling. With the shared server cache (TTL 30 to 900 seconds) origin load is
independent of visitor count: single-digit percentages of capacity even at
10,000 visitors a day.

**Actions:**

1. **Create a builder profile** (polymarket.com/settings → Builder) and email
   **builder@polymarket.com** with the API key, use case and expected volume,
   for the verified tier. It costs nothing, creates the written trail, and
   keeps the copy-trading feature viable (a builder code earns volume credit,
   weekly USDC rewards and grant eligibility).
2. Site terms of our own: display and analysis yes, no raw feed resale, and
   specifically not to financial institutions.
3. On growth: WSS instead of REST fan-out, historical backfills on-chain. Note
   that since 2026-04-28 the v2 datasets live at Goldsky and the old public
   subgraphs return wrong data.
4. No "Polymarket" in the product name or domain.

## 3. Auth: outsource, in this order

> ✅ **Done:** `st.login()` with Google OIDC in the terminal; Settings fails
> closed behind the `ADMIN_EMAILS` / `[admin].emails` allowlist; the fake
> sign-in shell is gone; without `.streamlit/secrets.toml [auth]` the whole
> thing is a no-op (local research mode). Template:
> `.streamlit/secrets.toml.example`, logic: `app/authz.py`. The Auth0 step
> below remains the later freemium build-out.

**Now (launch, admin protection, two to four hours):** Streamlit's native
**`st.login()` with Google OIDC directly** — free, no MAU limit, no vendor
lock-in. Gate the Settings page on `st.user.is_logged_in` plus an email
allowlist. Watch for: the cookie is fixed at 30 days; pin Streamlit past the
1.57 cookie regression; and `client_kwargs = { "prompt" = "login" }` if the
account chooser after logout is a problem.

**Later (freemium with accounts and Stripe, 12 to 24 hours total):**
**Auth0's free tier** — 25,000 MAU since late 2024, an EU tenant
(Frankfurt or Dublin), hosted login and signup pages, email verification, magic
links, social logins. Move off the Auth0 developer mailer before launch.
Integration is the same `st.login()` call with a different secrets.toml; the
gating code does not change. Payment: Stripe plus
[st-paywall](https://github.com/tylerjrichards/st-paywall), or roughly 100
lines of entitlement check (`st.user.email` → Stripe subscription → session
cache).

**Alternatives if they become relevant:** **WorkOS AuthKit** (1M MAU free, the
largest free tier; $99/month for a custom domain) if 25k MAU ever gets tight;
**Zitadel** (Swiss company, EU regions) if Swiss or EU data residency becomes
mandatory. **Not worth it:** Clerk (React-centric, the OIDC detour buys
nothing), Supabase Auth (no hosted login UI), Firebase (no OIDC server for
`st.login`), self-hosted Keycloak (operational load out of proportion for one
person). Cloudflare Access (50 users free, email OTP) stays the right answer
for a private beta or a separate admin instance — not for "public with a
protected settings tab", because a single Streamlit origin cannot be gated by
path.

## 4. Jurisdiction, company, revenue

**Territorial reach of the advertising ban (BGS Art. 74 para. 3):** the
protected interest is the Swiss market, and the commentary turns on advertising
that is **perceivable in, or directed at, Switzerland**. Foreign operators use
**Swiss geoblocking** to get off the GESPA list, which is the accepted,
system-conforming pattern. But whoever **acts from Swiss soil** acts in
Switzerland for criminal law, even with a foreign audience — so neither foreign
hosting nor a foreign company protects the person. GESPA practice in 2024/25:
12 to 25 criminal complaints, focused on operators and on **Swiss-directed
promotion** (influencer and affiliate cases). **No case** was found against an
English-language, Swiss-geoblocked information site. The distinction that
matters: neutral data presentation is information, not advertising — Swiss
outlets publish Polymarket odds routinely. The line sits at referral codes,
bonus content and "trade now" calls to action.

**Consequence for the jurisdiction question:** it is not the registered seat
but the **design of the site** that decides. Recommendation: launch
internationally, **geoblock Switzerland** (a Cloudflare rule, five minutes) or
at minimum hide outbound links to the venues from Swiss visitors, and monetise
nothing through referrals.

**Company structure (2026 costs):**

| Structure | One-off | Ongoing | Verdict |
|---|---|---|---|
| Private individual (phase 0) | CHF 0 | CHF 0 | Enough without revenue. Imprint and privacy policy still needed now. |
| **Sole proprietorship (phase 1)** | ~CHF 0 (register entry only mandatory from CHF 100k) | ~10% social contributions on net income (register above CHF 2,300/year) | **The standard for first revenue.** Does not worsen the gambling-law position, which attaches to the person regardless. |
| **GmbH (phase 2)** | CHF 20k capital plus CHF 800–3,500 formation | CHF 2,500–5,000/year (accounting) | From roughly CHF 100k revenue, or once B2B and advertising contracts appear. |
| US LLC / Estonian OÜ | $100–300 / €400+ | IRS form 5472 ($25k penalty if missed) / €59–179/month accounting | **A trap:** run from Switzerland it is a Swiss company for tax (duplicate obligations) and offers zero protection against the advertising ban. Only sensible after actually emigrating. |

**Revenue mechanics:**

- **Subscriptions:** below roughly CHF 100–200k revenue use a **merchant of
  record** (Paddle, Lemon Squeezy, ~5% plus $0.50), which takes on all EU and
  UK VAT as the seller. Higher margin alternative: Stripe (2.9% plus 0.30) with
  a **non-Union OSS** registration in an EU country — mandatory from the first
  euro of B2C digital revenue into the EU, with no threshold for non-EU
  sellers.
- **Swiss VAT:** registration from CHF 100k **worldwide** revenue, within 30
  days. Subscriptions to foreign customers carry 0% Swiss VAT.
- **Ads (AdSense):** the counterparty is Google Ireland, 0% Swiss VAT, but it
  counts toward the 100k threshold; file a W-8BEN. Note that AdSense may class
  a prediction-market site as gambling-adjacent and limit ads — subscriptions
  are the more robust model.

**The one legal consultation worth paying for** (phase 1, before monetising):
two to four hours with a gaming or ICT firm (CHF 250–450/hour, a short written
opinion CHF 1,000–3,000) on exactly two questions: (a) the link policy and
Swiss posture under BGS Art. 74 para. 3, and (b) sign-off on the geoblocking
setup. Nothing beyond that is needed.

## 5. Roadmap, in order

**Now (CHF 0):**

1. Kalshi builders application and Polymarket builder profile plus email —
   start both written trails.
2. Kalshi feature flag in Settings, for a clean shutdown.
3. `st.login()` with Google OIDC for admin gating; remove the fake auth shell.
4. Decide and implement Swiss geoblocking (Cloudflare country rule), and make
   the no-referral, no-CTA rule a fixed site policy.
5. Imprint and privacy policy (revDSG) as a page.

**Launch (~CHF 6–8/month, see PRODUCTION_READINESS.md):**

6. Domain, VPS, Cloudflare, deploy — the artifacts are ready.
7. Site terms of our own (display and analysis yes, no data feed resale).

**First revenue (< CHF 100k):**

8. Sole proprietorship and social-insurance registration (from CHF 2,300 net
   income), Paddle or Lemon Squeezy as merchant of record, Auth0 in front of
   `st.login()`, Stripe entitlements.
9. Short legal opinion (CHF 1,000–3,000) on the link policy and geoblocking.

**Scale (> CHF 100k):**

10. Convert to a GmbH; register for VAT (mind the 30-day deadline); consider
    Stripe plus OSS instead of a merchant of record; move to WSS and on-chain
    indexing instead of REST fan-out; re-assess the Kalshi position and watch
    their own terminal.
