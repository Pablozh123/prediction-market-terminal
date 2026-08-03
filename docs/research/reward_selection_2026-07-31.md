# Reward market selection (2026-07-31)

9,900 markets carry a pool, 164,661 USD per day in total. Median 4.00, largest 1770.00. The top 100 hold 26.5% of the pot.

The 45 largest pools were probed against their current book, quote size 100 shares. Of those, with a completely empty qualifying band: 14.

| Market | Pool/day | Band (c) | Spread (c) | Competition (shares) | Orders | Pool per competing share |
|---|---|---|---|---|---|---|
| LoL: CTBC Flying Oyster vs GAM Esports (BO3) | 1475.00 | 2.5 | 4.70 | 0 | 0 | 14.75000 |
| Games Total: O/U 2.5 | 632.00 | 2.5 | 4.00 | 0 | 0 | 6.32000 |
| LoL: CTBC Flying Oyster vs GAM Esports - Gam | 632.00 | 2.5 | 7.00 | 0 | 0 | 6.32000 |
| Game Handicap: GAM (-1.5) vs CTBC Flying Oys | 632.00 | 2.5 | 12.00 | 0 | 0 | 6.32000 |
| Map Handicap: FaZe (-1.5) vs TheMongolz (+1. | 632.00 | 2.5 | 13.90 | 0 | 0 | 6.32000 |
| Map 2 Rounds Handicap: FaZe (-3.5) vs TheMon | 632.00 | 2.5 | 63.00 | 0 | 0 | 6.32000 |
| Map 3 Rounds Handicap: FaZe (-3.5) vs TheMon | 632.00 | 2.5 | 64.00 | 0 | 0 | 6.32000 |
| Games Total: O/U 2.5 | 400.00 | 2.5 | 12.00 | 0 | 0 | 4.00000 |
| Counter-Strike: INOX Division vs Falcons For | 337.00 | 2.5 | 1.00 | 0 | 0 | 3.37000 |
| BetBoom Team vs MOUZ: Draw (1-1)? | 311.00 | 2.5 | 59.00 | 0 | 0 | 3.11000 |
| BetBoom Team to win 2-0? | 311.00 | 2.5 | 11.00 | 0 | 0 | 3.11000 |
| Dota 2: L1ga Team vs REKONIX (BO3) - Games o | 933.00 | 2.5 | 2.00 | 362 | 1 | 2.57735 |
| Will Warsh say "Supply shock" during July Pr | 250.00 | 4.5 | 8.00 | 0 | 0 | 2.50000 |
| Will Trump say "Venezuela" during cabinet me | 250.00 | 4.5 | 7.00 | 0 | 0 | 2.50000 |
| Will Trump say "Million" or "Billion" or "Tr | 250.00 | 4.5 | 35.00 | 0 | 0 | 2.50000 |
| Map 2 Total Rounds: Over/Under 21.5 | 632.00 | 2.5 | 2.00 | 423 | 1 | 1.49360 |
| Dota 2: Enjoy vs GLYPH - Game 2 Winner | 400.00 | 2.5 | 1.00 | 290 | 1 | 1.38045 |
| Dota 2: BetBoom Team vs MOUZ - Game 2 Winner | 400.00 | 2.5 | 1.00 | 500 | 1 | 0.80000 |
| Valorant: Global Esports vs Gen.G Esports (B | 933.00 | 2.5 | 1.00 | 1,176 | 1 | 0.79351 |
| Dota 2: L1ga Team vs REKONIX - Game 1 Winner | 400.00 | 2.5 | 3.00 | 580 | 1 | 0.68906 |
| Will Trump say "Filibuster" during cabinet m | 250.00 | 4.5 | 6.00 | 408 | 3 | 0.61274 |
| Games Total: O/U 2.5 | 632.00 | 2.5 | 4.00 | 1,270 | 2 | 0.49764 |
| Will Trump say "Putin" during cabinet meetin | 250.00 | 4.5 | 6.00 | 700 | 2 | 0.35715 |
| Dota 2: L1ga Team vs REKONIX - Game 2 Winner | 400.00 | 2.5 | 1.00 | 1,875 | 3 | 0.21332 |
| Dota 2: Enjoy vs GLYPH (BO3) - Games of the  | 933.00 | 2.5 | 2.00 | 4,837 | 2 | 0.19289 |

## How to read this

The last column is the ranking number: how many reward dollars per day fall on each share already standing inside the qualifying band. It is a ranking, not a payout. Your own share depends on the scores of every other maker in the same market, and the exchange does not publish those.

Competition is measured through resting depth inside the band. That is a proxy, but not an arbitrary one: the scoring rule weights every order by size and closeness to the mid, so exactly that depth is the observable part of what your own score is normalised against.

A large pool in a crowded book is worth less than a medium one in an empty book. That is why the ranking here is by ratio rather than by pool size - sorting by pool alone would be precisely the mistake this analysis exists to expose.

**An empty band is not an invitation, it is a warning.** In the run of 2026-07-31 the markets with the largest pools and zero competition are esports markets throughout, whose actual spread runs 4 to 64 cents while the qualifying band is 2.5 cents. Nobody stands there because nobody wants to stand there. Whoever collects the premium quotes many times tighter than the whole market and is thereby the cheapest target in the book for anyone informed. With the large pot the exchange is buying exactly the liquidity that does not otherwise exist, and the price of that is adverse selection. What it costs is measured by mm_pnl, not by this analysis - and there, at a two-minute requote interval, it ran two to five times the spread earned.

Limits: a snapshot, not a history. Anyone standing in a market permanently changes the competition they measured. Depth comes from a single fetch per market, and a volatile book can look different seconds later. And rewards are only one revenue line: what stands against them in adverse selection is measured by the MM study, not by this one.

Read-only research. Not trading advice.