# Where does the edge sit? Segmentation (july-2026)

Source: data/microstructure (REST, 120s grid), signal imbalance at threshold 0.65, horizon 300s, 205,835 firings over 11 days (2026-07-18 to 2026-07-28). Fee schedule 2026-07-30.

Every cut is knowable before the trade: spread and price stand in the book at decision time, signal strength follows from the signal itself, the fee category from the market. No cut uses anything that is only known afterwards.

## Fee category sports (rate 0.05)

Overall: net -2.498 cents per signal, gross +0.086, net positive in 3.8% of cases. Segments tested: 34.

### Cut: spread

| Bucket | n | Gross | Net | Net in-sample | Net out-of-sample | CI95 | thin |
|---|---|---|---|---|---|---|---|
| 0-0.5c | 62,082 | +0.075 | -1.635 | -1.724 | -1.468 | [-1.7802, -1.4673] | no |
| 0.5-1c | 13,601 | +0.105 | -2.184 | -2.245 | -2.077 | [-2.344, -2.0253] | no |
| 1-2c | 110,067 | +0.096 | -2.624 | -2.582 | -2.669 | [-2.7286, -2.5312] | no |
| 2-5c | 17,443 | +0.156 | -4.022 | -4.123 | -3.904 | [-4.2407, -3.8604] | no |
| 5-10.1c | 2,642 | -0.647 | -9.113 | -8.959 | -9.242 | [-9.7161, -8.5375] | no |

### Cut: price

| Bucket | n | Gross | Net | Net in-sample | Net out-of-sample | CI95 | thin |
|---|---|---|---|---|---|---|---|
| 0.05-0.15 | 35,353 | -0.012 | -1.715 | -1.673 | -1.777 | [-1.8601, -1.6003] | no |
| 0.15-0.35 | 41,048 | +0.064 | -2.721 | -2.781 | -2.646 | [-2.8028, -2.654] | no |
| 0.35-0.65 | 51,315 | +0.152 | -3.345 | -3.178 | -3.549 | [-3.4919, -3.1551] | no |
| 0.65-0.85 | 41,434 | +0.104 | -2.676 | -2.725 | -2.613 | [-2.758, -2.6074] | no |
| 0.85-0.95 | 36,685 | +0.090 | -1.619 | -1.584 | -1.666 | [-1.7126, -1.538] | no |

### Cut: strength

| Bucket | n | Gross | Net | Net in-sample | Net out-of-sample | CI95 | thin |
|---|---|---|---|---|---|---|---|
| 0.65-0.75 | 66,898 | +0.082 | -2.540 | -2.461 | -2.640 | [-2.6612, -2.4201] | no |
| 0.75-0.85 | 59,388 | +0.062 | -2.470 | -2.387 | -2.590 | [-2.6045, -2.3357] | no |
| 0.85-0.95 | 63,696 | +0.098 | -2.471 | -2.484 | -2.456 | [-2.5795, -2.3731] | no |
| 0.95-1.01 | 15,853 | +0.141 | -2.543 | -2.506 | -2.622 | [-2.8185, -2.2577] | no |

### Candidates

None. Of 34 segments tested, not one survives the in-sample and the out-of-sample condition simultaneously at a sufficient case count.

## Fee category politics (rate 0.04)

Overall: net -2.169 cents per signal, gross +0.086, net positive in 4.2% of cases. Segments tested: 34.

### Cut: spread

| Bucket | n | Gross | Net | Net in-sample | Net out-of-sample | CI95 | thin |
|---|---|---|---|---|---|---|---|
| 0-0.5c | 62,082 | +0.075 | -1.327 | -1.403 | -1.185 | [-1.4555, -1.1821] | no |
| 0.5-1c | 13,601 | +0.105 | -1.862 | -1.916 | -1.767 | [-2.0035, -1.7204] | no |
| 1-2c | 110,067 | +0.096 | -2.287 | -2.251 | -2.325 | [-2.3797, -2.2059] | no |
| 2-5c | 17,443 | +0.156 | -3.669 | -3.765 | -3.556 | [-3.8803, -3.5123] | no |
| 5-10.1c | 2,642 | -0.647 | -8.747 | -8.602 | -8.869 | [-9.3611, -8.1637] | no |

### Cut: price

| Bucket | n | Gross | Net | Net in-sample | Net out-of-sample | CI95 | thin |
|---|---|---|---|---|---|---|---|
| 0.05-0.15 | 35,353 | -0.012 | -1.542 | -1.500 | -1.605 | [-1.6842, -1.4323] | no |
| 0.15-0.35 | 41,048 | +0.064 | -2.353 | -2.404 | -2.288 | [-2.4325, -2.286] | no |
| 0.35-0.65 | 51,315 | +0.152 | -2.859 | -2.692 | -3.063 | [-3.0056, -2.6695] | no |
| 0.65-0.85 | 41,434 | +0.104 | -2.307 | -2.348 | -2.255 | [-2.3875, -2.2405] | no |
| 0.85-0.95 | 36,685 | +0.090 | -1.447 | -1.410 | -1.496 | [-1.5445, -1.3685] | no |

