# Paper trades of the arbitrage scanner, resolved against Polymarket

Snapshot 2026-09-05 13:53 UTC. Trades from the scanner's journal (paper_trades in trades.db, read-only). Resolution source: Polymarket Gamma /markets with closed=true, read per trade slug.
Modeled paper results, not realized returns: no order was placed and no capital moved.

## In one paragraph

The scanner's journal holds 167 paper trades and reports none of them as resolved. 156 of them sit on markets Polymarket has settled; 11 are still open. The scanner never sees a settlement because it asks Gamma for markets without `closed=true`, and that endpoint returns settled markets only with the parameter. Of the 156 settled trades, 98 were filled after their market had already closed, so they were never fills at all. Of the rest, 45 have an entry price the CLOB's own day price supports; those 45 legs staked 37.52 USD, paid out 31.32 USD, and made **-6.20 USD** before fees (22 won, 21 lost, 2 flat). Mean time from fill to settlement was 40.71 days (median 33.73, n = 58).

## The four linked baskets (the ones the site shows)

20 trades carry an opportunity id and a share count; they are the baskets the scanner fired between 2026-05-20 and 2026-05-23. All 20 legs have settled. Every entry price matches the CLOB day price of the NO token (entry checks: entry 20). Together they staked 12.52 USD and made **-1.52 USD**.

| basket | exclusive | legs | stake USD | payout USD | PnL USD | opened | settled | what happened |
|---|---|---|---|---|---|---|---|---|
| what-will-happen-before-gta-vi | no | 8 | 3.93 | 4.00 | +0.07 | 2026-05-23 | 2026-08-01 | 0 NO legs paid 1.00, 8 settled 0.50 |
| harvey-weinstein-prison-time | yes | 6 | 4.99 | 5.00 | +0.01 | 2026-05-20 | 2026-08-01 | 5 NO legs paid 1.00, 1 paid 0 |
| microstrategy-sell-any-bitcoin-in-2025 | no | 3 | 1.64 | 1.00 | -0.64 | 2026-05-23 | 2026-06-04 | 1 NO leg paid 1.00, 2 paid 0 |
| starmer-out-in-2025 | no | 3 | 1.96 | 1.00 | -0.96 | 2026-05-23 | 2026-06-22 | 1 NO leg paid 1.00, 2 paid 0 |

A NO-on-every-outcome basket pays n minus 1 dollars only when exactly one outcome can happen; Gamma marks such events `negRisk`. The Weinstein basket is one, and it paid what the model said, eight tenths of a cent on five dollars. The Starmer and MicroStrategy baskets sat on staggered deadlines (by May 31, by June 30, by December 31): once the event happened, every later deadline resolved YES too and every NO on it paid nothing, so those baskets lost about half their stake. The GTA VI legs were independent events that Polymarket settled 0.50/0.50, and the basket came out seven cents ahead by chance, not by structure.

## The journal's older rows

147 rows have no opportunity id and no share count (`link_status` legacy_unlinked); they carry a one dollar notional each. 136 sit on settled markets.

- **98 were filled after the market's closedTime**, 83 of them at an entry of 0.000. The scanner was pricing markets that had already settled. These rows get no PnL.
- Of the 38 filled while the market was open, the CLOB day price supports the recorded entry for 5 rows and supports it only as 1 minus entry for 20 rows: the journal stored the YES price on a NO trade. For 13 rows it supports neither.
- The 25 supported rows staked 25.00 USD and made **-4.68 USD** (12 won, 13 lost). Taken as recorded, the same rows would show +319.47 USD, because a NO recorded at a few cents turns one dollar into hundreds of shares that no book ever offered.
- 13 settled rows get no corrected PnL: entry_unsupported_by_day_price 13.

## Every basket

