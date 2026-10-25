# Pacsys testing: heteroskedastic noise

A testbed for modeling noise that changes across the tuning space
(heteroskedastic noise), on the same ACNET test/scratch devices as
`ZZ_PacsysTesting`. The devices read back exactly what was written, so the
noise is synthetic, with a known size at every setting: a model's estimate can
be scored against the truth.

Template: `development/ZZ_PacsysTesting_Heteroskedastic.yaml`. After a run,
score it: `pixi run python scripts/heteroskd_recovery.py <run file>`.

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

## Known limits of the model (found with this testbed, 2026-10-25)

- Xopt's heteroskedastic GP (3.2.2) does not resolve noise below about 1e-4 of
  the objective's own variance (its `MIN_INFERRED_NOISE_LEVEL`, applied after
  standardizing). A background much quieter than that is overstated (×35 for a
  `bump` with `noise_sigma0: 0.05` against an objective spread of ~9), though
  the noisy region is still right. Keep `noise_sigma0` above that to test
  recovery, or below it to test this limit.
- Far from any measured point the learned noise extrapolates (corners of the
  range in `scripts/heteroskd_recovery.py`'s maps).

## Offline test

`tests/heteroskd_noise_test.py` (pacsys FakeBackend, no writes): the observables,
each shape, an unbiased variance estimate, and recovery for each shape
(heteroskedastic GP beats the standard one; log correlation with the truth >
0.6, about 0.9 in practice), plus the noise floor above.
