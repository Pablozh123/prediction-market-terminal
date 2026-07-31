# Cross-venue gaps net of fees (2026-07-31)

As of 2026-07-30T23:34:02Z. Compared 300 open Polymarket markets against 600 Kalshi markets. Title match from similarity 0.45, basket size 100 shares, fee schedule 2026-07-30.

Candidate pairs: 8, of which suspected mismatches 3 (listed separately below), counted 5. With a positive gross gap: 4. **Positive after both fee curves: 3.**

Median gross gap +1.40 cents, median net gap +1.16 cents, median fee threshold 1.53 cents. Best net gap +3.07 cents.

| Pair | Score | Gross (c) | Threshold (c) | Net (c) | Size | Days to resolution | annualised |
|---|---|---|---|---|---|---|---|
| Will Marco Rubio win the 2028 US Preside / KXPRESPERSON-28-MRUB | 0.62 | +4.60 | 1.53 | +3.07 | 100 | 830 | +1.4% |
| Will Marine Le Pen win the 2027 French p / KXFRENCHPRES-27-MLEP | 0.60 | +4.00 | 2.68 | +1.32 | 12 | 273 | +1.8% |
| Will J.B. Pritzker win the 2028 Democrat / KXPRESNOMD-28-JBP | 0.57 | +1.40 | 0.24 | +1.16 | 100 | 830 | +0.5% |
| Will Donald Trump win the 2028 US Presid / KXPRESPERSON-28-DTRU | 0.62 | +0.20 | 0.33 | -0.13 | 100 | 830 | -0.1% |
| Will Sofia host Eurovision 2027? / KXEUROVISIONHOST-27-SO | 0.80 | -7.00 | 2.82 | -9.82 | 100 | 153 | -20.5% |

### Rejected pairs (similar titles, different questions)

These pairs are excluded from every number above. They are listed here because they show what a mismatch looks like: as the largest apparent edge in the entire run.

| Polymarket | Kalshi | apparent net (c) | Reason |
|---|---|---|---|
| Will Abdul El-Sayed win the 2026 Michigan De | Michigan Democratic Senate primary margin of | +78.87 | verschiedene Fragetypen: ergebnis gegen marge |
| Will Mark Kelly win the 2028 Democratic pres | Who will run for the Democratic presidential | +64.25 | verschiedene Fragetypen: ergebnis gegen ergebnis, teilnahme |
| Will Haley Stevens win the 2026 Michigan Dem | Michigan Democratic Senate primary margin of | -1.75 | verschiedene Fragetypen: ergebnis gegen marge |

## How to read this

A price difference is not arbitrage. Buying YES on one venue and NO on the other pays exactly 1.00 per pair at resolution, so the gross edge is 1 minus the sum of both purchase prices. The threshold column is what both fee curves demand together. Net is the difference. Only a positive net number is an edge at all, and even then only up to the depth shown in the size column.

The last column usually decides. A basket locks capital until resolution, and for the pairs that show up here at all that is typically years away. Two cents on thirty cents of stake over two years is not seven percent, it is a little over three per year, and against that stands the interest-free surrender of the capital plus resolution and rule risk on both sides. What is found here are carry positions, not arbitrages.

**The pairs are not verified.** The match runs on title similarity and says that two markets look like the same question, not that they resolve the same way. The Cardi B market around the Super Bowl is the standing counterexample: Kalshi judged the outcome ambiguous and settled at the last traded price, Polymarket paid YES in full, on identical footage under different rulebooks. Across a pair like that a basket is not hedged, it is two open bets. Before any further use, every pair needs a comparison of its resolution rules.

Further limits: quotes are a snapshot, not a history, and any statement about how long a gap lives needs the running recorders. Polymarket depth is not fetched here (it needs the token id per outcome), Kalshi depth is; where depth is missing the size is an assumption and the number an upper bound. Hitting both legs simultaneously is assumed, execution risk is not modelled.

Read-only research. Not trading advice.