| basket | linked | exclusive | legs | settled | after close | entry checks | stake USD | PnL USD (corrected) | PnL USD (as recorded) |
|---|---|---|---|---|---|---|---|---|---|
| what-will-happen-before-gta-vi | yes | no | 8 | 8/8 | 0 | entry 8 | 3.93 | +0.07 (n = 8) | +0.07 |
| harvey-weinstein-prison-time | yes | yes | 6 | 6/6 | 0 | entry 6 | 4.99 | +0.01 (n = 6) | +0.01 |
| microstrategy-sell-any-bitcoin-in-2025 | yes | no | 3 | 3/3 | 0 | entry 3 | 1.64 | -0.64 (n = 3) | -0.64 |
| starmer-out-in-2025 | yes | no | 3 | 3/3 | 0 | entry 3 | 1.96 | -0.96 (n = 3) | -0.96 |
| serie-a-top-4-finish | no | no | 20 | 20/20 | 16 | complement 1, entry 1, neither 2, no_data 16 | 20.00 | +3.38 (n = 2) | -2.95 |
| megaeth-airdrop-by | no | no | 8 | 7/8 | 6 | complement 2, no_data 6 | 8.00 | +0.41 (n = 1) | +2.45 |
| what-will-happen-before-gta-vi | no | no | 9 | 9/9 | 2 | complement 2, entry 4, neither 1, no_data 2 | 9.00 | +0.31 (n = 6) | -2.40 |
| hyperliquid-airdop-by | no | no | 6 | 3/6 | 3 | complement 2, entry 1, no_data 3 | 6.00 | — | — |
| epl-which-clubs-get-relegated | no | no | 20 | 20/20 | 18 | neither 2, no_data 18 | 20.00 | — | -0.88 |
| laliga-which-clubs-get-relegated | no | no | 8 | 8/8 | 4 | neither 4, no_data 4 | 8.00 | — | +90.42 |
| serie-a-which-clubs-get-relegated | no | no | 10 | 10/10 | 8 | neither 2, no_data 8 | 10.00 | — | -1.33 |
| who-will-bernie-endorse | no | no | 7 | 1/7 | 1 | complement 5, neither 1, no_data 1 | 7.00 | — | — |
| english-premier-league-top-4-finish | no | no | 20 | 20/20 | 18 | complement 1, neither 1, no_data 18 | 20.00 | -1.00 (n = 1) | -3.10 |
| who-will-trump-endorse | no | no | 7 | 6/7 | 4 | complement 2, neither 1, no_data 4 | 7.00 | -1.00 (n = 1) | -5.00 |
| will-russia-capture-kostyantynivka-by | no | no | 13 | 13/13 | 9 | complement 4, no_data 9 | 13.00 | -1.47 (n = 4) | +14.55 |
| microstrategy-sell-any-bitcoin-in-2025 | no | no | 5 | 5/5 | 2 | complement 3, no_data 2 | 5.00 | -1.47 (n = 3) | -0.10 |
| gpt-6-released-by | no | no | 5 | 5/5 | 2 | complement 3, no_data 2 | 5.00 | -1.90 (n = 3) | +7.53 |
| starmer-out-in-2025 | no | no | 9 | 9/9 | 5 | complement 4, no_data 5 | 9.00 | -1.93 (n = 4) | +297.97 |

## Every trade

Entry is the journal's price; day is the CLOB price of the traded token nearest the fill; check says whether entry matches the day price as recorded, as 1 minus entry (complement), neither, or could not be checked. Days run from fill to closedTime; a negative number is a fill after the close.

