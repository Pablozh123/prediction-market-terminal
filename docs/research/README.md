# Microstructure research — Polymarket and Kalshi

Own recorders, own tooling, read-only. Every number below was produced by a module
in this repository with unit tests behind it, from data this project recorded
itself. Nothing here is a backtest over someone else's dataset.

**Read this first:** [ONE_PAGER.md](ONE_PAGER.md) — the whole strand on one page,
written for someone who has not seen the repo.

No profitability claim is made anywhere in this work.

## How the data is collected

Four recorders run continuously across both venues: REST pollers on a 120-second
grid, and event-driven WebSocket recorders that write on every top-of-book change
at sub-second median gaps. The Kalshi socket is authenticated but read-only by
construction — [`app/kalshi_auth.py`](../../app/kalshi_auth.py) signs `GET` only and
refuses every order and portfolio path, so a credential with trading rights still
cannot trade through this code.

## The studies

| Question | Data | Verdict | Report | Module |
|---|---|---|---|---|
| Does book imbalance predict direction? | 205,835 firings at a five-minute horizon with no decision delay, 11 days, 370,423 snapshots. Four further horizon/delay cells are reported separately, never pooled (summed they would read 1,011,556, more observations than snapshots) | Yes. 55.5% hit rate, Wilson lower bound 55.2% | [order flow](orderflow_rest-2026-07.md) | [`src/orderflow_study.py`](../../src/orderflow_study.py) |
| Can it be taken as a taker? | same cell, net of both cost legs | No. Mean gross edge +0.09 cents per firing (+0.03 to +0.13 across the five cells) against a 2.58 cent round trip (0.938 spread, 1.646 fee) | [order flow](orderflow_rest-2026-07.md) | [`app/venue_fees.py`](../../app/venue_fees.py) |
| Is signed order flow a signal? | 93,868 firings at the same five-minute, no-delay cell | No. 51.7% hit rate, Wilson lower bound 51.3%, and gross edge already negative | [order flow](orderflow_rest-2026-07.md) | [`src/orderflow_study.py`](../../src/orderflow_study.py) |
| Does any segment rescue the signal? | 205,835 firings, 34 ex-ante cuts, 3 fee scenarios | No. Exactly one cut survives in and out of sample, and its day-resampled CI contains zero — the expected false-positive count at 34 tests | [segments](edge_segments_july-2026.md) | [`src/edge_segments.py`](../../src/edge_segments.py) |
| Does market making carry at a 120s requote? | 4,519 tokens, 12 days | No. Adverse selection takes 362 cents per fill against 148 cents of spread earned in the tape fill model (698 against 133 in the touch model) | [MM decomposition](mm_pnl_july-2026.md) | [`src/mm_pnl.py`](../../src/mm_pnl.py) |
| Is the binding constraint spread width or staleness? | 468 tokens, 5,413,998 streamed snapshots, 5 days | Staleness. Same code and parameters on seconds data, tape fill model: markout per fill falls from 362 to 70 cents while spread earned barely moves, 138 against 148 | [MM on seconds data](mm_pnl_stream-5tage.md) | [`src/mm_pnl.py`](../../src/mm_pnl.py) |
| Does market making pay, once the bootstrap can run? | same 5 days, daily block bootstrap | Not identified. The two fill models land on opposite sides of zero and neither interval touches it: touch (-12,121, -2,413) USD per day, tape (+881, +5,889). Queue position, not more data, is what would settle it | [MM on seconds data](mm_pnl_stream-5tage.md) | [`src/mm_pnl.py`](../../src/mm_pnl.py) |
| Are cross-venue gaps arbitrage? | 300 Polymarket against 600 Kalshi markets, both fee curves subtracted | No, carry. 3 of 5 verified pairs clear both fee curves, best 3.07 cents, all settling 2027 or 2028 — 0.5 to 1.8% annualised | [cross-venue gaps](cross_venue_gaps_2026-07-31.md) | [`src/cross_venue_gaps.py`](../../src/cross_venue_gaps.py) |
| How long does a gap stay open? | both stream recorders, 11.6 hours | 3 of 5 pairs were open at every moment observed. They do not close because they are not mispricings | [gap lifetime](gap_lifetime_2026-07-31.md) | [`src/gap_lifetime.py`](../../src/gap_lifetime.py) |
| Are the large reward pools free money? | 9,900 markets carrying a pool, 164,661 USD per day, snapshot of 2026-07-31 | No. 14 of the 45 largest have a completely empty qualifying band, paying 250 to 1,475 USD a day — and quote 1 to 64 cents wide against a 2.5 cent band (4.5 cents on three of them) | [reward selection](reward_selection_2026-07-31.md) | [`src/reward_selection.py`](../../src/reward_selection.py) |
| Do two venues settle the same event the same way? | 5 confirmed pairs, both rulebooks side by side | No. Kalshi resolves the 2028 presidential market on who is next inaugurated, Polymarket on who wins the election. A basket over that pair loses both legs instead of hedging | [resolution rules](resolution_rules_2026-07-31.md) | [`src/resolution_rules.py`](../../src/resolution_rules.py) |
| Does the streamed book drift against the venue? | 24 tokens, 3 rounds of 120 seconds | 98.6% agreement, mean divergence 0.07 ticks, largest 2 ticks | [book reconciliation](book_reconcile_tick-2026-07-31.md) | [`src/book_reconcile.py`](../../src/book_reconcile.py) |

