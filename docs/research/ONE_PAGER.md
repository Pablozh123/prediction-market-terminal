# Prediction-market microstructure: what I measured, and what I threw away

Own data, own tooling, read-only. Polymarket and Kalshi, July 2026. Every number
below comes from code in this repository with unit tests; the detailed reports
sit next to this file. Written in English because it exists to be read quickly
by someone who has not seen the repo.

## What was built

Four recorders and eight analysis modules, all running continuously. REST
pollers on both venues at two-minute cadence, and event-driven WebSocket
recorders on both, writing on every top-of-book change at sub-second median
gaps. The Kalshi socket is authenticated read-only: the signing module refuses
anything but GET and blocks every order and portfolio path, so a credential
with trading rights still cannot trade through this code.

On top: fee models for both venues, an order-flow study, a segmentation
harness, a market-making PnL decomposition, a cross-venue basket calculator, a
gap-lifetime reconstruction, a reward-market ranker, and a book reconciler.
1,096 unit tests.

## What was measured

**Book imbalance predicts direction.** 205,835 firings over 11 days, at a five
minute horizon with no decision delay. Hit rate 55.5 percent, Wilson lower
bound 55.2. Real, and far outside noise at that sample size. The study also
runs four other horizon and delay combinations; they are reported separately
rather than pooled, because every snapshot feeds each of them and summing them
would inflate the sample past the number of snapshots it came from.

**It is not tradable as a taker.** Mean gross edge 0.09 cents per firing
against a 2.58 cent round trip, of which 1.65 cents is fee and 0.94 is spread.
3.8 percent of firings end net positive.

**No segment rescues it.** 34 cuts knowable before the trade — spread, price
level, signal strength, their cross — across three fee scenarios including the
fee-free category. Exactly one survives both in-sample and out-of-sample, with
a day-resampled confidence interval containing zero. At 34 tests that is the
expected false-positive rate.

**Market making loses to adverse selection at a two-minute requote interval.**
Spread earned 148 cents per fill, adverse selection 362 to 698 cents depending
on the fill model. The decomposition is an identity, not an estimate: spread
capture plus markout plus late drift reconstructs terminal mark-to-mid exactly,
asserted to nine decimal places in the tests.

**The binding constraint is staleness, not spread width.** Same code, same
parameters, run on seconds-resolution data over five days, 468 tokens and 5.4
million streamed snapshots: markout per fill falls from 362 to 70 cents in the
tape model, from nothing but requoting faster. Spread earned per fill barely
moves, 138 against 148 cents - the quoting did not improve, the quotes stopped
standing still.

**Whether that makes money is not identified, and five days of data is what
established it.** Below three days the daily block bootstrap cannot run at all,
which is why the earlier two-day version of this study reported the fill-model
disagreement as a caveat. With five days it runs, and it places the two models
on opposite sides of zero with neither interval touching it: touch (-12,121,
-2,413) USD per day, tape (+881, +5,889). More data did not resolve the
ambiguity, it sharpened it. The sign reported would be chosen by the fill
assumption rather than by the data, and settling it needs queue position and
partial fills, not more days. Widening the quote instead buys a better
earned-to-markout ratio at every step and collapses the fill count with it: at
an 8 cent half spread the ratio is 89 and 393 fills remain out of 18,686.

**Cross-venue gaps are carry, not arbitrage — and they prove it by staying
open.** Both fee curves subtracted, size capped by real depth: five verified
pairs, three clear both fee curves, best 3.07 cents, all settling in 2027 or
2028, so 0.5 to 1.8 percent annualised against capital locked up to 830 days.
Reconstructing the gap over time from both recorders, three of the five were
open at *every moment observed* across eleven hours. The usual account has
these windows closing in seconds. They do not close because they are not
mispricings: the gap is the price of locking capital until resolution, plus
resolution-rule risk on both venues.

**Reward pools are large where nobody wants to stand.** Measured from the
venue's own API: 9,921 markets carry a pool, 165,578 USD per day, median 4,
largest 1,770. Of the 46 largest, 17 have a completely empty qualifying band
and pay 400 to 933 dollars a day. That reads like free money until the spread
column: those books quote 4 to 64 cents wide against a 2.5 cent qualifying
band. The venue is buying liquidity that does not otherwise exist, and adverse
selection is the price.

