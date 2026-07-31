# Access protocols for prediction-market venues: REST, WebSocket, FIX

Reference for building low-latency market-data infrastructure against Polymarket and Kalshi,
and for defending that build in a trading-firm interview.

Status: 2026-07-31. Written in English by preference; no Eszett character is used anywhere.

---

## 0. How to read this document

Every factual claim carries a source key. The register is in section 8.

| Marker | Meaning |
| --- | --- |
| `[P …]` | PRIMARY. Venue documentation, venue-published spec artifact, venue help centre. |
| `[S …]` | SECONDARY. Blog, tutorial, vendor page, third-party bug report. Treated as a lead, never as evidence. |
| `[OBS]` | First-hand observation made while writing this document, 2026-07-31, from a client in Central Europe. Reproducible commands are given. |
| **NOT DOCUMENTED** | The venue documentation is silent. This is stated explicitly rather than filled in from general knowledge. |

Two rules were applied throughout:

1. Where a secondary source contradicts a primary source, the primary source wins and the
   secondary source is named and flagged in section 7.
2. Where nothing could be verified, the document says so instead of guessing. Roughly a
   quarter of the interesting questions about these venues have no published answer, and
   pretending otherwise is how people ship silent book corruption.

---

## 1. REST

### 1.1 Polymarket: four separate hosts, and the distinction matters

Polymarket does not have "a REST API". It has several services on different hostnames with
different pagination models, different rate limits and different data shapes. Conflating them
is the single most common error in third-party writeups.

| Host | Purpose | Source |
| --- | --- | --- |
| `https://clob.polymarket.com` | Production CLOB. All live book and price primitives, plus trading and own-account ledger. | `[P P-OB]`, `[P P-POB]` |
| `https://gamma-api.polymarket.com` | Market and event metadata, discovery, search, tags, series. | `[P P-KEYSET]` |
| `https://data-api.polymarket.com` | Analytics and history: trades, positions, open interest, holders, leaderboards. | `[P P-TRADES]` |
| `https://bridge.polymarket.com` | Deposit and withdrawal bridge. Not market data. | `[P P-RATE]` |
| `https://api.perpetuals.polymarket.com` | Perpetuals product. A completely different API with its own schema. | `[P P-RATE]` |

The perpetuals host is a genuine trap. Polymarket's own documentation index exposes a page at
`api-reference/get-book` which is the **Perps** book (`GET /v1/info/book`, with a `depth`
parameter), not the CLOB book. The CLOB book is documented separately at
`api-reference/market-data/get-order-book`. The two have different schemas and different
request weights `[P P-RATE]`.

**Market-data endpoints on the CLOB** (all documented with `security: []`, that is, no
authentication) `[P P-OB]`, `[P P-POB]`:

| Purpose | Call | Notes |
| --- | --- | --- |
| Order book | `GET /book?token_id=` | **No `depth` parameter exists.** Whether the response is truncated is NOT DOCUMENTED. |
| Order books, batch | `POST /books` | "Maximum 500 items per request." |
| Best price | `GET /price?token_id=&side=BUY` | `BUY` returns the lowest ask, `SELL` the highest bid. |
| Midpoint / spread / last trade | `GET /midpoint`, `/spread`, `/last-trade-price` | Each has a `POST` batch twin, capped at 500 items. |
| Tick size | `GET /tick-size?token_id=` or `GET /tick-size/{token_id}` | Two documented variants. |
| Price history | `GET /prices-history?market=&interval=&fidelity=` | `interval` in `max, all, 1m, 1w, 1d, 6h, 1h`; `fidelity` in minutes. Returns `{"history":[{"t":<int>,"p":<float>}]}`, numeric, unlike the string-typed book. |

**Order book response shape** `[P P-OB]`. Ten required fields: `market`, `asset_id`,
`timestamp`, `hash`, `bids`, `asks`, `min_order_size`, `tick_size`, `neg_risk`,
`last_trade_price`. Every field is a **string** except `neg_risk` (boolean), including
`timestamp`, `price` and `size`. Levels are `{price, size}` objects. Sizes are absolute
per level, not cumulative.

> **Documented contradiction, resolved by measurement.** The OpenAPI spec says bids are
> "sorted by price descending" and asks ascending `[P P-OB]`. The prose guide says the exact
> opposite: "Bids are ordered by ascending price and asks by descending price, so the best bid
> and ask are the last entries in their respective arrays" `[P P-POB]`. A live call settles it:
> bids came back `0.001, 0.002` (ascending) and asks `0.999, 0.995` (descending), so the prose
> page is correct and the OpenAPI spec is wrong `[OBS]`. **Never index `[0]` or `[-1]`. Take
> `max(bids.price)` and `min(asks.price)` explicitly.** This repository's
> `src/book_recorder.py` already sorts explicitly and is therefore immune.

**Pagination: three different models on one venue** `[P P-KEYSET]`, `[P P-TRADES]`.

| Surface | Model | Limits |
| --- | --- | --- |
| Gamma legacy `GET /markets` | `limit` + `offset`, both `minimum: 0` | Max limit, default limit, max offset all NOT DOCUMENTED. Response is a bare array with no total count, so end-of-data is only implied by a short page. |
| Gamma keyset `GET /markets/keyset` | `after_cursor` from `next_cursor` | `limit` max 100, default 20. `offset` "Not allowed. Returns 422 if provided." `next_cursor` is "Omitted on the last page." `GET /events/keyset` is the same model with limit max 500. |
| Data API `GET /trades` | `limit` + `offset`, both capped at 10000 | Limit above max is clamped; **offset above max returns 400, never silently clamped**. To go deeper, page inside `start`/`end` windows, each of which has its own offset budget. |
| CLOB market data | None | Batching is by the 500-item request cap, not by cursor or offset. |

Polymarket's own SDK comparison table lists pagination for the raw API as "Varies by API"
`[P P-SDK]`, which is an unusually honest admission.

**Rate limits: two independent regimes.**

*Regime 1, IP-based, applies to reads* `[P P-RATE]`:

> "The limits on this page are IP-based and enforced using Cloudflare's throttling system.
> When you exceed the limit for any endpoint, requests are throttled (delayed/queued) rather
> than immediately rejected. Limits reset on sliding time windows."

This is operationally important and widely misreported: **exceeding a read limit does not give
you a 429, it gives you latency**. A poller that trips the limit degrades silently into a slow
consumer. No HTTP status is documented for exceeding the IP limits.

Selected values, all per 10 seconds `[P P-RATE]`: General 15,000. Gamma general 4,000,
`/events` 500, `/markets` 300, `/markets` plus `/events` listing 900. Data API general 1,000,
`/trades` 200, `/positions` 150. CLOB general 9,000, `/book` 1,500, `/books` 500, `/price`
1,500, `/prices` 500, `/midpoint` 1,500, `/prices-history` 1,000, tick size 200.

*Regime 2, per-signer token buckets, applies only to trading* `[P P-TRATE]`. Order and cancel
requests are metered per signer address, separately from the Cloudflare limits. Exceeding
returns **429** with headers `Poly-RateLimit-Remaining`, `Poly-RateLimit-Reset`,
`Poly-RateLimit-Tier`, `Retry-After`. Tiers run Standard (40 orders/s, burst 60) through Elite
at 10M USD 30-day volume (600 orders/s, burst 900); assignments refresh every three hours. A
batch "is admitted only when the bucket contains enough tokens for every entry. Otherwise, the
entire request is rejected and no entries are processed." The docs state enforcement began in
warning mode on 24 July 2026; **the live-enforcement date is NOT DOCUMENTED**.

**Bottom line: there is no per-key rate limit on Polymarket market data.** Reads are metered
per IP and throttled. This has a direct consequence for horizontal scaling that is worth
saying out loud in an interview: adding API keys buys you nothing on the read path, adding
egress IPs does.

**What Polymarket does NOT expose over REST** `[P P-WSMKT]`, `[P P-POB]`:

- Per-order queue position. NOT DOCUMENTED, no field and no endpoint.
- Order IDs or identities of other participants' resting orders. The book is explicitly
  "Full **aggregated** orderbook for an asset". Identity is public only *after* a fill: the
  Data API `/trades` returns `proxyWallet`, `name`, `pseudonym`, `profileImage` per trade.
  Pre-fill anonymity, post-fill transparency.
- Book depth control. No `depth` parameter on `/book`.
- Tick-size *change* events, new-market and market-resolved notifications, and `best_bid_ask`.
  These exist only on the WebSocket, the last three gated behind `custom_feature_enabled`.
- Deltas of any kind. REST is snapshot-only.

Additionally, `matching-engine.md` documents **HTTP 425 Too Early** on all order-related
endpoints during matching-engine restarts, plus 503 for cancel-only and post-only modes, and
"After every restart, the matching engine enters post-only mode for 2 minutes" `[P P-ME]`.
Anyone claiming to have built production order routing here should know 425 exists.

### 1.2 Kalshi

**Base URLs** `[P K-ENV]`:

| Environment | Recommended | Also supported |
| --- | --- | --- |
| Production REST | `https://external-api.kalshi.com/trade-api/v2` | `https://api.elections.kalshi.com/trade-api/v2` |
| Demo REST | `https://external-api.demo.kalshi.co/trade-api/v2` | `https://demo-api.kalshi.co/trade-api/v2` |

The `external-api` hosts are the newer dedicated external-trader infrastructure; the
`elections` hosts remain supported for backward compatibility. Despite the subdomain, "the
production Trade API provides access to all Kalshi markets, not only election-related markets"
`[P K-ENV]`. This repository currently points at the legacy host (section 6).

**Order book** `[P K-OB]`, confirmed live `[OBS]`: `GET /markets/{ticker}/orderbook`, with
`depth` documented as "0 or negative means all levels, 1-100 for specific depth". Unlike
Polymarket, Kalshi therefore does let you ask for full depth. The endpoint requires **no
authentication**; an unauthenticated call returned HTTP 200 `[OBS]`.

Response, verbatim from a live call `[OBS]`:

