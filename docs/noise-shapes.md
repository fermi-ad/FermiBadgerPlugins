# Non-Gaussian read noise: profiles, a robust GP, and measured-value risk

2026-11-19. Follows `docs/logger-read-noise.md` (the noise's size, shape, and correlation
from the data logger) and `docs/heteroskedastic-noise-model.md`. Per-family fits:
`docs/noise-shape-fit.md`. Patches: `xopt-3.2.2-noise-shapes`, `badger-1.6.0-noise-shapes`.

## What the logged noise looks like

Two different things make it non-Gaussian:

- **Shoulders and tails**: a continuous shape with more weight than a Gaussian beyond about
  1-2 sigmas.
- **Gross outliers**: rare, distinct events far outside it (pulse dropouts on L:D7TOR about
  200 sigmas low, efficiency dips and trips on B:BOOEFF). Beyond 8 robust sigmas:
  0.14-1.0 % of readings (`gross_outlier_rate` in each profile).

Fitting one smooth distribution to both fails: to give an outlier 100 sigmas out any
likelihood, every family flattens its tails everywhere (GaussExp splices collapse to the
0.1 floor). So the two are handled apart: gross outliers by a robust GP, the rest by a
noise shape.

## The noise shape: GaussExp

New term, **GaussExp** (the two-sided form of a "Crystal Ball" fit; the classic Crystal Ball
has a power-law tail on one side): a Gaussian core between -kL and +kR sigmas, an
exponential tail beyond each splice, the density and its first derivative continuous at
both. In sigma units z: log f = -z^2/2 inside, kL^2/2 + kL z below -kL, kR^2/2 - kR z above
+kR. Four parameters (center, sigma, kL, kR); the CDF needs only Phi and exp, so it is
cheap and differentiable inside an acquisition function (unlike Student-t or skew-t, whose
CDFs torch lacks).

Fit (`scripts/noise_shape_fit.py`): residuals of each reading from the median of the other
19 readings of its steady window (no false cusp at 0, no dropout leaking into its
neighbors), in units of the window noise at that level; maximum likelihood truncated to 8
robust sigmas. kL and kR change only moderately with that cut (6 to 12 sigmas: B:BOOEFF
0.67-0.68 / 1.11-1.13, G:LINEFF 1.56-1.58 / 1.22-1.24, L:TK1RAD 1.23-1.52 / 1.38-1.59,
L:D7TOR 1.67-2.13 / 2.67-3.07); without it they collapse to 0.1-0.6.

| device | kL | kR | gross outliers | held-out exceedance / alpha at 1 %, 5 % (low; high) |
|---|---|---|---|---|
| L:D7TOR | 1.86 | 2.70 | 0.26 % | 1.04, 1.01; 0.79, 0.92 |
| L:TK1RAD | 1.36 | 1.50 | 1.0 % | 0.94, 0.88; 1.11, 1.09 |
| G:LINEFF | 1.57 | 1.23 | 0.14 % | 0.95, 1.16; 4.36, 1.98 |
| B:BOOEFF | 0.68 | 1.13 | 0.43 % | 0.10, 0.26; 0.18, 0.48 |
| B:BLMLAM | 8 (none) | 0.60 | 0.18 % | 1.83, 2.53; 1.06, 0.95 |

