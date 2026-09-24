# Fed meeting comparison

Date: 2026-09-24. Status: implemented; all five meetings compared; publication verification pending.

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

- [x] Test and implement pure mapping, CSV parsing, as-of alignment and scoring
  in `app/fed_comparison.py` and `tests/test_fed_comparison.py`.
- [x] Collect and archive available real Polymarket/CME data with
  `scripts/collect_fed_comparison.py`; report inaccessible sources explicitly.
- [x] Implement the page and connect the existing navigation/research route.
- [x] Check backend math, frontend empty/data states, browser interactions,
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

The public CME Downloads screen starts at April 2026. March was recovered
from 18 public SinoPac PDF reports (11 February to 17 March). These reproduce
CME FedWatch target-range tables rounded to 0.1 percentage point. The importer
validates report/table date, header ranges, spatial cell assignment and total
probability. All 18 extracted March rows were visually checked against PDFs.
Raw PDFs and a derived CSV with input hashes remain local; the website exposes
numeric observations and provenance, not copies of the reports.

For these reports the end of the report date in Chicago is a conservative
availability bound, not a CME closing price. Intraday lead/lag remains unknown.
The holiday gap is retained. All three checkpoints now have five paired
meetings. The March result depends on this time convention and rounding. The UI labels
checkpoint age as distance to the availability bound. Original report time
(08:41, timezone unstated) is retained verbatim in each PDF manifest entry.
The 96-hour rule does not establish actual quote freshness. Reusing an
unchanged archived PDF preserves its original retrieval timestamp.

## Verification and review

10 Python logic tests and 258 web tests passed on the isolated main-based branch. The Node renderer harness is
included in unittest discovery. 160 API-view tests and 11 published-payload
tests passed; FastAPI TestClient returned the expected research payload.
Ruff, JavaScript syntax and diff whitespace checks passed. Static build passed
to `artifacts/fed-preview`; graphify was updated. All 70 archived source hashes
match, and the published scores recompute exactly from the saved series.

Browser checks covered the live local page, all three actual x-axis windows,
all Brier horizons, March archive provenance, December comparability gating, source
selection and both themes. No page errors were observed. Desktop layout is
the existing terminal convention.

Independent code review found one pairing bug, fixed with a failing-then-passing
regression: when the latest CME observation has an incomplete PM vector, use
the latest earlier complete pair still inside the 96-hour limit. Descriptive
reliability charts explicitly disable binomial confidence intervals because
outcomes within a meeting are dependent. Ponytail review found no unnecessary
dependencies or abstractions.

Fed changes are isolated on `codex/fed-comparison`; unrelated edits remain in the original checkout. Publication is pending final verification.
The stored analysis is in `docs/research/fed_comparison_2026-09-24.md`.