```json
{"orderbook_fp":{"no_dollars":[["0.7600","150.00"],["0.7800","264.32"],["0.8400","500.00"]],
                 "yes_dollars":[["0.0700","3195.84"],["0.0800","253.00"],["0.0900","743.03"]]}}
```

**Both arrays are bid ladders.** This is the defining structural fact about Kalshi and the
easiest way to invert every spread you compute `[P K-OBRESP]`:

> "Kalshi's orderbook only returns bids, not asks. [...] A **YES BID** at price X is equivalent
> to a **NO ASK** at price ($1.00 - X)"
> "Arrays are sorted by price in **ascending order**. The **highest** bid (best bid) is the
> **last** element in each array"

So the best YES ask is `1.00 - max(no_dollars.price)`. In the live sample: best YES bid 0.09
(from the shown slice), best NO bid 0.84, implied best YES ask 0.16.

**Fixed-point representation.** Kalshi has migrated off integer cents `[P K-FP]`. Prices are
`*_dollars` fixed-point strings with up to 4 decimals; quantities are `*_fp` strings with 2
decimals and a minimum granularity of 0.01 contracts. Both are **strings**, "to support
subpenny pricing and fractional contract" sizes `[P K-OBRESP]`. Parse with `Decimal`, not
`float`. The documentation gives **no deprecation timeline or sunset date** for the legacy
integer fields, so a client cannot plan the cutover from published information alone.

**Pagination** `[P K-PAGE]`: uniform cursor model. `limit` 1 to 100, default 100; `cursor`
from the previous response; "Continue until the cursor is `null` (no more pages)." Simpler
and more consistent than Polymarket.

**Rate limits** `[P K-RATE]`: a token-bucket system with **independent Read and Write buckets**,
metered **per authenticated request, not by IP**. Most requests cost the default of 10 tokens;
`GET /account/endpoint_costs` is the authoritative list of exceptions. Batch operations bill
each item separately, so batching saves round trips but not tokens.

| Tier | Read tokens/s | Write tokens/s |
| --- | --- | --- |
| Basic | 200 | 100 |
| Advanced | 300 | 300 |
| Expert | 600 | 600 |
| Premier | 1,000 | 1,000 |
| Paragon | 2,000 | 2,000 |
| Prime | 4,000 | 4,000 |
| Prestige | 6,000 | 8,000 |

Burst: higher-tier buckets hold up to two seconds of budget and can spend twice the per-second
budget in one burst after two idle seconds; Basic-tier write buckets and the higher Predictions
Read buckets hold one second only. Exceeding returns **429 Too Many Requests** with no penalty
or cooldown, the bucket simply keeps refilling. Basic comes with signup, Advanced via the
Upgrade Account API Usage Level endpoint, and Expert and above are granted from 30-day trading
volume (a "volume share" of 0.075 percent to 1.0 percent of monthly exchange volume depending
on tier) or assigned manually.

Note the asymmetry versus Polymarket, and its architectural consequence: Kalshi meters per key,
so scaling reads means more keys or a higher tier. Polymarket meters per IP, so scaling reads
means more egress addresses. The same "just add workers" instinct is wrong on both, differently.

**Crucially, the tier table does not govern WebSockets.** The page scopes itself explicitly:
"The split is by operation type, not by protocol. REST and FIX requests drain the same buckets"
`[P K-RATE]`. WebSocket is never mentioned. FIX is (section 3).

**What Kalshi does NOT expose over REST:**

- Historical order book depth. Only markets, candlesticks, trades, orders and positions move to
  the historical endpoints, with a live-data retention target of three months `[P K-HIST]`.
  There is no historical book-snapshot product. If you want book history you must record it,
  which is precisely what this repository does.
- Resting-order identity or queue position on the public book. The book is aggregated.
  (Kalshi does expose `GET /orders/queue_position` and a batch variant, but for **your own**
  orders `[P K-LLMS]`.)
- Per-order granularity of any kind on the public feed.

**Two operational facts that belong in any Kalshi integration:**

- **Maintenance**: "every Thursday from 3:00 AM to 5:00 AM ET", with "Clients should be prepared
  for session disconnections during this window and reconnect after 5:00 AM ET" `[P K-MAINT]`.
  A recorder that alerts on disconnects will page you every Thursday unless it knows this.
- **Exchange sharding**: Kalshi is splitting trading across multiple matching engines, with
  combos migrating to shard 1 **starting 6 August 2026** `[P K-SHARD]`. An `exchange_index`
  field is exposed on `GET /markets`, `GET /events` and the WebSocket stream. It is already
  live: a call today returned `exchange_index` on both the event and the market object `[OBS]`.
  Order groups do not work across shards, and collateral must be preallocated per shard.

---

## 2. WebSocket

### 2.1 Polymarket

**Endpoints** `[P P-WSMKT]`, `[P P-WSUSER]`, `[P P-WSRFQ]`, `[P P-WSSPORT]`, `[P P-RT]`:

| Channel | URL | Auth |
| --- | --- | --- |
| Market | `wss://ws-subscriptions-clob.polymarket.com/ws/market` | None. Public. |
| User | `wss://ws-subscriptions-clob.polymarket.com/ws/user` | L2 credentials in the message body |
| RFQ | `wss://combos-rfq-gateway-quoter.polymarket.com/ws/rfq` | L2 credentials plus identity block |
| Sports | `wss://sports-api.polymarket.com/ws` | None. No subscription frame at all. |
| RTDS | `wss://ws-live-data.polymarket.com` | Crypto/equity prices and comments |

**Authentication is in the payload, not in headers.** All four AsyncAPI documents declare
`securitySchemes: []`; the `auth` object (`apiKey`, `secret`, `passphrase`, note the camelCase
`apiKey` among otherwise snake_case fields) is a message field `[P P-WSUSER]`. Credentials come
from the L1/L2 flow: an EIP-712 signature over domain `{"name":"ClobAuthDomain","version":"1",
"chainId":137}` exchanged at `POST /auth/api-key` (persists) or `GET /auth/derive-api-key`
(deterministic) `[P P-AUTH]`. **The market channel needs no credentials at all.**

**Subscription** `[P P-WSMKT]`. Required `assets_ids` and `type: "market"`. Optional and
generally overlooked:

- `initial_dump` (bool, default `true`) suppresses the on-subscribe snapshot when `false`.
- `level` (integer, enum `[1,2,3]`, default 2). **What the levels mean is NOT DOCUMENTED.**
- `custom_feature_enabled` (bool, default `false`) unlocks `best_bid_ask`, `new_market`,
  `market_resolved`, and nothing else.

Live modification without reconnecting uses `{"operation": "subscribe"|"unsubscribe",
"assets_ids": [...]}`.

> Wire format warning: the JSON field is snake_case `custom_feature_enabled`. The camelCase
> `customFeatureEnabled` appears only in the TypeScript SDK example. The SDK also presents a
> normalized envelope `{topic, type, payload}` with camelCase fields that the raw socket never
> emits `[P P-RT]`. Copying SDK snippets into a raw socket client silently does nothing.

**Market channel events** `[P P-WSMKT]`. Every value is a JSON string, including numbers and
timestamps.

| `event_type` | Payload | Gated |
| --- | --- | --- |
| `book` | `asset_id`, `market`, `bids[]`, `asks[]` of `{price,size}`, `timestamp`, `hash` | no |
| `price_change` | `market`, `timestamp`, `price_changes[]` each with `asset_id`, `price`, `size`, `side`, `hash`, optional `best_bid`/`best_ask` | no |
| `last_trade_price` | `asset_id`, `market`, `price`, `size`, `side` (taker's perspective), `timestamp`, optional `fee_rate_bps`, `transaction_hash` | no |
| `tick_size_change` | `asset_id`, `market`, `old_tick_size`, `new_tick_size`, `timestamp` | no |
| `best_bid_ask` | `asset_id`, `market`, `best_bid`, `best_ask`, `spread`, `timestamp` | yes |
| `new_market` | `id`, `question`, `market`, `slug`, `assets_ids[]`, `outcomes[]`, plus a large optional block | yes |
| `market_resolved` | `id`, `market`, `assets_ids[]`, `winning_asset_id`, `winning_outcome` | yes |

**Book integrity semantics. This is the part that decides whether your book is correct.**

- **`book` is a full snapshot**, and its trigger is broader than most implementations assume:
  "Full orderbook snapshot sent on subscribe **or after a trade**" `[P P-WSMKT]`. You get a free
  periodic resync every time the market prints.
- **`price_change` carries the new absolute size, not a change amount.** The prose calls it a
  "delta update", but the field description is decisive: `size` is "New aggregate size (0 means
  level removed)" `[P P-WSMKT]`. "Delta" refers to *which levels* changed, not to the quantity.
  **Overwrite the level; never add.** Zero deletes.
- **There is no sequence number of any kind.** No `seq`, `sequence`, or monotonic counter
  appears on any market-channel schema `[P P-WSMKT]`. **You cannot detect a dropped message
  from the wire protocol.** This is a genuine absence, not a documentation gap, and it is the
  single most important thing to know about this feed.
- **The `hash` is not a usable checksum.** The `book` message carries `hash`, described only as
  "Hash of the orderbook content"; the algorithm and the serialization it covers are
  **NOT DOCUMENTED**, so you cannot recompute it. Worse, the `hash` inside each `price_changes`
  item is a different object entirely: "Hash of the order that caused this change". Treating
  the latter as a running book checksum is a plausible and completely wrong implementation.
  What the hash *is* good for is stated in the REST guide: "Compare it with the previous
  response's hash to determine whether the book changed between reads" `[P P-POB]`. It is a
  change detector, not an integrity check.
  Format note: the docs example shows `"0xabc123..."`, but a live REST `/book` returned a
  40-character lowercase hex string with **no `0x` prefix** `[OBS]`, so do not pattern-match
  on the prefix.
- **`timestamp` is a string of Unix milliseconds.** Whether it is matching time or send time is
  **NOT DOCUMENTED**, and there is no monotonicity or uniqueness guarantee.
