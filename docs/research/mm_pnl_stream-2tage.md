# Paper market-making PnL decomposition (stream-2tage)

Source: data/microstructure (stream, event driven), 112 tokens, 1,049,354 snapshots, 39,774 tape prints, 2 days (2026-07-30 to 2026-07-31).

Quoting: half spread 0.01, gamma 0.08, quote 50.0 USD, inventory cap 250.0 USD. Maker economics for category sports, fee schedule 2026-07-30.

| Item | Touch model (USD) | Tape model (USD) |
|---|---|---|
| Fills | 2,277 | 3,260 |
| Spread earned | +2705.17 | +4579.52 |
| Markout 5min (adverse selection) | -6752.96 | -532.11 |
| Late drift (inventory) | -1212.98 | +1363.59 |
| Maker rebate | +426.25 | +585.77 |
| Mark-to-mid (identity) | -5260.77 | +5411.00 |
| Total | -4834.52 | +5996.77 |
| Spread earned per fill (cents) | +118.804 | +140.476 |
| Markout per fill (cents) | -296.573 | -16.322 |
| Result per fill (cents) | -212.320 | +183.950 |
| Mean |inventory| (USD) | 41.62 | 75.86 |
| Max |inventory| (USD) | 957.57 | 756.20 |

## touch fill model

Block-bootstrap 95% CI at day level for the daily total: not computable USD.

| gamma | Fills | Spread earned | Markout | Total | mean \|inventory\| |
|---|---|---|---|---|---|
| 0.00 | 2,110 | +3056.06 | -5642.88 | -3471.88 | 125.50 |
| 0.04 | 2,115 | +2800.88 | -6189.87 | -3494.62 | 62.93 |
| 0.08 | 2,277 | +2705.17 | -6752.96 | -4834.52 | 41.62 |
| 0.16 | 2,528 | +2438.60 | -6997.19 | -5587.06 | 27.39 |
| 0.32 | 3,134 | +1835.37 | -7289.59 | -6817.28 | 17.90 |

Liquidity rewards: on average 100% of quoting time inside the reward band, 112 markets, pool assumption 3.0 USD per market per day (median of the 9,562 markets carrying a pool, as of 2026-07-31).

| Competition (multiple of own score) | own share | Reward (USD) | Total incl. reward (USD) |
|---|---|---|---|
| 1x | 50.0% | +42.06 | -4792.46 |
| 5x | 16.7% | +14.02 | -4820.50 |
| 20x | 4.8% | +4.01 | -4830.52 |

| Quoting mode | Fills | Spread earned per fill (c) | Markout per fill (c) | Total (USD) | CI95 daily total |
|---|---|---|---|---|---|
| symmetric | 2,277 | +118.80 | -296.57 | -4834.52 | - |
| signal | 1,415 | +120.52 | -288.60 | -2337.66 | - |
| lean | 1,825 | +120.93 | -292.80 | -3150.26 | - |

| Half spread | Fills | Spread earned | Markout | Earned/markout | Total |
|---|---|---|---|---|---|
| 0.005 | 4,730 | +2557.80 | -11009.66 | 0.23 | -9036.19 |
| 0.010 | 2,277 | +2705.17 | -6752.96 | 0.40 | -4834.52 |
| 0.020 | 839 | +2148.22 | -3425.36 | 0.63 | -2072.32 |
| 0.040 | 233 | +1228.93 | -1934.77 | 0.64 | -1267.51 |
| 0.080 | 53 | +519.68 | -666.31 | 0.78 | -139.69 |

Walk-forward: gamma chosen on the early days 0.0; on the late days it yields -3286.37 USD against -3286.37 USD without skew (gamma 0).

## tape fill model

Block-bootstrap 95% CI at day level for the daily total: not computable USD.

| gamma | Fills | Spread earned | Markout | Total | mean \|inventory\| |
|---|---|---|---|---|---|
| 0.00 | 2,647 | +4810.55 | -494.28 | +6251.95 | 221.81 |
| 0.04 | 3,152 | +4816.95 | -117.47 | +6550.77 | 113.57 |
| 0.08 | 3,260 | +4579.52 | -532.11 | +5996.77 | 75.86 |
| 0.16 | 3,300 | +4067.88 | -912.80 | +4778.91 | 48.16 |
| 0.32 | 3,668 | +3263.32 | -1249.14 | +3602.06 | 34.51 |

