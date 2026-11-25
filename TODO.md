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

## Upstream

- [ ] **Heteroskedastic noise testbed** (2026-10-25; on main since the 2026-10-28 merge):
  `ZZ_PacsysTesting_Heteroskedastic` + `development/ZZ_PacsysTesting_Heteroskedastic.yaml`
  + `scripts/heteroskd_recovery.py` + `tests/heteroskd_noise_test.py` (offline).
  Live run 2026-10-25 (`scripts/heteroskd_live_run.py distance`, 40 points,
  devices restored): heteroskedastic GP median |log10 error| 0.038, log corr
  0.985; standard GP 0.182, -0.53. Proportional and bump live too (log).
  Open: quiet regions overstated ~x2, not by the floor (test by varying
  n_samples and the number of points). GUI run + Continue with a widened
  range scored from the archive (log): widening raises the model floor.
  Next: a test of the Xopt PR's
  `train_Yvar` site (several objectives with `_var`).
  Found: Xopt's heteroskedastic GP floors noise at ~1e-4 of the objective's
  variance (README).

- [ ] **Xopt PR: copy DataFrame selections before `torch.tensor`** (the
  `xopt-3.2.2-negative-strides.patch`, plus a sixth site, `train_Yvar`).
  Branch `fix-negative-strides` on github.com/jasonstjohn/Xopt (worktree
  `../Xopt-negative-strides`), cut from upstream main d48ec24b, with a test in
  `test_turbo.py`. Tested 2026-10-25: fork CI all green (Lint; Tests on
  ubuntu 3.11-3.14, macOS, Windows; Test Notebooks); full suite locally on
  upstream main vs branch in one env (botorch 0.17.2): no new failures (4
  torch-compile tests fail on both, on this Mac). Not opened yet: user wants
  more testing first. Once released, drop the local patch.
- [x] Badger PR: the docs window's Back button: **xopt-org/Badger#298**
  (opened 2026-10-28; branch `docs-back-button` on jasonstjohn/Badger, clone
  `../Badger-docs-back`; fork CI green, its test ran). Once merged and
  released, drop `badger-1.6.0-docs-back-button.patch`.
- [ ] Badger PR: `badger/tests/utils.get_current_vars` returned `list(dict.values())` in
  the environment's order, zipped with `vocs.variable_names` by the run monitor: the Apply
  Solution dialog mispaired values, and Reset wrote each variable another's starting value
  (user saw "crazy" differences, 2026-11-24). Local fix `badger-1.6.0-current-vars-order.patch`.
