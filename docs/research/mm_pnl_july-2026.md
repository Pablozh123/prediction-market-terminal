# Paper market-making PnL decomposition (july-2026)

Source: data/microstructure (REST, 120s grid), 4519 tokens, 370,903 snapshots, 679,209 tape prints, 12 days (2026-07-18 to 2026-07-30).

Quoting: half spread 0.01, gamma 0.08, quote 50.0 USD, inventory cap 250.0 USD. Maker economics for category sports, fee schedule 2026-07-30.

| Item | Touch model (USD) | Tape model (USD) |
|---|---|---|
| Fills | 32,553 | 13,341 |
| Spread earned | +43285.15 | +19781.63 |
| Markout 5min (adverse selection) | -227282.81 | -48298.95 |
| Late drift (inventory) | -14417.10 | -19037.24 |
| Maker rebate | +6117.93 | +2519.77 |
| Mark-to-mid (identity) | -198414.76 | -47554.56 |
| Total | -192296.84 | -45034.79 |
| Spread earned per fill (cents) | +132.968 | +148.277 |
| Markout per fill (cents) | -698.193 | -362.034 |
| Result per fill (cents) | -590.719 | -337.567 |
| Mean |inventory| (USD) | 38.90 | 40.61 |
| Max |inventory| (USD) | 1449.18 | 1490.59 |

## touch fill model

Block-bootstrap 95% CI at day level for the daily total: [-18924.1105, -12204.2181] USD.

| gamma | Fills | Spread earned | Markout | Total | mean \|inventory\| |
|---|---|---|---|---|---|
| 0.00 | 30,892 | +45432.21 | -223218.72 | -190712.65 | 82.91 |
| 0.04 | 31,823 | +44681.79 | -226771.05 | -190461.52 | 49.95 |
| 0.08 | 32,553 | +43285.15 | -227282.81 | -192296.84 | 38.90 |
| 0.16 | 33,044 | +40658.21 | -226046.65 | -198559.07 | 27.51 |
| 0.32 | 33,268 | +36720.50 | -224379.96 | -204416.14 | 20.82 |

Liquidity rewards: on average 99% of quoting time inside the reward band, 1450 markets, pool assumption 3.0 USD per market per day (median of the 9,562 markets carrying a pool, as of 2026-07-31).

| Competition (multiple of own score) | own share | Reward (USD) | Total incl. reward (USD) |
|---|---|---|---|
| 1x | 50.0% | +1298.62 | -190998.21 |
| 5x | 16.7% | +432.87 | -191863.96 |
| 20x | 4.8% | +123.68 | -192173.16 |

| Quoting mode | Fills | Spread earned per fill (c) | Markout per fill (c) | Total (USD) | CI95 daily total |
|---|---|---|---|---|---|
| symmetric | 32,553 | +132.97 | -698.19 | -192296.84 | [-18924.1105, -12204.2181] |
| signal | 25,623 | +130.90 | -698.99 | -157584.65 | [-15738.2326, -9919.8139] |
| lean | 29,623 | +132.33 | -701.82 | -177399.84 | [-17427.9135, -11310.4551] |

| Half spread | Fills | Spread earned | Markout | Earned/markout | Total |
|---|---|---|---|---|---|
| 0.005 | 42,126 | +27450.11 | -242696.48 | 0.11 | -238301.36 |
| 0.010 | 32,553 | +43285.15 | -227282.81 | 0.19 | -192296.84 |
| 0.020 | 23,349 | +62329.76 | -198591.80 | 0.31 | -140942.45 |
| 0.040 | 13,671 | +71065.44 | -149900.74 | 0.47 | -81478.79 |
| 0.080 | 6,116 | +61961.24 | -90962.55 | 0.68 | -40859.12 |

Walk-forward: gamma chosen on the early days 0.0; on the late days it yields -71532.83 USD against -71532.83 USD without skew (gamma 0).

## tape fill model

Block-bootstrap 95% CI at day level for the daily total: [-4999.2322, -2439.3496] USD.

