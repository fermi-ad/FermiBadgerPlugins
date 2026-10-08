# TODO

Open work, roughly in priority order. Session-by-session detail lives in
`docs/progress.md`; this file is just the list.

## Environment and setup

- [ ] **Make pixi the default environment manager** (decided 2026-10-08, deferred).
  Blocked on the MCR installation, which relies on `badger` being on the `PATH`
  after `conda activate`; pixi keeps the env in `.pixi/envs/default` and expects
  `pixi run` / `pixi shell`. Before switching:
  - confirm MCR hosts (`config_MCR.yaml`, `/home/lcape/...`) can reach conda-forge
    and PyPI and can write a pixi cache;
  - decide how `badger` reaches the operator's `PATH` there (a `pixi shell-hook`
    line in the profile, or a wrapper script).
  Then: `pixi.toml` with a `default` environment and an `onsite` feature that adds
  `acsys` from the FNAL index (so off-site installs still work); committed
  `pixi.lock` for osx-arm64 and linux-64; patches/config/verify as `pixi run setup`;
  a `bootstrap.sh` that installs pixi if missing and runs install + setup; swap the
  fifteen `conda run -n FermiBadger_env` references (CLAUDE.md, test docstrings,
  README, Dockerfile); keep `setup.sh` one release as a legacy wrapper, then generate
  any conda export from the lock (`pixi project export conda-environment`) rather
  than hand-maintaining `environment.yml`. Do not run both paths as equals: one
  source of truth.
- [ ] Offer the three-line turbo.py fix in `patches/xopt-3.2.2-turbo-serialization.patch`
  upstream to xopt-org/Xopt.

## Pacsys interface (needs the machine)

- [ ] Live check with `development/ZZ_PacsysTesting.yaml`: a setting lands, no
  readback warning fires.
- [ ] `01_Linac_RIL_tuning_Pacsys` with `average_events: {default: 3}`: expect each
  evaluation ~3 cycles slower and smoother objectives.
- [ ] Try `development/01_Linac_RIL_tuning_Pacsys.yaml` at all (untested copy of the
  Acsys template).
- [ ] Pick an array device for a first `|rms` observable.

## Later

- [ ] Ramps as variables (Booster skew quads via pacsys `BoosterSQRamp`) once a
  Booster environment exists; `sim_configs/Booster/` lattice bundle is still untracked.
- [ ] `-mini` has no "Save as Template" button (upstream removed it; the handler
  `save_template_yaml` still exists). One button in the mini env box if wanted.
- [ ] Bulk-supply ratings in the RIL environments are 7.0 A stand-ins pending expert
  confirmation.