**Two venues can price the same event and settle it differently.** All five
confirmed cross-venue pairs carry a resolution clause on one side the other
does not mention. One is substantive: Kalshi resolves the 2028 presidential
market on who is next *inaugurated*, Polymarket on who *wins the election* per
named media sources. A candidate who wins and is not inaugurated pays YES on
one venue and NO on the other, so a basket over that pair loses both legs
instead of hedging. The titles are near identical; the difference lives only in
the rule text, and that pair had passed my own mismatch screen as clean.

**The streamed book holds up, and that is now tested rather than assumed.**
Polymarket sends no sequence numbers, so a dropped update is invisible and the
book would drift silently. Reconciling against the authoritative REST book over
twenty minutes of streaming: 98.6 percent agreement, mean divergence 0.07 ticks,
the single exception two ticks. A first short run reported a perfect score and
a longer one did not, which is the reason this module records a series instead
of asserting a verdict.

## What I threw away

**Signal-conditioned quoting.** The obvious next idea: if the signal is too
small to pay a spread for, use it to choose which side to quote. On the
two-minute data total PnL improved by 18 percent while markout per fill did not
move at all, minus 361 against minus 365 cents: the gain came only from placing
fewer quotes, and losing less by trading less is not an edge. On five days of
seconds data it does not even do that much. Markout per fill gets worse, minus
82 against minus 70, and the total falls from 16,032 to 11,007 USD. The per-fill
metric exists to catch exactly this, and here it caught it twice.

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

**A two-clock liveness watchdog.** The protocol review recommended separating
liveness from data staleness. Building it showed why it cannot work here: the
client library answers Kalshi's protocol pings internally and never surfaces
them, so a dead socket and a quiet market look identical from this side. The
second clock would have moved in lockstep with the first and only looked like a
distinction. One honest clock, documented as a backstop, replaced it.

## Six silent failures, and how they surfaced

None of these crashed, raised, or failed a test. Each would have corrupted
numbers while every log stayed clean.

1. **Sequence scope.** Kalshi numbers messages per subscription, not per
   market. Tracking it per market reported a gap on almost every message.
   Found by reading raw frames against the live feed.
2. **A dated time bomb.** The subscription relied on `use_yes_price`
   defaulting to false. Kalshi has announced that default will flip, at which
   point every ask, spread and mid would have inverted with no error and no
   gap. Found by reviewing our client against the venue's own documentation.
3. **Recorders watching the wrong markets.** Both streams select by volume.
   The cross-venue pairs are long-dated and thin and never rank, so zero of
   them had ever been recorded — the question they exist to answer was
   unanswerable no matter how long the recorders ran. Found by checking
   coverage before building the analyser.
4. **A watchdog punishing the normal case.** Ninety seconds of silence ended
   the cycle and rebuilt the market selection, on markets where silence is the
   resting state.
5. **A tolerance that assumed a constant tick.** The reconciler measured
   divergence in ticks of 0.001, but Polymarket trades some markets on a cent
   grid and changes tick size at runtime. Every ordinary one-cent move on those
   markets was reported as ten ticks of drift. The giveaway was the shape of
   the numbers: eight flagged divergences, all exact whole-cent multiples, in
   both directions. Drift accumulates and is directional; a moving market jumps
   by whole ticks either way. The tick is now read off the observed prices.
6. **A pair that passed my own screen.** The mismatch detector cleared the 2028
   presidential pair because the titles matched and no keyword tripped. Only
   reading both rulebooks showed that one settles on inauguration and the other
   on winning. A screen that finds nothing has not cleared anything.

## What the literature says

Three independent studies covering 2.5 million users and 41 million trades reach
the same split this work measured: makers earn, takers lose. Two anomalies worth
not chasing are already explained — near-certainty pricing is a 3 to 7 percent
funding cost rather than mispricing, and longshot overpricing is roughly an
eighth of the spread needed to reach it. On Kalshi's FIX access: the published
dictionary defines 34 messages and none of them are market data, so a FIX engine
pointed at the venue's own dictionary receives nothing without extending it.

## Limits

Eleven days of two-minute data, five days of seconds data, paper simulation
without queue position or partial fills. That last omission is no longer a
footnote: with the bootstrap now running, queue position is the specific thing
standing between this work and a signed answer on market making, because it is
what separates the two fill models. Cross-venue pairs are matched on titles and
their resolution rules have not been compared, which is the difference between a
hedge and two open bets. Fee rates are taken from venue documentation dated
2026-07-30 and are overridable.

No profitability claim is made anywhere in this work.
