# Paper market-making PnL decomposition (stream-first-hour)

Source: data/microstructure (stream, event driven), 38 tokens, 56,482 snapshots, 3,276 tape prints, 1 days (2026-07-30 to 2026-07-30).

Quoting: half spread 0.01, gamma 0.08, quote 50.0 USD, inventory cap 250.0 USD. Maker economics for category sports, fee schedule 2026-07-30.

| Item | Touch model (USD) | Tape model (USD) |
|---|---|---|
| Fills | 92 | 288 |
| Spread earned | +136.40 | +395.95 |
| Markout 5min (adverse selection) | -238.24 | -6.48 |
| Late drift (inventory) | +33.87 | -37.12 |
| Maker rebate | +17.51 | +52.04 |
| Mark-to-mid (identity) | -67.98 | +352.34 |
| Total | -50.47 | +404.38 |
| Spread earned per fill (cents) | +148.260 | +137.481 |
| Markout per fill (cents) | -258.962 | -2.250 |
| Result per fill (cents) | -54.860 | +140.410 |
| Mean |inventory| (USD) | 29.56 | 50.04 |
| Max |inventory| (USD) | 166.19 | 309.01 |

## touch fill model

Block-bootstrap 95% CI at day level for the daily total: not computable USD.

| gamma | Fills | Spread earned | Markout | Total | mean \|inventory\| |
|---|---|---|---|---|---|
| 0.00 | 92 | +151.93 | -131.53 | +352.26 | 63.12 |
| 0.04 | 94 | +144.88 | -228.75 | +168.19 | 39.40 |
| 0.08 | 92 | +136.40 | -238.24 | -50.47 | 29.56 |
| 0.16 | 100 | +119.45 | -238.29 | -135.63 | 22.20 |
| 0.32 | 131 | +103.03 | -248.28 | -366.28 | 16.68 |

Liquidity rewards: on average 100% of quoting time inside the reward band, 36 markets, pool assumption 3.0 USD per market per day (median of the 9,562 markets carrying a pool, as of 2026-07-31).

| Competition (multiple of own score) | own share | Reward (USD) | Total incl. reward (USD) |
|---|---|---|---|
| 1x | 50.0% | +2.55 | -47.92 |
| 5x | 16.7% | +0.85 | -49.62 |
| 20x | 4.8% | +0.24 | -50.23 |

| Quoting mode | Fills | Spread earned per fill (c) | Markout per fill (c) | Total (USD) | CI95 daily total |
|---|---|---|---|---|---|
| symmetric | 92 | +148.26 | -258.96 | -50.47 | - |
| signal | 54 | +151.69 | -312.14 | -260.88 | - |
| lean | 80 | +147.38 | -254.74 | -62.56 | - |

| Half spread | Fills | Spread earned | Markout | Earned/markout | Total |
|---|---|---|---|---|---|
| 0.005 | 216 | +139.63 | -304.77 | 0.46 | -94.54 |
| 0.010 | 92 | +136.40 | -238.24 | 0.57 | -50.47 |
| 0.020 | 28 | +97.52 | -68.76 | 1.42 | -202.26 |
| 0.040 | 6 | +36.45 | -57.47 | 0.63 | -219.18 |
| 0.080 | 2 | +18.63 | +0.00 | - | -147.42 |

Walk-forward: gamma chosen on the early days 0.0; on the late days it yields - USD against - USD without skew (gamma 0).

## tape fill model

Block-bootstrap 95% CI at day level for the daily total: not computable USD.

| gamma | Fills | Spread earned | Markout | Total | mean \|inventory\| |
|---|---|---|---|---|---|
| 0.00 | 282 | +456.67 | -81.40 | -161.32 | 163.59 |
| 0.04 | 297 | +442.41 | -51.44 | +449.91 | 85.35 |
| 0.08 | 288 | +395.95 | -6.48 | +404.38 | 50.04 |
| 0.16 | 304 | +358.36 | +4.71 | +327.00 | 32.48 |
| 0.32 | 314 | +243.99 | -38.31 | +162.72 | 24.67 |