| gamma | Fills | Spread earned | Markout | Total | mean \|inventory\| |
|---|---|---|---|---|---|
| 0.00 | 11,994 | +19614.86 | -48271.77 | -45973.29 | 93.86 |
| 0.04 | 12,884 | +20033.16 | -48557.12 | -45506.75 | 53.61 |
| 0.08 | 13,341 | +19781.63 | -48298.95 | -45034.79 | 40.61 |
| 0.16 | 13,569 | +19050.57 | -48476.76 | -43150.87 | 28.95 |
| 0.32 | 13,538 | +17800.64 | -45943.59 | -40619.01 | 21.42 |

Liquidity rewards: on average 99% of quoting time inside the reward band, 1450 markets, pool assumption 3.0 USD per market per day (median of the 9,562 markets carrying a pool, as of 2026-07-31).

| Competition (multiple of own score) | own share | Reward (USD) | Total incl. reward (USD) |
|---|---|---|---|
| 1x | 50.0% | +1298.62 | -43736.16 |
| 5x | 16.7% | +432.87 | -44601.91 |
| 20x | 4.8% | +123.68 | -44911.11 |

| Quoting mode | Fills | Spread earned per fill (c) | Markout per fill (c) | Total (USD) | CI95 daily total |
|---|---|---|---|---|---|
| symmetric | 13,341 | +148.28 | -362.03 | -45034.79 | [-4999.2322, -2439.3496] |
| signal | 10,378 | +145.41 | -365.47 | -41326.72 | [-4540.5633, -2258.1129] |
| lean | 12,103 | +146.14 | -364.33 | -41072.40 | [-4628.5566, -2142.5131] |

| Half spread | Fills | Spread earned | Markout | Earned/markout | Total |
|---|---|---|---|---|---|
| 0.005 | 20,012 | +15591.61 | -49164.90 | 0.32 | -49201.72 |
| 0.010 | 13,341 | +19781.63 | -48298.95 | 0.41 | -45034.79 |
| 0.020 | 8,341 | +23997.20 | -42326.33 | 0.57 | -28373.02 |
| 0.040 | 4,672 | +27140.99 | -31683.93 | 0.86 | -8458.39 |
| 0.080 | 1,971 | +21408.35 | -20350.46 | 1.05 | -5187.05 |

Walk-forward: gamma chosen on the early days 0.32; on the late days it yields -16398.95 USD against -16403.21 USD without skew (gamma 0).

## How to read this

The three price items are not an estimate but an identity: spread earned plus markout plus late drift reconstructs the terminal mark-to-mid value per fill exactly. Spread earned is what the quoting made, markout is what informed counterparties took back out of it, and late drift is the price of the inventory carried.

The two fill models bracket the truth. Touch fills only when the other side crosses our quote, so it ignores fills at the touch and understates the fill count. Tape fills on every crossing print, so it assumes queue priority and overstates it. Computing only one model means choosing the result with the assumption.

The earned/markout column in the width table is the break-even ratio: below 1, adverse selection eats more than the quoting takes in. It rises with quote width, because spread earned grows with width while the adverse move is set by the market and not by our quote. Where the ratio crosses 1, the fills collapse at the same time - a quote that wide stands past the market.

Makers pay no fee on Polymarket and receive a share of the taker fees collected. The rebate here is the upper bound on that share; the actual daily distribution can come out lower.

Liquidity rewards are the third revenue line and the only one that does not depend on a fill happening at all: what is paid for is presence near the mid. Your own share cannot be computed, because it depends on every other maker in the same market, so a range stands there instead of a number. The pool assumption is the median across all markets carrying a pool and therefore deliberately conservative: the distribution is strongly right skewed, the largest pool sits at 1000 USD per day against a median of 3. The lever on this revenue line is therefore market selection, not quoting tighter - a statement this calculation suggests rather than proves, because nothing here was selected by pool size.

The most important limitation, and at the same time the actual finding: the 120-second grid means every quote stands unchanged in the book for two minutes. Exactly that staleness is the adverse selection being measured - you are filled preferentially when the market has walked past the stale quote. A real market maker requotes on a millisecond scale. These numbers therefore do not measure whether market making works on Polymarket, but what happens when you fail to requote for two minutes.

Further limits: mark-to-mid without resolution modelling, quotes only where the mid is in (0.05, 0.95) and the spread at most 0.10, no queue position, no partial fills. Paper only. Not trading advice.