# Differentiation strategy — prediction-market intelligence

Last updated 2026-08-07. Based on eleven parallel research threads (competitor
deep dives, user segments, pain points, trust and custody, unmet needs,
willingness to pay, the Kalshi ecosystem) with primary sources. The goal is
**not another whale feed** but a defensible position in a crowded market.

---

## 0. The thesis in one sentence

The market is full of Polymarket-only clones combining a whale feed, an insider
score and a copy bot, all built on **misleading vanity leaderboards** and
**insider-copy hype** — both demonstrably wrong mathematically and
loss-making for users. The way to win is **honesty, mathematical correctness
and cross-venue breadth**: a neutral prediction-market intelligence terminal
with verifiable, settled-only, survivorship-corrected track records, positioned
as research rather than as a gambling funnel.

---

## 1. Market reality (evidenced)

- **Barbell:** about 2% of users account for roughly 90% of volume; the **top
  0.04–0.1% take about 67–70% of the profits**; and **84% of traders lose
  money** (WSJ across 1.7M addresses; an on-chain study of 2.5M wallets, April
  2026). The winners are bots, arbitrage and market makers — **not humans worth
  copying**. Bots trade 89 times a day against 2.2 for humans, and 14 of the
  top 20 wallets are bots.
- **Paying segments:** degens (copy, churny), sharps (high willingness to pay,
  often build their own), **quants and builders** (recurring, a $99/month data
  API is proven). Researchers, journalists and forecasters have low willingness
  to pay but form a **credibility funnel**. Casual users are a huge,
  price-sensitive base.
- **Demand is spiky:** Kalshi peaked around 400k daily users on election night
  and sat near 27k by mid-2025. Novelty churn is real, so retention needs
  workflow lock-in.
- **60% of prediction-market users are new to crypto**, so onboarding and
  clarity matter.

## 2. Competitors

| Tool | Positioning | Venues | Strength | Gap |
|---|---|---|---|---|
| **Unusual Whales** (Unusual Predictions, 01/2026) | Insider detection, 3M+ followers | **Polymarket only** | Distribution, brand, its own score | Monitoring only — no copy, alerts, API or backtest for prediction markets; **no Kalshi**; the category is a bolt-on |
| **Verso** (YC-backed) | "Bloomberg terminal for prediction markets" | Both | **Best-funded independent**, AI news engine (30k articles to contracts), mobile, 15k+ contracts | New, no copy or backtest known — **the direct competitor** |
| **Kreo** | "find insiders before the rest" | Both | Roughly non-custodial, AI matcher, real copy | **Opaque fee, no backtest, no API, Telegram only**, and under Polymarket audit |
| **Oddpool** (YC S26) | "institutional data layer" | Both | Cross-venue, API, whale feed | Free tier is one event, no licence, young |
| **PredictFolio / OrcaLayer** | Data-accuracy reference | Polymarket | **Correct mathematics** (NegRisk correction, farmer filter), cited by journalists | Niche, single venue |
| **polywhaler** | Whale and insider, $9/$99 | Polymarket | Insider scoring | Copy outsourced to a referral partner, anonymous, domain five months old |
| **Stand.trade** | Pro terminal, copy | Polymarket (plus Kalshi) | $0, profiled in Polymarket's newsletter | Monetisation unclear |
| **Copy bots (several)** | Copy execution | Polymarket | Execution | **Custody risk** (one lost ~$230k to a hack), referral spam |
| **adj.news / Dome** | Multi-venue **API** | All | Broadest data | **API, no interface**; Dome was **acquired by Polymarket** |

## 3. Table stakes versus white space

**Table stakes (everyone has them):** whale feed, insider or smart score,
leaderboard, copy trade, a "backtest" label, Telegram alerts.

**White space, ranked by demand times how badly it is solved:**

1. **Verifiable, correct track records instead of vanity leaderboards** — the
   biggest wedge. The defects every leaderboard demonstrably has:
   - **NegRisk double counting:** multi-outcome markets are counted per
     outcome, which **inflates win rates by up to 2×**.
   - **Wrong or sign-flipped PnL:** winning positions are auto-redeemed and
     vanish from the API, so naive tools show a loss where there was a profit
     — one documented case showed −$3.5M against a real +$11.4M.
   - **Survivorship and zombie orders:** naive win rates land at 70–80% while
     **settled-only rates are 55–62%**. Roughly 16% of the leaderboard top are
     airdrop farmers, and **about 25% of volume is wash trading** (Columbia;
     45% in sports).
   - Nobody except the two accuracy-focused sites computes this correctly.
     → **The moat: settled-only, NegRisk-corrected, farmer-filtered,
     exit-liquidity-adjusted, calibration-scored, behaviour-labelled
     (directional, hedge, market-making, arbitrage), multi-wallet-linked
     (the Louvain clustering already exists), with a published methodology.**