Liquidity rewards: on average 100% of quoting time inside the reward band, 36 markets, pool assumption 3.0 USD per market per day (median of the 9,562 markets carrying a pool, as of 2026-07-31).

| Competition (multiple of own score) | own share | Reward (USD) | Total incl. reward (USD) |
|---|---|---|---|
| 1x | 50.0% | +2.55 | +406.93 |
| 5x | 16.7% | +0.85 | +405.23 |
| 20x | 4.8% | +0.24 | +404.62 |

| Quoting mode | Fills | Spread earned per fill (c) | Markout per fill (c) | Total (USD) | CI95 daily total |
|---|---|---|---|---|---|
| symmetric | 288 | +137.48 | -2.25 | +404.38 | - |
| signal | 226 | +138.22 | +26.83 | +193.34 | - |
| lean | 254 | +144.01 | +20.66 | +321.07 | - |

| Half spread | Fills | Spread earned | Markout | Earned/markout | Total |
|---|---|---|---|---|---|
| 0.005 | 617 | +369.95 | -155.19 | 2.38 | +203.49 |
| 0.010 | 288 | +395.95 | -6.48 | 61.10 | +404.38 |
| 0.020 | 56 | +213.15 | +1.85 | 115.21 | +222.30 |
| 0.040 | 11 | +193.53 | -1.13 | 171.78 | +87.72 |
| 0.080 | 1 | +5.81 | +0.00 | - | -45.99 |

Walk-forward: gamma chosen on the early days 0.04; on the late days it yields - USD against - USD without skew (gamma 0).

## How to read this

The three price items are not an estimate but an identity: spread earned plus markout plus late drift reconstructs the terminal mark-to-mid value per fill exactly. Spread earned is what the quoting made, markout is what informed counterparties took back out of it, and late drift is the price of the inventory carried.

The two fill models bracket the truth. Touch fills only when the other side crosses our quote, so it ignores fills at the touch and understates the fill count. Tape fills on every crossing print, so it assumes queue priority and overstates it. Computing only one model means choosing the result with the assumption.

The earned/markout column in the width table is the break-even ratio: below 1, adverse selection eats more than the quoting takes in. It rises with quote width, because spread earned grows with width while the adverse move is set by the market and not by our quote. Where the ratio crosses 1, the fills collapse at the same time - a quote that wide stands past the market.

Makers pay no fee on Polymarket and receive a share of the taker fees collected. The rebate here is the upper bound on that share; the actual daily distribution can come out lower.

Liquidity rewards are the third revenue line and the only one that does not depend on a fill happening at all: what is paid for is presence near the mid. Your own share cannot be computed, because it depends on every other maker in the same market, so a range stands there instead of a number. The pool assumption is the median across all markets carrying a pool and therefore deliberately conservative: the distribution is strongly right skewed, the largest pool sits at 1000 USD per day against a median of 3. The lever on this revenue line is therefore market selection, not quoting tighter - a statement this calculation suggests rather than proves, because nothing here was selected by pool size.

Resolution: quotes are reposted on every top-of-book move, at a median of under a second. That is the case the REST run cannot measure, and the only one in which the market-making question is posed sensibly at all.

SAMPLE WARNING: 1 day(s), at most 288 fills. Below 3 days neither a walk-forward split nor a daily bootstrap can be computed, and the selection of tokens and times of day is not representative. This run is a first look from which no statement about profitability follows.

The two fill models do not even agree on the sign here. The result is therefore undecided: in this run the sign reported would be chosen by the fill assumption rather than by the data.

Further limits: mark-to-mid without resolution modelling, quotes only where the mid is in (0.05, 0.95) and the spread at most 0.10, no queue position, no partial fills. Paper only. Not trading advice.