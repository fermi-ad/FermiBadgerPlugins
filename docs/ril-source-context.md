# RIL objectives and their context: ion sources, beam rate, and the RIL knobs

2026-11-20. Question (user): do the ion-source parameters (parameter page L48, sub-page
<1>, tabs SRC_A and SRC_B) and the Booster's injection turns predict what the RIL's
objectives reach, and do they act as context, changing how the objectives respond to the
knobs? Scripts: `scripts/logger_series.py`, `scripts/event_counts.py`,
`scripts/ril_context_study.py` (boosted trees), `scripts/ril_context_gp.py` (GP kernels).
Tables: `docs/ril-source-context-results.md`, `docs/ril-source-context-gp.md`.

## Data

- 90 days of logged history, 2026-08-22 to 11-20, in 5-minute bins: 94 devices (both
  sources' parameters, the turns `G:TURN13..1D`, the RIL knob settings, the objectives).
  Not logged: the turns settings (their readings are), the gas-pressure setpoints,
  `L:D7LMSM`.
- Beam cycles per bin by type, from the clock-event history: all beam cycles ($10), beam
  to MiniBooNE/BNB ($1D), NuMI ($19), Booster studies ($17), MI studies ($14-16), and
  others; and a turn-weighted rate (cycles of each type x its turns), a proxy for the charge
  the Linac delivers.
- Which source fed the RIL: from the logbook (source B until the swap to A on 2026-09-15,
  08:39-11:23; A after), confirmed by `L:SRCNOW` from 10-17. Not from the toroid currents:
  the source not in use is often run (re-commissioning, studies) at full current. Each
  source parameter is also taken from the source in use (`active_<param>`).
- Bins with beam: 14530 (the beam-on median of `L:D7TOR` above 5 mA; untested cut).
  Integrating loss monitors (`L:TK4RAD`, `L:TUNRAD`) read the same on beam and null cycles
  (event tagging, `scripts/event_tag.py`), so their bins are not cycle-type mixtures.

## Method

Held-out weeks (14): every score is on whole weeks the model never saw, so neighboring
bins cannot leak. Boosted trees (scikit-learn defaults; untested): R2 and the skill of a
quantile model for the attainable level (10th percentile of losses, 90th of the toroid and
efficiency) against a constant. Permutation importance for the context model (source in
use, turns, beam cycles). Offline self-checks of both scripts on synthetic data
(`--selftest`).

## Results (boosted trees)

Held-out R2, by predictor group (full table with quantile skill: the results file):

| target | active source | + beam rate | RIL knobs only | all |
|---|---|---|---|---|
| L:D7TOR (output current) | 0.86 | 0.86 | 0.47 | 0.87 |
| L:TUNRAD (loss) | 0.72 | 0.80 | 0.65 | 0.84 |
| L:TK1RAD (loss) | 0.51 | 0.71 | 0.61 | 0.75 |
| L:TK4RAD (loss) | -0.72 | -1.16 | -0.57 | -1.48 |
| G:LINEFF (efficiency) | -0.42 | -0.29 | -0.05 | -0.25 |

- The source in use, and above all its extractor-voltage setting (`active_EXTSV`), plus
  the beam rate (turn-weighted) explain most of the week-to-week variation of the output
  current and of `L:TUNRAD` and `L:TK1RAD`, more than the RIL knobs do. Top predictors:
  `L:D7TOR`: `active_EXTSV`, which source; `L:TUNRAD` and `L:TK1RAD`: `active_EXTSV`,
  turn-weighted rate (and BNB cycles for `L:TK1RAD`).
- `L:TK4RAD` (the operations loss template's objective) is not predicted by anything here:
  it varies less across weeks than within them (std of weekly medians 5.9 vs 6.8 within),
  so there is little level for context to explain; its quantile skill is also negative.
- `G:LINEFF`: its mean is not predictable across weeks, but its upper range partly is
  (quantile skill 0.19-0.31).
- Weekly levels: `L:TUNRAD` about doubled in weeks 40-43 (108-132 vs 50-65); `L:TK1RAD`
  rose from about 14 to 19 in week 40 and to 23 by week 47; `L:D7TOR` rose from 19 mA
  (source B, weeks 34-37) to 23-25 mA (source A, from week 38, the swap).

## Does the context change how the knobs act? (trees)

The same held-out weeks, trees on the RIL knobs plus the context (source in use, turns,
beam cycles), two ways: knob and context features may only add up (scikit-learn
`interaction_cst`: interactions inside each group, none across), or may combine freely.
Ratio: the free model's unexplained variance over the additive one's; well below 1 means
the context changes how the target responds to the knobs (self-check on synthetic data:
1.10 for additive data, 0.02 for interacting).

| target | additive R2 | free R2 | ratio |
|---|---|---|---|
| L:D7TOR | 0.64 | 0.87 | 0.36 |
| L:TUNRAD | 0.79 | 0.76 | 1.11 |
| L:TK1RAD | 0.73 | 0.73 | 1.00 |
| L:TK4RAD | -0.50 | -0.54 | 1.03 |
| G:LINEFF | -0.30 | -0.31 | 1.01 |

- **L:D7TOR: yes.** Letting the knobs combine with the context removes about two thirds of
  the unexplained variance. Located: knobs x the parameters of the source in use gives R2
  0.864 (ratio 0.39), nearly all of it; knobs x beam rate 0.778 (0.63); knobs x which
  source alone 0.642 (1.00: nothing); source x beam with the knobs kept apart 0.642. So it
  is the source settings, not the swap itself or the beam rate, that change how L:D7TOR
  responds to the RIL knobs.
- **L:TUNRAD, L:TK1RAD: no.** Their levels follow the context, but not their response to
  the knobs.
- Sensitivity: learning rate 0.05 / 0.1 / 0.2 gives ratios 0.38 / 0.36 / 0.32 for
  L:D7TOR and 1.10 / 1.11 / 1.02 for L:TUNRAD: the conclusion does not depend on it.

## GP kernels (additive vs interacting)

`docs/ril-source-context-gp.md`: exact GPs (RBF-ARD, 1000 training bins per fold, top 10
context features) predict held-out weeks poorly (best R2 0.36 for L:D7TOR, against 0.86
for the trees) and give inconsistent answers between the additive and interacting
kernels. The week-scale steps in this history (the source swap, operating periods) suit
trees better than a smooth kernel; the GP comparison is inconclusive here, not negative.

## What it means for RIL tuning

- The best RIL knob settings for throughput (L:D7TOR) can shift when the ion source
  settings do, the extractor voltage of the source in use most of all. Record the source
  settings (L48 <1>, tabs SRC_A and SRC_B) with each run, and compare runs within a source
  state.
- Badger's Context column (never moved; read every step and modeled) is the way to give
  the optimizer these settings; the RIL environment does not list them as variables yet.
- For the loss objectives, context explains level, not response: comparing runs needs the
  context, but the optimizer gains less from it. L:TK4RAD (the operations loss objective)
  follows none of it.

## Caveats

- Correlation, not cause: operators retune sources and the RIL together; the source swap
  and operating periods move many predictors at once (week-scale regimes).
- The RIL knobs move only in tuning sessions; their effect is poorly sampled by history.
- Model settings: the trees' learning rate was varied (above) without changing the
  conclusions; their other defaults, the GP context size and training-sample size, are
  untested.
- History is not an experiment: operators may retune the RIL after source changes, which
  also looks like an interaction. A designed test (scan a knob at two source settings)
  would settle it.
