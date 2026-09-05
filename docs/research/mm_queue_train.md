# Queue-position study, per-day candidates (train)

22 days (2026-07-30 to 2026-09-03), 6 candidates x 2 queue models, plus the tape reference at the published parameters. Each day loaded and scored on its own; the mark-to-mid horizon is the day.

| Model | Half spread | Gamma | Days | Fills | Total (USD) | Mean/day (USD) | CI95 daily (USD) | Spread/fill (c) | Markout/fill (c) |
|---|---|---|---|---|---|---|---|---|---|
| queue_back | 0.005 | 0.08 | 22 | 100,079 | +26528.86 | +1205.86 | (488.1401, 2021.0047) | +96.42 | -81.54 |
| queue_back | 0.005 | 0.00 | 22 | 106,938 | -7311.08 | -332.32 | (-1385.0541, 806.9895) | +80.67 | -80.49 |
| queue_back | 0.010 | 0.08 | 22 | 57,142 | +45166.03 | +2053.00 | (1369.7904, 2843.4889) | +163.82 | -109.45 |
| queue_back | 0.010 | 0.00 | 22 | 47,439 | +34751.41 | +1579.61 | (749.1032, 2492.8835) | +174.12 | -118.89 |
| queue_back | 0.020 | 0.08 | 22 | 23,813 | +51932.10 | +2360.55 | (1650.1987, 3136.0422) | +321.54 | -167.37 |
| queue_back | 0.020 | 0.00 | 22 | 21,732 | +45339.84 | +2060.90 | (1360.7732, 2779.3057) | +334.06 | -177.80 |
| queue_front | 0.005 | 0.08 | 22 | 137,477 | +36162.64 | +1643.76 | (814.0639, 2543.0482) | +80.78 | -62.32 |
| queue_front | 0.005 | 0.00 | 22 | 161,161 | -4550.48 | -206.84 | (-1286.273, 918.3201) | +60.79 | -56.46 |
| queue_front | 0.010 | 0.08 | 22 | 76,499 | +51536.70 | +2342.58 | (1539.8183, 3173.4693) | +139.96 | -88.86 |
| queue_front | 0.010 | 0.00 | 22 | 61,030 | +40529.09 | +1842.23 | (905.5282, 2804.4105) | +150.90 | -94.98 |
| queue_front | 0.020 | 0.08 | 22 | 31,590 | +64076.71 | +2912.58 | (2109.7849, 3786.5187) | +277.30 | -131.41 |
| queue_front | 0.020 | 0.00 | 22 | 28,125 | +56490.18 | +2567.74 | (1835.0021, 3387.6052) | +292.03 | -139.05 |
| tape | 0.010 | 0.08 | 22 | 90,595 | +71151.56 | +3234.16 | (2270.4129, 4232.5952) | +143.40 | -81.39 |

## Choice
Pre-registered rule (highest total in queue_back with at least 1,000 fills): half spread 0.02, gamma 0.08, latency 0.0 s. Total +51932.10 USD over 22 days, CI95 (1650.1987, 3136.0422).

## How to read this

This is the training window. Nothing in it is a result: the numbers exist to pick one parameter set by a rule written down before the test window was recorded. The test window is scored once, with that set, and reported whatever it says.

Read-only research. Not trading advice.