### Cut: strength

| Bucket | n | Gross | Net | Net in-sample | Net out-of-sample | CI95 | thin |
|---|---|---|---|---|---|---|---|
| 0.65-0.75 | 66,898 | +0.082 | -2.200 | -2.122 | -2.298 | [-2.3125, -2.0894] | no |
| 0.75-0.85 | 59,388 | +0.062 | -2.145 | -2.070 | -2.255 | [-2.2667, -2.0241] | no |
| 0.85-0.95 | 63,696 | +0.098 | -2.148 | -2.154 | -2.142 | [-2.2512, -2.0593] | no |
| 0.95-1.01 | 15,853 | +0.141 | -2.216 | -2.167 | -2.317 | [-2.4634, -1.9576] | no |

### Candidates

None. Of 34 segments tested, not one survives the in-sample and the out-of-sample condition simultaneously at a sufficient case count.

## Fee category geopolitics (rate 0.0)

Overall: net -0.853 cents per signal, gross +0.086, net positive in 8.4% of cases. Segments tested: 34.

### Cut: spread

| Bucket | n | Gross | Net | Net in-sample | Net out-of-sample | CI95 | thin |
|---|---|---|---|---|---|---|---|
| 0-0.5c | 62,082 | +0.075 | -0.097 | -0.122 | -0.051 | [-0.1499, -0.0408] | no |
| 0.5-1c | 13,601 | +0.105 | -0.574 | -0.599 | -0.530 | [-0.6405, -0.5015] | no |
| 1-2c | 110,067 | +0.096 | -0.936 | -0.926 | -0.948 | [-0.9797, -0.8902] | no |
| 2-5c | 17,443 | +0.156 | -2.256 | -2.333 | -2.167 | [-2.4459, -2.1237] | no |
| 5-10.1c | 2,642 | -0.647 | -7.285 | -7.175 | -7.376 | [-7.9073, -6.6446] | no |

### Cut: price

| Bucket | n | Gross | Net | Net in-sample | Net out-of-sample | CI95 | thin |
|---|---|---|---|---|---|---|---|
| 0.05-0.15 | 35,353 | -0.012 | -0.852 | -0.808 | -0.917 | [-0.9927, -0.7459] | no |
| 0.15-0.35 | 41,048 | +0.064 | -0.880 | -0.897 | -0.859 | [-0.9654, -0.8007] | no |
| 0.35-0.65 | 51,315 | +0.152 | -0.914 | -0.746 | -1.119 | [-1.0606, -0.7291] | no |
| 0.65-0.85 | 41,434 | +0.104 | -0.834 | -0.841 | -0.824 | [-0.9177, -0.7498] | no |
| 0.85-0.95 | 36,685 | +0.090 | -0.758 | -0.714 | -0.817 | [-0.8655, -0.6793] | no |

### Cut: strength

| Bucket | n | Gross | Net | Net in-sample | Net out-of-sample | CI95 | thin |
|---|---|---|---|---|---|---|---|
| 0.65-0.75 | 66,898 | +0.082 | -0.840 | -0.767 | -0.933 | [-0.9094, -0.7649] | no |
| 0.75-0.85 | 59,388 | +0.062 | -0.848 | -0.800 | -0.917 | [-0.9229, -0.776] | no |
| 0.85-0.95 | 63,696 | +0.098 | -0.857 | -0.834 | -0.883 | [-0.9313, -0.7852] | no |
| 0.95-1.01 | 15,853 | +0.141 | -0.906 | -0.814 | -1.099 | [-1.0848, -0.7201] | no |

### Candidates (positive in-sample AND out-of-sample, not thin)

| Segment | n | Net | out-of-sample | CI95 |
|---|---|---|---|---|
| spread x strength: 0-0.5c x 0.95-1.01 | 6,323 | +0.008 | +0.438 | [-0.1124, 0.2033] |

## How to read this

The out-of-sample column is the only one that counts. A segment that is positive in-sample only is exactly what data mining supplies for free: with enough cuts, one of them always looks good. The number of segments tested therefore stands at the head of every section, so the selection probability stays visible.

The fee categories are the sharpest instrument in this table, because they show the same dataset under different costs. Geopolitics is fee free, so there the only cost left is the spread. If the edge stays negative there too, the fees are not the reason - the move is simply too small.

Thin segments are marked and excluded from the candidate list, but printed deliberately: a segment with 40 observations and a large number is not a find, it is noise, and that should be visible rather than omitted.

Read-only research. Not trading advice.