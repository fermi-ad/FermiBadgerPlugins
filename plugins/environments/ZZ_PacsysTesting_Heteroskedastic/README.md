# Pacsys testing: heteroskedastic noise

A testbed for modeling noise that changes across the tuning space
(heteroskedastic noise), on the same ACNET test/scratch devices as
`ZZ_PacsysTesting`. The devices read back exactly what was written, so the
noise is synthetic, with a known size at every setting: a model's estimate can
be scored against the truth.

Template: `development/ZZ_PacsysTesting_Heteroskedastic.yaml`. After a run,
score it: see [Scoring a run](#scoring-a-run).

## What it can tune (variables)

- `G:AMANDA`, `Z:CUBE_X`, `Z:CUBE_Y`, `Z:CUBE_Z` (-100 to 100), as in
  `ZZ_PacsysTesting`. The template tunes `Z:CUBE_X` and `Z:CUBE_Y` over -5 to 5.

## What it can read (objectives, constraints, observables)

Everything `ZZ_PacsysTesting` reads, plus:

- `Heteroskd_f`: the sum over `heteroskd_devices` of (reading − 0.5)², minimum 0 at
  0.5 on each, plus noise of known sigma(x), averaged over `n_samples` draws (as
  averaging over pulses would be on the machine).
- `Heteroskd_f_var`: the variance of that average, estimated from the draws
  (sample variance / `n_samples`). **Select it as an observable**: Xopt then
  models `Heteroskd_f` with its heteroskedastic GP, which also learns how the noise
  varies, so it can predict it at untried settings. Without it, Xopt's standard
  GP assumes one noise level everywhere.
- `Heteroskd_f_true_var`: the true variance of the average, sigma(x)² /
  `n_samples`. Logged only, to score the recovery; never give it to a model.

## Parameters (Machine Interface)

- `settings_role`, `debug`: as in `ZZ_PacsysTesting`.
- `heteroskd_devices`: the devices `Heteroskd_f` and the noise depend on.
- `noise_shape`, with r = distance from `noise_center` (the same value on every
  heteroskd device):
  - `proportional`: sigma = `noise_sigma0` + `noise_scale` × |f|; noise grows
    with the signal (like an intensity reading).
  - `distance`: sigma = `noise_sigma0` + `noise_scale` × r; noisier away from
    nominal.
  - `bump`: sigma = `noise_sigma0` + `noise_scale` × exp(−r² / 2`noise_width`²);
    a localized noisy region.
- `n_samples`: draws averaged per point (at least 2).
- `seed`: for a repeatable noise stream; -1 for a fresh one each run.

## Scoring a run

How well did the model learn the noise? Run, then score the run's file.

1. **Run** the template in `-mini` or `-g` (Continue works too: the continued
   run is scored like any other). Keep `Heteroskd_f_var` and
   `Heteroskd_f_true_var` selected as observables: the first is what the model
   learns from, the second is what the score compares against.
2. **Find the run file.** In the History tab, right-click the run →
   File Path → click the path to copy it. Runs are archived under
   `BADGER_ARCHIVE_ROOT` (see `config.local.yaml`) as
   `YYYY/YYYY-MM/YYYY-MM-DD/ZZ_PacsysTesting_Heteroskedastic-<time>.yaml`.
3. **Score it**, from the repo directory:

   ```
   pixi run python scripts/heteroskd_recovery.py <run file>
   ```

   It fits two models to the run's points, Xopt's heteroskedastic GP (which is
   given `Heteroskd_f_var`) and its standard GP (one noise level everywhere),
   prints a score for each, and writes `<run name>.heteroskd.png` in the
   current directory (`--out <file>.png` to choose; not next to the run, to
   keep the archive to run files). Takes a few seconds.

**Reading the printout.** Two numbers per model, comparing its predicted noise
variance with the true one:

- *median |log10(pred/true)|*: 0 is perfect, 0.1 is typically within ×1.26,
  0.3 within ×2, 1 off by ×10.
- *log corr*: whether the model has the right **shape** (where it is noisy and
  where quiet), whatever the scale: 1 is perfect, around 0 is none. The
  standard GP always has none: it assumes one level.

Each is given **at the run's points**, and, for a run over two variables,
**over the grid**, a uniform grid of the whole range. BO crowds its points at
the optimum, so the first mostly measures that one spot (there a single level
can look fine); the second also counts the rest of the range, including far
from any point, where a model can only extrapolate.

**Reading the picture** (`.heteroskd.png`):

- *Left*: each run point's predicted vs true noise variance, log-log, both
  models. On the dashed line is perfect; a horizontal row is a model that
  assumes one level. The dotted line is the **model floor**: Xopt's
  heteroskedastic GP cannot go below it (see
  [Known limits](#known-limits-of-the-model-found-with-this-testbed-2026-10-25));
  points piled just above it are floor-limited.
- *Middle and right* (two-variable runs only): the true and the learned noise
  over the whole range, on the same color scale; white dots are the run's
  points. Compare shapes: where they differ far from the dots, the model is
  extrapolating.

**What good looks like.** On the live runs of 2026-10-25 (40 points, ±5):
heteroskedastic GP 0.03-0.22 at the points (the high end where BO's cluster
sat on quiet noise the model overstated) and 0.13-0.21 over the grid, log corr
0.96-1.00 and 0.76-0.97; the standard GP 0.07-0.20 and 0.28-2.5, no shape.

**Without the GUI** (repeatable, fixed seed): `pixi run python
scripts/heteroskd_live_run.py [proportional|distance|bump]` runs the template
headless, 8 random points then 32 BO steps, and saves
`logs/heteroskd_runs/<time>-<shape>.yaml` to score the same way. It **writes
to ACNET** (Z:CUBE_X, Z:CUBE_Y; VPN, Kerberos and the `testing` role
needed); it reads their settings first and writes them back at the end, also
on failure.

## Known limits of the model (found with this testbed, 2026-10-25)

- Xopt's heteroskedastic GP (3.2.2) does not resolve noise below about 1e-4 of
  the objective's own variance (its `MIN_INFERRED_NOISE_LEVEL`, applied after
  standardizing). A background much quieter than that is overstated (×35 for a
  `bump` with `noise_sigma0: 0.05` against an objective spread of ~9), though
  the noisy region is still right. Keep `noise_sigma0` above that to test
  recovery, or below it to test this limit.
- The floor scales with the objective's spread over **all** the run's points,
  so widening a range (or seeding from a wide run with Continue) raises it: in
  a `-mini` run continued with `Z:CUBE_X` widened to about ±11, the floor rose
  to 0.12, above the quiet noise at the optimum (0.05-0.1), which the model
  then overstated. Wide sweeps cost noise resolution near the optimum.
- Far from any measured point the learned noise extrapolates (corners of the
  range in `scripts/heteroskd_recovery.py`'s maps).

## Offline test

`tests/heteroskd_noise_test.py` (pacsys FakeBackend, no writes): the observables,
each shape, an unbiased variance estimate, and recovery for each shape
(heteroskedastic GP beats the standard one; log correlation with the truth >
0.6, about 0.9 in practice), plus the noise floor above.