- [ ] Badger: `_compose_routine` resets TuRBO state only for the short
  controller names (the repo's `badger-1.6.0-turbo-state-reset.patch`); worth a
  Badger PR too.

## Docs

- [x] The action bar's "?" in `-mini` shows this repo's own page,
  `docs/guides/minimode.md` (2026-10-28; the plugin-docs patch prefers
  `docs/guides/<name>.md` over Badger's guide). The full GUI's "?"
  (`gui-usage`) still shows Badger's; a page from this repo can follow the same way.
- [ ] Upstream Badger's expected-improvement guide gives `max_travel_distances`
  in absolute units; Xopt 3.2.2 treats it as a fraction of each range. The repo's page
  says so; worth reporting upstream.

## Environment bugs found while writing their docs (2026-10-23) — fixed 2026-10-28

- [x] `09_DeliveryRing_Muon_PID_tune_*`: Acsys twin's syntax error (import
  failed); `DR_SDF_calc` checked for `'DR_SDF'` so the spill arrays were never
  read; a spill starting at sample 0 sliced from the end.
- [x] `01_Linac_AutoSteerRestore_*`: `VTrajError_SumSqBPM_calc` hit an undefined
  name; `W_SumLosses` was never computed (the name was removed, then tested);
  repeated `setpoints` keys.
- [x] `01_Linac_MinD7LMSM_using_Tank5Phase_*`: brought up to date with the
  interfaces (`get_settings`, `get_values` with `sample_events`, bare names to
  `set_values`); parameter `sample_event` became `sample_events`.
- All three, both twins: the caller's list of names is left alone and only the
  requested names come back. `tests/env_fixes_test.py` (stub interface).
- [x] Found 2026-11-04 by the new `tests/env_smoke_test.py`: `01_Linac_RIL_tuning_Pacsys`
  never computed `W_SumLosses` (removed, then tested, as AutoSteerRestore had);
  `01_Linac_QuadTuning_Pacsys` always computed it, so any read without it raised
  KeyError. Both also changed the caller's list and returned the inputs. Fixed.

## safe-badger: revert and crash safety (built 2026-10-21 on main; `docs/safe-badger.md`)

Startup snapshot of every writable device (at template load and at Go), a
Revert button and Keep/Revert on close in both GUIs, and `pixi run safe-badger
mini|g`: a launcher that restores automatically if Badger
exits undecided. Offline tests pass (`settings_snapshot_test.py`,
`settings_snapshot_gui_test.py`, FakeBackend).

- [x] **Machine tests on gmpsai2: all pass** (2026-10-26/27, ZZ_PacsysTesting,
  `safe-badger mini`): Close → Keep / Revert; Ctrl-C (passes through pixi;
  launcher restores); `kill -9` on the GUI, idle and mid-run (with the worker
  patch: workers gone, devices restored); `kill -9` on the idle launcher (the
  documented limit: Badger carries on, snapshot `*.stale` at next start);
  SIGHUP to the launcher (restored); no Kerberos ticket (a `kdestroy` in
  another terminal leaves the launcher's own ticket; with none in its own
  terminal the run cannot write at all). Full offline suite passes there.
- [x] **Operator launch line requested** (2026-10-28, the user):
  `cd <repo> && pixi run safe-badger mini -t 01_Linac_RIL_tuning.yaml`
  (replaces `pixi run badger -mini -cf config.local.yaml -t ...`).
- [ ] Machine test: an ssh connection with X forwarding dropping mid-run (the way
  operators connect): expect Badger to exit, the launcher to restore, and the
  log to say so. Each part already passed (SIGHUP, GUI killed mid-run).
- [x] **Revert dialog: a percent-difference column** (user, 2026-11-24; done the same day):
  beside Now and Startup, the change reverting would make, 100 (startup - now) / |now| (a
  dash when now is 0), in `settings_snapshot.format_changes`; the same table (user: in
  every before/after confirmation) in the run monitor's Apply Solution, Reset, and Load
  Checkpoint (`badger-1.6.0-change-tables.patch`; `tests/change_tables_test.py`).
- Never `pkill -f badger` (or `pgrep -f badger | kill -9`): it also hits the
  launcher, and a SIGKILLed launcher can't restore. `pixi run safe-badger pids`
  says which PID is which.
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

- [x] (user: up to date, 2026-11-24, through 85c9915: the L:RFQPAH limit and the mini
  GUI's Context header fix included; `config.local.yaml` kept, synced to the per-user
  config) **On gmpsai2:** `git pull && pixi run setup -- --yes` for the patches since the
  last pull there (51aebab): risk tolerance (f5ad771), noise shapes (d0a8b73; skew-t
  added in cd02b16), the Context column (98f51a8; read-only `.READING` context variables,
  ranges that widen, 9fedf98). The pull also brings the Booster-wide environment
  (d5cb46d) and the RIL templates with source A's context variables ticked.
- [x] (user reported `pixi install` done, 2026-11-17) **On gmpsai2 after the Acsys retirement (2026-11-04):** `git pull && pixi install
  && pixi run setup -- --yes` (the lock changed: acsys gone; grpcio 1.84.0→1.85.1,
  anyio, cython, pyasn1 minor bumps). Then one read-only template load to exercise
  pacsys on the new grpcio. Leftover `_Acsys/__pycache__` folders are harmless
  (Badger lists only folders with an `__init__.py`); `rm -rf` them if wanted.

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
  - [x] Operator shortcut on the MCR host -> `cd <repo> && pixi run
    safe-badger mini -t 01_Linac_RIL_tuning.yaml`: requested 2026-10-28.
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
- [x] **Cutover (decided and done 2026-10-28):** Pacsys is vetted as well as it can be
  (live testing-role checks, the safe-badger machine tests); the planned
  multi-shift Acsys/Pacsys dual run is dropped. Every real-world tuning
  template switches to its `_Pacsys` environment; `_Acsys` environments stay
  in the repo (off-site/sim use) but no template uses them. Done: the
  operators' `01_Linac_RIL_tuning.yaml` (same filename) and the three
  development templates (renamed `..._Pacsys.yaml`); each twin checked to
  accept every template parameter and name, with identical variables, hard
  limits and observables. `tests/pacsys_cutover_test.py` guards it.
- Follow-ups after the cutover, on the machine:
  - [ ] `average_events: {default: 3}` on RIL: each evaluation ~3 cycles
    slower, smoother objectives.
  - [ ] Pick an array device for a first `|rms` observable.
  - [ ] Mults check on the testing role: both quads of a pair move by
    coefficient × step × steps, `MultOOB` stays 0.

## Simulation speed and new environments (2026-11)

- [x] **Booster-wide environment `03_Booster_Pacsys`** (2026-11-19,
  `docs/booster-environment.md`): 440 settings (402 with ranges: 94 from 90 days of
  logged settings, 308 from database limits), 503 readings, from ad-tools, the logbook,
  and the data logger; replaces the injection draft (deleted; its template re-pointed).
- [ ] **Booster, for the hardware owners:** how Badger writes interact with the loops
  that also write the 50 `auto_written` settings (`B:VIMIN` autotune, `L:C7PHAS` on
  nearly every pulse, 400 MeV trims, extraction kickers, gamma-t, ...): each stays
  refused until named in `allow_auto_written`. Also: what the ring magnets' base-device
  settings do; `L:C7PHAS` vs `L:L7PADJ`; `L:C7PHAS`'s second state near 316 degrees.
- [ ] **Booster noise profiles per cycle type:** tag logged readings by cycle
  (`scripts/event_tag.py`; validated on `B:BLMS13`, not on `B:CHG0`), then profile the
  constraint candidates (BLMs, `B:BEFFnn`).
- [x] **Exogenous (contextual) variables in Badger**: done 2026-11-20, the Context column
  (`badger-1.6.0-context-variables.patch`, `docs/plans/context-variables.md`). Was: (user, 2026-11-20; after the RIL
  source-context study, `scripts/ril_context_study.py`, `scripts/ril_context_gp.py`):
  Xopt 3.2.2 has `ContextualVariable` in the VOCS (Bayesian generators support it; the
  evaluator returns its measured value, the GP takes it as an input, and the acquisition
  holds it at its last value: `_apply_fixed_features_and_contextual_variables`;
  `xopt/tests/generators/bayesian/test_contextual_bo.py`). Badger needs a way to mark a
  variable exogenous (a GUI column), compose it as a `ContextualVariable`, never write
  it, and have the environment return its reading. Candidates: the L48 source
  parameters, Booster turns, if the study finds they change the knobs' response.
- [ ] **RIL: source parameters as context variables** (user, 2026-11-24): only the
  conclusively important ones, Context checked in the RIL templates, ranges from the last
  months' logged values with beam on.
  - [x] Mechanism (2026-11-24): a `.READING` variable in the RIL environment is read as a
    reading (`L:AEXTSV.SETTING` reads about 0) and refused on write; safe-badger skips it.
    Context variables: no outside-limits warning, never recentered, and a reading outside
    the range widens it (user), at load, at Go, and each step (`docs/plans/context-variables.md`).
  - [x] Selection (`scripts/ril_context_study.py --select`): none passed (best: `L:AARCI`
    for `L:D7TOR`, better in 10 of 14 held-out weeks; 13 needed). The list is empty.
  - [x] User's call (2026-11-24): at least 3 of 14 weeks, top 3 or 4. Taken: `ARCI`,
    `SRCI`, `EXTV` for `L:D7TOR` (the 4th, `LCC`, gains R2 0.001); `EXTV`'s chance of being
    a fluke 0.02 alone, at most 0.34 as the best of 21. Added as `L:A/B...READING` context
    variables, ticked (source A) in the four RIL templates.
  - [x] On the machine, loading (user, 2026-11-24): the context variables read fine.
  - [ ] On the machine, a run: does the GP use them (length scales), and does the mini
    GUI's Context header read clearly now (fixed in 85c9915)?
  - [ ] A designed test on the machine would settle it: one knob scanned at two source states.
- [ ] **Source A and Source B versions of the RIL templates** (user, 2026-11-24), and of
  any Linac template that uses or consults ion-source devices. Today: the four RIL
  templates (`01_Linac_RIL_tuning.yaml`, `01_Linac_LossObjective_RIL_tuning.yaml`,
  `development/01_Linac_RIL_tuning_Pacsys.yaml`,
  `development/01_Linac_ThroughputVsLosses_RIL_tuning_Pacsys.yaml`) tune source A's
  trims and solenoid; source B has its own (`L:BTRM*`, `L:BSOL`) and its own source
  parameters (context variables). `development/ZZ_Archetype_Pacsys.yaml` also names
  source devices (a teaching example; probably exempt).
- [ ] **Booster templates for the other tasks** (plan set aside 2026-11-20, user's call:
  `docs/plans/booster-templates.md`): orbit, RF capture and RF transition (two), extraction,
  notching, tunes, and chromaticity against `03_Booster_Pacsys`, every logbook-named
  device checked; tunes and chromaticity by OCR of their entries' screenshots, then
  indexed (ramp-table) settings in the interface.
- [x] **RIL loss-objective template promoted to operations** (2026-11-17, the user's
  decision): `01_Linac_LossObjective_RIL_tuning.yaml` (minimize `L:TK4RAD`, `L:D7TOR`
  > 20 floor), beside the original `01_Linac_RIL_tuning.yaml`.
- [ ] **Booster draft template:** review `development/03_Booster_InjectionTuning_Pacsys.yaml`
  (now against `03_Booster_Pacsys`) with operators before promoting it.
- [ ] **RIL MEBT trim bulk supplies: confirm with the machine experts, then regroup**
  (2026-11-17). The user reports the upstream and downstream MEBT quads are on separate
  power supplies. Today `BulkPS_Limit` groups the trims by quad number, mixing upstream
  and downstream: `MEBTQ1trims` = `L:MUQ1H/V` + `L:MDQ1H/V`, `MEBTQ2trims` = `L:MUQ2H/V`
  + `L:MDQ2H/V` (7.0 A placeholders). Proposed, once confirmed: upstream `L:MUQ1H/V` +
  `L:MUQ2H/V`, downstream `L:MDQ1H/V` + `L:MDQ2H/V`, with their real limits. Touches
  `_BULK_PS` in `01_Linac_RIL_tuning_Pacsys` and the archetype, both RIL operations
  templates' `BulkPS_Limit`, their `BulkPS_*` constraints/observable names, and the
  tests that name the groups. No change until confirmed.
- [ ] **MOBO RIL template: started 2026-11-18** as
  `development/01_Linac_ThroughputVsLosses_RIL_tuning_Pacsys.yaml`: maximize `L:D7TOR`,
  minimize `L:TUNRAD` (the user: "the lowest losses for the most throughput"); reference
  point `L:D7TOR` 20 (about the 10th percentile of 192 beam-on sessions), `L:TUNRAD` 150
  (the operations limit; 99th percentile 146); operations constraints minus
  `L:TUNRAD < 150`; acquisition 0.5 s, 5 restarts. Passes the lint; its generator
  produces a point from synthetic data in 2.75 s. Next: run it on the machine with the
  operators; decide whether `G:LINEFF` (efficiency) should replace `L:D7TOR`; trim its
  six observables if steps run slow (each is a fitted GP).
- [ ] **DR EI template's observables:** Xopt fits a GP to each VOCS output; listing
  only the objective and constraint cut the closed-loop step 0.72 -> 0.46 s (3
  seeds), but stops recording `qx`, `qy` and the rest. Decide.
- [ ] **Not yet measured:** GUI overhead per step (plots, archive), a run's start-up
  cost, and timings on gmpsai2 (the profiles ran on the MacBook).
- [ ] **DR task templates (simulation, 2026-11-16): follow-ups.**
  - Confirm two readings of the task list with the DR experts: the "M_DSX602 ~
    M_DSX502" phase condition read as the horizontal phase advance from `m0_dsx602` to
    `m0_dsx502` (design 1051.8 deg, target 1050 = 35 x 30 deg); "the kickers" read as
    `d_dkk3i*`, `d_dkk5a*`.
  - The lattice defines the quad stand variables `LH_DQ*`, `LV_DQ*` but never uses
    them; ask the lattice owner. Offsets are modeled with `<quad>.shift_x/y`.
  - LatticeFunctions: the straights' dispersion stays (0.08 m vs 0.017 m design):
    three erring quads have only main-bus power, and the shunts I_DQS213 and I_DQS607
    of two others are not knobs (try adding them; untested); only 8 of 34 points met all constraints in the
    closed-loop check. Its knob choice suits its error set only.
  - Tunes: the existing DR_BetatronTunes templates use i_dqf and i_dqd; add i_dqss as
    an option if the lattice distorts.
  - Load each new template once in the live `-mini` GUI (the integration test only
    emulates the GUI's name lookups).
- [ ] **DR real-machine twins:** a `09_DeliveryRing_*_Pacsys` environment.
  ad-lattices (`sections/delivery-ring/shared/`) covers only the BPMs (119, confirmed:
  `P_DHP101` -> `D:HP101`) and the trims (19, confirmed: `T_DHT301` -> `D:HT301`), so
  the orbit templates can go first. Missing, from a relevant expert: the ACNET names
  of the main quad buses (`I_DQF`, `I_DQD`, `I_DQSS`, `I_DQ404`), the 61 shunts
  `I_DQS*`, and the sextupole buses (`I_DSEXF`, `I_DSEXD`); whether `D:HT*` settings
  are in amps like the lattice's trim currents. The model fit needs a measured orbit
  response instead of `truth_errors`.
- [ ] **Multi-turn tracking templates** (slow extraction, dynamic aperture): the
  simulation would dominate; try xsuite's OpenMP and GPU contexts then.

## Later

- [ ] Ramps as variables (Booster skew quads via pacsys `BoosterSQRamp`) once a
  Booster environment exists; `sim_configs/Booster/` lattice bundle is still untracked.
- [x] `-mini` "Save as..." button (simpler_mini, 2026-10-23): saves to the
  gitignored `tuning_templates/saved/`, listed in the dropdown as `saved/<name>`;
  overwriting operations templates refused. Full GUI also got the -mini VOCS
  layout (`badger-1.6.0-full-gui-vocs-layout.patch`). Both still to be tried
  on the production host along with the simpler mini.
- [x] Bulk-supply ratings for source B and the two MEBT trim supplies: 7.0 A confirmed (user, 2026-10-28); was a stand-in pending expert
  confirmation. (Mult coefficients 20.0 and step size 0.05 were confirmed 2026-10-08.)
- [x] **The `-mini` "Refresh" button** (next to Variables) is now **"Re-read
  values"** (user's decision, 2026-10-28; `badger-1.6.0-mini-reread-values.patch`):
  an on-demand live read of the Current column, which also updates by itself
  after Reset Env, Dial In and each point.
## Simplified `-mini` — UI redesign for typical operators (simpler_mini, merged into main 2026-10-23)

Branch off `main` at `8c7b557` (2026-10-21); **merged into main 2026-10-23**
(fast-forward to `bc6b9b7`, user's decision after trying it locally; the MCR
trial was skipped). The simplified `-mini` is now the norm. Goal: streamline
`-mini` for the typical user, who thinks "machine"/"accelerator section"
and doesn't need Badger-developer concepts surfaced as main-window rows.

- [x] Collapsed the "Badger Environment" and "Algorithm" rows into one
  "Parameters" row with "Machine Interface"/"Optimization Algo" buttons
  (now in `badger-1.6.0-mini-simpler-ui.patch`). `env_cb`/`algo_cb` stay
  functional, just not shown — see docs/log.md 2026-10-21.
- [x] **"Open Docs" stays where it is** (user's decision, 2026-10-28): inside
  the Machine Interface / Optimization Algo panels, next to the settings it
  describes; the action bar's "?" is for the window as a whole
  (`docs/guides/minimode.md`).
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

## Feature wish list (experimental, not scheduled)

- [x] **Merged `bells-and-whistles` into main** (2026-10-28): Continue from
  run (phases 1-2), the heteroskedastic testbed, the lit review. Full suite
  (28 tests) passes on the merged tree.

Ideas to explore; nothing here is built yet. Each entry says what already
exists and what it would touch.

- Plan (2026-10-24), decided: widening and seeding are one action, "Continue
  from run": a **new linked run** seeded with an earlier run's points, in
  **both GUIs**, with a **fresh trust region**. Phases:
  - [x] 1. Continue + widen: action-bar Continue button and History menu
    entry (`patches/badger-1.6.0-continue-run.patch`,
    `tests/continue_run_gui_test.py`). Tried live on the sim 2026-10-24: runs
    well.
  - [x] 2. Seed from several runs (plan agreed and built 2026-10-24; several
    runs not yet tried live):
    - Pick: with Continue armed, History right-click "Add its points" appends
      a run without changing the displayed one (History stays single-select);
      status bar shows "Seeding from K runs, N points".
    - Merge: rows stacked oldest first, renumbered, `live = 0`. Plots already
      draw `live = 0` points as a separate curve. (No per-row `seed_run`
      column after all: nothing reads it, and the description lists the
      sources.)
    - Changed meaning (added 2026-10-24): environment parameters, formulas or
      environment differing from a source run's are reported (question for
      one run, notes in the summary); constraint thresholds are always the
      new run's, since only raw readings are archived.
    - Per run: variables + objectives must match by name, else skipped; a run
      missing a constraint of the new run is skipped (Xopt would count its
      points infeasible); missing observables fine; another environment with
      matching names allowed, with a warning.
    - Go summary dialog, only when seeding from several runs: each source
      with its points or why skipped, filters "older than N hours" and
      "outside the new ranges" (both off by default), "Seed with N of M".
    - Fresh trust region; description lists every source. Both GUIs (`-g`
      keeps its Data-tab dialog too). Extend `tests/continue_run_gui_test.py`.
  - [ ] 3. History signposting: labels with routine name, template,
    algorithm, number of points, best value; description as tooltip; a search
    box; the template name recorded at Go; the safe-badger snapshot records
    the run's archive file. (Not chosen for now: making "update description" save post-run notes;
    upstream's `update_run` is an empty stub.)
  - Not doing: live range edits within one run (pause, edit, resume), which
    needs a new channel into the run subprocess and TuRBO VOCS sync.
- [x] **Widen a variable's range mid-run and carry on with the data so far.**
  Built as Continue, phase 1 above; tried live by the user 2026-10-25 (`-mini`,
  heteroskedastic template, `Z:CUBE_X` widened).
  If a run shows the optimum lies past a variable's range, widen the range and
  resume, keeping every point already measured.
  - Exists: the full GUI's data panel ("Load displayed data into routine",
    "Skip initial point sampling") starts a new run from a displayed run's
    data (`gui/components/data_panel.py`, `prepare_run(data=...)` in
    `gui/pages/home_page.py`). The simplified `-mini` has no data panel.
    Xopt itself accepts new VOCS bounds plus existing data (the GP refits on
    all of it); Badger has no "edit bounds and continue" flow.
  - Would touch: a "Widen range and continue" action (stop, edit Range (Δ),
    restart with the run's data), probably in both GUIs; the hard limits in
    the environment still apply. safe-badger's snapshot needs nothing new.
  - Open: same run (append to its archive) or a new run seeded from it? What
    if the template's trust region (turbo) was already shrunk?
- [x] **Seed a run with historical data.** Built as Continue, phase 2 above
  ("Add its points"); seeding from several runs still to try live. Start a run from one or more
  archived runs' points as the GP's initial data instead of fresh initial
  points.
  - Exists: the same full-GUI data panel loads the displayed (archived) run;
    `-mini` lacks it. Points must have the same variables; points outside the
    new ranges, or taken when the machine was in another state, are a judgment
    call.
  - Would touch: bringing a "start from run(s)..." choice to `-mini`
    (history tab or Tuning Task box), and a way to pick several runs.
  - Open: how old is too old (drift)? Mark seeded points in the plots?
- [x] **Risk-aware constraints** (built 2026-11-18: a Risk Tolerance column per constraint, the
  Critical column renamed Stopping; `xopt-3.2.2-constraint-risk-tolerance.patch`,
  `badger-1.6.0-constraint-risk-tolerance.patch`; not yet tried on the machine). Constraints are modeled by GPs just like the
  objective; avoid proposing settings where a constraint is likely on the
  wrong side of its bound, or where its uncertainty makes that too likely,
  with the operator setting the acceptable risk.
  - Exists (Xopt 3.2.2): expected improvement already multiplies by each
    constraint's modeled probability of being satisfied
    (`_get_constraint_callables()` in `bayesian_generator.py`, a smooth
    weighting, not a hard limit), and `SafetyTurboController` keeps the trust
    region around feasible points. Nothing lets the operator say "at most 5 %
    chance of violating L:D7LMSM < 18".
  - Would touch: a per-constraint (or global) risk level, e.g. require
    P(satisfied) >= 1 - risk, as a hard filter in the acquisition optimization
    (an Xopt generator option or a small custom generator) or a tightened
    bound (mean + k sigma); a field in the template's constraints and in the
    GUI's constraint table. Interacts with `critical_constraint_names`
    (Badger stops a run on a critical violation).
  - Open: risk per constraint or one global number? What to do when no point
    meets the risk (stay put, or shrink the step)?
- [ ] **Propose gentle range expansions, risk-gated, each approved by the operator**
  (user's idea, 2026-11-24). When better performance looks out of reach inside the set
  ranges, propose widening one variable's range a little, but only where the modeled risk
  of violating any constraint there stays below the run's tolerance; the operator accepts
  or declines each proposal. First use case: RIL tuning with the loss objective
  (`01_Linac_LossObjective_RIL_tuning.yaml`).
  - Exists: Continue widens a range by hand and keeps the data (above); per-constraint
    Risk Tolerance on the measured value, with GaussExp noise shapes; the environment's
    hard limits, which no proposal may cross.
  - Open: the trigger for "out of reach" (incumbent at a range edge, the GP's slope
    pointing outward, or acquisition value just outside the box beating the best
    inside); step size (a fraction of the range, or where the constraint risk reaches
    the tolerance); whether the run pauses for the answer or carries on inside the old
    ranges; how a declined proposal is remembered.
  - Prior art, unexplored: safe-set expansion in safe BO (SafeOpt, and its
    descendants), which grows the explored region only where a constraint model is
    confident.
- [ ] **Heteroskedastic noise as the default (planned 2026-11-18).** Xopt fits its
  heteroskedastic GP for any outcome whose data row carries `<outcome>_var` (the variance
  of the recorded value); nothing needs listing in the VOCS (checked: Badger's evaluator
  keeps every key `get_observables` returns). Our testbed listed `_var` as VOCS
  observables, which fits a useless GP to each; environments should instead return
  `<name>_var` beside each requested outcome (an exception to "only what was asked for";
  update the developer guide and archetype).
  - [x] Calibration study (2026-11-18; `scripts/heteroskd_calibration.py`, findings in
    `docs/heteroskedastic-noise-model.md`): the heteroskedastic GP halves the overall
    probability error and maps the noise well from N >= 5, but at a 5 % tolerance's edge
    it overshoots in 13-26 % of fits for Gaussian noise and 32-70 % for skewed, spiky,
    or heavy-tailed noise (the standard GP is more conservative there).
  - [ ] Before trusting low risk tolerances: try a safety factor, recalibration from the
    run's residuals, or a heavier-tailed/transformed noise model; extend the study to
    two or more variables.
    - [x] Heavier tails (user prefers them; 2026-11-24, `docs/noise-shapes.md`, "Which
      shape keeps a tolerance honest"): with the noise's size right, skew-t is the most
      honest at 1 % (e.g. overshooting fits 0.05 vs Gaussian 0.60 for t3 noise; 0.30 vs
      0.85 skewed), GaussExp close; symmetric Student-t fails on skewed noise.
    - [x] Skew-t (Jones-Faddy) as a profile family in the xopt patch (2026-11-24, user's
      go-ahead): CDF tabulated for torch (16001 points in asinh(e), log F and log(1 - F));
      chosen per device by held-out 1 % tail calibration; `noise_shape_fit.py --profiles`.
    - [ ] Spikes more frequent than the tolerance: a mixture (outlier rate and size).
    - [ ] The residual overshoot from the GP itself (15-30 % of fits even with Gaussian
      noise): a safety factor or recalibration from the run's residuals.
  - [x] Machine check, first look (2026-11-18; `scripts/logger_noise.py`, findings in
    `docs/logger-read-noise.md`): Linac noise 0.5-0.6 % of level; cores near Gaussian,
    4-sigma tails 1.1-6.5 times Gaussian; B:BOOEFF skewed low; consecutive L:D7TOR
    pulses correlated, so s^2/N understates an N-pulse mean's variance by 1.6-2.1x (R).
  - [ ] Wider levels (other periods), per-cycle Booster reads (`@e,XX`), and
    device-to-device correlation (loss monitors vs L:D7TOR, pulse by pulse).
  - [x] Non-Gaussian noise (2026-11-19; `docs/noise-shapes.md`; patches
    `xopt-3.2.2-noise-shapes`, `badger-1.6.0-noise-shapes`): GaussExp profiles
    (Gaussian core, exponential tails) for five devices in `plugins/noise_profiles/`;
    the risk tolerance is now on the measured value, with the profile's shape; a
    staleness check of the run's residuals; `robust_outcomes` (robust GP) for gross
    outliers. Offline-tested only.
  - [ ] Try it on the machine: a RIL run with a risk tolerance on a profiled constraint
    (L:D7TOR > x; its profile is now a skew-t), and `robust_outcomes: [L:D7TOR]`
    (dropouts); watch the staleness log.
  - [ ] Refresh profiles from other periods; profiles for L:TK4RAD/L:TUNRAD need a
    quantized shape (they read in steps of about one sigma).
  - [ ] Then: `_var` from `average_events`, corrected for correlated events (batch
    means, or s^2/N times a per-device R), in `BasicPacsysInterface`; computed
    observables per event, then mean and variance. With N > 1 the single-reading shape
    no longer applies as is (an average is more Gaussian).
- [ ] **Front-end noise statistics as a central resource** (user, 2026-11-18): check (or
  ask the pacsys author) whether pacsys can provide front-end noise statistics for a
  reading; if not there, look for a central home (the ACNET device database, or another
  shared place). Long-standing wish: front ends declaring each device's known
  resolution up front.
  - [ ] **A central repository of fitted noise profiles** (user, 2026-11-24): profiles
    for chosen devices (the format of `plugins/noise_profiles/*.yaml`: family GaussExp or
    skew-t, fit date, source, held-out calibration), pulled when needed, above all at the
    start of a run, when the run's own data say little about the noise (the staleness
    check needs about 50 points). Today the profiles live in this repo.
  - [ ] **Archived Badger runs as noise history** (user, 2026-11-24): production has many
    archived runs; their readings (and the GP residuals of each run) are a second source
    for fitting and refreshing profiles, beside the data logger, and for testing the
    calibration on real runs rather than the mock-up.

- [ ] **Better GP visualizations.** Revisit how the model (objective and
  constraints, with uncertainty) is shown during a run.
  - Exists: Badger 1.6.0's BO visualizer extension (extensions palette,
    `add_bo_visualizer`), and Xopt's `visualize_model` (with
    `show_feasibility`). Badger 1.6.1 (released 2026-10-15) adds a BAX
    visualization extension (PR #275) and a few fixes (incl. the turbo
    controller fix from this repo, PR #284).
  - First step: try 1.6.1's and upstream main's visualizers before building
    anything. Moving to 1.6.1 means re-checking all 13 patches against it.
- [ ] **Smart data curation for long runs** (possibly bigger than Badger: a
  tool Badger/Xopt could use). Fitting a GP on N points costs O(N^3), so a
  long run slows down. Between iterations, prune redundant points, older ones
  first, keeping the most informative, to hold N (and the cost) roughly fixed.
  Not a new problem: **needs a literature search first.**
  - Exists (Xopt 3.2.2): `TimeDependentBayesianGenerator`
    (`generators/bayesian/time_dependent.py`) has `forgetting_time`, which
    drops data older than a time window (age only, not informativeness); the
    time-dependent generators aren't among the 8 algorithms Badger offers.
    The trust region's `restrict_model_data` fits the GP only to points inside
    the region, which also bounds N, by location.
  - Literature review done: [docs/literature/gp-data-curation.md](docs/literature/gp-data-curation.md).
    Closest fits: W-DBO / BOLT (Bardou et al. 2024–25: drop the point whose
    removal moves the posterior least; BOLT also picks the budget), the APS
    adaptive-BO subsampling (Kuklev et al. 2022), and greedy budgeted subsets
    (Csató & Opper, IVM) for static objectives. The review ends with a
    suggested prototype: a `get_training_data` override with a point budget,
    benchmarked on the VirtualAccelerator sim. First step: measure fit time
    vs. N on the operator machine.
  - Would touch, if pursued: a pruning step between Xopt's `add_data` and the
    GP fit (a custom generator or model constructor), a budget parameter, and
    a record of pruned points so the archive keeps everything.
  - Open: what "informative" means here (near the optimum? diverse?
    constraint boundaries?), and how it interacts with drift (old data may be
    wrong, not just redundant).

- [ ] **Draft an environment from the Elog and Device DB** (idea 2026-11-05). For a given
  machine: scrape the Elog for an initial list of the variables and objectives
  operators tune and watch; estimate each variable's valid range from its
  history; hand back a working draft environment. The screen grabs in Elog
  entries (parameter pages, plots) could help build those first lists.
  - Would reuse: `pixi run new-env` (the draft is a filled-in copy of the
    archetype, so the lint, smoke, and feature tests check it at once); the
    Elog search work in `~/Development/elog_investigation` (access, speed).
  - Ranges: from device history (the ACNET data logger: no logger client in
    pacsys 0.3.0 seen yet, so how to read it is open), cross-checked against
    the device database's limits (`pacsys.devdb`). Draft hard limits must be
    marked unconfirmed until the hardware owner signs off.
  - Open: Elog access needs a login session (no automation yet); reading
    device names from screen grabs needs OCR or a vision model, and its error
    rate is untested; which entries count as "tuning" for a machine; how to
    pick read/set pairs and mults from the text.
  - In progress elsewhere (user, separate sessions, 2026-11-05): on-premise OCR
    of the screen grabs, with the extracted strings and data stored in the
    Elog's backend DB tables. Then this tool reads that text from the DB and
    does no OCR itself.
  - Landed 2026-11-11, text-only (no OCR, no vision model): the `tuning-reflection`
    skill in `ProjectDT_FNAL/.claude/skills/`. Elog -> catalog -> data-logger
    pull (pacsys LOGGER reads, resolved: `DEVICE@<event><-LOGGER:<t1>:<t2>`) ->
    reflection -> draft template, reusing `new-env` only when an environment
    itself needs to change. First run: RIL tuning (`docs/reflections/ril/`,
    now `tuning_templates/01_Linac_LossObjective_RIL_tuning.yaml`, promoted 2026-11-17).
    DevDB cross-check still not attempted (still times out from the dev Mac as
    of the RIL run, before that session's VPN fix -- worth retrying).
  - Second run, landed 2026-11-12: Booster injection tuning, the first Booster
    environment (region `03`, no DevDB access, device names and ranges from elog
    screenshots read with a vision model). Objective is a computed observable
    (`WorstLossNorm`, max over calibrated BLMs of normalized deviation from
    baseline), not one device -- `B:BOOEFF` is a floor constraint instead, per
    the user's framing that efficiency is a thing to not let slip, not the thing
    to chase. `docs/reflections/booster_injection/`,
    `plugins/environments/03_Booster_InjectionTuning_Pacsys/`,
    `tuning_templates/development/03_Booster_InjectionTuning_Pacsys.yaml`.
    Found along the way: a bare LOGGER DRF with no `@event` works for this
    region when explicit event qualifiers (`@p,...`, `@e,...`) do not; worth
    trying first on any future region. Also found: the earlier RIL reflection's
    claim that `B:BOOEFF` has no logger data was wrong for that same reason --
    not yet corrected in `docs/reflections/ril/`.
  - [ ] 2026-11-19: bare DRFs return every device the RIL probe had listed as
    missing, all RIL `.SETTING`s included, so its "settings are not logged" is wrong
    too. `tasks/ril.yaml` (ProjectDT_FNAL) updated to match, not committed there.
    Next: commit it there (user's say), rerun the RIL reflection with the
    settings-based window, and correct `docs/reflections/ril/`.

- [ ] **RF capture tuning draft template** (idea 2026-11-11, after the RIL and
  Booster-injection reflections). Booster RF-capture tuning (transition frequency,
  DC1 offset) is the third recurring named tuning task found in the elog (4
  sessions in the last 30 days alone), often done in the same shift as Booster
  injection tuning but with a distinct objective (bucket capture efficiency, not
  orbit/losses). Settled 2026-11-19: a template against the Booster-wide
  `03_Booster_Pacsys`, which holds the RF capture and transition devices.

- [ ] **Variable ranges from alarm limits, or around a typed center** (idea 2026-11-17).
  Two new ways to set a variable's range, beside today's `limit_option_idx` 0
  (ratio of the current value), 1 (ratio of the hard-limit span), and 2 (+-delta
  around the current value):
  - **Alarm limits:** min and max = the device's ACNET analog alarm limits, read
    when the template loads. pacsys reads alarm blocks (`pacsys.alarm_block`:
    `AnalogAlarm`, `LimitType`), and `FakeBackend.set_analog_alarm` allows an
    offline test.
  - **Typed center:** the center = a value typed in the variable table, not the
    live readback, with the range +-delta around it.
  - Would touch: the `-mini` variable table's Range column and its patch,
    `vrange_limit_options` in templates (new `limit_option_idx` values),
    `template_lint_test.py`, and `BasicPacsysInterface` for the alarm read.
  - Open: alarm limits as the window or also as the hard limits (always inside the
    environment's)? What if a device has no alarm, or the limits are nominal/
    tolerance rather than min/max? Is a typed center kept in a saved template?

- [x] **Switching between MOBO and EI templates logged a spurious ERROR** (found and fixed
  2026-11-18, both ways, both GUIs): `badger-1.6.0-quiet-generator-switch.patch`.
- [ ] **Plots-only view in `-mini`** (idea 2026-11-17): an option to collapse the
  settings (the Tuning and History tabs on the left) into a sidebar, open the window
  much larger, and show just the plots, e.g. for watching a run on a large screen.
  - Would touch: the `-mini` layout in `badger-1.6.0-mini-simpler-ui.patch` (the
    splitter between the tabs and the plots can collapse a pane; a toggle on the
    action bar or a keyboard shortcut), and the window's starting size.
  - Open: remembered between sessions or per launch? A launch flag for the operator
    shortcut (e.g. `safe-badger mini --plots-only`)? Do the action bar's buttons
    (Stop, Pause) stay visible? They should, for safety.
