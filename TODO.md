# TODO

Open work, roughly in priority order. Session-by-session detail lives in
`docs/progress.md`; this file is just the list.

## Editing parameters without braces and commas (plan agreed 2026-10-23)

Environment parameters holding a mapping arrive in the editor as a plain dict,
without the class's type hints, so each is one line of YAML text.

- [x] **v1: check as you type** (`badger-1.6.0-param-validation.patch`, main):
  red mark + reason, Go refused while any is bad.
- [x] **Table editor** (`badger-1.6.0-param-table-editor.patch`, main,
  2026-10-23): an **Edit...** button inside each mapping field opens a
  Name/Value table (Add/Remove rows, values checked against the kinds the
  template used, names completing from the environment's variables,
  observables and `-SETPOINT` readings). Value kinds come from the template's
  own values, not the class's declared types: the editor still gets a plain
  dict. The line keeps the YAML text (what is saved), so templates are
  unchanged and it can still be typed into.
  - [ ] Try on the MCR host with the RIL template (`w_sumsq`, `setpoints`,
    `BulkPS_Limit`, `mults`).
- [x] **Mults and bulk supplies** (2026-10-23, user's design): each is now ONE
  nested parameter, `mults: {name: {step, members: {device: scale}}}` and
  `supplies: {group: {limit, devices: [...]}}` (replacing `mults` +
  `mult_step_size` and `supply_groups` + `supply_limits`; both RIL
  templates migrated, old form rejected by validation). Edit... opens one
  dialog per parameter: step size or limit plus members from device
  pulldowns. Existing mults/supplies only: a new one also needs a
  `mult:<name>` variable or `BulkPS_<group>` observable in the class.
- [x] **Bulk power supplies renamed and split limits** (2026-10-23): parameter
  `supplies` -> `BulkPS_Limit`, observables `SumAbs_<group>` -> `BulkPS_<group>`.
  A supply can instead limit the sum of +I and the magnitude of the sum of -I
  separately (`positive`/`negative`; observables `_Pos`/`_Neg`); RIL source A
  uses that at 8 A each, constrained < 8 in both RIL templates.

## Docs

- [ ] The action bar's "?" button opens Badger's own `minimode` guide, which
  shows the stock `-mini` layout. Once simpler_mini is the norm, give it our
  own page (e.g. `docs/guides/minimode.md` and a loader tweak).
- [ ] Upstream Badger's expected-improvement guide gives `max_travel_distances`
  in absolute units; Xopt 3.2.2 treats it as a fraction of each range. Our page
  says so; worth reporting upstream.

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
- Machine-test results on gmpsai2 so far: full offline suite passes there
  (2026-10-26, after the config.local.yaml test fix); **Ctrl-C passes through
  pixi** and the launcher restores (log, 2026-10-26 12:02); Close → Revert
  works (2026-10-27 10:28). **GUI killed mid-run (after the worker patch):
  workers gone, devices reverted** (2026-10-27). kill -9 on the idle GUI and
  on the idle launcher: smooth (user, 2026-10-27; the launcher case is the
  documented limit, Badger carries on and the snapshot is flagged `.stale`
  at the next start). **SIGHUP to the launcher: passed** (2026-10-27 11:37:
  stopped Badger, restored 4 devices). **All planned machine tests pass**
  (2026-10-27): next, hand over the operator launch line above.
  - [x] **Kerberos:** restore after a `kdestroy` in the *second* terminal
    succeeded (2026-10-27): that terminal's cache only; the launcher's own
    ticket survived. With `kdestroy` in the launcher's own terminal before
    starting it, the run could not write at all (0 of 4 devices differed after
    a mid-run kill; restore had nothing to do). No ticket, no writes. Never `pkill -f badger`: it also hits the
  launcher, and a SIGKILLed launcher can't restore.
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
  - [x] **pixi is the norm** (2026-10-23, user's decision): README's
    Quick Start and Troubleshooting no longer mention conda; one
    "Legacy conda path (frozen 2026-10-23)" paragraph remains. `setup.sh`,
    `environment.yml` and `tests/test-quick-start-conda.sh` are marked
    frozen: kept, unmaintained, no new patches. The planned conda-vs-pixi
    dual run was skipped.
  - [ ] Operator shortcut on the MCR host -> `cd <repo> && pixi run
    safe-badger mini -t 01_Linac_RIL_tuning.yaml` (the user updates it).
  - [ ] Then retire `FermiBadger_env` on the MCR host by hand
    (`conda env remove -n FermiBadger_env`), and later decide whether to
    delete the frozen conda files from the repo.
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
- [x] `-mini` "Save as..." button (simpler_mini, 2026-10-23): saves to the
  gitignored `tuning_templates/saved/`, listed in the dropdown as `saved/<name>`;
  overwriting operations templates refused. Full GUI also got the -mini VOCS
  layout (`badger-1.6.0-full-gui-vocs-layout.patch`). Both still to be tried
  on the production host along with the simpler mini.
- [ ] Bulk-supply ratings for source B and the two MEBT trim supplies are 7.0 A stand-ins pending expert
  confirmation. (Mult coefficients 20.0 and step size 0.05 were confirmed 2026-10-08.)
- [ ] **Deferred design decision**: the `-mini` "Refresh" button next to Variables
  (`refresh_current_btn` in `env_cbox.py`) does an on-demand live read of all
  listed variables' current values (distinct from the auto-refresh on Reset
  Env, Dial In, and after each evaluated point — see docs/log.md 2026-10-21).
  User is considering either renaming it to something clearer like
  "Re-Read Values" or removing it outright; undecided, not yet acted on.

## `simpler_mini` branch — UI redesign for typical operators, not developers

Branch off `main` at `8c7b557` (2026-10-21); **merged into main 2026-10-23**
(fast-forward to `bc6b9b7`, user's decision after trying it locally; the MCR
trial was skipped). The simplified `-mini` is now the norm. Goal: streamline
`-mini` for the typical user, who thinks "machine"/"accelerator section"
and doesn't need Badger-developer concepts surfaced as main-window rows.

- [x] Collapsed the "Badger Environment" and "Algorithm" rows into one
  "Parameters" row with "Machine Interface"/"Optimization Algo" buttons
  (now in `badger-1.6.0-mini-simpler-ui.patch`). `env_cb`/`algo_cb` stay
  functional, just not shown — see docs/log.md 2026-10-21.
- [ ] **Open: where should "Open Docs" live, and what should it show?**
  Currently a provisional button inside each new collapsible panel. User
  explicitly undecided on placement, and separately noted the docs
  content itself (`BadgerDocsWindow`) is bare-bones and needs filling in
  — that's a distinct task from the button's placement.
- [x] Removed the empty left sidebar next to Variables/Objectives/
  Constraints/Observables: each table now spans full width, left-justified
  where the label used to start, instead of a fixed 96px label column with
  a tall empty strip below it. Each label leads its own action row (same
  line as its "Add …" dropdown, Refresh too for Variables) rather than a
  separate heading line (now in `badger-1.6.0-mini-simpler-ui.patch`). See
  docs/log.md 2026-10-21.
- [x] Removed the "▼ Variables" and "▼ Constraints + Observables" collapse
  bars (both redundant/risky — the latter could hide two whole sections
  with one click); both always visible now, no toggle. "▶ Initial Points"
  keeps its bar for visual separation but is locked expanded — clicking it
  does nothing (now in `badger-1.6.0-mini-simpler-ui.patch`). See docs/log.md
  2026-10-21.
- [x] Renamed "Template" to "Tuning Task", and moved the Parameters row
  (Machine Interface/Optimization Algo) into that same styled box as a
  second line, instead of its own separate row below it
  (now in `badger-1.6.0-mini-simpler-ui.patch`). Noted, not fixed: the
  buttons' checked/expanded state isn't visually distinct from unchecked
  against the box's dark background. See docs/log.md 2026-10-21.
- [x] Fixed the Tuning Task box's right edge being clipped by the tab's
  vertical scrollbar (hardcoded 5px margin → actual scrollbar width via
  `QStyle.PM_ScrollBarExtent`), and renamed the "Environment + VOCS" tab
  to "Tuning" (now in `badger-1.6.0-mini-simpler-ui.patch`). See docs/log.md
  2026-10-21.
- [ ] More `simpler_mini` streamlining changes to come; this file should
  track each one as it lands, same as this entry.