- **Snapshot-versus-delta race: NOT DOCUMENTED.** There is no guidance on buffering
  `price_change` events that arrive while the initial `book` is in flight, no ordering
  guarantee, and no resync procedure. The only recovery guidance in the entire doc set is for
  the *user* channel and it explicitly disclaims replay: "Real-time updates do not replace
  authoritative account reads or replay every change missed during a disconnection. After
  reconnecting, fetch the account's open orders and recent trades [...] then resume applying
  new stream events from that refreshed state" `[P P-RTORD]`.

**Heartbeat** `[P P-WSMKT]`, `[P P-RT]`: an **application-level text frame**, not a WebSocket
protocol ping. The AsyncAPI declares `contentType: text/plain` with payload `const: PING`.
"Send the text frame `PING` every 10 seconds; the server replies with `PONG`." What happens if
you skip it is NOT DOCUMENTED for market and user. The Sports channel inverts this: the server
sends lowercase `ping` every 5 seconds and closes the connection if you do not reply `pong`
within 10. RTDS wants `PING` every 5 seconds. RFQ has no ping at all, only a 30-second auth
deadline.

**Limits: essentially undocumented.** Max subscriptions per connection, max connections per IP
or account, and WebSocket message rate limits are all **NOT DOCUMENTED**. The dedicated
rate-limits page is exhaustive for REST and contains zero occurrences of "websocket", "wss",
"connection" or "subscri" `[P P-RATE]`.

**Known failure mode, from the vendor's own issue tracker** `[S P-ISSUE292]`: the market socket
intermittently accepts TCP connections and subscriptions, keeps application ping/pong working,
and then never delivers a single `book` or `price_change` event. Reported 5 March 2026 with a
timeline of six connections cycling through reconnect, acceptance and silence every 15 to 30
minutes over more than two hours; a standalone client received only an empty array `[]` after
subscribing. No maintainer response is recorded in the thread. This is a user report, not
venue documentation, so treat the mechanism as unconfirmed; but it is exactly the "silent
disconnect" failure class from section 5, and it is why a data-inactivity watchdog is not
optional on this feed.

### 2.2 Kalshi

**Endpoints** `[P K-WS]`, `[P K-ENV]`:

| Environment | Recommended | Also supported |
| --- | --- | --- |
| Production | `wss://external-api-ws.kalshi.com/trade-api/ws/v2` | `wss://api.elections.kalshi.com/trade-api/ws/v2` |
| Demo | `wss://external-api-ws.demo.kalshi.co/trade-api/ws/v2` | `wss://demo-api.kalshi.co/trade-api/ws/v2` |

**Authentication happens on the HTTP upgrade request**, unlike Polymarket `[P K-QSWS]`:

> "WebSocket connections require authentication during the connection handshake."

Headers `KALSHI-ACCESS-KEY`, `KALSHI-ACCESS-SIGNATURE`, `KALSHI-ACCESS-TIMESTAMP`. The signed
string is `timestamp + "GET" + "/trade-api/ws/v2"`, with the timestamp in **milliseconds** and
the path taken without query parameters. Signature is RSA-PSS, MGF1(SHA-256),
`salt_length = DIGEST_LENGTH`, SHA-256, base64. The host does not enter the signature payload
`[P K-ENV]`.

**The whole connection requires authentication even for public data** `[P K-WSCONN]`:

> "Authentication is required to establish the connection; include API key headers during the
> WebSocket handshake. Some channels carry only public market data, but the connection itself
> still requires authentication."

Confirmed first-hand: unauthenticated handshakes to both the recommended and the legacy host
returned **HTTP 401 Unauthorized** `[OBS]`.

**Command envelope** `[P K-WSCONN]`. `{"id": <int>, "cmd": <string>, "params": {...}}`. `id` is
client-generated and should be unique per session; `id: 0` is treated as absent. Commands:
`subscribe`, `unsubscribe` (by `sids`), `list_subscriptions`, `update_subscription` (with
`action` in `add_markets | delete_markets | get_snapshot`). Server responses are typed
`subscribed`, `unsubscribed`, `ok`, `error`. Notable optional subscribe params:
`market_ticker`/`market_tickers` (mutually exclusive), `market_id`/`market_ids`,
`send_initial_snapshot`, `skip_ticker_ack`, and **`use_yes_price`** (see below).

**Channels: 13, from the `params.channels` enum** `[P K-WSCONN]`:

| Channel | Carries | Access |
| --- | --- | --- |
| `orderbook_delta` | `orderbook_snapshot` then incremental `orderbook_delta` | Auth required (connection-level) |
| `ticker` | last price, best bid/ask, sizes, volume, open interest | Public data, no extra channel auth |
| `trade` | public executed trades | Public data, no extra channel auth |
| `market_lifecycle_v2` | market/event creation, close changes, determination, settlement | Public data |
| `multivariate_market_lifecycle` | lifecycle for multivariate events | Public data |
| `multivariate` | **deprecated**, "predates RFQs and should not be used" | Public data |
| `fill` | your own fills | Private |
| `market_positions` | your positions, values as `_dollars` strings | Private |
| `user_orders` | your order lifecycle | Auth required |
| `order_group_updates` | order group created/triggered/reset/deleted | Private |
| `communications` | RFQ and quote events | Private, and scoped: quote events arrive "only if you created the quote OR you created the RFQ" |
| `cfbenchmarks_value` | CF Benchmarks index values | Auth required |
| `pyth_value` | Pyth prices per underlying | Auth required |

On **permission scope**, which the brief asked about specifically: the quick-start splits
channels into "private (user-specific data)" and "public market-data (no additional
channel-level auth)" `[P K-QSWS]`. Two caveats that a careful reader should carry into an
interview rather than repeat the doc verbatim:

1. `orderbook_delta` is listed as *private* even though it carries aggregated public book data.
   Its only user-specific content is the optional `client_order_id` and `subaccount` fields that
   appear on deltas **you** caused. The classification looks like a doc simplification, not a
   real entitlement tier.
2. `user_orders`, `cfbenchmarks_value` and `pyth_value` are omitted from the split entirely;
   only their own pages state "Authentication required".

**A read/write scope model for WebSocket channels is NOT DOCUMENTED.** There is no published
mapping from API-key scope to channel access. The only hint is error code 9, "Authentication
required - The requested channel or action requires authentication or channel access that was
not granted", whose phrasing implies an entitlement concept that is never specified. Note that
this repository's `app/kalshi_auth.py` enforces read-only *client-side*, by refusing to sign
anything but GET and blocking order paths; that is a stronger and more auditable guarantee than
anything the venue documents, and it is a good thing to be able to explain.

**Message shapes** `[P K-WSOB]`. Snapshot:

```json
{"type":"orderbook_snapshot","sid":2,"seq":2,
 "msg":{"market_ticker":"FED-23DEC-T3.00","market_id":"...",
        "yes_dollars_fp":[["0.0800","300.00"],["0.2200","333.00"]],
        "no_dollars_fp":[["0.5400","20.00"],["0.5600","146.00"]]}}
```

Delta, and note the negative value:

```json
{"type":"orderbook_delta","sid":2,"seq":3,
 "msg":{"market_ticker":"FED-23DEC-T3.00","price_dollars":"0.960",
        "delta_fp":"-54.00","side":"yes","ts_ms":1669149841000}}
```

> **`delta_fp` is a change amount, not a new size.** The field is documented as "Fixed-point
> contract delta (2 decimals)" and there is **no absolute-size field on the delta message at
> all** `[P K-WSOB]`. Apply `level += delta_fp` and prune at zero. This is the exact opposite
> of Polymarket's `price_change`, where you overwrite. Running one venue's semantics against
> the other drifts within seconds and never raises an error.

**`use_yes_price`: a scheduled, silent breaking change.** By default, no-side deltas and
snapshot levels arrive in **no-leg pricing**, so the two sides use different price scales and
you must map no-side levels through `1.00 - price` to get a single YES-space book. Passing
`use_yes_price: true` at subscribe time makes the server do that mapping. Kalshi has announced
that the default will flip to `true` and the flag will later be removed, with dates to be
announced `[P K-ORDDIR]`. **A client that does not set the flag explicitly will have its book
silently re-scaled on the flip date.** See section 6, item 1.

**Sequence numbers** `[P K-WSOB]`, `[P K-WSCONN]`. Field `seq`, integer, `minimum: 1`. The only
description Kalshi publishes is:

> "Sequential number that should be checked if you want to guarantee you received all the
> messages. Used for snapshot/delta consistency"

Which messages carry `seq`: `orderbook_snapshot`, `orderbook_delta`, `order_group_updates`,
`pyth_value`, `cfbenchmarks_value` and their list variants, plus the `unsubscribed` and `ok`
control responses. Which do **not**: `trade`, `ticker`, `fill`, `user_order`, `market_position`,
all lifecycle messages, and all `communications` messages. On those channels there is no gap
detection at all.

**Scope of the counter is NOT DOCUMENTED.** Kalshi never states whether `seq` is per connection,
per subscription or per market. Circumstantial evidence points to per-subscription (per `sid`):
`seq` always accompanies `sid`, the documented example runs `sid:2, seq:2` then `sid:2, seq:3`,
and `unsubscribed` carries a terminal `seq` for the sid being cancelled. This repository's
`src/kalshi_stream_state.py` already assumes per-subscription and documents the reasoning. It
is very likely right, but it is an **inference, not a documented fact**, and section 6 proposes
turning it into a measurement.

**Documented client behaviour on a gap: NOT DOCUMENTED.** There is no published recovery
procedure. The mechanism that obviously serves as one is `update_subscription` with
`action: "get_snapshot"`, which "returns an `orderbook_snapshot` for the requested
`market_tickers` without modifying the subscription" `[P K-WSOB]`, but the docs never connect it
to gap recovery. Also NOT DOCUMENTED: whether `seq` resets on resubscribe, and whether it wraps.

**Heartbeat** `[P K-WSKA]`. The entire published content:

> "Kalshi sends Ping frames (`0x9`) every 10 seconds with body `heartbeat` to maintain the
> connection. Clients should respond with Pong frames (`0xA`). Clients may also send Ping
> frames to which Kalshi will respond with Pong."

