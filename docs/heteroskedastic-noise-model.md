# How Xopt models per-point noise (heteroskedastic GP)

Notes from reading Xopt 3.2.2 and botorch 0.17.2, 2026-11-18, so this need not be
rediscovered. Calibration results: `docs/heteroskd-calibration.md`.

## Where the variance comes from, and how it reaches the model

- The environment supplies it: for an outcome (objective, constraint, or observable)
  `name`, a key `name_var` in the dictionary `get_observables` returns, holding the
  variance of the recorded value. With `average_events` N, that is s²/N, where s² is
  the sample variance of the N events. Variables (settings) have no noise in this model.
- Badger's evaluator (`badger/routine.py`, `evaluate_point`) stores every returned key
  as a column of the run's data row; nothing needs listing in the VOCS. A `_var` listed
  as a VOCS observable instead gets a GP of its own, which is wasted work.
- Xopt pairs the columns by name and row (`xopt/generators/bayesian/utils.py`,
  `get_training_data`): `train_Yvar` from `name_var`, row by row with `train_Y`. When
  it is present, the outcome's model is an `XoptHeteroskedasticSingleTaskGP`.
- The suffix means variance, not variable. An outcome whose real name ends in `_var`
  would be taken for another outcome's variance.

## The noise model

`xopt/generators/bayesian/custom_botorch/heteroskedastic.py`:

- A second GP, fitted to log(variance) (`outcome_transform=Log()`), over the same inputs.
- Inputs are rescaled to [0, 1] across each variable's range in the VOCS (the
  template's window), so length scales are fractions of the window, one per variable.
- Kernel: none passed by Xopt, so botorch's default
  (`get_covar_module_with_dim_scaled_prior`): RBF (squared exponential), one length
  scale per variable, LogNormal prior with loc sqrt(2) + log(d)/2 and scale sqrt(3)
  (median about 4.1·sqrt(d) ranges, so smooth fits are favored, but the prior is
  broad), and a hard floor of 0.025 of the range.
- The noise GP has its own noise on the log-variance values (a smoothed-box prior over
  log noise from -3 to 5). For Gaussian noise, log(s²) scatters with variance about
  2/(N-1): N = 3 gives 1.0, N = 5 gives 0.5.
- It is fitted together with the main GP (its marginal likelihood is added to the main
  one: `NoiseModelAddedLossTerm`).
- Floor on the inferred noise: `MIN_INFERRED_NOISE_LEVEL` = 1e-4, after the outcome is
  standardized, so about 1e-4 of the outcome's variance over all the run's points.
  Quieter noise is overstated (x35 in a testbed case), and widening the ranges (or
  seeding from a wide run) raises the floor (testbed README, "Known limits").

## How far one point's variance reaches

Between two points r apart (in fractions of each variable's range), the modeled
log-noise is correlated by exp(-r²/2l²), l the learned length scale: 0.61 at r = l,
0.14 at 2l, 0.01 at 3l. So a point's variance shapes the modeled noise within about
2l. Because l is a fraction of the window, the same physical distance counts as
closer when the window is wider.

## Calibration findings (2026-11-18)

`scripts/heteroskd_calibration.py`: one variable, a constraint c(x) that must stay below
0.8, n = 20 or 50 random settings, N draws averaged per setting, seven noise scenarios,
20 seeds, Xopt's heteroskedastic GP (with `c_var`) against its standard GP. Full medians:
`docs/heteroskd-calibration.md`; per-fit rows: `docs/heteroskd-calibration.csv`.

- Noise map: in the scenarios whose noise varies (proportional, bump, step; 50 points),
  the heteroskedastic GP's median error in the noise variance falls from a factor of
  1.9 at N = 2 (|log10| 0.28) to 1.2 at N = 20 (0.07). The standard GP stays near a
  factor of 2.5 (0.36-0.42) whatever N, and a factor of 10-13 for the localized bump.
- Overall probability calibration (mean |predicted - actual| chance that a fresh
  recorded value satisfies the constraint): heteroskedastic 0.012-0.037 vs standard
  0.041-0.083 (50 points); about half the error. 20 points: 0.022-0.063 vs 0.057-0.104.
- Tails, right at a 5 % risk tolerance's edge (settings predicted 95-99 % safe):
  medians are honest for Gaussian noise (actual violation 1.7-3.1 %), but in 13-26 % of
  heteroskedastic fits the edge violates more than 5 %, against 0-22 % for the standard
  GP, which is more conservative there (it overstates the noise in quiet regions).
- Non-Gaussian noise breaks the tails: the edge violates more than 5 % in 62 % (skewed,
  lognormal), 70 % (rare spikes), and 32 % (Student-t, 3 dof) of heteroskedastic fits,
  against 29 %, 42 %, and 13 % for the standard GP. Worst single settings reach 10-17 %
  actual violation at a predicted 5 %. The sharper model trusts its Gaussian tails more.
- Spikes also bias the recorded mean, so even the true value's 95 % intervals cover
  only 64-85 % of the time.
- N: N = 2-3 is poor; N = 5 workable; N = 10 roughly halves the noise-map error again.
- The 0.025 length-scale floor is hit in 2-10 % of fits (17 % with spikes), so the
  earlier single fit at the floor was an unlucky case, not the rule.
- Limits: one variable, one constraint shape, one bound; the 95-99 % band holds only a
  few settings per fit, so per-fit rates are noisy. Higher dimensions untested.

What this suggests (not yet tried): the heteroskedastic GP is worth making the default
for its noise map and overall calibration (with N >= 5), but a stated risk tolerance is
not guaranteed at the tail, especially if the machine's noise is skewed or spiky.
Options: a safety factor on the tolerance, recalibrating the predicted probabilities
from the run's own residuals, or a heavier-tailed or transformed noise model. The
machine-data check (is the noise Gaussian?) decides how much this matters.

## Seen once, explained by the study

A quick fit (one variable, noise standard deviation rising linearly from 0.05 to 0.55
over the range, N = 5, 30 random points, one seed): main GP l = 0.41, but the noise GP's
l sat at its 0.025 floor with log-variance noise 2.9 (expected about 0.5 for N = 5), so
it did not smooth a strong, simple trend. The calibration study found this in only 2-10 %
of fits (above).
