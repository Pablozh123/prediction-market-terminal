# Plan: wallet connect, live copy-trading, crypto payment, speed

Last updated 2026-08-07. Four research threads with primary sources. Research
support, **not legal advice** — the points marked **[LAWYER REQUIRED]** are not
negotiable before a single live trade runs.

---

## The important finding first

There are **two entirely different risk tiers**, and they must not be
conflated:

| Tier | What | Legal risk | Effort |
|---|---|---|---|
| **A. Read-only wallet connect** | Connect an address, show positions and PnL | ~none (reading public chain data) | 2–4 days |
| **B. Fast-copy speed upgrade** (paper stays paper) | WebSocket instead of on-chain polling | none (internal plumbing) | hours to a day |
| **C. Live-money copy-trading** | Execute real orders with the user's wallet | **HIGH — gambling-law escalation** | weeks plus a lawyer |
| **D. Crypto payment** | USDC subscription alongside cards | low (the gateway is the intermediary) | 2–6 days |

**A, B and D are buildable at any time. C is a strategic decision carrying real
criminal exposure for a Swiss resident** — see section 3.

---

## 1. Speed: on-chain polling was the slowest usable method

> ✅ **Step 1 is implemented.** The copy daemon now detects on the RTDS
> WebSocket and keeps on-chain polling as reconciliation. See HANDOFF.md §6 for
> what that took, including the worker thread that had to be split out after
> the first version measured a 105-second median.

**The finding:** the original worker polled a free Polygon RPC with
`eth_getLogs` for `OrderFilled` events. But the on-chain log is the **last**
event in the trade lifecycle: Polymarket matches off-chain **immediately** and
settles on-chain about two seconds later, one Bor block. So the design paid
roughly two seconds plus the one-second poll interval. It is hard to be slower.

**Trade lifecycle, earliest to latest visibility:**

1. User signs an order, the CLOB operator matches in memory (milliseconds).
2. **The CLOB WebSocket broadcasts the trade** ← the earliest public signal.
3. The settlement transaction is built and handed to a relayer.
4. **On-chain `OrderFilled` is mined (~2 s later)** ← where the old design
   listened.

**The 80/20 win:** move detection to the **CLOB WebSocket**.

- The **RTDS `activity/trades` feed** (`wss://ws-live-data.polymarket.com`)
  carries `proxyWallet`, `side`, `size`, `price`, `asset`, `conditionId` and
  `transactionHash` — **including the wallet** — at match time. Gotcha: the
  per-wallet filter upstream is broken, so subscribe to the global firehose
  with an empty filter and match `proxyWallet` client-side against the target
  list. Send `PING` every five seconds.
- That removes about two seconds of latency outright; on-chain polling stays as
  **reconciliation and fallback**, catching what the socket misses and
  confirming settlement.

**Ranked upgrade path:**

| # | Step | Latency gain | Effort | Cost |
|---|---|---|---|---|
| 1 | **WS detection instead of on-chain polling** ✅ done | **~2 s → sub-second** | hours | $0 |
| 2 | Harden execution: keep-alive HTTPS to the CLOB, cached L2 credentials, preloaded tick sizes and token IDs, **FOK** market orders via py-clob-client | ~100–200 ms of critical path | ~1 day | $0 |
| 3 | **Co-locate the worker in Dublin or London** (the CLOB runs in AWS eu-west-2) | ~70–130 ms → ~1–10 ms RTT | ~half a day | ~$5–40/month VPS |
| 4 | Paid WSS RPC with `eth_subscribe` as the on-chain fallback | replaces an unreliable free RPC | ~half a day | $0–50/month |
| 5 | ~~Mempool or builder partner tier~~ | — | **skip**: settlement is relayer-batched so the mempool buys nothing, and the partner tier only matters at scale | — |

**Net:** steps 1 to 3 move the system from "two to three seconds behind plus US
round trip" to "**sub-second, often 100 to 300 ms end to end, on the earliest
signal, next to the matching engine**", for a small Dublin VPS and a day or two
of work. Step 1 dominates, and it also improves the paper copy (more realistic
fills) and the live and suspicious feeds.

## 2. Read-only wallet connect: low risk, high value

**The pattern:** "connect wallet" means read the address only, then show
positions and PnL. No signature, no custody, no financial-services or gambling
footprint. It is exactly what the engine already does, since it reads
`OrderFilled` by address.

**The Streamlit problem, which is not trivial:** Streamlit is server-side, and
real wallet JavaScript only runs in a **custom React component (iframe)** using
wagmi or WalletConnect, which hands the address and optionally a signature back
through `Streamlit.setComponentValue`. The off-the-shelf components are stuck
in 2022, MetaMask-only and without message signing — **not usable**, only worth
reading as reference.

