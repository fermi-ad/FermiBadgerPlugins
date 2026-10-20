# TODO

Open work, roughly in priority order. Session-by-session detail lives in
`docs/progress.md`; this file is just the list.

## Production migration (plan: `~/.claude/plans/it-s-time-to-move-peppy-sky.md`)

Decided 2026-10-20, order swapped same day: pixi first (fully landed),
Pacsys after. Both are dual-run cutovers — old path stays live alongside
the new one until the new one is verified on hardware, then the old one
retires. The external operator launcher shortcut is out of scope to edit;
each cutover below hands over the exact command line for whoever maintains
it to paste in.

### Environment and setup — do first

- [x] **Make pixi the default environment manager** (decided 2026-10-08,
  built 2026-10-20). `pixi.toml`: the default environment includes `acsys`
  from the FNAL index (matches the MCR host, which always has FNAL network);
  an `offsite` environment (`pixi install -e offsite` / `./bootstrap.sh
  --offsite`) drops it for off-network dev work — swapped same day from the
  original default-is-offsite layout once the MCR host turned out to need
  the flag-free command. Committed `pixi.lock` for osx-arm64 and linux-64;
  patches/config/verify wired as `pixi run setup` (`pixi_setup.sh`); a
  `bootstrap.sh` that installs pixi if missing and runs install + setup;
  swapped the `conda run -n FermiBadger_env` references in test docstrings,
  `patches/README.md`, `README.md`, `CLAUDE.md`, `HANDOFF.md`, `Dockerfile`
  to `pixi run ...`; `setup.sh` and `environment.yml` kept as the legacy
  conda path per the dual-run decision, clearly marked as such. Verified
  locally: both `default` and `offsite` environments resolve and install,
  patches apply, `config.local.yaml` generates, the plugin is discoverable,
  and the existing offline test suite (`mults_test.py`, `pacsys_drf_lint_test.py`,
  `pacsys_interface_test.py`, `periodic_phase_test.py`, `supply_limits_test.py`,
  `template_lint_test.py`, `VA_plugin_smoke_test.py`) passes under
  `pixi run python tests/...py`.
  - [x] MCR host confirmed reachable: `./bootstrap.sh` ran there
    successfully (conda-forge/PyPI/FNAL index all reachable, pixi cache
    writable).
  - **Gotcha found on the MCR host:** the pixi installer's `export PATH=...`
    only lands in the shell that ran it, and a headless/login session
    doesn't source `~/.bashrc` the way an interactive one does, so `pixi`
    wasn't found in the session that matters. Fixed with
    `sudo ln -s ~/.pixi/bin/pixi /usr/local/bin/pixi` (a system-PATH
    directory, not a shell-rc one) rather than relying on PATH exports or
    aliases, neither of which a headless session picks up.
  - [ ] Dual-run on the MCR host: run the (still Acsys, at this point)
    production template through both conda and pixi, compare, then hand
    over the pixi-based launch line (`pixi run badger -g -cf config.local.yaml
    -t <template>`, no `-e` flag needed now) for the external shortcut —
    don't edit it ourselves.
  - [ ] Cutover: once validated for several sessions, retire the conda env
    on that host, update README's Quick Start to drop the legacy conda
    callouts.
- [ ] Offer the three-line turbo.py fix in `patches/xopt-3.2.2-turbo-serialization.patch`
  upstream to xopt-org/Xopt.

### Pacsys interface (needs the machine) — after pixi lands

- [ ] Live check with `development/ZZ_PacsysTesting.yaml`: a setting lands, no
  readback warning fires.
- [ ] `01_Linac_RIL_tuning_Pacsys` with `average_events: {default: 3}`: expect each
  evaluation ~3 cycles slower and smoother objectives.
- [ ] Try `development/01_Linac_RIL_tuning_Pacsys.yaml` at all (untested copy of the
  Acsys template).
- [ ] Pick an array device for a first `|rms` observable.
- [ ] Mults machine check on the Pacsys testing role: both quads of a pair
  move by coefficient × step × steps, `MultOOB` stays 0.
- [ ] Once the above pass: run the Pacsys template side-by-side with the
  Acsys production template for several operating shifts (dual-run),
  watching for divergence or Pacsys-only errors (`DeviceError`, `RuntimeError`).
- [ ] Cutover: flip `01_Linac_RIL_tuning.yaml`'s `environment.name` from
  `..._Acsys` to `..._Pacsys` (filename/operator-facing name unchanged — no
  shortcut edit needed for this phase, it's already running the pixi
  launch line from the phase above). Retire `_Acsys` from production use
  (interface code stays for off-site/sim use). Log the switch date and
  evidence in `docs/log.md` / `docs/progress.md`.

## Later

- [ ] Ramps as variables (Booster skew quads via pacsys `BoosterSQRamp`) once a
  Booster environment exists; `sim_configs/Booster/` lattice bundle is still untracked.
- [ ] `-mini` has no "Save as Template" button (upstream removed it; the handler
  `save_template_yaml` still exists). One button in the mini env box if wanted.
- [ ] Bulk-supply ratings in the RIL environments are 7.0 A stand-ins pending expert
  confirmation. (Mult coefficients 20.0 and step size 0.05 were confirmed 2026-10-08.)
