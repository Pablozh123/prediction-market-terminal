# Lifetime of a cross-venue gap (2026-07-31)

Source: C:\Users\chole\Projects\prediction-market-terminal\data\microstructure, both stream recorders. Basket size 100 shares, opposite leg at most 60 seconds old, fee schedule 2026-07-30. 5 of 5 pairs recorded on both sides, 6 open windows in total.

| Pair | Observations | Hours | Windows | open (s) | share open | longest (s) | median (s) | over 5s | peak net (c) |
|---|---|---|---|---|---|---|---|---|---|
| KXEUROVISIONHOST-27-SOF | 109 | 11.56 | 3 | 4828 | 11.6% | 4827 | 0.83 | 1 | +4.72 |
| KXPRESPERSON-28-DTRU | 13 | 11.56 | 0 | 0 | 0.0% | 0 | - | 0 | +0.00 |
| KXPRESPERSON-28-MRUB | 21 | 11.56 | 1 | 41626 | 100.0% | 41626 | 41625.85 | 1 | +3.18 |
| KXFRENCHPRES-27-MLEP | 27 | 11.56 | 1 | 41626 | 100.0% | 41626 | 41626.05 | 1 | +3.27 |
| KXPRESNOMD-28-JBP | 26 | 11.56 | 1 | 41626 | 100.0% | 41626 | 41625.95 | 1 | +1.17 |

## How to read this

An open window means: at that moment both legs together would have made money after subtracting both fee curves. The share-open column is the fraction of observed time for which that held. The over-5s column counts only windows that stayed open long enough to be reachable at all over a REST path or by hand; anything shorter is theory for everything except a resting order.

The pairing looks backwards only. Every Kalshi observation is matched with the last Polymarket quote before it, and discarded if that quote is older than the permitted staleness. Looking forward would be more convenient and would use prices from the future.

**A window is only as dense as the observations inside it.** The recorders write only when the top of book moves, and these markets barely move: a pair can have two dozen observations across eleven hours. A window spanning that range therefore does not mean the gap was demonstrably open throughout, but that it was open at every moment we looked. The observations column always belongs read alongside.

The finding fits the annualised calculation from the snapshot study and explains it. These gaps do not close in seconds, they stand open for hours - because they are not arbitrage. Taking one locks capital until resolution, and at 830 days remaining an edge of a few cents is a little over one percent a year. The market is not failing to close the gap; the gap is the price of the locked capital and of the resolution-rule risk on both sides.

Limits: the pairs are matched on titles and their resolution rules have not been compared, so whether a basket would be hedged at all remains open. Depth does not enter, so the numbers hold for the standard size and not for what actually rests in the book. Simultaneous execution of both legs is assumed. And a window is an observation, not an opportunity: anyone stepping into it would change it.

Read-only research. Not trading advice.