These are **WebSocket protocol control frames**, the opposite of Polymarket's application-level
text frames. There is no `{"cmd":"ping"}`. **The server timeout before disconnect is NOT
DOCUMENTED**: no grace period, no missed-pong threshold, no idle timeout.

**Limits.** Max connections per key: NOT DOCUMENTED. Max subscriptions per connection: NOT
DOCUMENTED. The numeric per-subscription market cap: NOT DOCUMENTED, its existence is revealed
only by error 26, "Adding markets would exceed the per-subscription market limit". WebSocket
command rate limit: NOT DOCUMENTED numerically, only error 27. The one documented backpressure
mechanism is the one that will actually bite a high-fanout subscriber, error 25:

> "Subscription buffer overflow - The subscription's event buffer overflowed during a message
> burst. Subscribe to a smaller subset of data, or ensure that your connection read throughput
> is optimized."

That is Kalshi telling you, in the error table rather than the documentation, that **slow
consumers get dropped data**. It arrives as an explicit error rather than a silent gap, which
is better behaviour than most venues offer.

### 2.3 The two feeds side by side

| Property | Polymarket market channel | Kalshi `orderbook_delta` |
| --- | --- | --- |
| Auth to connect | None | Signed handshake, required even for public data |
| Auth transport | Message body (`auth` object) | HTTP upgrade headers |
| Update semantics | **Absolute** new size per level | **Additive** delta per level |
| Sides | True bids and asks | Two bid ladders, one per outcome |
| Price scale | Single | Two scales by default, unify with `use_yes_price: true` |
| Sequence numbers | **None** | `seq`, scope undocumented |
| Gap detection | Impossible from the protocol | Possible on the book channel only |
| Documented resync | None | None, but `get_snapshot` exists |
| Free periodic resync | Yes, full `book` after every trade | No |
| Heartbeat | App-level text `PING`, client sends, 10s | Protocol ping `0x9`, server sends, 10s |
| Backpressure signal | None documented | Error 25, buffer overflow |
| Numeric connection limits | None documented | None documented |

Two feeds, opposite conventions on nearly every axis. Any shared abstraction over them has to
be explicit about which semantics it is normalizing to, which is exactly why this repository
keeps `src/book_stream.py` and `src/kalshi_stream_state.py` as separate state machines rather
than one parameterized one. That is the right call and worth defending as such.

---

## 3. FIX on Kalshi

### 3.1 What FIX is, and why an exchange offers it

FIX (Financial Information eXchange) is a tag-value message protocol that predates the modern
web API and remains the default institutional connection to most regulated venues. Messages are
`tag=value` pairs separated by SOH (0x01), for example
`8=FIXT.1.1|9=nnn|35=D|49=<sender>|56=<target>|34=<seq>|52=<time>|...|10=nnn|`.

The important conceptual split, and the one an interviewer will probe:

- **Session layer.** A stateful, ordered, reliable byte stream over a single long-lived TCP
  connection. It owns Logon, Logout, Heartbeat, TestRequest, ResendRequest, SequenceReset, and
  Reject. Its job is to guarantee that both sides agree on an exactly-once, in-order stream of
  application messages, and to detect and repair divergence. Sequence numbers are per session
  and per direction, and they persist across reconnects unless explicitly reset.
- **Application layer.** The business messages: NewOrderSingle, ExecutionReport,
  MarketDataRequest, and so on. These ride on top and assume the session layer has already
  solved ordering and loss.

That separation is the whole point, and it is exactly what REST and WebSocket lack. REST is
stateless request/response with no notion of a stream, so recovery means "poll again and hope".
A WebSocket gives you a stream but no standard session semantics: as sections 2.1 and 2.2 show,
Polymarket has no sequence numbers at all and Kalshi has sequence numbers with **no documented
recovery procedure**. FIX standardises both. When something goes wrong on a FIX session, there
is a defined, interoperable protocol for putting it right, and both sides implement the same
one because it is a published specification rather than a venue convention.

Exchanges offer FIX for four reasons, roughly in order of how often they are actually the
motivation: institutional clients already have FIX engines and connectivity, it is the format
regulators and post-trade systems expect, it has real recovery semantics, and it avoids
per-message HTTP and JSON overhead.

### 3.2 Documentation status: public, contrary to the common claim

**Kalshi's FIX documentation is public and reasonably complete.** It lives at
`https://docs.kalshi.com/fix/` across twelve pages, with a parallel `fix-margin/` tree for the
perpetuals product `[P K-LLMS]`. There is also a machine-readable dictionary at
`https://assets.kalshi.com/fix/kalshi-fix-dictionary.xml` `[P KF-COMMON]`.

This is worth stating plainly because a good deal of writing about Kalshi asserts the opposite,
or asserts a different FIX version. See section 7.

### 3.3 Version

**FIXT.1.1 as the session-layer version, with FIX50SP2 as the application version**
`[P KF-CONN]`, `[P KF-COMMON]`. Verified first-hand in the published dictionary, whose root
element is `<fix type='FIXT' major='1' minor='1' servicepack='0'>` `[OBS]`.

The split is itself a FIX 5.x concept and a fair interview question: from FIX 5.0 onward, the
session layer (FIXT.1.1) was versioned independently of the application layer, so `BeginString`
(tag 8) carries `FIXT.1.1` and the application version travels in `DefaultApplVerID` (tag 1137),
set to `9` for FIX50SP2 on Logon `[P KF-AUTH]`. In FIX 4.x, `BeginString` carried both, which is
why anyone claiming Kalshi runs "FIX 4.4" is describing a protocol whose header would look
materially different.

### 3.4 Endpoints, ports and session types

Hosts `[P KF-CONN]`: production `mm.fix.elections.kalshi.com` (order entry) and
`marketdata.fix.elections.kalshi.com` (market data); demo `fix.demo.kalshi.co` and
`marketdata.fix.demo.kalshi.co`.

| Session | Port | TargetCompID | Purpose |
| --- | --- | --- | --- |
| Order Entry, no retransmission | 8228 | `KalshiNR` | Submit, modify, cancel. No message persistence. Supports listener sessions. |
| Order Entry, with retransmission | 8230 | `KalshiRT` | Adds retransmission and RFQ creation. Institutional access. |
| Drop Copy | 8229 | `KalshiDC` | Request/response queries for historical execution reports. |
| Post Trade | 8231 | `KalshiPT` | Read-only settlement and position resolution stream. Institutional. |
| RFQ | 8232 | `KalshiRFQ` | Market-maker RFQ broadcast and quote management. |
| **Market Data** | **8233** | **`KalshiMD`** | **Order book snapshots and incremental updates. Market data host only.** |

`SenderCompID` is your FIX API key in UUID form; the session ID is TargetCompID plus
SenderCompID. **"Only one FIX connection is allowed per API key"**, so concurrent sessions need
separate keys `[P KF-CONN]`. Transport is **TLS 1.2 or higher, mandatory**, with cipher suites
following AWS Network Load Balancer policies; certificate pinning is supported.

### 3.5 Session lifecycle

**Logon (35=A)** `[P KF-AUTH]`. Required fields: `EncryptMethod` (98) = 0 (None); `RawData` (96)
= base64 signature; `HeartBtInt` (108) = N, documented as greater than 3 seconds;
`DefaultApplVerID` (1137) = 9 (FIX50SP2).

The signature is RSA-PSS over SHA-256, base64-encoded, computed over this pre-hash string with
SOH separators:

```
SendingTime <SOH> MsgType <SOH> MsgSeqNum <SOH> SenderCompID <SOH> TargetCompID
```

`SendingTime` must exactly match tag 52, formatted `YYYYMMDD-HH:MM:SS.mmm`, and **must be
within 30 seconds of server time** `[P KF-AUTH]`, `[P KF-COMMON]`. The same RSA key pair as the
REST API is used, and the API Key ID becomes the `SenderCompID`. Note this is a different
pre-hash string from the REST and WebSocket scheme (`timestamp + METHOD + path`), so a shared
signing helper cannot simply be reused.

**Standard header** `[P KF-COMMON]`: `BeginString` (8) always `FIXT.1.1`, `BodyLength` (9)
second, `MsgType` (35) third, `SenderCompID` (49), `TargetCompID` (56), `MsgSeqNum` (34)
monotonically increasing from 1, `SendingTime` (52). Optional recovery fields `PossDupFlag`
(43), `PossResend` (97), `OrigSendingTime` (122, required when `PossDupFlag=Y`). Trailer:
`CheckSum` (10), sum of every byte before it modulo 256, always three digits zero-padded.

**Heartbeats.** `HeartBtInt` is negotiated on Logon. Each side sends Heartbeat (35=0) when
otherwise idle for that interval; a side that has heard nothing sends TestRequest (35=1), and
the counterparty must answer with a Heartbeat echoing the `TestReqID`. This is standard FIX
session behaviour; **Kalshi does not publish a specific missed-heartbeat disconnect threshold**,
but it does say that after an unexpected disconnection you should "wait for server heartbeat
timeout (up to 60 seconds) before reconnecting" `[P KF-ERR]`.

**Sequence numbers, and Kalshi's specific policy.** This is where Kalshi deviates from textbook
FIX and where an implementation will break if you assume the standard:

- **`ResetSeqNumFlag` (141) = Y is required on every Logon for `KalshiNR`, `KalshiDC`,
  `KalshiRFQ` and `KalshiMD`; the Logon is rejected without it** `[P KF-ERR]`. So the market
  data session starts from sequence 1 every time by mandate.
- **Message retransmission is unsupported on `KalshiMD`** `[P KF-MD]`. Only `KalshiRT` and
  `KalshiPT` support ResendRequest.
- Kalshi does not initiate sequence resets during maintenance; clients should reset on their
  side when reconnecting. `KalshiRT` sessions retain message continuity across the maintenance
  window and can request retransmission of messages missed during downtime `[P KF-CONN]`.
- If a client's stored sequence exceeds the server's state, the server may request a resend of
  messages it does not have, and the connection fails `[P KF-ERR]`.

