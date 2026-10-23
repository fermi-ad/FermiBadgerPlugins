# TODO

Open work, roughly in priority order. Session-by-session detail lives in
`docs/progress.md`; this file is just the list.

## Environment bugs found while writing their docs (2026-10-23)

Each README says so under "Known issue"; none affects the RIL, EnergyStabilization,
QuadTuning or ZZ_PacsysTesting environments.

- [ ] `09_DeliveryRing_Muon_PID_tune_Acsys` does not import: line 69 is
  `= result[...]`, missing `itgsig_spill` on the left (the Pacsys twin has it).
- [ ] `09_DeliveryRing_Muon_PID_tune_*`: `get_observables` checks for
  `'DR_SDF'`, not `'DR_SDF_calc'`, so the spill arrays are never read and
  `DR_SDF_calc` fails.
- [ ] `01_Linac_AutoSteerRestore_*`: asking for `VTrajError_SumSqBPM_calc`
  appends an undefined `input_dev`; its `setpoints` dict also repeats keys.
- [ ] `01_Linac_MinD7LMSM_using_Tank5Phase_*`: calls `interface.get_value`
  and passes `sample_event` positionally, and adds `.SETTING` itself; out of
  date with the interfaces.

## safe-badger: revert and crash safety (built 2026-10-21 on main; `docs/safe-badger.md`)

Startup snapshot of every writable device (at template load and at Go), a
Revert button and Keep/Revert on close in both GUIs, and `pixi run safe-badger
mini|g`: a launcher that restores automatically if Badger
exits undecided. Offline tests pass (`settings_snapshot_test.py`,
`settings_snapshot_gui_test.py`, FakeBackend).

- [ ] **Hand over the new operator launch line** for the external shortcut,
  once machine-tested: `cd <repo> && pixi run safe-badger mini -t 01_Linac_RIL_tuning.yaml`
  (replaces `pixi run badger -mini -cf config.local.yaml -t ...`).
- [ ] **Machine tests — next, planned for 2026-10-22 on the MCR host** (steps in
  `docs/progress.md`), with `development/ZZ_PacsysTesting.yaml` (role `testing`),
  both `safe-badger mini` and `safe-badger g`, including Go in `-g` with an
  environment chosen without a template:
  close → Revert; close → Keep; Revert button mid-session; `kill -9` Badger
  idle and mid-run (run subprocess must die before the restore); Ctrl-C in the
  launcher's terminal (check pixi passes Ctrl-C through and safe-badger still
  restores); closing the terminal (SIGHUP); a crash after `kdestroy`
  (expect the loud warning at start and the manual `pixi run safe-badger restore` line).
  Then RIL Acsys: the snapshot should record role `ril_tuning`.
- [x] Maximum age for the *automatic* restore: 2 h from the first template load
  (decided 2026-10-21; sessions normally last under 30 min, 2 h leaves room
  for slow applications). Past it the snapshot becomes `*.expired`, not
  restored. Reminder up front: status bar after each template load, and
  safe-badger's start-up message.
- Not covered, by design for now: supply-limit group sums aren't rechecked on
  restore (it writes back a previously live state); an environment switched
  without loading a template isn't snapshotted; if the launcher itself is
  SIGKILLed or the host dies, the next launch flags the snapshot `*.stale`
  rather than restoring it.
- Note: the dev Mac reaches ACNET (VPN + Kerberos), so a real `pixi run safe-badger mini`
  / `restore` there writes to real devices. 2026-10-21 a smoke test wrote
  Z:CUBE_X 1.0 → 5.0; restored to 1.0 straight away.

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
  - **Gotcha found testing the RIL template under `-mini` on the MCR host:**
    `pixi.toml` didn't pin `pydantic`, so pixi resolved conda-forge's
    current release (2.14.1) instead of the conda env's months-old cached
    one (2.13.5) — and `pydantic_editor-badger-1.6.0-dict-subtypes.patch`'s
    fix is version-sensitive, so 2.14.1 reintroduced "Dict type must have
    subtypes". Fixed by pinning `pydantic = "2.13.5.*"` in `pixi.toml`;
    re-verified (offline tests, headless `-mini` repro of
    `select_env`→`load_template_yaml`→`compose_vocs` on the production
    template). Noted but not fixed: three unrelated upstream `badger-opt`
    files also differ between the two installs (conda-forge can rebuild a
    noarch package's source without a version bump) — no evidence yet
    that matters; an exact-build pin is the fallback if it ever does.
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

- [x] **Per-user Badger config staleness fixed at the root**: `pixi_setup.sh`
  and `setup.sh` now sync `config.local.yaml`'s paths into Badger's own
  per-user settings file too (`~/.config/config.yaml` on Linux,
  `~/Library/Application Support/Badger/config.yaml` on macOS) every time
  setup runs — some code paths (the "Go" run subprocess) read that file
  instead of `-cf config.local.yaml`, and a stale one caused a same-machine
  "file not found" failure here. No manual per-host check needed anymore:
  running setup (which the MCR host does anyway on a fresh clone/rebuild)
  keeps it in sync automatically. See docs/log.md 2026-10-20.
- [x] Live check with `development/ZZ_PacsysTesting.yaml`: ran to
  completion (dev machine, VPN); no readback warning reported. Hit and
  fixed two unrelated pre-existing bugs along the way (stale per-user
  config above, and `Picker.setText` on stop — see docs/log.md).
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
- [ ] **Deferred design decision**: the `-mini` "Refresh" button next to Variables
  (`refresh_current_btn` in `env_cbox.py`) does an on-demand live read of all
  listed variables' current values (distinct from the auto-refresh on Reset
  Env, Dial In, and after each evaluated point — see docs/log.md 2026-10-21).
  User is considering either renaming it to something clearer like
  "Re-Read Values" or removing it outright; undecided, not yet acted on.