2. **A real cross-venue interface** (both venues now, more later): consolidated
   odds, arbitrage, and **PnL reconciled across venues**. One competitor is API
   only, another was bought, and the rest are single-venue. Everyone currently
   diffs this by hand. **Cross-venue neutrality is the one moat the venues
   themselves will never build**, because neither will show a competitor's
   odds.

3. **Honesty about copy decay.** The core defect: a whale's own entry moves a
   thin book, so the copier buys the top (the whale realises ~127% of the move
   against the copier's ~100%). Add MEV front-running at millisecond scale and
   the cat-and-mouse of second accounts, iceberging and merge exits, and the
   copier becomes exit liquidity. **Nobody discloses this.** We would: "the
   median copier filled X cents worse", and only where copying is viable at
   all.

4. **Prediction-market-native tax and cross-venue reconciliation.** No provider
   solves it. The venues issue no tax forms, every trade is a crypto event, and
   cross-venue means two tax frameworks. **High willingness to pay, wide
   open.**

5. **A personal calibration dashboard for real-money traders.** The play-money
   forecasting sites have Brier scores and calibration curves; the real-money
   venues have **neither**. "Am I actually calibrated, do I have an edge?" is a
   clean, unoccupied gap and a perfect free-tier credibility funnel.

6. **Resolution and dispute risk alerts.** Real losses happen here — a $7M
   market resolved wrongly, with a quarter of the oracle voting power in few
   hands. No mainstream tool warns that "your open position is under dispute".
   Defensible through a resolution-precedent dataset.

7. **Category-aware, explainable insider screening.** The incumbents score
   sports odds as "insider", which is noise. We exclude sports and weather,
   keep politics and geopolitics, and say why a row was flagged. **Nobody else
   does this.**

## 4. What we already have

- **Both venues in one interface**, not just an API.
- **Category-aware insider screening** — sports and weather excluded, which
  nobody else does.
- **A rigorous backtester** (copy and fade, four sizing modes, exposure cap,
  mid-window resolutions, and honest flat curves) that now charges the real
  venue fee curve rather than a flattering flat rate.
- **A Louvain co-trading network** for multi-wallet clusters, which is exactly
  the tool against the cat-and-mouse problem.
- **Non-custodial by architecture** (paper only) — custody is *the* trust
  bottleneck in this category.
- **Sub-second WebSocket fast copy.**

## 5. Four pillars

**Pillar 1 — correct, verifiable track records ("the mathematics is right").**
This is the category's number one trust lever; the sports-betting analogues
that won did it with pre-committed, undeletable records. Settled-only,
NegRisk-corrected, survivorship-adjusted, calibrated, verifiable on-chain, with
the methodology published. **Prove before you copy:** the backtester scores a
wallet honestly, with real fees, slippage and decay, *before* anyone follows
it. That is the moat against monitoring-only incumbents and against blind
mirroring bots.

**Pillar 2 — a cross-venue truth layer.** The neutral unified terminal: odds,
arbitrage, reconciled PnL and tax. Defensible precisely because the venues have
a conflict of interest and will not build it.

**Pillar 3 — research and intelligence instead of a copy funnel.** The insider
screen is an explainable **warning**, category-aware, not "tail the insider".
That avoids the audit and gambling-law trap the copy-focused tools walked into,
and it wins sharps, researchers and journalists — the free calibration layer
turns into citations, which is free marketing.

**Pillar 4 — honest, non-custodial positioning.** "We never touch your funds"
plus "you would have lost money copying this" — exactly the analytics the
conflicted incumbents cannot publish.

## 6. Threats and consolidation

- **Consolidation is underway:** Polymarket bought Dome (the unified API) and
  runs its own copy surface. Kalshi is building its own Bloomberg-style
  terminal. Raw data normalisation and native copy will be commoditised and
  first-party. **Do not fight there.**
- **Verso:** the best-funded independent multi-venue terminal. Beat them on
  trust rigour, backtesting, category intelligence and honest copy decay, none
  of which they have.
- **Unusual Whales:** the distribution is unreachable, so do not fight on
  Polymarket insider terrain; win on cross-venue breadth, rigour and
  actionability.
- **Kalshi anonymity:** insider work, copy and verified leaderboards are
  **structurally impossible** on Kalshi because there are no wallets. Be honest
  about it — the Kalshi layer is event-level, and wallet-level rigour is
  Polymarket-native.
- **The funding wave is time pressure:** the venues are raising at enormous
  valuations, ICE put in $2bn, and the first dedicated venture fund (~$35M)
  will finance roughly twenty more tooling startups. The space fills up fast.
  **Take the position now.**

**Least contested axes (nearly empty, real niches):**

- **Non-English markets** — every tool found is English-only. Unoccupied.
- **Mobile** — almost nobody.
- **Counter-trading** — automatically fading demonstrably bad wallets; one
  competitor does it. **The fade strategy already exists in our backtester**
  and is directly extendable.
- **A prosumer tier (~$20–40)** — serious retail wants institutional analytics
  at a fair price and is thinly served.

## 7. Build plan, prioritised

1. **Track-record engine v2** — the biggest wedge, and it uses the Louvain
   clustering and the backtester we already have: settled-only PnL that handles
   auto-redeem, **NegRisk correction**, farmer and wash filters, an
   exit-liquidity haircut, calibration, behaviour labels, multi-wallet
   clusters, and a published methodology. It replaces the vanity leaderboard.
2. **Cross-venue reconciled PnL and tax export** — high willingness to pay,
   unoccupied.
3. **Copy-decay honesty** from the detection-versus-fill data: "the median
   copier filled X cents worse", per market and size band.
4. **A personal calibration dashboard** ("was 70% actually 70%?") — the
   resolved page plus a Brier and calibration curve. Free tier, credibility
   funnel.
5. **Resolution and dispute risk alerts** — "your position is under dispute",
   plus an ambiguity score per market.
6. **Alerts with context** (a hedge versus new risk), against spammy alerts.

## 8. Monetisation

**Price reality:** tools in this category are **anchored low ($10–20/month)**
because the data is public and free competition exists. The ladder for
comparison: charting tools at $15/**$30 (the sweet spot)**/$60; a betting
tracker at $40; on-chain analytics at $129; the heavy platforms at $399 for
professionals only. Usage-based pricing is emerging.

- **Free (reach and trust):** the calibration layer, basic feeds, citable odds
  → researchers, journalists and casual users as the funnel.
- **Pro (~$19–29/month, sharps and degens):** cross-venue flow, the
  track-record engine, copy decay, reconciled PnL and tax, alerts with context,
  the backtester.
- **Data/API (~$99/month, builders and quants):** historical order-book data
  plus an API — proven recurring willingness to pay.
- **Optional usage credits** for occasional users, instead of a $100+
  subscription.
- **Frictionless self-serve cancellation and transparent billing** — the
  incumbents lose customers on exactly this.
- **Not:** vanity leaderboards, insider-copy hype, custody, referral links
  (gambling law plus trust), or a flat fee for signals (incentive
  misalignment).

## 9. Anti-goals (deliberately not doing)

No blind copy without a decay warning. No tail-the-insider funnel (audit and
gambling law). No custody. No single-venue thinking. No wash- or
NegRisk-distorted leaderboard. No hype marketing ("up 900%"), which burns
exactly the paying sharps and researchers. No undisclosed referral deals, which
kill trust.

## 10. One-line pitch

> **"Bloomberg for prediction markets — cross-venue, honest, non-custodial.
> Verified settled-only track records instead of inflated leaderboards. Prove
> before you copy."**

## 11. Immediate, free opportunities

- **The Kalshi builders grant** ($2M+ pool, up to $10k per grant, naming
  "analytics dashboards" explicitly) — applying gets funding, distribution and
  written authorisation at once.
- **A Polymarket builder profile** for the written trail and the verified tier.
- **Use the accuracy-focused sites as a benchmark** (aim for 0.7% deviation);
  journalist citations follow, which is free marketing.

Related: [LAUNCH_PLAN.md](LAUNCH_PLAN.md) (law, auth, company),
[LIVE_COPYTRADING_PLAN.md](LIVE_COPYTRADING_PLAN.md) (speed, wallet connect,
copy law), [HANDOFF.md](HANDOFF.md) (state and roadmap).