**ResendRequest (35=2), SequenceReset (35=4) and gap fill.** Standard FIX: on detecting an
inbound sequence higher than expected, a party sends ResendRequest with `BeginSeqNo` and
`EndSeqNo`; the counterparty replays application messages with `PossDupFlag=Y` and the original
`OrigSendingTime`, and collapses runs of administrative or no-longer-relevant messages into
SequenceReset with `GapFillFlag=Y` pointing at `NewSeqNo`. Both messages are defined in Kalshi's
dictionary `[OBS]`. **For market data this machinery is unavailable**, because `KalshiMD` does
not support retransmission and mandates a sequence reset on every Logon. The practical
consequence is important and worth saying in an interview: **on the Kalshi market-data FIX
session, recovery from loss is reconnect-and-resnapshot, exactly as on the WebSocket.** FIX
buys you framing, standard session semantics and lower overhead here, not replay.

**Logout (35=5).** Standard bilateral logout. Kalshi exempts Logout, Heartbeat and TestRequest
from rate limiting but **not** Logon `[P KF-CONN]`.

**Rejects** `[P KF-ERR]`. Session-level violations produce Reject (35=3) with `RefSeqNum` (45),
`RefTagID` (371), `SessionRejectReason` (373) and `Text` (58); reason 10 is the SendingTime
accuracy failure. Application-layer failures before exchange processing produce
BusinessMessageReject (35=j) with `RefMsgType` (372) and `BusinessRejectReason` (380). Note the
subtlety Kalshi calls out explicitly: **order rejections from the exchange come back as
ExecutionReport (35=8) with `ExecType=Rejected` and `OrdRejReason` (103), not as
BusinessMessageReject.** Cancel failures use OrderCancelReject (35=9) with `CxlRejReason` (102).

### 3.6 Market data messages

Supported types on `KalshiMD` `[P KF-MD]`:

| MsgType | Message |
| --- | --- |
| `V` | MarketDataRequest |
| `W` | MarketDataSnapshotFullRefresh |
| `X` | MarketDataIncrementalRefresh |
| `Y` | MarketDataRequestReject |
| `e` | SecurityStatusRequest |
| `f` | SecurityStatus |

**MarketDataRequest (35=V)**: `SubscriptionRequestType` (263) with `0` = snapshot, `1` = snapshot
plus updates, `2` = disable; `NoRelatedSym` (146) counting a repeating group of `Symbol` (55),
which is the market ticker.

**Snapshot (35=W)**: `Symbol` (55), `NoMDEntries` (268), and per entry `MDEntryType` (269),
`MDEntryPx` (270), `MDEntrySize` (271). `MDEntryType` is `0` = Bid, `1` = Offer.

**Incremental (35=X)**: `NoMDEntries` (268), and per entry `MDUpdateAction` (279) with
`0` = New, `1` = Change, `2` = Delete; `Symbol` (55); `MDEntryType` (269) with `0` = Bid,
`1` = Offer, `2` = Trade; `MDEntryPx` (270) as a dollar amount; `MDEntrySize` (271) as a
contract count; and `AggressorSide` (2446) on trades only, `1` = Buy, `2` = Sell.

> **Note the semantic difference from Kalshi's own WebSocket.** FIX market data uses
> `MDUpdateAction` New/Change/Delete, which is *level-replace* semantics: a `Change` carries the
> new size at that level. The WebSocket `orderbook_delta` carries an additive `delta_fp`. The
> same venue therefore ships two different book-maintenance conventions on two different
> transports, and code cannot be shared between them without an explicit adapter. This is the
> kind of detail that separates someone who has read the docs from someone who has built
> against them.

Also documented `[P KF-MD]`: unknown tickers receive **empty snapshots rather than rejections**,
and rejection reasons include insufficient bandwidth or an unsupported subscription type.

`MDEntryType` `1` is labelled "Offer", which raises the question of whether the FIX feed
presents a true two-sided book or Kalshi's two-bid-ladder convention. **The FIX market-data page
does not state which**, and the subpenny page lists only tags 6, 31, 44, 132 and 133 as
dollar-format tags, **not 270** `[P KF-SUB]`, while the market-data page describes 270 as a
"Dollar amount" `[P KF-MD]`. These two statements are not obviously consistent. **I could not
resolve from published documentation whether `MDEntryPx` on `KalshiMD` follows the
`UseDollars` (21005) toggle.** Anyone building this must confirm it on the demo session before
trusting a price.

### 3.7 Order-entry messages

`[P KF-OE]`: NewOrderSingle (35=D), OrderCancelReplaceRequest (35=G), OrderCancelRequest (35=F),
ExecutionReport (35=8), OrderMassCancelRequest (35=q, `KalshiNR` only), OrderMassCancelReport
(35=r), OrderCancelReject (35=9). Key tags are conventional: `ClOrdID` (11), `OrigClOrdID` (41),
`OrderQty` (38), `OrdType` (40), `Price` (44), `Side` (54), `Symbol` (55), `TimeInForce` (59),
`ExpireTime` (126), and on reports `OrderID` (37), `ExecType` (150), `OrdStatus` (39), `CumQty`
(14), `LeavesQty` (151), `AvgPx` (6), `LastPx` (31), `LastQty` (32).

Kalshi custom tags, verified against the published dictionary `[OBS]`, `[P KF-OE]`: 21001
`BeginExecID`, 21002 `EndExecID`, 21003 `ResendEventCount`, 21004 `EventResendRejectReason`,
21005 `UseDollars`, 21006 `CancelOrderOnPause`, 21007 `EnableIocCancelReport`, 21008
`PreserveOriginalOrderQty`, 21009 `MaxExecutionCost`, 21010 `QuoteConfirmStatus`, 21011
`SkipPendingExecReports`, 21012 `UseExpiredOrdStatus`, 21013 `RFQCancelStatus`, 21015
`RestRemainder`, 21016 `ReplaceExisting`, 21022 `PreferBetterQuote`, 21023 `RfqId`, 21024
`AcceptedQuoteId`, 21025 `AcceptQuoteStatus`, 21026 `AlwaysEmitNewBeforeTrade`.

Sharding reaches FIX through `ExDestination` (100): omitted defaults to shard 0, `-1` routes
automatically, non-negative values route to a specific shard `[P K-SHARD]`.

### 3.8 Drop copy and application-level replay

Worth knowing because it is where Kalshi solves recovery outside the session layer
`[P KF-DC]`. Drop Copy is request/response, not streaming, over a **three-hour lookback window**.
`EventResendRequest` (35=U1) takes `BeginExecID` (21001, inclusive) and `EndExecID` (21002,
optional, defaults to latest). The ExecID format is `clock;event` for exchange index 0 and
`clock;event;exchange_index` otherwise, and both bounds must reference the same exchange index,
which is the sharding model surfacing again. `EventResendComplete` (35=U2) confirms with
`RefSeqNum` (45) and `ResendEventCount` (21003); `EventResendReject` (35=U3) covers too many
concurrent requests, server errors, or a `BeginExecID` outside the three-hour window.

The design point: **resent messages get new FIX sequence numbers, so reconciliation is by ExecID
rather than by sequence number.** That is an application-level replay mechanism deliberately
layered on top of, and independent from, session-level resend.

Separately, **listener sessions** are a read-only mode on `KalshiNR` or `KalshiRT`, enabled with
`ListenerSession=Y` on Logon and a separate read-only API key. They deliver ExecutionReports for
new orders, fills, cancels and replaces, and reject every order-sending message `[P KF-LISTEN]`.
They are an execution-report feed and have nothing to do with market data.

### 3.9 How you get access

`[P KF-COMMON]`: **"Premier tier members have FIX access by default; other tiers should contact
institutional@kalshi.com"**. Premier is the 1,000/1,000 token tier, reached by trading volume or
by manual assignment `[P K-RATE]`.

Some sessions carry an extra requirement: `KalshiRT` "requires institutional access" and
`KalshiPT` is "institutional only" `[P KF-CONN]`. **`KalshiMD`, the market data session, carries
no such note**, so on published information market data appears to be available to any
FIX-enabled account.

AWS PrivateLink is available for network-level isolation, requested through the same
institutional address, with **Premier tier as the stated minimum** `[P KF-CONN]`; the production
hosts covered are `external-api.kalshi.com` and `external-api-ws.kalshi.com` `[P K-ENV]`.

On **agreements and minimum volume**: the FIX documentation states no agreement requirement, no
minimum volume and no approval process for FIX itself beyond the tier `[P KF-AUTH]`. Market
maker status is a separate thing, granted "following a thorough review of financial resources,
trading experience, and business reputation" with ongoing liquidity obligations, and the help
centre does not publish concrete thresholds `[P K-MM]`. **Whether a written agreement is
required in practice is NOT DOCUMENTED and I could not verify it.** Anyone told otherwise by a
blog post is reading marketing.

### 3.10 The dictionary gap: a verified, practical finding

Kalshi publishes a QuickFIX-style data dictionary at
`https://assets.kalshi.com/fix/kalshi-fix-dictionary.xml` `[P KF-COMMON]`. I downloaded and
inspected the complete file rather than relying on a summary `[OBS]`: HTTP 200, 35,549 bytes,
header comment `Kalshi FIX Dictionary v1.03`, root `<fix type='FIXT' major='1' minor='1'
servicepack='0'>`, 143 field definitions and 34 message definitions.

**None of the 34 messages is a market-data message.** The dictionary defines the seven admin
messages (Heartbeat, TestRequest, ResendRequest, Reject, SequenceReset, Logout, Logon) and 27
application messages covering orders, quotes/RFQ, order groups, market settlement and the U1/U2/U3
event-resend family. A search for `MarketDataRequest`, `MDEntryType`, `MDUpdateAction`,
`MDEntryPx`, `NoMDEntries`, `SubscriptionRequestType` and `AggressorSide` returns **zero
occurrences of each** `[OBS]`.

The practical consequence for anyone actually building this: **you cannot point a FIX engine at
Kalshi's published dictionary and receive market data.** The 35=V/W/X/Y messages and their tags
are documented in prose only. You must merge the standard FIX50SP2 market-data definitions with
Kalshi's custom fields yourself and validate the result against the demo `KalshiMD` session.
That is a half-day of unglamorous work that no tutorial mentions, and it is a very good concrete
answer to "what was hard about it".