| market | linked | entry | day | check | stake | status | settle | days | PnL corrected | PnL as recorded |
|---|---|---|---|---|---|---|---|---|---|---|
| microstrategy-sell-any-bitcoin-in-2025 | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -135 | filled_after_close | invalid_entry_price |
| microstrategy-sells-any-bitcoin-by-december-31-2 | no | 0.835 | 0.160 | complement | 1.00 | resolved | 0.00 | 13 | -1.00 | -1.00 |
| microstrategy-sells-any-bitcoin-by-march-31-2026 | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -48 | filled_after_close | invalid_entry_price |
| microstrategy-sells-any-bitcoin-by-june-30-2026 | no | 0.656 | 0.335 | complement | 1.00 | resolved | 0.00 | 13 | -1.00 | -1.00 |
| microstrategy-sells-any-bitcoin-by-may-31-2026 | no | 0.345 | 0.655 | complement | 1.00 | resolved | 1.00 | 15 | +0.53 | +1.90 |
| starmer-out-in-2025-873 | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -138 | filled_after_close | invalid_entry_price |
| starmer-out-by-june-30-2026-862-594-548-219 | no | 0.295 | 0.705 | complement | 1.00 | resolved | 0.00 | 34 | -1.00 | -1.00 |
| starmer-out-by-december-31-2026-936-416-977-234- | no | 0.735 | 0.265 | complement | 1.00 | resolved | 0.00 | 34 | -1.00 | -1.00 |
| starmer-out-by-february-28-2026-352-692 | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -79 | filled_after_close | invalid_entry_price |
| starmer-out-by-march-31-2026 | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -48 | filled_after_close | invalid_entry_price |
| starmer-out-by-april-30-2026 | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -18 | filled_after_close | invalid_entry_price |
| starmer-out-by-may-15-2026 | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -3 | filled_after_close | invalid_entry_price |
| starmer-out-by-may-31-2026 | no | 0.061 | 0.939 | complement | 1.00 | resolved | 1.00 | 13 | +0.07 | +15.26 |
| starmer-out-by-may-19-2026 | no | 0.004 | 0.999 | complement | 1.00 | resolved | 1.00 | 1 | +0.00 | +284.71 |
| russia-ukraine-ceasefire-before-gta-vi-554 | no | 1.000 | — | no_data | 1.00 | resolved | 0.00 | -11 | filled_after_close | -1.00 |
| new-rhianna-album-before-gta-vi-926 | no | 0.570 | 0.465 | complement | 1.00 | resolved | 0.50 | 74 | +0.16 | -0.12 |
| new-playboi-carti-album-before-gta-vi-421 | no | 0.545 | 0.455 | complement | 1.00 | resolved | 0.50 | 74 | +0.10 | -0.08 |
| will-jesus-christ-return-before-gta-vi-665 | no | 0.485 | 0.515 | entry | 1.00 | resolved | 0.50 | 74 | +0.03 | +0.03 |
| trump-out-as-president-before-gta-vi-846 | no | 0.505 | 0.505 | entry | 1.00 | resolved | 0.50 | 74 | -0.01 | -0.01 |
| will-china-invades-taiwan-before-gta-vi-716 | no | 0.505 | 0.495 | entry | 1.00 | resolved | 0.50 | 74 | -0.01 | -0.01 |
| will-bitcoin-hit-1m-before-gta-vi-872 | no | 0.484 | 0.515 | entry | 1.00 | resolved | 0.50 | 74 | +0.03 | +0.03 |
| will-gpt-6-be-released | no | 0.655 | 0.460 | neither | 1.00 | resolved | 0.50 | 74 | entry_unsupported_by_day_price | -0.24 |
| will-drake-release-iceman-before-gta-vi | no | 1.000 | — | no_data | 1.00 | resolved | 0.00 | -4 | filled_after_close | -1.00 |
| will-russia-capture-kostyantynivka-by-august-31 | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -260 | filled_after_close | invalid_entry_price |
| will-russia-capture-kostyantynivka-by-december-3 | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -138 | filled_after_close | invalid_entry_price |
| will-russia-capture-kostyantynivka-by-october-31 | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -199 | filled_after_close | invalid_entry_price |
| will-russia-capture-kostyantynivka-by-september- | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -230 | filled_after_close | invalid_entry_price |
| will-russia-capture-kostyantynivka-by-november-3 | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -169 | filled_after_close | invalid_entry_price |
| will-russia-capture-kostyantynivka-by-january-31 | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -107 | filled_after_close | invalid_entry_price |
| will-russia-capture-kostyantynivka-by-march-31-8 | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -48 | filled_after_close | invalid_entry_price |
| will-russia-capture-kostyantynivka-by-december-3 | no | 0.755 | 0.255 | complement | 1.00 | resolved | 0.00 | 92 | -1.00 | -1.00 |
| will-russia-capture-kostyantynivka-by-february-2 | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -79 | filled_after_close | invalid_entry_price |
| will-russia-capture-kostyantynivka-by-june-30-38 | no | 0.316 | 0.709 | complement | 1.00 | resolved | 1.00 | 43 | +0.46 | +2.17 |
| will-russia-capture-kostyantynivka-by-april-30 | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -18 | filled_after_close | invalid_entry_price |
| will-russia-capture-kostyantynivka-by-may-31 | no | 0.065 | 0.950 | complement | 1.00 | resolved | 1.00 | 13 | +0.07 | +14.38 |
| will-russia-capture-kostyantynivka-by-september- | no | 0.565 | 0.445 | complement | 1.00 | resolved | 0.00 | 92 | -1.00 | -1.00 |
| will-hyperliquid-perform-an-airdrop-by-june-30 | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -322 | filled_after_close | invalid_entry_price |
| will-hyperliquid-perform-an-airdrop-by-september | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -230 | filled_after_close | invalid_entry_price |
| will-hyperliquid-perform-an-airdrop-by-december- | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -138 | filled_after_close | invalid_entry_price |
| will-hyperliquid-perform-an-airdrop-by-december- | no | 0.240 | 0.755 | complement | 1.00 | open | — | 109 | — | — |
| will-hyperliquid-perform-an-airdrop-by-december- | no | 0.505 | 0.480 | entry | 1.00 | open | — | 109 | — | — |
| will-hyperliquid-perform-an-airdrop-by-june-30-2 | no | 0.400 | 0.600 | complement | 1.00 | open | — | 109 | — | — |
| will-megaeth-perform-an-airdrop-by-september-30 | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -230 | filled_after_close | invalid_entry_price |
| will-megaeth-perform-an-airdrop-by-june-30-143-2 | no | 0.290 | 0.702 | complement | 1.00 | resolved | 1.00 | 43 | +0.41 | +2.45 |
| will-megaeth-perform-an-airdrop-by-december-31 | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -138 | filled_after_close | invalid_entry_price |
| will-megaeth-perform-an-airdrop-by-january-31-93 | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -107 | filled_after_close | invalid_entry_price |
| will-megaeth-perform-an-airdrop-by-february-28-6 | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -79 | filled_after_close | invalid_entry_price |
| will-megaeth-perform-an-airdrop-by-february-15 | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -89 | filled_after_close | invalid_entry_price |
| will-megaeth-perform-an-airdrop-by-march-15 | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -64 | filled_after_close | invalid_entry_price |
| will-megaeth-perform-an-airdrop-by-december-31-2 | no | 0.820 | 0.160 | complement | 1.00 | open | — | 109 | — | — |
| will-liverpool-be-relegated-from-the-english-pre | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -37 | filled_after_close | invalid_entry_price |
| will-arsenal-be-relegated-from-the-english-premi | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -69 | filled_after_close | invalid_entry_price |
| will-man-city-be-relegated-from-the-english-prem | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -69 | filled_after_close | invalid_entry_price |
| will-chelsea-be-relegated-from-the-english-premi | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -31 | filled_after_close | invalid_entry_price |
| will-newcastle-be-relegated-from-the-english-pre | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -9 | filled_after_close | invalid_entry_price |
| will-leeds-be-relegated-from-the-english-premier | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -9 | filled_after_close | invalid_entry_price |
| will-man-utd-be-relegated-from-the-english-premi | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -65 | filled_after_close | invalid_entry_price |
| will-tottenham-be-relegated-from-the-english-pre | no | 0.321 | 0.848 | neither | 1.00 | resolved | 1.00 | 5 | entry_unsupported_by_day_price | +2.12 |
| will-aston-villa-be-relegated-from-the-english-p | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -58 | filled_after_close | invalid_entry_price |
| will-nottm-forest-be-relegated-from-the-english- | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -9 | filled_after_close | invalid_entry_price |
| will-brighton-be-relegated-from-the-english-prem | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -31 | filled_after_close | invalid_entry_price |
| will-bournemouth-be-relegated-from-the-english-p | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -31 | filled_after_close | invalid_entry_price |
| will-burnley-be-relegated-from-the-english-premi | no | 1.000 | — | no_data | 1.00 | resolved | 0.00 | -27 | filled_after_close | -1.00 |
| will-everton-be-relegated-from-the-english-premi | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -31 | filled_after_close | invalid_entry_price |
| will-crystal-palace-be-relegated-from-the-englis | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -9 | filled_after_close | invalid_entry_price |
| will-west-ham-be-relegated-from-the-english-prem | no | 0.345 | 0.140 | neither | 1.00 | resolved | 0.00 | 5 | entry_unsupported_by_day_price | -1.00 |
| will-fulham-be-relegated-from-the-english-premie | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -24 | filled_after_close | invalid_entry_price |
| will-brentford-be-relegated-from-the-english-pre | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -31 | filled_after_close | invalid_entry_price |
| will-wolves-be-relegated-from-the-english-premie | no | 1.000 | — | no_data | 1.00 | resolved | 0.00 | -29 | filled_after_close | -1.00 |
| will-sunderland-be-relegated-from-the-english-pr | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -17 | filled_after_close | invalid_entry_price |
| will-gpt-6-be-released-by-december-31 | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -138 | filled_after_close | invalid_entry_price |
| will-gpt-6-be-released-by-march-31-2026 | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -48 | filled_after_close | invalid_entry_price |
| will-gpt-6-be-released-by-june-30-2026 | no | 0.095 | 0.905 | complement | 1.00 | resolved | 1.00 | 43 | +0.10 | +9.53 |
| will-gpt-6-be-released-by-december-31-2026-834 | no | 0.815 | 0.185 | complement | 1.00 | resolved | 0.00 | 108 | -1.00 | -1.00 |
| will-gpt-6-be-released-by-september-30-2026 | no | 0.540 | 0.460 | complement | 1.00 | resolved | 0.00 | 108 | -1.00 | -1.00 |
| will-espanyol-be-relegated-from-la-liga-after-th | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -2 | filled_after_close | invalid_entry_price |
| will-oviedo-be-relegated-from-la-liga-after-the- | no | 1.000 | — | no_data | 1.00 | resolved | 0.00 | -8 | filled_after_close | -1.00 |
| will-getafe-be-relegated-from-la-liga-after-the- | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -6 | filled_after_close | invalid_entry_price |
| will-osasuna-be-relegated-from-la-liga-after-the | no | 0.011 | 0.904 | neither | 1.00 | resolved | 1.00 | 4 | entry_unsupported_by_day_price | +85.96 |
| will-alavs-be-relegated-from-la-liga-after-the-2 | no | 0.312 | 0.998 | neither | 1.00 | resolved | 1.00 | 4 | entry_unsupported_by_day_price | +2.20 |
| will-valencia-be-relegated-from-la-liga-after-th | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -2 | filled_after_close | invalid_entry_price |
| will-sevilla-be-relegated-from-la-liga-after-the | no | 0.190 | 0.995 | neither | 1.00 | resolved | 1.00 | 4 | entry_unsupported_by_day_price | +4.26 |
| will-mallorca-be-relegated-from-la-liga-after-th | no | 0.137 | 0.081 | neither | 1.00 | resolved | 0.00 | 4 | entry_unsupported_by_day_price | -1.00 |
| will-cremonese-be-relegated-from-serie-a-after-t | no | 0.585 | 0.195 | neither | 1.00 | resolved | 0.00 | 5 | entry_unsupported_by_day_price | -1.00 |
| will-pisa-be-relegated-from-serie-a-after-the-20 | no | 1.000 | — | no_data | 1.00 | resolved | 0.00 | -18 | filled_after_close | -1.00 |
| will-verona-be-relegated-from-serie-a-after-the- | no | 1.000 | — | no_data | 1.00 | resolved | 0.00 | -18 | filled_after_close | -1.00 |
| will-lecce-be-relegated-from-serie-a-after-the-2 | no | 0.375 | 0.790 | neither | 1.00 | resolved | 1.00 | 5 | entry_unsupported_by_day_price | +1.67 |
| will-sassuolo-be-relegated-from-serie-a-after-th | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -26 | filled_after_close | invalid_entry_price |
| will-cagliari-be-relegated-from-serie-a-after-th | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -2 | filled_after_close | invalid_entry_price |
| will-parma-be-relegated-from-serie-a-after-the-2 | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -24 | filled_after_close | invalid_entry_price |
| will-genoa-be-relegated-from-serie-a-after-the-2 | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -15 | filled_after_close | invalid_entry_price |
| will-udinese-be-relegated-from-serie-a-after-the | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -25 | filled_after_close | invalid_entry_price |
| will-torino-be-relegated-from-serie-a-after-the- | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -23 | filled_after_close | invalid_entry_price |
| will-napoli-finish-in-the-top-4-in-the-2025-26-s | no | 1.000 | — | no_data | 1.00 | resolved | 0.00 | -2 | filled_after_close | -1.00 |
| will-atalanta-finish-in-the-top-4-in-the-2025-26 | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -16 | filled_after_close | invalid_entry_price |
| will-torino-finish-in-the-top-4-in-the-2025-26-s | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -43 | filled_after_close | invalid_entry_price |
| will-lecce-finish-in-the-top-4-in-the-2025-26-se | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -58 | filled_after_close | invalid_entry_price |
| will-inter-finish-in-the-top-4-in-the-2025-26-se | no | 1.000 | — | no_data | 1.00 | resolved | 0.00 | -32 | filled_after_close | -1.00 |
| will-lazio-finish-in-the-top-4-in-the-2025-26-se | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -30 | filled_after_close | invalid_entry_price |
| will-pisa-finish-in-the-top-4-in-the-2025-26-ser | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -69 | filled_after_close | invalid_entry_price |
| will-parma-finish-in-the-top-4-in-the-2025-26-se | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -45 | filled_after_close | invalid_entry_price |
| will-ac-milan-finish-in-the-top-4-in-the-2025-26 | no | 0.814 | 0.170 | complement | 1.00 | resolved | 1.00 | 5 | +4.38 | +0.23 |
| will-fiorentina-finish-in-the-top-4-in-the-2025- | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -58 | filled_after_close | invalid_entry_price |
| will-cagliari-finish-in-the-top-4-in-the-2025-26 | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -58 | filled_after_close | invalid_entry_price |
| will-udinese-finish-in-the-top-4-in-the-2025-26- | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -31 | filled_after_close | invalid_entry_price |
| will-juventus-finish-in-the-top-4-in-the-2025-26 | no | 0.550 | 0.880 | neither | 1.00 | resolved | 1.00 | 5 | entry_unsupported_by_day_price | +0.82 |
| will-bologna-finish-in-the-top-4-in-the-2025-26- | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -24 | filled_after_close | invalid_entry_price |
| will-verona-finish-in-the-top-4-in-the-2025-26-s | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -69 | filled_after_close | invalid_entry_price |
| will-genoa-finish-in-the-top-4-in-the-2025-26-se | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -43 | filled_after_close | invalid_entry_price |
| will-roma-finish-in-the-top-4-in-the-2025-26-ser | no | 0.240 | 0.260 | entry | 1.00 | resolved | 0.00 | 5 | -1.00 | -1.00 |
| will-como-finish-in-the-top-4-in-the-2025-26-ser | no | 0.113 | 0.699 | neither | 1.00 | resolved | 0.00 | 5 | entry_unsupported_by_day_price | -1.00 |
| will-us-cremonese-finish-in-the-top-4-in-the-202 | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -64 | filled_after_close | invalid_entry_price |
| will-sassuolo-finish-in-the-top-4-in-the-2025-26 | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -30 | filled_after_close | invalid_entry_price |
| will-arsenal-finish-in-the-top-4-of-the-epl-2025 | no | 1.000 | — | no_data | 1.00 | resolved | 0.00 | -24 | filled_after_close | -1.00 |
| will-manchester-city-finish-in-the-top-4-of-the- | no | 1.000 | — | no_data | 1.00 | resolved | 0.00 | -16 | filled_after_close | -1.00 |
| will-tottenham-finish-in-the-top-4-of-the-epl-20 | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -58 | filled_after_close | invalid_entry_price |
| will-aston-villa-finish-in-the-top-4-of-the-epl- | no | 0.631 | 0.408 | complement | 1.00 | resolved | 0.00 | 5 | -1.00 | -1.00 |
| will-nottingham-forest-finish-in-the-top-4-of-th | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -58 | filled_after_close | invalid_entry_price |
| will-brentford-finish-in-the-top-4-of-the-epl-20 | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -10 | filled_after_close | invalid_entry_price |
| will-crystal-palace-finish-in-the-top-4-of-the-e | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -16 | filled_after_close | invalid_entry_price |
| will-west-ham-finish-in-the-top-4-of-the-epl-202 | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -58 | filled_after_close | invalid_entry_price |
| will-burnley-finish-in-the-top-4-of-the-epl-2025 | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -69 | filled_after_close | invalid_entry_price |
| will-fulham-finish-in-the-top-4-of-the-epl-20252 | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -17 | filled_after_close | invalid_entry_price |
| will-liverpool-finish-in-the-top-4-of-the-epl-20 | no | 0.525 | 0.635 | neither | 1.00 | resolved | 1.00 | 5 | entry_unsupported_by_day_price | +0.90 |
| will-chelsea-finish-in-the-top-4-of-the-epl-2025 | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -15 | filled_after_close | invalid_entry_price |
| will-manchester-united-finish-in-the-top-4-of-th | no | 1.000 | — | no_data | 1.00 | resolved | 0.00 | -4 | filled_after_close | -1.00 |
| will-newcastle-finish-in-the-top-4-of-the-epl-20 | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -30 | filled_after_close | invalid_entry_price |
| will-everton-finish-in-the-top-4-of-the-epl-2025 | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -15 | filled_after_close | invalid_entry_price |
| will-bournemouth-finish-in-the-top-4-of-the-epl- | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -4 | filled_after_close | invalid_entry_price |
| will-brighton-finish-in-the-top-4-of-the-epl-202 | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -4 | filled_after_close | invalid_entry_price |
| will-wolves-finish-in-the-top-4-of-the-epl-20252 | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -69 | filled_after_close | invalid_entry_price |
| will-leeds-finish-in-the-top-4-of-the-epl-202526 | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -37 | filled_after_close | invalid_entry_price |
| will-sunderland-finish-in-the-top-4-of-the-epl-2 | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -17 | filled_after_close | invalid_entry_price |
| will-bernie-endorse-kshama-sawant-for-wa-09-by-n | no | 0.300 | 0.705 | complement | 1.00 | open | — | 109 | — | — |
| will-bernie-endorse-antonio-delgado-for-ny-gov-b | no | 0.087 | 0.912 | complement | 1.00 | open | — | 109 | — | — |
| will-bernie-endorse-alan-grayson-for-fl-sen-nov- | no | 0.087 | 0.913 | complement | 1.00 | open | — | 109 | — | — |
| will-bernie-endorse-james-talarico-for-tx-sen-by | no | 0.895 | 0.105 | complement | 1.00 | open | — | 109 | — | — |
| will-bernie-endorse-dan-osborn-for-ne-sen-by-nov | no | 0.344 | 0.508 | neither | 1.00 | open | — | 109 | — | — |
| will-bernie-endorse-omar-fateh-in-minneapolis-ma | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -195 | filled_after_close | invalid_entry_price |
| will-bernie-endorse-zach-wahls-for-ia-sen-nov-2- | no | 0.161 | 0.839 | complement | 1.00 | open | — | 109 | — | — |
| will-trump-endorse-ken-paxton-for-tx-sen-by-nov- | no | 1.000 | 0.741 | neither | 1.00 | resolved | 0.00 | 0 | entry_unsupported_by_day_price | -1.00 |
| will-trump-endorse-winsome-earle-sears-for-va-go | no | 0.000 | — | no_data | 1.00 | resolved | 1.00 | -195 | filled_after_close | invalid_entry_price |
| will-trump-endorse-susan-collins-for-me-sen-by-n | no | 0.170 | 0.820 | complement | 1.00 | resolved | 0.00 | 25 | -1.00 | -1.00 |
| will-trump-endorse-john-cornyn-for-tx-sen-by-nov | no | 0.016 | 0.976 | complement | 1.00 | open | — | 109 | — | — |
| will-trump-endorse-andy-barr-for-ky-sen-by-nov-2 | no | 1.000 | — | no_data | 1.00 | resolved | 0.00 | -17 | filled_after_close | -1.00 |
| will-trump-endorse-steve-hilton-in-ca-gov-for-no | no | 1.000 | — | no_data | 1.00 | resolved | 0.00 | -21 | filled_after_close | -1.00 |
| will-trump-endorse-lindsey-graham-for-sc-sen-by- | no | 1.000 | — | no_data | 1.00 | resolved | 0.00 | -247 | filled_after_close | -1.00 |
| will-harvey-weinstein-be-sentenced-to-no-prison- | yes | 0.218 | 0.223 | entry | 0.22 | resolved | 0.00 | 73 | -0.22 | -0.22 |
| will-harvey-weinstein-be-sentenced-to-less-than- | yes | 0.958 | 0.958 | entry | 0.96 | resolved | 1.00 | 73 | +0.04 | +0.04 |
| will-harvey-weinstein-be-sentenced-to-between-5- | yes | 0.955 | 0.953 | entry | 0.95 | resolved | 1.00 | 73 | +0.04 | +0.04 |
| will-harvey-weinstein-be-sentenced-to-between-10 | yes | 0.951 | 0.962 | entry | 0.95 | resolved | 1.00 | 73 | +0.05 | +0.05 |
| will-harvey-weinstein-be-sentenced-to-between-20 | yes | 0.911 | 0.933 | entry | 0.91 | resolved | 1.00 | 73 | +0.09 | +0.09 |
| will-harvey-weinstein-be-sentenced-to-more-than- | yes | 0.999 | 0.957 | entry | 1.00 | resolved | 1.00 | 73 | +0.00 | +0.00 |
| another-pandemic-before-gta-vi | yes | 0.510 | 0.505 | entry | 0.51 | resolved | 0.50 | 70 | -0.01 | -0.01 |
| new-playboi-carti-album-before-gta-vi-421 | yes | 0.470 | 0.470 | entry | 0.47 | resolved | 0.50 | 70 | +0.03 | +0.03 |
| new-rhianna-album-before-gta-vi-926 | yes | 0.460 | 0.470 | entry | 0.46 | resolved | 0.50 | 70 | +0.04 | +0.04 |
| trump-out-as-president-before-gta-vi-846 | yes | 0.500 | 0.495 | entry | 0.50 | resolved | 0.50 | 70 | +0.00 | +0.00 |
| will-bitcoin-hit-1m-before-gta-vi-872-424 | yes | 0.509 | 0.507 | entry | 0.51 | resolved | 0.50 | 70 | -0.01 | -0.01 |
| will-china-invades-taiwan-before-gta-vi-716-644 | yes | 0.500 | 0.495 | entry | 0.50 | resolved | 0.50 | 70 | +0.00 | +0.00 |
| will-gpt-6-be-released | yes | 0.460 | 0.450 | entry | 0.46 | resolved | 0.50 | 70 | +0.04 | +0.04 |
| will-jesus-christ-return-before-gta-vi-665 | yes | 0.520 | 0.515 | entry | 0.52 | resolved | 0.50 | 70 | -0.02 | -0.02 |
| microstrategy-sells-any-bitcoin-by-december-31-2 | yes | 0.210 | 0.190 | entry | 0.21 | resolved | 0.00 | 9 | -0.21 | -0.21 |
| microstrategy-sells-any-bitcoin-by-june-30-2026 | yes | 0.539 | 0.546 | entry | 0.54 | resolved | 0.00 | 9 | -0.54 | -0.54 |
| microstrategy-sells-any-bitcoin-by-may-31-2026 | yes | 0.890 | 0.875 | entry | 0.89 | resolved | 1.00 | 11 | +0.11 | +0.11 |
| starmer-out-by-december-31-2026-936-416-977-234- | yes | 0.280 | 0.285 | entry | 0.28 | resolved | 0.00 | 30 | -0.28 | -0.28 |
| starmer-out-by-june-30-2026-862-594-548-219 | yes | 0.720 | 0.765 | entry | 0.72 | resolved | 0.00 | 30 | -0.72 | -0.72 |
| starmer-out-by-may-31-2026 | yes | 0.960 | 0.961 | entry | 0.96 | resolved | 1.00 | 9 | +0.04 | +0.04 |

## Method

Shares are size_shares or size_usd / entry_price; payout is shares times the settlement price of the traded side (1, 0, or 0.5 on a split settlement); PnL is payout minus stake, before any fee. Days held run from the paper fill to the market's closedTime. A trade without a valid entry price gets no PnL and a reason, as in the scanner's own rule. A second computation (corrected) uses the entry the CLOB day price supports: where the journal's entry only matches as 1 minus entry, the journal stored the other side's price and the corrected entry is 1 minus the recorded one. A leg whose entry matches neither side, has no day price, or was filled after the market's closedTime gets no corrected PnL, only the reason.

The scanner itself is unchanged. The one-line fix (`closed=true` on its Gamma lookup) belongs in the prediction-alpha-bot repository, together with a check that a market is still open before a paper fill is written.