Held out: fitted on the first half of the steady windows in time, tested on the second
(1 = calibrated; > 1 understates that tail's risk). L:D7TOR and L:TK1RAD are calibrated;
G:LINEFF's second week had more upward excursions and B:BOOEFF's was quieter: the shape
drifts from week to week, which is what the staleness check below is for. B:BLMLAM reads
in steps of about 1/3 sigma, so its low side is not resolved.

Even with gross outliers set apart, the shapes matter on each device's long side (low for
L:D7TOR, L:TK1RAD, and B:BOOEFF; high for G:LINEFF and B:BLMLAM): 1 % quantiles 2.48-3.38
sigmas (Gaussian: 2.33) and 0.1 % quantiles 3.68-5.49 (Gaussian: 3.09). B:BOOEFF's low side,
for one, needs 5.0 sigmas of margin at 0.1 % where a Gaussian gives 3.1. On the short side
they are near Gaussian (1 %: 2.20-2.49; B:BLMLAM's low side, 1.62, is not resolved).

Ruled out on the same data (`docs/noise-shape-fit.md`): Gaussian (its sigma, inflated by
the outliers, overstates the 1-5 % tails yet understates 0.1 % tails by up to 7.5 times),
skew-normal (Gaussian tails), the classic Crystal Ball (Gaussian on its other side: 3.1-3.9
nats per reading worse than a Gaussian for L:D7TOR and B:BOOEFF). Student-t, Johnson SU, and Jones-Faddy skew-t fit the untruncated
data 0.08-0.46 nats per reading better than GaussExp (B:BLMLAM aside), but out of sample
every family understates at least one 0.1 % tail by 1.6-10 times alpha, because the
outlier rate changes with time.

## Profiles

`plugins/noise_profiles/<device>.yaml` (':' written '_'), written by

    pixi run python scripts/logger_noise.py --end <date> --days <n> --devices <device>
    pixi run python scripts/noise_shape_fit.py <cached pull> --profiles plugins/noise_profiles

Each holds kL and kR (all that the risk tolerance uses: the noise's size comes from the
run's own GP), the shape's standardized moments, sigma vs level, the gross-outlier rate,
the held-out calibration, the source pull, and the fit date. Refresh by hand when the
staleness check says so, or after a long shutdown.

## In a run

- **Risk tolerance, measured value.** P(a fresh reading at x satisfies the constraint) =
  E over the GP's latent f of P(noise < bound - f), the noise of the GP's own size (its
  observation noise at x) with the profile's shape, or Gaussian without a profile. This
  replaces the earlier P on the latent value alone, so every tolerance now includes the
  noise. Computed by quadrature over whichever of f and the noise has the larger spread
  (Gauss-Hermite over f, or Gauss-Legendre on the GaussExp core plus Gauss-Laguerre on its
  tails); within 3.2 Monte Carlo standard errors of 4e6-draw Monte Carlo over 144 cases,
  latent spread / noise from 0.02 to 50, probabilities 0.05 % to 99.9 %.
- **Effect** (`tests/noise_shapes_test.py`): a constraint with a strongly skewed upper tail
  (kR = 0.5) at a 1 % tolerance. Assuming Gaussian noise, the proposed point's true chance
  of a violating reading is 3.7 %; given the shape, 1.1 %.
- **Robust GP**, `gp_constructor.robust_outcomes: [names]`: botorch's
  `RobustRelevancePursuitSingleTaskGP` (Ament et al. 2024, relevance pursuit) gives
  individual training points extra noise when the data say they are outliers. One
  150-sigma outlier among 25 points pulls a standard GP's mean 0.34 off the truth there;
  the robust GP's, 0.001. Fits take several times longer (several outlier counts are
  tried). With a `_var` column the robust GP takes it as fixed noise (no heteroskedastic
  noise model); not combined with `use_cached_hyperparameters`. Off unless named.
- **Staleness check**: each step, each shaped constraint's leave-one-out residuals (closed
  form for an exact GP) are compared with its shape by an Anderson-Darling test; at
  p < 0.01 the log says so once per run: a warning when the run's tails are heavier
  (higher excess kurtosis; risk tolerances may be optimistic), a note otherwise. The cause
  may be a stale profile or a model that misfits. In an offline check (one variable, 20
  seeds each) it flagged all 80-point runs with 10 % gross outliers and no clean run, but
  none at 30 points: it needs about 50 points or more to say anything.

## Which shape keeps a tolerance honest (calibration, 2026-11-24)

`scripts/heteroskd_calibration.py --shapes` (tables: `docs/heteroskd-shapes-calibration.md`):
the one-variable mock-up, 50 points, 20 seeds; each shape fitted to 20,000 draws of the
scenario's noise (GaussExp cut at 8 robust sigmas, as the profiles are; Student-t and
Jones-Faddy skew-t untruncated); the measured-value risk computed with that shape. Share
of fits whose tolerance edge (settings predicted 1 - alpha to 1 - alpha/5 safe) violates
more than alpha, noise of constant size, so only its shape is at stake:

| noise | readings, GP | alpha | Gaussian | GaussExp | Student-t | skew-t |
|---|---|---|---|---|---|---|
| Student-t, 3 dof | 1, standard | 1 % | 0.60 | 0.50 | 0.10 | 0.05 |
| lognormal (skewed) | 1, standard | 1 % | 0.85 | 0.75 | 0.90 | 0.30 |
| lognormal | 1, standard | 5 % | 0.50 | 0.20 | 0.90 | 0.35 |
| lognormal | 5-mean, standard | 1 % | 0.95 | 0.10 | 0.70 | 0.15 |
| spikes (3 %, +8 sigma) | 5-mean, heteroskd | 1 % | 1.00 | 0.40 | 0.80 | 0.25 |
| spikes | 1, standard | 1 % | 1.00 | 1.00 | 1.00 | 1.00 |