### 3.11 What latency advantage FIX actually gives

This is where most published material becomes unreliable, so here is what is defensible.

**What Kalshi documents:** nothing. I found **no published latency figures of any kind** in
Kalshi's developer documentation, and no claim that FIX is faster than WebSocket. The
connectivity page discusses transport, ports, TLS and rate limits, and never mentions latency
`[P KF-CONN]`. Any specific millisecond number attributed to Kalshi's docs should be treated as
fabricated until someone shows the page (see section 7).

**What is structurally true**, independent of venue, and defensible in an interview:

1. **Encoding and parsing.** FIX tag-value is cheaper to parse than JSON: no string allocation
   for keys, no unescaping, fixed field ordering, and numeric tags. On a busy book feed this is
   a real but modest saving, typically microseconds per message, and it matters mainly because
   it reduces jitter and GC pressure rather than mean latency.
2. **Framing.** One long-lived TCP session with no HTTP semantics per message, versus WebSocket
   framing over an HTTP-upgraded connection. The difference is small; both are persistent TCP.
3. **Network path.** This is the part that actually dominates, and it is not really about FIX.
   Kalshi offers AWS PrivateLink, so traffic stays on the AWS backbone rather than traversing
   the public internet `[P KF-CONN]`. PrivateLink is documented for the REST and WebSocket hosts
   too `[P K-ENV]`, so **the private path is not exclusive to FIX**. Proximity to the matching
   engine is worth far more than protocol choice: my own measurements from Central Europe gave
   a median REST round trip of **381 ms to Kalshi** and **52 ms to Polymarket** `[OBS]`, and no
   protocol change closes a 380 ms geographic gap.
4. **What FIX does not buy you here.** On `KalshiMD` specifically, FIX gives you **no
   retransmission** and mandates a sequence reset on every Logon `[P KF-MD]`, `[P KF-ERR]`. So
   the recovery advantage that normally justifies FIX for market data does not apply to Kalshi's
   market-data session. You get standard framing and session semantics, not replay.

**Honest conclusion:** for market data on Kalshi, FIX is a modest constant-factor improvement in
parsing and framing plus access to a session model your infrastructure may already speak. It is
not an order-of-magnitude latency win over the WebSocket, and the documentation makes no such
claim. The large wins available are geographic (colocation or PrivateLink in the right region)
and architectural (not blocking the read loop), both of which apply equally to the WebSocket.
For order entry the calculus differs, because the FIX order-entry sessions offer retransmission
and drop copy that the REST path does not.

### 3.12 Open questions on FIX that published docs do not answer

- Whether `MDEntryPx` (270) honours `UseDollars` (21005) on `KalshiMD` (section 3.6).
- Whether the FIX book is a true two-sided book or the two-bid-ladder convention.
- Any latency figures, SLAs or jitter characteristics.
- Any market-data-specific rate limit. The connectivity page states application messages consume
  tokens matching REST equivalents, and that order entry and RFQ draw on the Write bucket
  `[P KF-CONN]`, but does not say what a MarketDataRequest costs.
- Whether a written agreement is required in practice for FIX access.
- Maximum number of symbols per MarketDataRequest, or per `KalshiMD` session.

---

## 4. Practical comparison: when to use what

| Dimension | REST | WebSocket | FIX (Kalshi only) |
| --- | --- | --- | --- |
| **Latency** | Round trip per query. Measured median 52 ms Polymarket, 381 ms Kalshi from Central Europe `[OBS]`. Polling adds up to one full interval of staleness on top. | Push. Bounded by network plus venue fanout. The only realistic choice for sub-second reaction. | Push. Marginally cheaper parsing and framing than WS; dominated by geography. No published figures. |
| **Completeness** | Snapshots only. No deltas, no lifecycle events, no `best_bid_ask`, no tick-size changes. Kalshi allows full depth (`depth` up to 100); Polymarket has no depth parameter at all. | Full event stream. Both venues expose events with no REST equivalent. Kalshi additionally exposes lifecycle, positions, fills and index feeds. | Book snapshots and incrementals plus security status. Order entry, drop copy, post-trade and RFQ on separate sessions. |
| **Recovery** | Trivially stateless: retry the call. This is REST's one genuine advantage and the reason it stays in the architecture as a reconciliation path. | Polymarket: **no sequence numbers, gaps undetectable**, but a full `book` arrives after every trade. Kalshi: `seq` on the book channel, **no documented recovery**, `get_snapshot` available. | Session-layer resend exists in FIX generally, but **`KalshiMD` does not support retransmission** and forces a seqnum reset on every Logon. Application-level replay (U1/U2/U3) exists on drop copy only, three-hour window, reconcile by ExecID. |
| **Operational complexity** | Lowest. HTTP client and a scheduler. | Moderate. Long-lived connections, heartbeats (opposite conventions per venue), reconnect with backoff, book state machines with opposite update semantics, staleness watchdogs. | Highest. A FIX engine, a dictionary you must extend yourself because the published one has no market-data messages `[OBS]`, sequence-number persistence, TLS with cipher constraints, one connection per key, and demo-environment certification before you trust anything. |
| **Credential risk** | Polymarket market data: none, fully public. Kalshi market data: none for REST, also public `[OBS]`. | Polymarket market channel: none. **Kalshi: an API key is required even for public data**, so a read-only feed forces you to hold a signing key. | Always credentialed. Same RSA key pair as REST. Order-entry sessions sit behind the same credential as market data unless you provision separate keys. |
| **Rate limiting** | Polymarket: per **IP**, throttled not rejected, so overuse shows up as latency. Kalshi: per **authenticated request**, token buckets by tier, clean 429. | Polymarket: **NOT DOCUMENTED**. Kalshi: **NOT DOCUMENTED** numerically; error 25 signals buffer overflow, 26 a market-count cap, 27 a command rate limit. | Consumes the same token buckets as REST; Logon is rate-limited, Heartbeat/TestRequest/Logout are not; MassCancel capped at 1/s. |
| **Use it when** | Discovery, metadata, backfill, and as the independent reconciliation source against a streamed book. Also the correct choice for anything where a 2-minute cadence genuinely suffices. | Default for all live market data on both venues. Everything time-sensitive belongs here. | You are already Premier tier, already run a FIX engine, and need order entry with drop copy and retransmission. **Not justified for market data alone** on current published information. |

**The decision in one line:** WebSocket for the live path, REST for discovery and for an
independent truth source to reconcile against, FIX only when order entry and institutional
post-trade requirements pull you there. Anyone who proposes FIX for market data on a
latency argument should be asked for the number.

---

## 5. What a trading firm expects you to know

### 5.1 Concepts

- **Session layer versus application layer**, and why FIX separates them while REST and
  WebSocket do not. What `BeginString` versus `DefaultApplVerID` implies about FIX 5.x.
- **Snapshot plus delta book maintenance**, and the two incompatible delta conventions:
  absolute level replace (Polymarket `price_change`, Kalshi FIX `MDUpdateAction=Change`) versus
  additive change (Kalshi WebSocket `delta_fp`). Being able to name a venue for each is the
  difference between having read about this and having built it.
- **Aggregated versus order-level (MBP versus MBO)** feeds. Both venues publish aggregated
  books; neither exposes resting-order identity or queue position publicly. Know what you
  therefore cannot compute: true queue position, order-level lifetime, individual maker
  behaviour before a fill.
- **Sequence numbers as the only reliable loss detector**, why per-connection, per-subscription
  and per-instrument scoping produce very different recovery logic, and what you do when a venue
  provides none.
- **Conflation.** Venues that coalesce updates give you a correct book but a lossy event
  history. Kalshi's `ticker` channel updates "whenever any ticker field changes"; the book
  channel is the unconflated one. Know which of your metrics survives conflation and which
  does not (realized spread, yes; per-order flow, no).
- **Time.** Exchange timestamp versus receive timestamp, and the fact that Polymarket does not
  document which of the two its `timestamp` is `[P P-WSMKT]`. Never compute latency from a field
  whose provenance is undocumented.
- **Idempotency and client order IDs**, `PossDupFlag` and `OrigSendingTime` on FIX replay, and
  why a resent message must not be processed as a new event.

### 5.2 Failure modes and the standard mitigations

**Sequence gap.** A message is missing; the local book silently diverges from the venue.
*Mitigation:* check every sequence number and treat a gap as invalidating, not as a warning.
Mark affected books untrusted, stop emitting derived data immediately, and re-snapshot.
The important discipline is that a book you cannot vouch for must produce **no output at all**
rather than plausible-looking output. Where the venue offers no sequence number (Polymarket),
you need an out-of-band check instead: periodic REST reconciliation, and the `hash` field as a
cheap change detector.

**Slow consumer.** Your reader falls behind, the venue's send buffer fills, and the venue either
drops data or disconnects you. This is the most common cause of production data loss and the one
juniors rarely mention. *Mitigation:* never do work on the socket-read thread. Read into a
bounded queue, process elsewhere, and instrument queue depth as a first-class metric. Decide
explicitly what to shed under pressure and make shedding visible. Kalshi surfaces this directly
as error 25, "Subscription buffer overflow [...] ensure that your connection read throughput is
optimized" `[P K-WSCONN]`, and its remedy of subscribing to fewer markets is the right
structural answer: fan out across connections rather than widening one.

**Silent disconnect / half-open connection.** TCP believes the connection is alive; no data
flows. A firewall or NAT dropped the flow, or the venue stopped publishing. *Mitigation:*
heartbeats plus a **data-inactivity watchdog**, and understand that these are different checks.
A heartbeat proves the socket is alive; only data flow proves the feed is alive. Polymarket's
documented silent-freeze reports are exactly this class: connection open, ping/pong working,
zero events for hours `[S P-ISSUE292]`. Reconnect on data silence, not only on socket error, and
use exponential backoff with jitter to avoid synchronized reconnect storms.

