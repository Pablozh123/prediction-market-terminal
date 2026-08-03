# Paper market-making PnL decomposition (stream-5tage)

Source: data/microstructure (stream, event driven), 468 tokens, 5,413,998 snapshots, 309,219 tape prints, 5 days (2026-07-30 to 2026-08-03).

Quoting: half spread 0.01, gamma 0.08, quote 50.0 USD, inventory cap 250.0 USD. Maker economics for category sports, fee schedule 2026-07-30.

| Item | Touch model (USD) | Tape model (USD) |
|---|---|---|
| Fills | 12,923 | 18,686 |
| Spread earned | +15241.36 | +25830.81 |
| Markout 5min (adverse selection) | -43877.12 | -13138.37 |
| Late drift (inventory) | -9837.62 | -111.25 |
| Maker rebate | +2413.05 | +3451.03 |
| Mark-to-mid (identity) | -38473.38 | +12581.19 |
| Total | -36060.32 | +16032.23 |
| Spread earned per fill (cents) | +117.940 | +138.236 |
| Markout per fill (cents) | -339.527 | -70.311 |
| Result per fill (cents) | -279.040 | +85.798 |
| Mean |inventory| (USD) | 45.56 | 79.52 |
| Max |inventory| (USD) | 957.57 | 3197.55 |

## touch fill model

Block-bootstrap 95% CI at day level for the daily total: (-12121.0187, -2412.6995) USD.

| gamma | Fills | Spread earned | Markout | Total | mean \|inventory\| |
|---|---|---|---|---|---|
| 0.00 | 12,026 | +17071.25 | -40970.52 | -24430.98 | 127.48 |
| 0.04 | 12,125 | +15731.29 | -43191.38 | -33822.99 | 67.45 |
| 0.08 | 12,923 | +15241.36 | -43877.12 | -36060.32 | 45.56 |
| 0.16 | 14,354 | +13943.79 | -45561.86 | -38677.91 | 28.63 |
| 0.32 | 17,731 | +10070.41 | -46108.05 | -44792.70 | 18.19 |

Liquidity rewards: on average 100% of quoting time inside the reward band, 458 markets, pool assumption 3.0 USD per market per day (median of the 9,562 markets carrying a pool, as of 2026-07-31).

| Competition (multiple of own score) | own share | Reward (USD) | Total incl. reward (USD) |
|---|---|---|---|
| 1x | 50.0% | +182.19 | -35878.13 |
| 5x | 16.7% | +60.73 | -35999.59 |
| 20x | 4.8% | +17.35 | -36042.97 |

| Quoting mode | Fills | Spread earned per fill (c) | Markout per fill (c) | Total (USD) | CI95 daily total |
|---|---|---|---|---|---|
| symmetric | 12,923 | +117.94 | -339.53 | -36060.32 | (-12121.0187, -2412.6995) |
| signal | 8,008 | +115.50 | -326.34 | -21398.22 | (-7484.5488, -1267.3122) |
| lean | 10,250 | +117.60 | -323.81 | -26093.66 | (-8764.7825, -1726.6777) |

| Half spread | Fills | Spread earned | Markout | Earned/markout | Total |
|---|---|---|---|---|---|
| 0.005 | 26,008 | +13461.67 | -64538.98 | 0.21 | -58305.07 |
| 0.010 | 12,923 | +15241.36 | -43877.12 | 0.35 | -36060.32 |
| 0.020 | 5,397 | +13549.32 | -27260.48 | 0.50 | -18828.90 |
| 0.040 | 1,795 | +9126.65 | -14384.79 | 0.63 | -8121.39 |
| 0.080 | 485 | +4838.24 | -5836.37 | 0.83 | -2857.22 |

Walk-forward: gamma chosen on the early days 0.0; on the late days it yields -7990.67 USD against -7990.67 USD without skew (gamma 0).

## tape fill model

Block-bootstrap 95% CI at day level for the daily total: (881.0463, 5888.9829) USD.

