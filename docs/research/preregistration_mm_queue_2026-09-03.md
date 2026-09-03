# Pre-registration: does symmetric market making pay once queue position is modelled?

Frozen 2026-09-03, before any day of the test window was recorded. Code as
of pull request #148 on this repository (`src/mm_pnl.py` queue models,
`src/mm_queue_study.py` driver). Internal pre-registration, not submitted
to AsPredicted; the git history is the timestamp.

## Background

The published five-day study (`mm_pnl_stream-5tage.md`) leaves the sign of
market-making PnL unidentified: the touch fill model puts the daily total at
(-12,121, -2,413) USD and the tape model at (+881, +5,889), and what
separates them is queue position, which neither models. Pull request #148
adds two fill models that stand in line: `queue_front` (cancels ahead of us
leave from the front) and `queue_back` (they leave from the back, and a
level the recorder never showed counts as crowded until seen). On one day
of data they landed at +18 and +11 cents per fill against +51 for tape.
One day is not a result. This document fixes how the question is answered.

## Hypothesis

H1: Symmetric quoting at the chosen parameters earns a positive daily total
net of adverse selection, inventory drift and maker rebate, in both queue
fill models, over the test window.

H0: It does not, in at least one of the two.

## Data

- Source: this project's own event-driven Polymarket stream recorder
  (`stream_books_<day>.csv`, `stream_trades_<day>.csv`, and from
  2026-09-03 the depth sidecar `stream_depth_<day>.csv`).
- Training window: every stream day from 2026-07-30 to 2026-09-03
  inclusive. These days carry the size at the touch only; queue positions
  one tick or more behind the touch are the models' blind spot there.
- Test window: 2026-09-04 to 2026-09-17 inclusive, fourteen calendar days,
  none of which exists at the time of freezing. These days carry the top
  five levels with sizes.
- Exclusions, applied identically to both windows by the existing loader:
  snapshots with a mid outside (0.05, 0.95), spreads above 0.10 or at zero,
  tokens with fewer than 20 snapshots on a day.

## Candidates and choice rule

Six candidate parameter sets, the product of half spread in {0.005, 0.01,
0.02} and gamma in {0, 0.08}, all at zero requote latency, quote size 50
USD, inventory cap 250 USD, sports fee category (the published defaults).

Every candidate is scored on every training day separately, mark-to-mid
horizon the day. The chosen set is the one with the highest total USD in
`queue_back` over the training days, among candidates with at least 1,000
fills there. `queue_back` is the pessimistic model, so a candidate that wins
there did not win by assuming the front of the line. If no candidate
qualifies, the test window is not run and that is the result.

Gamma and half spread are chosen this way; nothing else is tuned. Latency
stays at zero in the primary test.

## Primary metric and success threshold

Primary metric: the daily total USD (spread earned + markout + late drift +
maker rebate) of the chosen set on the test window, one number per day, in
each queue model.

H1 is supported if the day-level block-bootstrap 95% interval of the daily
total lies entirely above zero in **both** `queue_front` and `queue_back`.
It is rejected if either interval contains or lies below zero. There is no
partial credit: one model above zero and the other not is a rejection, and
is reported as "not identified, again".

Sample floor: at least ten test days with data. Fewer than ten, or fewer
than 1,000 fills in either model over the window, is published as
"insufficient sample", not as a pass or a fail.

## Secondary, exploratory, reported but not scored

- The same at 0.25 s requote latency (the one-day smoke turned negative
  there).
- The gap between `queue_front` and `queue_back` per fill, as the width of
  what the paper model can say.
- Share of fills that were partial, mean wait until fill, share of joins at
  a level with unobserved depth.
- The tape model at the published parameters, as the optimistic reference.

## What may change between freeze and test

Nothing in the quoting rule, fill models, candidate grid, choice rule,
metric or threshold. A defect found in the code before the test is scored
is fixed, logged in this document with the commit, and the training window
is re-run under the fix; the test window is still scored once. A defect
found after scoring is reported next to the result, not used to re-score.

## Reporting

One report (`mm_queue_test.md`) written by the driver from the frozen
rows, whichever way it comes out, linked from the research index and the
preregistrations register. Read-only research; no order is placed by
anything in this repository, and no profitability claim follows from a
pass.
