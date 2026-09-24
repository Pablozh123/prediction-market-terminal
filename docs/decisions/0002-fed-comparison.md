# Fed meeting comparison

Date: 2026-09-24. Status: implementation in progress.

## Scope and design

Add `#fed` to the existing vanilla JS terminal. Compare Polymarket YES prices
with CME FedWatch probabilities derived from 30-Day Fed Funds futures. Keep
the existing read-only research endpoint and static JSON fallback. No new
dependency, trading path, scheduled task or credentials are required.

Archive the five latest scheduled decisions (18 March, 29 April, 17 June,
29 July, 16 September 2026), plus October and December. Federal Reserve
statements verify the outcomes: four holds at 350–375 bp, then a 25 bp hike
to 375–400 bp. Preserve source files under `data/fed_comparison/raw/` and
publish a reproducible comparison under `public/data/fed_comparison.json`.

The 30/7/1-day controls change the x-axis to time remaining until the 14:00
America/New_York decision. Probabilities remain on a 0–100% scale. An
additional full-history control allows upcoming meetings outside 30 days.

## Comparability and scoring

CME target ranges are unconditional levels. Polymarket contracts resolve to
the change at one meeting. Only map CME levels to change buckets after the
previous meeting and when its actual target upper bound is known. Never
subtract an expected prior rate or assume December's October outcome.
Aggregate tails using each Polymarket contract's actual bucket definition.

CME CSV dates have no intraday timestamps. Assign the END of that date in
America/Chicago conservatively, exclude decision-day EOD rows, and label
the convention. Match Polymarket as of this same timestamp (at most 2 h old).
Checkpoints T-30/T-7/T-1 use the latest common prior observation, at most
96 h old to allow weekends. No future observations, interpolation of missing
history, settlement prices, or invented zeroes. Show observation age.

Normalize a complete Polymarket bucket vector by its sum for multiclass
Brier scores only (sum of squared errors, range 0–2); retain raw prices for
curves and spreads. Require all outcomes and a plausible sum (0.9–1.1).
Compare scores on paired meetings only. Report n; five decisions cannot
establish calibration. Per-outcome reliability bins are descriptive and
dependent within each meeting. Price differences are not executable arbitrage
or P&L because payoff, timing, basis, fees and market depth differ.

## Implementation plan

- [ ] Test and implement pure mapping, CSV parsing, as-of alignment and scoring
  in `app/fed_comparison.py` and `tests/test_fed_comparison.py`.
- [ ] Collect and archive real Polymarket/CME data with
  `scripts/collect_fed_comparison.py`; report inaccessible sources explicitly.
- [ ] Implement the page and connect the existing navigation/research route.
- [ ] Check backend math, frontend empty/data states, browser interactions,
  static build and source provenance. Update this record and `docs/HANDOFF.md`.

## Sources

- https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
- https://www.federalreserve.gov/newsevents/pressreleases/monetary20260916a.htm
- https://www.cmegroup.com/articles/2023/understanding-the-cme-group-fedwatch-tool-methodology.html
- https://www.cmegroup.com/tools-information/quikstrike/cme-fedwatch-tool-user-guide.html
- https://cmegroupclientsite.atlassian.net/wiki/spaces/EPICSANDBOX/pages/457320466
- https://gamma-api.polymarket.com/events/slug/fed-decision-in-september-762
- https://clob.polymarket.com/prices-history

## Data limitation observed during collection

The public CME Downloads screen starts at April 2026. The March export returns
HTML without data. Four completed meetings and two future meetings have CSV
downloads. Do not represent missing March CME history as a completed comparison.
An entitled FedWatch API or an authentic older export can fill this gap.