**Clock skew.** Signed requests and timestamped events both break. Kalshi rejects any FIX message
whose `SendingTime` is more than 30 seconds from server time, with
`SessionRejectReason=10`, and recommends NTP explicitly `[P KF-ERR]`, `[P KF-COMMON]`. The
WebSocket and REST signatures are also timestamped. *Mitigation:* run NTP or better, monitor
offset as a metric rather than assuming it, and measure your skew against the venue rather than
against a public pool: Polymarket exposes `GET /time` and Kalshi exposes an exchange status
endpoint. A live check showed the Polymarket book `timestamp` 405 ms ahead of local time
`[OBS]`, which is a mixture of genuine skew and one-way network delay and illustrates why you
cannot separate the two from a single sample.

**Snapshot-versus-delta race.** Deltas that arrive while the initial snapshot is in flight are
either lost or applied to a stale base. *Mitigation:* the standard pattern is to buffer incoming
deltas from the moment you subscribe, apply the snapshot when it lands, then replay buffered
deltas whose sequence exceeds the snapshot's. **Neither venue documents the ordering guarantee
that makes this sound.** Kalshi at least numbers snapshot and delta in one `seq` series, which
makes the pattern implementable; Polymarket does not, so the honest answer there is to treat the
snapshot as authoritative on arrival and accept a small window of uncertainty, then rely on the
post-trade re-snapshot to converge.

**Crossed or locked book.** Best bid at or above best ask after applying updates. Almost always a
symptom of one of the above, not a real market state. *Mitigation:* assert on it, and treat a
persistent cross as a resync trigger rather than something to clamp away.

**Duplicate delivery.** FIX replay delivers messages you already processed, marked
`PossDupFlag=Y`. Kalshi's application-level resend goes further: resent messages get **new**
sequence numbers, so deduplication must key on `ExecID` `[P KF-DC]`. *Mitigation:* idempotent
handlers keyed on a business identifier, never on arrival order.

**Silent schema or semantics migration.** The failure mode nobody lists, and the one that
actually costs research data. Kalshi has announced that `use_yes_price` will flip its default
from `false` to `true`, changing the price scale of one side of the book, with dates to be
announced later `[P K-ORDDIR]`. Nothing breaks; the numbers just quietly change meaning.
*Mitigation:* pin every optional protocol flag explicitly rather than relying on defaults, and
alert on shape changes (unexpected fields, disappeared fields, distribution shifts in prices)
rather than only on errors.

**Venue maintenance mistaken for an outage.** Kalshi disconnects sessions every Thursday 03:00
to 05:00 ET by design `[P K-MAINT]`. *Mitigation:* encode the schedule so monitoring suppresses
alerts and the recorder resumes cleanly.

### 5.3 Answers that land well

Interviewers are generally probing whether you have operated a feed, not whether you can recite
one. Three things read as real experience:

- Naming a specific failure you detected and how you detected it, especially one that was silent.
- Knowing what your data **cannot** answer. Aggregated books mean no true queue position; a
  120-second REST poll cannot measure quote lifetime; a gap-invalidated book must produce no
  rows rather than plausible ones.
- Distinguishing what the docs say, what you inferred, and what you measured. Saying "Kalshi
  does not document the scope of `seq`; I inferred per-subscription from the schema layout and
  then confirmed it empirically" is a much stronger answer than asserting it as fact.

---

## 6. Concrete next steps for this repository

Current state: `src/book_stream.py` (Polymarket CLOB WebSocket, public), `src/kalshi_stream.py`
plus `src/kalshi_stream_state.py` (Kalshi WebSocket, authenticated read-only),
`src/kalshi_recorder.py` and `src/book_recorder.py` (REST pollers, 120 s), and
`app/kalshi_auth.py` (RSA-PSS signing that refuses anything but GET and blocks order paths).

The existing code is in better shape than most of what is written about these APIs. Verified
correct against primary docs: Polymarket `price_change` is applied as an assignment
(`apply_change` overwrites, zero deletes) which matches "New aggregate size"; Kalshi `delta_fp`
is applied additively which matches "contract delta"; Kalshi's `no` ladder is reflected through
`1 - p`; `yes_dollars_fp` / `no_dollars_fp` / `price_dollars` / `delta_fp` / `count_fp` field
names match the current fixed-point schema; both REST parsers sort explicitly rather than
indexing, which sidesteps the Polymarket sort-order contradiction entirely; and
`websocket-client` 1.9.0 auto-answers Kalshi's protocol ping frames inside `recv_data_frame`,
so the Kalshi stream does not have a heartbeat bug `[OBS]`.

Ordered by value.

**1. Set `use_yes_price: true` explicitly in the Kalshi subscription. Highest value, and it is
a scheduled time bomb.**
`subscribe_message` in `src/kalshi_stream.py` does not send the flag, so it relies on the
current default of `false`. `kalshi_stream_state.py` correctly reflects the NO ladder through
`1 - p` on that assumption. When Kalshi flips the default to `true` `[P K-ORDDIR]`, no-side
prices arrive already in YES space, the reflection becomes wrong, and **every ask, spread and
mid silently inverts with no error and no gap**. Existing CSV history would not be retroactively
wrong, but new rows would be, and the transition would be invisible in the status JSON. Send the
flag explicitly, decide which convention the state machine expects, and add a test that fails if
a NO level ever arrives outside the expected range. This is roughly an hour of work against an
unbounded silent-corruption risk.

**2. Fix the post-gap deadlock in the Kalshi stream.**
`StreamState.check_seq` marks every book broken on a gap and sets `needs_resync`, but
`stream_once` never acts on it: `needs_resync` is written and never read, and Kalshi only sends
`orderbook_snapshot` at subscribe time. So after a single sequence gap, **no book recovers until
the connection cycles**, which with the default `duration_s = 600` is up to ten minutes of
recorded silence from one dropped message. The fix is the documented-but-never-labelled recovery
path: send `{"cmd":"update_subscription","params":{"sids":[sid],"action":"get_snapshot",
"market_tickers":[...]}}` `[P K-WSOB]`. Track the `sid` from the `subscribed` confirmation,
which the code currently discards. Small change, large behavioural difference, and it makes the
existing gap accounting actually useful.

**3. Separate liveness from data staleness in both streams.**
`kalshi_stream.py` breaks the loop after `STALE_AFTER_S = 90` seconds without a **data** frame.
Because `websocket-client` consumes Kalshi's 10-second protocol pings internally and does not
surface them `[OBS]`, `last_message` never advances on heartbeats. A genuinely quiet market
therefore triggers a needless reconnect and a full re-discovery cycle. Track two clocks: last
frame of any kind (liveness, from the pong path) and last data frame (staleness), and report
both in the status JSON. On the Polymarket side, keep the 90-second data watchdog exactly as it
is, because the documented silent-freeze reports are precisely what it defends against
`[S P-ISSUE292]`; just record the distinction so the status file says which condition fired.

**4. Handle `exchange_index` before 6 August 2026.**
Kalshi begins sharding combos onto shard 1 on that date `[P K-SHARD]`, and `exchange_index` is
already present on live event and market objects `[OBS]`. Nothing in `kalshi_recorder.py` or the
stream reads it. Capture it in discovery, carry it into the recorded rows, and record it in
trades. Even if the current market selection never touches combos, having the column from before
the migration is what makes any later cross-shard latency question answerable. Cheap now,
impossible to backfill.

**5. Build a book-reconciliation harness. This is the highest-value new component.**
Polymarket gives you no sequence numbers, so correctness of the streamed book is currently an
assumption. Add a module (streamlit-free, in `src/`, with `tests/test_<modul>.py` per repo
convention) that periodically pulls REST `/book` for a sampled subset of streamed tokens and
compares top-of-book and top-N depth against the in-memory state, recording a divergence time
series rather than just asserting. Two things make this cheap: `/book` is rate-limited at 1,500
requests per 10 seconds `[P P-RATE]`, which is enormous relative to a sampling reconciler, and
the `hash` field lets you skip comparisons when the book has not changed `[P P-POB]`. The same
harness works on Kalshi against `GET /markets/{ticker}/orderbook`, where it doubles as an
independent check on the additive-delta logic. Beyond correctness, **a measured divergence rate
is a genuinely interesting research output** and is exactly the kind of artifact that survives
interview scrutiny, because it converts "I think my book is right" into a number.

**6. Turn the `seq` scope assumption into a measurement.**
`kalshi_stream_state.py` documents, persuasively, that the counter is per subscription rather
than per market. Kalshi does not document this `[P K-WSOB]`. Run a short instrumented session
that subscribes to several markets on one `sid` and logs `(sid, seq, market_ticker)`, then write
up whether the counter is contiguous across markets, whether it resets on resubscribe, and
whether a second subscription gets an independent series. This closes an open question in the
codebase's own docstring, costs one recording session, and produces a documented finding on a
question the venue leaves unanswered.

**7. Instrument latency and clock skew as first-class outputs.**
Both stream recorders already write `recv_ts`; Kalshi trades carry `ts_ms` and Polymarket
messages carry `timestamp`. Persist the difference. Add a periodic skew probe against
Polymarket's `GET /time` and Kalshi's exchange status. Two caveats to state in any report:
Polymarket does not document whether its `timestamp` is matching time or send time
`[P P-WSMKT]`, so the difference is an upper bound on feed latency and not a clean measurement;
and a single-sample skew figure mixes clock offset with one-way delay `[OBS]`.

**8. Migrate to the recommended Kalshi hosts.**
`src/kalshi_recorder.py` uses `https://api.elections.kalshi.com/trade-api/v2` and
`src/kalshi_stream.py` uses `wss://api.elections.kalshi.com/trade-api/ws/v2`. Both are the legacy
"also supported" hosts; the recommended ones are `external-api.kalshi.com` and
`external-api-ws.kalshi.com` `[P K-ENV]`. The signature payload is unaffected because the host
does not enter it, and the recommended REST host returned HTTP 200 unauthenticated on the first
try `[OBS]`, so this is a constant change plus a test run. Low effort, removes a deprecation
risk, and is a prerequisite for PrivateLink should that ever become relevant.

