# Where does the money come from? Own measurement against the literature (2026-07-31)

This note brings together what the studies in `docs/research/` measured and what
the published research says about the same questions. It makes no claim about
whether any strategy is tradable; it sorts which revenue paths the data support
and which they rule out.

## The finding in one sentence

Predicting direction works measurably and does not pay: the gross edge of the
best book signal is about two orders of magnitude smaller than the cost of
collecting it. What remains is the other side of the same transaction, posting
the spread instead of paying it.

## What our own data show

**The signal is real and too small.** Across 1.0 million observations over
eleven days, book imbalance shows a hit rate of 55.2 percent (Wilson lower bound
55.0). The mean gross edge is 0.03 to 0.13 cents per signal for imbalance, and
up to 0.28 cents for the combined signal. A taker round trip costs 2.58 cents,
of which 1.65 cents is fee and 0.94 cents is spread. Source:
`orderflow_rest-2026-07.md`.

**There is no segment where that flips.** 34 cuts knowable before the trade
(spread, price level, signal strength, their cross) across three fee categories.
In the fee-free category, where spread is the only remaining cost, exactly one
segment survives both conditions, with a confidence interval that includes zero.
At 34 tests that is precisely the expected false-positive rate. Source:
`edge_segments_july-2026.md`.

**Adverse selection is a latency problem, not a market problem.** At a
120-second requote interval the quoting earns 148 cents of spread per fill and
loses 362 to 698 cents per fill to better-informed counterparties, depending on
the fill model. Per share at the quoted size that is roughly 1.5 cents earned
against 3.6 to 7.0 cents lost. On seconds-resolution data, same code and same
parameters, markout per fill in the tape model falls from 362 to 16 cents while
spread earned barely moves, 148 against 140. Source: `mm_pnl_july-2026.md`
against `mm_pnl_stream-2tage.md`.

That comparison is a direction, not yet a result. The stream run covers two
calendar days, which is one short of what the walk-forward split and the daily
block bootstrap require, and the two fill models do not agree in sign over that
window. The report states both.

**The signal does not help the market making.** Using the imbalance to quote
only the favoured side does not lower markout per fill (minus 361 against minus
365 cents). The better total comes solely from trading less. Losing less by
trading less is not an edge.

## What the literature says

Three independent studies reach the same conclusion as our own measurement, on
both venues and with vastly larger samples.

- Akey, Gregoire, Harvie and Martineau (SSRN 6443103; dataset public under
  CC-BY): 2.47 million users, 588 million trades. 68.8 percent lose money.
  Winners post limit orders, losers take with market orders.
- Bartlett and O'Hara, "Adverse Selection in Prediction Markets: Evidence from
  Kalshi" (SSRN 6615739): 41.6 million trades. Market makers earn twice as much
  per contract in single markets. The exploitable axis is the YES/NO skew, not
  favourite against longshot.
- Buergi, Deng and Whelan (CEPR DP20631): takers lose around 32 percent, makers
  around 10 percent.

Two obvious-looking anomalies are already explained and are not an edge:

- Near-certain contracts are not mispriced. The discount is a funding premium of
  3.06 to 6.89 percent annually, because the capital is locked until resolution
  (Gebele and Matthes, arXiv 2605.31431). After adjusting for it the
  significance disappears.
- Overpriced longshots on Polymarket do exist, but are about eight times smaller
  than the spread you would have to cross to reach them. The median half spread
  below 10 cents is 1,818 basis points (Dubach, arXiv 2604.24366,
  preregistered).

One result from that same work independently explains our own null result:
trade-direction inference on Polymarket is near-random (tick rule 49.83 percent,
bulk volume 50.51 percent). Our flow signal from the polled tape reached a 51.3
percent hit rate. The two fit together, and the implication is that analyses
built on inferred trade direction measure little more than coin flips.

## The third revenue stream that appears in no PnL calculation

Polymarket pays makers for mere presence near the mid, whether or not a fill
happens. Own measurement against the CLOB API on 2026-07-31: 9,900 markets carry
a pool, 164,661 USD per day in total. Median 4.00 USD per market per day, largest
pool 1,770. The modal configuration pays quotes within 4.5 cents of the mid from
20 shares of size upward. Per the scoring rule the score is quadratic in
closeness to the mid.

On top of that come maker rebates of 15 to 25 percent of the taker fees
collected, while makers pay no fee themselves, plus a negative maker fee on the
US platform. The three streams stack.

In our simulation the reward line comes out small, because the calculation uses
the median pool and applies no market selection at all. That is exactly the
hint: the lever on this revenue source is selecting markets by pool size, not
quoting tighter. The calculation suggests that; it does not prove it.

The follow-up study did apply that selection, and the answer is a warning rather
than an invitation. Of the 45 largest pools, 14 have a completely empty
qualifying band, and those books quote 1 to 64 cents wide against a 2.5 cent
band. Nobody stands there because nobody wants to stand there. The venue is
buying liquidity that does not otherwise exist, and adverse selection is the
price. Source: `reward_selection_2026-07-31.md`.

## What follows from this

For the question of where positive expectation can come from, the data rank the
paths like this:

1. **Providing liquidity, requoted fast enough.** The only path supported by
   both our own measurement and three independent studies. The bottleneck is
   demonstrably the staleness of the quote, not its width.
2. **Programme revenue as its own stream.** Rewards, rebates and open-interest
   compensation do not depend on a forecast. They belong reported separately,
   otherwise programme money gets credited to a trading idea.
3. **Directional bets on book signals.** Not per this measurement. The edge is
   real and too small, and no cut knowable before the trade changes that.

## Limits

Eleven days of REST data and two days of seconds data, a slice of the most
active markets, paper simulation without queue position and without partial
fills. The seconds finding is the most important and at the same time the
thinnest; it becomes a result only once enough calendar days allow a
walk-forward split. Fee rates come from venue documentation dated 2026-07-30 and
are overridable.

Read-only research. Not trading advice. No claim of returns.