Two supporting documents sit alongside these: [`ertragsquellen_2026-07-31.md`](ertragsquellen_2026-07-31.md)
places the measurements against the published literature, and
[`protokolle_referenz.md`](protokolle_referenz.md) is a protocol reference for REST,
WebSocket and FIX access on both venues.

## What was discarded, and why that is in here

**Signal-conditioned quoting.** On the two-minute data total PnL improved 8% in
the tape fill model and 18% in the touch model. Markout per fill did not move at
all, minus 362 against minus 365 cents in the tape model. The gain came only
from placing fewer quotes, and losing less by trading less is not an edge. The
per-fill metric exists to catch exactly that.

**Signed order flow.** 51.7% hit rate at the same five-minute, no-delay cell,
Wilson lower bound 51.3%, gross edge negative before any cost. Published work later
explained why: trade-direction inference on Polymarket is near-random, 49.8 to
50.5% depending on method. Most third-party "smart money flow" analytics rest on
that inference.

**Two apparent cross-venue edges of 79 and 64 cents.** Both were mismatched pairs:
winning a primary compared against the margin of victory, and winning a nomination
compared against merely running for one. The matcher now compares question types
rather than words, and the rejected pairs stay in the report, because what a
mismatch looks like is the lesson.

**A two-clock liveness watchdog.** The client library answers Kalshi's protocol
pings internally and never surfaces them, so a dead socket and a quiet market look
identical from this side. The second clock would have moved in lockstep with the
first and only looked like a distinction. One honest clock replaced it.

## Silent failures found

Six defects that never crashed, never raised, and never failed a test, each of
which would have corrupted numbers while every log stayed clean. The full list is
in the [one-pager](ONE_PAGER.md); the two that generalise best:

- **Recorders watching the wrong markets.** Both streams select by volume. The
  cross-venue pairs are long-dated and thin and never rank, so zero of them had
  ever been recorded. The question the recorders existed to answer was
  unanswerable no matter how long they ran. Found by checking coverage before
  building the analyser, not after.
- **A tolerance that assumed a constant tick.** The reconciler measured divergence
  in ticks of 0.001, but Polymarket trades some markets on a cent grid and changes
  tick size at runtime. The giveaway was the shape of the numbers: every flagged
  divergence was an exact whole-cent multiple, in both directions. Drift
  accumulates and is directional; a moving market jumps by whole ticks either way.

## Reproducing

Every study is a module with a CLI. The recorder directory is the only input.

```bash
python -m src.orderflow_study --recorder-dir data/microstructure --tag rest-2026-07
```

```bash
python -m src.mm_pnl --recorder-dir data/microstructure --stream --tag stream-5tage
```

The market-making study also carries two queue-position fill models
(`queue_front`, `queue_back`) that rest orders on the tick grid, stand in
line behind the depth the recorder shows, fill partially, and lose their
place on every re-price, plus a requote-latency sweep. They are not part of
the published reports above; the stream recorder writes the depth ladder
they need (`stream_depth_<day>.csv`) from 2026-09-03 on. A run restricted to
a day window, for a parameter choice frozen on earlier days. The choice rule, test window and success threshold are fixed in
[preregistration_mm_queue_2026-09-03.md](preregistration_mm_queue_2026-09-03.md); the per-day driver is `python -m src.mm_queue_study`:

```bash
python -m src.mm_pnl --recorder-dir data/microstructure --stream --fill-models tape,queue_front,queue_back --latency 0 --day-from 2026-08-26 --day-to 2026-09-03 --tag queue-test
```

```bash
python -m unittest discover -s tests -p "test_*.py"
```

## Limits

Eleven days of two-minute data for the order-flow studies, twelve for the
market-making run, and five days of seconds data. Paper simulation
without queue position or partial fills, and that omission is now the binding
one: five days was enough to make the daily bootstrap run, and it showed the two
fill models sitting on opposite sides of zero. What separates them is queue
position, so the open question is no longer how many days but what a fill model
can be held to. Fee rates are taken from venue documentation dated 2026-07-30
and are overridable.