Liquidity rewards: on average 100% of quoting time inside the reward band, 112 markets, pool assumption 3.0 USD per market per day (median of the 9,562 markets carrying a pool, as of 2026-07-31).

| Competition (multiple of own score) | own share | Reward (USD) | Total incl. reward (USD) |
|---|---|---|---|
| 1x | 50.0% | +42.06 | +6038.83 |
| 5x | 16.7% | +14.02 | +6010.79 |
| 20x | 4.8% | +4.01 | +6000.78 |

| Quoting mode | Fills | Spread earned per fill (c) | Markout per fill (c) | Total (USD) | CI95 daily total |
|---|---|---|---|---|---|
| symmetric | 3,260 | +140.48 | -16.32 | +5996.77 | - |
| signal | 2,374 | +135.08 | -27.44 | +3624.13 | - |
| lean | 2,881 | +140.30 | -15.80 | +4994.73 | - |

| Half spread | Fills | Spread earned | Markout | Earned/markout | Total |
|---|---|---|---|---|---|
| 0.005 | 7,660 | +5023.78 | -1629.17 | 3.08 | +5530.63 |
| 0.010 | 3,260 | +4579.52 | -532.11 | 8.61 | +5996.77 |
| 0.020 | 901 | +3038.56 | -148.20 | 20.50 | +4076.58 |
| 0.040 | 195 | +1916.53 | +828.86 | 2.31 | +3510.23 |
| 0.080 | 41 | +335.95 | -35.27 | 9.53 | +414.43 |

Walk-forward: gamma chosen on the early days 0.04; on the late days it yields +6266.37 USD against +6480.55 USD without skew (gamma 0).

## How to read this

The three price items are not an estimate but an identity: spread earned plus markout plus late drift reconstructs the terminal mark-to-mid value per fill exactly. Spread earned is what the quoting made, markout is what informed counterparties took back out of it, and late drift is the price of the inventory carried.

The two fill models bracket the truth. Touch fills only when the other side crosses our quote, so it ignores fills at the touch and understates the fill count. Tape fills on every crossing print, so it assumes queue priority and overstates it. Computing only one model means choosing the result with the assumption.

The earned/markout column in the width table is the break-even ratio: below 1, adverse selection eats more than the quoting takes in. It rises with quote width, because spread earned grows with width while the adverse move is set by the market and not by our quote. Where the ratio crosses 1, the fills collapse at the same time - a quote that wide stands past the market.

Makers pay no fee on Polymarket and receive a share of the taker fees collected. The rebate here is the upper bound on that share; the actual daily distribution can come out lower.

Liquidity rewards are the third revenue line and the only one that does not depend on a fill happening at all: what is paid for is presence near the mid. Your own share cannot be computed, because it depends on every other maker in the same market, so a range stands there instead of a number. The pool assumption is the median across all markets carrying a pool and therefore deliberately conservative: the distribution is strongly right skewed, the largest pool sits at 1000 USD per day against a median of 3. The lever on this revenue line is therefore market selection, not quoting tighter - a statement this calculation suggests rather than proves, because nothing here was selected by pool size.

Resolution: quotes are reposted on every top-of-book move, at a median of under a second. That is the case the REST run cannot measure, and the only one in which the market-making question is posed sensibly at all.

SAMPLE WARNING: 2 day(s), at most 3,260 fills. Below 3 days neither a walk-forward split nor a daily bootstrap can be computed, and the selection of tokens and times of day is not representative. This run is a first look from which no statement about profitability follows.

The two fill models do not even agree on the sign here. The result is therefore undecided: in this run the sign reported would be chosen by the fill assumption rather than by the data.

Further limits: mark-to-mid without resolution modelling, quotes only where the mid is in (0.05, 0.95) and the spread at most 0.10, no queue position, no partial fills. Paper only. Not trading advice.