- **Phase 1a (address only):** the user types or connects an address and the
  engine reads public data. Minimal, no risk.
- **Phase 1b (authenticated):** **SIWE / EIP-4361**, finalised in 2025 — a
  plaintext signature proves wallet ownership and gates premium analytics. No
  transaction, no funds. The backend verifies with `eth_account` or `siwe`.
- **Effort:** two to four days, most of it the first React component build and
  the iframe rerun handling.

## 3. Live copy-trading: technically feasible, legally the red line

### 3a. How the incumbents build it (non-custodial)

One competitor's terms, verbatim: *"PolyHuntr does not hold, custody, or
control your funds. All trades execute directly on Polymarket or Kalshi using
your own wallet."* On privacy: *"exchange API secrets stay in your browser
session only."* Fee: **10% of realised profit, billed off-chain through
Stripe** — no on-chain skim, consistent with being non-custodial. **Operator
and jurisdiction are not disclosed** (their /about is a 404), which is a
warning sign rather than a model for our own legal hygiene.

### 3b. Polymarket supports this technically

The order struct separates `maker` (the source of funds) from `signer` (who
signs): *"Optional; if not present the signer is the maker."* That is the
non-custodial delegation hook. A clean architecture:

1. Register as a **Polymarket builder** — the builder code is serialised into
   the signed order and the builder never holds funds.
2. The user connects a proxy wallet (Gnosis Safe or deposit wallet) and signs
   a **one-time** capped USDC allowance to the four exchange contracts; the
   relayer pays gas.
