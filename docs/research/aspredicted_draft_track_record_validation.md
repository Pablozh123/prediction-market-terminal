# AsPredicted-Entwurf: Out-of-sample persistence of the corrected wallet track-record score

Einreichfertiger Entwurf fuer das AsPredicted-Standardformular (9 Fragen). Vor dem Absenden pruefen und festlegen:

- **Stichtag T1/T2 (unten 2026-07-31) bestaetigen oder anpassen.** Er muss VOR der ersten Auswertung von T2-Daten liegen; einreichen bevor irgendein T2-Outcome angesehen wurde.
- Git-SHA des Methodik-Freezes am Einreichtag eintragen (Platzhalter `<GIT-SHA>`): der Commit-Stand von `app/track_record.py` und `app/calibration.py` am Einreichtag.
- Autor kann bei AsPredicted vorerst privat bleiben; das PDF mit Zeitstempel herunterladen und unter `docs/research/` ablegen.

Antworten unten sind englisch (zitierfaehig), eigene Formulierungen, beschreibend statt prognostisch.

---

**1) Have any data been collected for this study already?**

It's complicated. Period-1 data (historical resolved Polymarket positions up to the split date) exist and have been used to build and explore the rating methodology. Period-2 outcome data do not exist yet: period 2 lies entirely in the future at submission time, and no period-2 outcomes have been observed or analyzed.

**2) What's the main question being asked or hypothesis being tested in this study?**

Does a wallet's corrected composite track-record score, computed only from period-1 data, rank-correlate positively with the wallet's realized edge in the subsequent period 2? The score corrects for leg inflation (NegRisk netting), winner-only feed bias, wash/farm patterns and profit concentration; the hypothesis is that this corrected reading of past performance persists out of sample better than chance. This is a persistence test of a descriptive rating, not a claim that any rating tells anyone what to trade.

**3) Describe the key dependent variable(s) specifying how they will be measured.**

Realized edge per wallet in period 2: mean of (settlement outcome minus entry price) per resolved event, with legs of one NegRisk event netted to a single observation (module `app/calibration.py::realized_edge`, methodology frozen at commit `<GIT-SHA>`). Settlement is read from decisive resolved token prices (<= 0.02 or >= 0.98), with the realized-PnL sign as fallback, identical to the frozen implementation.

**4) How many and which conditions will participants be assigned to?**

No assigned conditions; this is an observational split-sample design. The single independent variable is the period-1 composite score (module `app/track_record.py::track_record`, key `score`, frozen at commit `<GIT-SHA>`), computed per wallet on period-1 data only. Period 1: all resolved positions settled on or before 2026-07-31 23:59 UTC. Period 2: positions entered after the split date and resolved between 2026-08-01 00:00 UTC and 2026-10-31 23:59 UTC.

**5) Specify exactly which analyses you will conduct to examine the main question/hypothesis.**

Primary analysis, one test: Spearman rank correlation (rho) between the period-1 composite score and the period-2 realized edge over the qualifying wallet cohort. Success criterion, fixed in advance: rho >= +0.15 with one-sided p < 0.05. Any other cut (per-category correlations, alternative scores, alternative windows) is exploratory and will be labeled exploratory wherever shown.

**6) Describe exactly how outliers will be defined and handled, and your precise rule(s) for excluding observations.**

Excluded before looking at period-2 outcomes: (a) wallets flagged by the frozen wash/farm heuristic (volume >= $25,000 with absolute settled PnL per dollar of volume < 0.005 over >= 5 resolved markets); (b) wallets whose public closed-positions feed is capped on both tails (extremes-only history, >= ~50 wins and >= ~50 losses beyond the cap); (c) market-maker-pattern wallets where more than 50% of period-1 gross profit comes from events in which the wallet held two or more outcomes of the same market (structural share per `pnl_attribution`); (d) wallets with fewer than 30 resolved period-1 events. No outlier trimming on the dependent variable: realized edge is bounded by construction (entry prices in (0,1), outcomes in {0,1}).

**7) How many observations will be collected or what will determine sample size?**

The cohort is every wallet that appears in the public all-time Polymarket PnL or volume leaderboard slices (top 250 each) on the split date and passes the rules in (6). Target floor: 30 qualifying wallets. If fewer than 30 qualify, the result will be published as "insufficient sample, no verdict" — that outcome is considered valid and citable, not a failure to report.

**8) Anything else you would like to pre-register?**

Commitment to publish the result in either direction within 14 days of the period-2 close (by 2026-11-14): if the criterion is met, as a positive persistence result with effect size and CI; if not, as the first entry of a public negative-results register with the same numbers. The methodology is frozen at commit `<GIT-SHA>`; any code change to the scoring path between submission and evaluation will be disclosed as a deviation note. Analyst degrees of freedom outside this document are treated as exploratory.

**9) Give a title for this AsPredicted pre-registration.**

Out-of-sample persistence of a corrected Polymarket wallet track-record score (period-1 rating vs period-2 realized edge).
