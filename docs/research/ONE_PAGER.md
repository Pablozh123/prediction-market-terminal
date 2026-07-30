# Prediction-market microstructure: what I measured, and what I threw away

Own data, own tooling, read-only. Polymarket and Kalshi, July 2026. Every number
below comes from code in this repository with unit tests; the detailed reports
sit next to this file. Written in English because it exists to be read quickly
by someone who has not seen the repo.

## What was built

Two recorders and five analysis modules. A REST recorder polling both venues
every two minutes, and an event-driven recorder on Polymarket's CLOB WebSocket
that writes on every top-of-book change, median gap under one second. On top:
fee models for both venues, an order-flow study, a segmentation harness, a
market-making PnL decomposition, and a cross-venue basket calculator. 923 unit
tests.

## What was measured

**Book imbalance predicts direction.** 1,011,556 observations over 11 days.
Hit rate 55.2 percent, Wilson lower bound 55.0. Real, and far outside noise at
that sample size.

**It is not tradable as a taker.** Mean gross edge 0.07 to 0.28 cents per
signal against a 2.56 cent round trip, of which 1.65 cents is fee and 0.92 is
spread. 4.2 percent of firings end net positive.

**No segment rescues it.** 34 cuts knowable before the trade - spread, price
level, signal strength, their cross - across three fee scenarios including the
fee-free category. Exactly one survives both in-sample and out-of-sample, with
a day-resampled confidence interval containing zero. At 34 tests that is the
expected false-positive rate.

**Market making loses to adverse selection at a two-minute requote interval.**
Spread earned 1.4 cents per fill, adverse selection 3.6 to 7.0 cents. The
decomposition is an identity, not an estimate: spread capture plus markout plus
late drift reconstructs terminal mark-to-mid exactly, asserted to nine decimal
places in the tests.

**The binding constraint is staleness, not spread width.** Same code, same
parameters, run on seconds-resolution data: markout per fill falls from 361 to
4 cents. Sample so far is one hour and 273 fills, so this is a first look, not
a result. Widening the quote instead only crosses breakeven near an 8 cent half
spread, where fills collapse tenfold.

**Cross-venue gaps are carry, not arbitrage.** Live universe, both fee curves
subtracted, size capped by real depth: five verified pairs, three clear both
fee curves, best 3.07 cents. All settle in 2027 or 2028, so 0.5 to 1.8 percent
annualised against capital locked up to 830 days, plus resolution-rule risk on
both venues.

## What I threw away

**Signal-conditioned quoting.** The obvious next idea: if the signal is too
small to pay a spread for, use it to choose which side to quote. Total PnL
improved by 18 percent. Markout per fill did not move at all, minus 361 against
minus 365 cents. The gain came only from placing fewer quotes. Losing less by
trading less is not an edge, and the per-fill metric exists to catch exactly
that.

**Signed order flow as a signal.** 51.3 percent hit rate, no usable edge.
Published work later explained why: trade-direction inference on Polymarket is
near-random, 49.8 to 50.5 percent depending on method. Most third-party "smart
money flow" analytics rest on that inference.

**Two apparent cross-venue edges of 79 and 64 cents.** Both were mismatched
pairs: winning a primary compared against the margin of victory, and winning a
nomination compared against merely running for one. A basket over either is not
a hedge, it is two open bets. The matcher now compares question types rather
than words, and the rejected pairs stay in the report because what a mismatch
looks like is the lesson.

## What the literature says

Three independent studies covering 2.5 million users and 41 million trades reach
the same split this work measured: makers earn, takers lose. Two anomalies worth
not chasing are already explained - near-certainty pricing is a 3 to 7 percent
funding cost rather than mispricing, and longshot overpricing is roughly an
eighth of the spread needed to reach it.

## Limits

Eleven days of two-minute data, one hour of seconds data, one venue for the
microstructure work, paper simulation without queue position or partial fills.
The seconds finding is the most important and the thinnest; it becomes a result
only once several days allow a walk-forward split. Fee rates are taken from
venue documentation dated 2026-07-30 and are overridable.

No profitability claim is made anywhere in this work.