3. The engine mirrors leader trades by building orders that **the user's wallet
   signs** — either (A) a backend **session key** as `signer` with on-chain
   spend caps (best UX for unattended copying, but the backend holds a
   *limited* key) or (B) **the browser signs every order** (maximally
   non-custodial, but the browser has to be open and consenting, so no "set and
   forget").
4. The fee is billed off-chain through Stripe.

**Stack delta:** a small **JavaScript microservice** (Next.js, Polymarket's
`wagmi-safe-builder-example` as the base) for onboarding — wallet connect, Safe
deployment, the approval batch, L2 credential derivation — plus
`py-clob-client` in the engine. **Effort for option A: two to four weeks.**
Session-key registration is under-documented, so prototype against testnet or
tiny amounts first.

### 3c. The legal picture — this is where it gets serious

**Financial law (workable with the right design):** non-custodial, no
discretionary management and no personalised advice probably keeps this out of
the heavy licences. But "copy-trading" is its own regulated category under the
functional test:

- **Auto-execute with no user action → portfolio management**, which is
  licensed. Avoid.
- **User confirms each trade → investment advice or order transmission**, with
  conduct obligations and adviser registration. Lighter.
- **Execution-only (the user triggers, you only transmit) → the lightest
  tier.** ← the design to aim for.
- Custody is the bright line everywhere: **never hold funds or keys**, and the
  banking and anti-money-laundering obligations do not attach.

**⚠️ Gambling law (BGS) — the escalation, and why this is not a data site:**

- Polymarket is on the GESPA blocklist as unlicensed online gambling.
- **BGS Art. 130:** intentionally organising unlicensed large-scale games **or
  "providing the technical means for them, knowing the intended use"** to
  parties without a licence carries **imprisonment up to three years, five if
  done commercially**.
- **BGS Art. 131:** advertising unlicensed games, fines up to CHF 500,000.
- A **data and leaderboard site** displays public information. A tool that
  **routes or eases live trading for Swiss users on a blocked gambling market**
  sits much closer to "providing the technical means" — that is the qualitative
  jump from information to facilitation.
- **Counterweight:** Swiss authorities show little appetite for criminal
  proceedings against foreign sites, and extraterritorial application is
  uncertain; enforcement so far has been administrative (blocklist, DNS) rather
  than criminal. **But** that "acting from abroad" uncertainty is precisely the
  protection a **Swiss resident does not have**. Providing the technical means
  from inside Switzerland is territorially clear.

**Consequence:** live copy is **[LAWYER REQUIRED]**, not optional. The precise
question — may a Swiss resident facilitate live trades for *non*-Swiss users on
a GESPA-blocked market — can only be answered by a Swiss fintech and gaming
firm. Budget: **CHF 5,000–15,000** for a classification memo, **CHF
15,000–25,000+** for a full cross-border opinion. Against the custodial
exposure in Art. 130 that is the cheapest insurance available.

### 3d. The competition: fee models, custody, security incidents

**Fee models, for orientation:**

- 10% of realised profit, off-chain through Stripe, no subscription; live
  access only after manual admin approval.
- $30/month plus **1% taker and 0.5% maker as Polymarket builder fees**
  on-chain — the clearest disclosed use of the builder-fee rail; key custody
  through an HSM/TEE provider.
- $299/month (up to 250 wallets, dedicated RPC), non-custodial. Another at
  ~0.5%. One at $0 for now, until Polymarket switches fees on.
- So there are **two revenue rails**: (a) an on-chain builder fee (0.5–1%) or
  (b) an off-chain performance fee through Stripe (10% of profit). (b) is more
  consistent with being non-custodial and avoids the on-chain fee mechanics
  question entirely.

**Security incidents, which underline the non-custodial requirement:**

- One service lost roughly $230k in January 2026. It was **custodial** — the
  backend generated and stored per-user private keys and signed server-side.
  The vector included SSRF plus a reversible key store. That is exactly the
  model **not** to build.
- Another lost roughly $70k in February 2026, and malicious GitHub
  "copy-trading-bot" repositories exfiltrate private keys out of `.env`. The
  lesson is the same: keys on the server are attack surface.

**Polymarket's own stance, directly relevant to the insider feature:** in April
2026 Polymarket began **auditing builder startups whose apps help users copy
suspicious insider wallets**, triggered by four wallets created on the same day
making $663k on one market, alongside a monitoring partnership and new
insider-trading rules. Importantly this is "embrace builders, police
insider-copying", not anti-copy-trading — Polymarket's own newsletter profiles
copy tools positively. **What follows for us:** the suspicious and insider
screen is valuable, but a feature that "copies this insider wallet
automatically" is precisely what is being audited. Position insider detection
as **research and warning**, not as a tail-the-insider funnel.

**Counterparty observation:** the two best-known tools disclose **no legal
entity, address or governing law**, only an email. For a tool that touches live
trading credentials that is a risk signal — we do it differently, with a named
entity and real terms.

### 3e. A defensible design, if C ever happens

- **Strictly non-custodial:** never funds, keys or secrets on the server; a
  capped, revocable allowance; the fee off-chain through Stripe.
- **Execution-only or user-confirmed** rather than silent auto-execution, and
  signals **generic, not personalised**, so it is not advice.
- **Real geoblocking: Switzerland and the US** (event contracts are a CFTC
  minefield), plus Polymarket's own restricted list — IP geofencing plus
  attestation plus terms, not merely a checkbox.
- **Real terms** with restricted jurisdictions, "not financial advice", "not
  affiliated", a non-custodial statement, a named operating entity, a liability
  cap and a governing law.
- **The legal memo before the first live trade.**

## 4. Crypto payment

**Two workable routes alongside cards:**

1. **A gateway with automatic conversion to fiat** (~0.5–1%): the processor
   becomes the regulated intermediary instead of you, you receive fiat, and
   there is no volatility or custody. An EU-licensed provider fits Swiss and EU
   requirements better. Two to four days. Recurring billing is invoice- and
   reminder-based, not a true auto-pull.
2. **A direct USDC-on-Polygon address sold as a 30-day prepaid** (no
   auto-renew): crypto-native for a Polygon audience, under $0.01 in fees,
   settled in seconds. A per-user deposit address gives attribution and an RPC
   watcher confirms payment. Three to six days, no processor cut, but the edge
   cases are yours.

**Dead or unsuitable:** Coinbase Commerce (shut down 2026-03-31), Stripe
stablecoin (US merchants only), Solana-based gateways (wrong chain), auto-pull
protocols (over-engineering until users ask for auto-renew).

**Tax and law (Switzerland):** accepting crypto does **not** make you a
financial intermediary, because selling your own service is not intermediation,
and automatic conversion through a gateway keeps the regulator out of it.
Revenue books at its CHF value on receipt as business income, with no private
capital-gains exemption. VAT follows the SaaS service, not the payment method.

**Recommendation: fiat only at launch.** Stripe or a merchant of record earns
more revenue per hour of work and solves EU VAT. Add crypto (option 2, a
USDC-on-Polygon button) once paying users ask for it — for a crypto-native
audience it is then a real differentiator.

## 5. Recommended order

**Buildable now (no or low risk):**

1. ✅ **Speed step 1**: WS detection instead of on-chain polling. Done.
2. Speed 2–3: harden execution and move the worker to Dublin — the public
   deploy puts it on an EU VPS anyway.
3. Read-only wallet connect (React component plus SIWE), two to four days.
4. Crypto payment only after launch, if asked for.

**Strategic decision (not without a lawyer):**

5. Live copy-trading only after a **legal memo (CHF 5–25k)** on the BGS
   Art. 130 question, plus a defensible design (non-custodial, execution-only,
   CH and US geoblocking, real terms, named entity). The engineering is then
   two to four weeks plus the JavaScript onboarding microservice.

**The short version:** we can be the fastest *paper* copy and analytics
platform and ship wallet-connect analytics, both without legal exposure. The
jump to **live money** is a separate decision that needs a lawyer, because for
a Swiss resident it touches the gambling-law boundary.
