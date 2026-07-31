# Order flow study (rest-2026-07)

Source: data/microstructure (REST, 120s grid), 4489 tokens, 370,423 snapshots, 678,665 tape prints, 11 days (2026-07-18 to 2026-07-28).

Threshold 0.65, cost model sports category, fee schedule 2026-07-30. Cost per round trip = spread plus two taker fees. Hit rate conditional on movement.

## Signal: imbalance

Observations 1,011,556 over 11 days, of which moved 39.1%. Hit rate 55.2% (Wilson lower bound 55.0%).

| Horizon | Delay | n | Hits | Gross (cents) | Spread (cents) | Fee (cents) | Net (cents) | Edge retained |
|---|---|---|---|---|---|---|---|---|
| 300s | 0s | 205,835 | 55.5% | +0.086 | 0.938 | 1.646 | -2.498 | 100% |
| 300s | 120s | 204,191 | 53.7% | +0.030 | 0.918 | 1.645 | -2.533 | 35% |
| 900s | 0s | 201,430 | 56.8% | +0.130 | 0.920 | 1.649 | -2.439 | 100% |
| 900s | 120s | 200,099 | 55.6% | +0.080 | 0.903 | 1.649 | -2.473 | 62% |
| 900s | 300s | 200,001 | 53.8% | +0.043 | 0.904 | 1.648 | -2.509 | 33% |

Walk-forward: train (early days) net -2.448 cents, test (late days) net -2.546 cents.
Block-bootstrap 95% CI at day level for net without delay: [-2.591, -2.3561] cents.

## Signal: flow

Observations 450,492 over 11 days, of which moved 60.5%. Hit rate 51.3% (Wilson lower bound 51.1%).

| Horizon | Delay | n | Hits | Gross (cents) | Spread (cents) | Fee (cents) | Net (cents) | Edge retained |
|---|---|---|---|---|---|---|---|---|
| 300s | 0s | 93,868 | 51.7% | -0.002 | 1.025 | 1.849 | -2.875 | - |
| 300s | 120s | 93,344 | 51.1% | -0.003 | 1.024 | 1.841 | -2.868 | - |
| 900s | 0s | 88,126 | 51.5% | -0.052 | 0.992 | 1.866 | -2.910 | - |
| 900s | 120s | 87,711 | 51.3% | -0.054 | 0.990 | 1.862 | -2.907 | - |
| 900s | 300s | 87,443 | 50.9% | -0.035 | 0.997 | 1.851 | -2.883 | - |

Walk-forward: train (early days) net -2.819 cents, test (late days) net -3.001 cents.
Block-bootstrap 95% CI at day level for net without delay: [-3.063, -2.7353] cents.

## Signal: combo

Observations 90,890 over 11 days, of which moved 59.3%. Hit rate 55.6% (Wilson lower bound 55.2%).

| Horizon | Delay | n | Hits | Gross (cents) | Spread (cents) | Fee (cents) | Net (cents) | Edge retained |
|---|---|---|---|---|---|---|---|---|
| 300s | 0s | 18,891 | 56.6% | +0.211 | 0.991 | 1.823 | -2.603 | 100% |
| 300s | 120s | 18,797 | 54.0% | +0.019 | 0.959 | 1.817 | -2.756 | 9% |
| 900s | 0s | 17,793 | 57.7% | +0.276 | 0.954 | 1.837 | -2.515 | 100% |
| 900s | 120s | 17,717 | 56.2% | +0.111 | 0.921 | 1.834 | -2.645 | 40% |
| 900s | 300s | 17,692 | 53.4% | +0.073 | 0.928 | 1.825 | -2.680 | 27% |

Walk-forward: train (early days) net -2.660 cents, test (late days) net -2.609 cents.
Block-bootstrap 95% CI at day level for net without delay: [-2.74, -2.4125] cents.

## How to read this

Gross is the mid movement in the signal's direction. Net subtracts the full round trip: crossing the spread once on entry, once on exit, plus two taker fees. A signal with a high hit rate and a negative net is correct and still untradable.

The two numbers are at the same time the bounds on execution style. Net is the lower bound (everything taken aggressively), gross the upper bound (everything filled passively; on Polymarket makers pay no fee). If a signal's value lies only between those two bounds, it is not a taker signal but a reason to shift quotes as a maker. The separate columns for spread and fee show which of the two eats the edge.

The delay column simulates reaction time: the signal fires at t, the entry price is the book at t plus delay, the exit stays at t plus horizon. If the edge already falls sharply at small delays, it is a latency race and not a research edge.

Limits: the REST grid resolves delays only in 120-second steps, so smaller values land on the same snapshot and show no decay. Seconds resolution comes only from the stream recorder. The REST tape is polled and can miss prints between two fetches, which understates the flow share.

Read-only research. Not trading advice.