| gamma | Fills | Spread earned | Markout | Total | mean \|inventory\| |
|---|---|---|---|---|---|
| 0.00 | 15,258 | +27399.08 | -11444.54 | +17252.00 | 255.49 |
| 0.04 | 18,047 | +26956.39 | -11818.15 | +19282.46 | 122.15 |
| 0.08 | 18,686 | +25830.81 | -13138.37 | +16032.23 | 79.52 |
| 0.16 | 19,221 | +23695.03 | -12946.34 | +14527.29 | 50.51 |
| 0.32 | 21,242 | +19308.84 | -13239.71 | +9626.21 | 36.18 |

Liquidity rewards: on average 99% of quoting time inside the reward band, 458 markets, pool assumption 3.0 USD per market per day (median of the 9,562 markets carrying a pool, as of 2026-07-31).

| Competition (multiple of own score) | own share | Reward (USD) | Total incl. reward (USD) |
|---|---|---|---|
| 1x | 50.0% | +182.19 | +16214.42 |
| 5x | 16.7% | +60.73 | +16092.96 |
| 20x | 4.8% | +17.35 | +16049.58 |

| Quoting mode | Fills | Spread earned per fill (c) | Markout per fill (c) | Total (USD) | CI95 daily total |
|---|---|---|---|---|---|
| symmetric | 18,686 | +138.24 | -70.31 | +16032.23 | (881.0463, 5888.9829) |
| signal | 13,275 | +135.04 | -82.37 | +11007.37 | (75.5392, 4327.4091) |
| lean | 16,376 | +136.95 | -79.06 | +13477.88 | (190.693, 5476.3343) |

| Half spread | Fills | Spread earned | Markout | Earned/markout | Total |
|---|---|---|---|---|---|
| 0.005 | 42,631 | +27974.54 | -20766.16 | 1.35 | +13838.93 |
| 0.010 | 18,686 | +25830.81 | -13138.37 | 1.97 | +16032.23 |
| 0.020 | 6,236 | +20201.86 | -6045.63 | 3.34 | +16464.16 |
| 0.040 | 1,669 | +13250.95 | -3250.46 | 4.08 | +10970.93 |
| 0.080 | 393 | +6649.67 | -74.51 | 89.24 | +3962.48 |

Walk-forward: gamma chosen on the early days 0.04; on the late days it yields +8406.94 USD against +8276.89 USD without skew (gamma 0).

## How to read this

The three price items are not an estimate but an identity: spread earned plus markout plus late drift reconstructs the terminal mark-to-mid value per fill exactly. Spread earned is what the quoting made, markout is what informed counterparties took back out of it, and late drift is the price of the inventory carried.

The two fill models bracket the truth. Touch fills only when the other side crosses our quote, so it ignores fills at the touch and understates the fill count. Tape fills on every crossing print, so it assumes queue priority and overstates it. Computing only one model means choosing the result with the assumption.

The earned/markout column in the width table is the break-even ratio: below 1, adverse selection eats more than the quoting takes in. It rises with quote width, because spread earned grows with width while the adverse move is set by the market and not by our quote. Where the ratio crosses 1, the fills collapse at the same time - a quote that wide stands past the market.

Makers pay no fee on Polymarket and receive a share of the taker fees collected. The rebate here is the upper bound on that share; the actual daily distribution can come out lower.

Liquidity rewards are the third revenue line and the only one that does not depend on a fill happening at all: what is paid for is presence near the mid. Your own share cannot be computed, because it depends on every other maker in the same market, so a range stands there instead of a number. The pool assumption is the median across all markets carrying a pool and therefore deliberately conservative: the distribution is strongly right skewed, the largest pool sits at 1000 USD per day against a median of 3. The lever on this revenue line is therefore market selection, not quoting tighter - a statement this calculation suggests rather than proves, because nothing here was selected by pool size.

Resolution: quotes are reposted on every top-of-book move, at a median of under a second. That is the case the REST run cannot measure, and the only one in which the market-making question is posed sensibly at all.

The two fill models do not even agree on the sign here. The result is therefore undecided: in this run the sign reported would be chosen by the fill assumption rather than by the data.

Further limits: mark-to-mid without resolution modelling, quotes only where the mid is in (0.05, 0.95) and the spread at most 0.10, no queue position, no partial fills. Paper only. Not trading advice.