**9. Correct the stale docstring in `src/kalshi_recorder.py`.**
It states "The Kalshi WebSocket requires an API key and this repo does not handle credentials,
so the feed here is REST polling". That has been false since `app/kalshi_auth.py` and
`src/kalshi_stream.py` landed. Given the repo's stated policy of stating limitations in every
report rather than assuming them away, a docstring that misdescribes the system's own
capabilities is worth more than a typo fix.

**10. Consider a read-only `KalshiMD` FIX spike, explicitly as an interview artifact.**
Not because the repository needs FIX market data (it does not, per section 4), but because a
working `KalshiMD` client is a disproportionately strong signal and almost nobody has built one.
Scope it honestly before starting: it needs Premier tier or an institutional conversation
`[P KF-COMMON]`, and it needs you to extend the published dictionary yourself because that
dictionary contains no market-data messages at all `[OBS]`. Do it on the demo host
(`marketdata.fix.demo.kalshi.co:8233`) first, and use it to answer the two questions section
3.12 leaves open: whether `MDEntryPx` honours `UseDollars`, and whether the FIX book is
two-sided or two bid ladders. Both are unanswerable from public documentation, which is exactly
what makes measuring them worth something.

**Deliberately not recommended:** unifying the two book state machines behind one abstraction.
The update semantics are opposite (section 2.3), and the shared-interface version of this code
would be harder to verify than two explicit ones. The current separation is correct.

---

## 7. Claims encountered that do not survive checking

The brief asked for low-quality material to be flagged. These all appeared in ordinary search
results for these APIs.

| Claim | Source | Verdict |
| --- | --- | --- |
| "Kalshi's FIX 4.4 protocol is specifically designed for the lowest-latency order management" | `[S S-NYCS]`, surfaced via search summary | **False.** Kalshi runs FIXT.1.1 with FIX50SP2 `[P KF-CONN]`, `[P KF-COMMON]`, verified in the published dictionary root element `[OBS]`. FIX 4.4 has a materially different session/application versioning model. |
| "The REST API's 50-200ms baseline latency quoted in Kalshi's developer documentation" | `[S S-TRADOX]`, surfaced via search summary | **Unverifiable, and the attribution appears fabricated.** I found no latency figures anywhere in Kalshi's developer documentation. The number is presented as a quotation from a source that does not appear to contain it. |
| "Professional market makers target sub-10ms total latency" | `[S S-TRADOX]` | Plausible as a general industry statement, but it is vendor content on a VPS sales page and carries no measurement or citation. Not usable as evidence for anything. |
| Kalshi FIX documentation is not public / requires an institutional agreement to read | implied by several secondary pages | **False.** Twelve public pages under `docs.kalshi.com/fix/` plus a downloadable dictionary `[P K-LLMS]`, `[P KF-COMMON]`. Access to the *sessions* is tier-gated; the *documentation* is not. |
| Polymarket order book bids are sorted descending | `[P P-OB]`, the venue's own OpenAPI spec | **Contradicted by the venue's own prose page** `[P P-POB]` and by live data `[OBS]`. Even primary sources conflict here; measurement settled it. |

A general note on the genre: several of the highest-ranking "Kalshi API guide" and "Polymarket
API guide" pages are affiliate or lead-generation content for VPS, proxy and backtesting
products, and read as though assembled from model output. They reliably get the shape of an API
right and the specifics wrong, which is the worst possible failure mode because it is
superficially checkable and wrong in the details. **Everything in sections 1 to 3 of this
document is sourced to venue documentation, a venue-published artifact, or a first-hand
measurement, and nothing was taken from that class of source.**

---

## 8. Source register

**PRIMARY: Kalshi**

| Key | URL |
| --- | --- |
| `K-LLMS` | https://docs.kalshi.com/llms.txt |
| `K-ENV` | https://docs.kalshi.com/getting_started/api_environments.md |
| `K-RATE` | https://docs.kalshi.com/getting_started/rate_limits.md |
| `K-PAGE` | https://docs.kalshi.com/getting_started/pagination.md |
| `K-OBRESP` | https://docs.kalshi.com/getting_started/orderbook_responses.md |
| `K-ORDDIR` | https://docs.kalshi.com/getting_started/order_direction.md |
| `K-FP` | https://docs.kalshi.com/getting_started/fixed_point_migration.md |
| `K-SHARD` | https://docs.kalshi.com/getting_started/exchange_sharding.md |
| `K-MAINT` | https://docs.kalshi.com/getting_started/maintenance_and_pauses.md |
| `K-HIST` | https://docs.kalshi.com/getting_started/historical_data.md |
| `K-QSWS` | https://docs.kalshi.com/getting_started/quick_start_websockets.md |
| `K-OB` | https://docs.kalshi.com/api-reference/market/get-market-orderbook.md |
| `K-WS` | https://docs.kalshi.com/websockets.md |
| `K-WSCONN` | https://docs.kalshi.com/websockets/websocket-connection.md |
| `K-WSOB` | https://docs.kalshi.com/websockets/orderbook-updates.md |
| `K-WSTRADE` | https://docs.kalshi.com/websockets/public-trades.md |
| `K-WSTICK` | https://docs.kalshi.com/websockets/market-ticker.md |
| `K-WSKA` | https://docs.kalshi.com/websockets/connection-keep-alive.md |
| `K-MM` | https://help.kalshi.com/en/articles/13823819-how-to-become-a-market-maker-on-kalshi |
| `KF-CONN` | https://docs.kalshi.com/fix/connectivity.md |
| `KF-AUTH` | https://docs.kalshi.com/fix/authentication.md |
| `KF-COMMON` | https://docs.kalshi.com/fix/common-components.md |
| `KF-MD` | https://docs.kalshi.com/fix/market-data.md |
| `KF-OE` | https://docs.kalshi.com/fix/order-entry.md |
| `KF-ERR` | https://docs.kalshi.com/fix/error-handling.md |
| `KF-DC` | https://docs.kalshi.com/fix/drop-copy.md |
| `KF-LISTEN` | https://docs.kalshi.com/fix/listener-sessions.md |
| `KF-SUB` | https://docs.kalshi.com/fix/subpenny-pricing.md |
| `KF-DICT` | https://assets.kalshi.com/fix/kalshi-fix-dictionary.xml |

**PRIMARY: Polymarket**

| Key | URL |
| --- | --- |
| `P-SDK` | https://docs.polymarket.com/getting-started/sdks-apis.md |
| `P-RATE` | https://docs.polymarket.com/api-reference/rate-limits.md |
| `P-TRATE` | https://docs.polymarket.com/api-reference/trading-rate-limits.md |
| `P-OB` | https://docs.polymarket.com/api-reference/market-data/get-order-book.md |
| `P-POB` | https://docs.polymarket.com/market-data/prices-order-books.md |
| `P-DISC` | https://docs.polymarket.com/market-data/discover-markets.md |
| `P-KEYSET` | https://docs.polymarket.com/api-reference/markets/list-markets-keyset-pagination.md |
| `P-TRADES` | https://docs.polymarket.com/api-reference/core/get-trades-for-a-user-or-markets.md |
| `P-RT` | https://docs.polymarket.com/market-data/realtime-data.md |
| `P-WSMKT` | https://docs.polymarket.com/api-reference/wss/market.md |
| `P-WSUSER` | https://docs.polymarket.com/api-reference/wss/user.md |
| `P-WSRFQ` | https://docs.polymarket.com/api-reference/wss/rfq.md |
| `P-WSSPORT` | https://docs.polymarket.com/api-reference/wss/sports.md |
| `P-RTORD` | https://docs.polymarket.com/trading/realtime-order-updates.md |
| `P-AUTH` | https://docs.polymarket.com/trading/wallets-auth.md |
| `P-ME` | https://docs.polymarket.com/trading/matching-engine.md |
| `P-CONC` | https://docs.polymarket.com/concepts/prices-orderbook.md |

**SECONDARY**

| Key | URL | Note |
| --- | --- | --- |
| `P-ISSUE292` | https://github.com/Polymarket/py-clob-client/issues/292 | User bug report in the vendor's repo. Credible and detailed, but not venue documentation and unanswered by maintainers. |
| `S-NYCS` | https://newyorkcityservers.com/blog/prediction-market-making-guide | Vendor content. Contains a false FIX version claim. |
| `S-TRADOX` | https://tradoxvps.com/why-kalshi-traders-need-a-1ms-vps-in-chicago/ | VPS sales page. Contains an apparently fabricated documentation attribution. |
| `S-ZUPLO` | https://zuplo.com/learning-center/kalshi-api | Lead-generation content. Not relied on for any claim here. |
| `S-APIDOG` | https://apidog.com/blog/kalshi-api-devolpers-guide/ | Lead-generation content. Not relied on for any claim here. |

**`[OBS]` first-hand observations, 2026-07-31, client in Central Europe**

All read-only, all public endpoints, all reproducible:

- Kalshi `GET /events` and `GET /markets/{ticker}/orderbook` on `external-api.kalshi.com`
  returned HTTP 200 **without authentication**; `exchange_index` present on both event and
  market objects; `orderbook_fp` with `yes_dollars` / `no_dollars` string pairs confirmed.
- Kalshi WebSocket handshake **without** auth headers returned **HTTP 401 Unauthorized** on both
  `external-api-ws.kalshi.com` and `api.elections.kalshi.com`.
- Polymarket `GET /book` returned the ten documented fields; `hash` was 40 lowercase hex
  characters with **no `0x` prefix**; **no sequence-like field of any kind**; bids ascending and
  asks descending, confirming the prose page against the OpenAPI spec.
- Polymarket book `timestamp` (ms) was 405 ms ahead of local clock; `GET /time` returns Unix
  seconds.
- REST round trip, 8 samples each: Kalshi orderbook min 361 / median 381 / max 398 ms;
  Polymarket book min 48 / median 52 / max 77 ms.
- Kalshi FIX dictionary: HTTP 200, 35,549 bytes, `Kalshi FIX Dictionary v1.03`,
  `<fix type='FIXT' major='1' minor='1' servicepack='0'>`, 143 field definitions, 34 message
  definitions, **zero market-data messages or fields**.
- `websocket-client` 1.9.0 `WebSocket.recv_data_frame` auto-sends Pong on receiving a Ping and
  does not surface the frame to the caller by default.