- Skew-t is the best or tied-best shape at a 1 % tolerance; GaussExp is close behind and
  best in some 5-reading cases; symmetric Student-t fails on skewed noise (worse than
  Gaussian there). Both skew-t and GaussExp clearly beat Gaussian.
- Spikes more frequent than the tolerance (3 % spikes at 1 %): no shape is honest. That
  needs a mixture (a stated outlier rate at a stated size), not a smooth tail.
- What a shape cannot fix: with Gaussian noise and the Gaussian shape, 15-30 % of fits
  still overshoot at the edge (the GP's own uncertainty); and where the noise's size
  varies across the range, a standard GP on single readings misjudges it (the original
  scenarios: lognormal single readings overshoot in all fits at 1 % whatever the shape).
  A safety factor or recalibration from the run's residuals is still needed for those.
- Skew-t is now a profile family (next section).

## Skew-t profiles (2026-11-24)

New term, **skew-t**: the Jones-Faddy skew-t, parameters a and b; its left tail falls as
|e|^-(2a+1) and its right as e^-(2b+1) (a = b: a Student-t with 2a degrees of freedom).
Power-law tails, heavier than GaussExp's exponential ones. The risk needs a finite variance
(it standardizes the shape), so a and b must exceed 1.

- In the xopt patch: `SkewTShape`, `make_shape({family: jf_skew_t, a, b})`. Its CDF, a
  regularized incomplete beta function, is tabulated once (log F and log(1 - F) on 16001
  points uniform in asinh(e), |e| <= 1e4) and interpolated in torch: within 1e-6 of scipy,
  and within 0.1 % relative in tails below 1e-3. Quadrature over the noise: 96
  Gauss-Legendre points in probability. Checked against Monte Carlo
  (`tests/noise_shapes_test.py`).
- Profiles (`scripts/noise_shape_fit.py --profiles`) carry both families, fitted to the
  same residuals with the same 8-sigma cut; `family` picks the one whose more optimistic
  1 % tail is lower held out (safety first: an optimistic tail breaks a tolerance, a
  cautious one only costs performance), skew-t on a tie, never a skew-t with a or b below
  1.05. Held-out exceedance / alpha at 1 %, low and high side:

| device | family | GaussExp | skew-t (a, b) |
|---|---|---|---|
| L:D7TOR | skew-t | 1.04, 0.79 | 0.91, 0.75 (7.98, 9.87) |
| L:TK1RAD | skew-t | 0.94, 1.11 | 0.90, 1.01 (2.77, 2.93) |
| G:LINEFF | skew-t | 0.95, 4.36 | 0.99, 4.34 (3.41, 2.88) |
| B:BOOEFF | GaussExp | 0.10, 0.18 | 0.15, 0.26 (2.30, 3.55) |
| B:BLMLAM | GaussExp | 1.83, 1.06 | 1.83, 0.35 (2.77, 1.00) |

  The differences between the families are small next to the drift between the two
  halves of each pull (G:LINEFF's high side, 4.3 for both): the staleness check and
  refreshed profiles matter more than the family. The rule was set after seeing a first
  pass (which weighed cautious and optimistic tails alike); its reason is the tolerance's
  purpose, not the result.

## Limits and open avenues

- Shapes are of single readings. Templates read one event per reading (`average_events`
  1), so that is what the GP sees; with N > 1 an average is more Gaussian and correlated
  pulses make `s^2/N` too small (`docs/logger-read-noise.md`, R). Untested.
- The noise's size is the GP's (homoskedastic, or heteroskedastic from `_var`), not the
  profile's sigma vs level; using the profile's size as a prior is unexplored.
- Profiles exist for five devices; L:TK4RAD and L:TUNRAD read in steps about one sigma
  wide, so a continuous shape is not meaningful for them (Gaussian is used).
- Only constraints carry shapes (the risk tolerance is on constraints); objectives with
  profiles are not checked for staleness.
- No template turns on `robust_outcomes` yet; L:D7TOR (dropouts) is the first candidate.
- Untested on the machine.
