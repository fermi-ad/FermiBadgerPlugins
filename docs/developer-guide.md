# Developer guide: writing a Badger environment and a tuning template

For new developers. Setup is in the README's Quick Start; this guide starts
once `./bootstrap.sh` (or `pixi run setup`) has passed.

## Quickstart: a new environment and template in ten minutes

One command, from the repo root, with your new environment's name
(`<region>_<Descriptive>_Pacsys`; see "Names" below):

```bash
pixi run new-env 01_Linac_MyTask_Pacsys
```

It copies the **archetype**, `ZZ_Archetype_Pacsys` and its development template,
to `plugins/environments/01_Linac_MyTask_Pacsys/` and
`tuning_templates/development/01_Linac_MyTask_Pacsys.yaml`. It renames them
throughout, and makes both read only (`settings_role: nosettings`). Then it
checks them offline (nothing reaches ACNET): the template loads as the GUI
would (`tests/template_lint_test.py`), and the environment reads and sets on a
fake ACNET (`tests/env_smoke_test.py`). It refuses a name that breaks the
convention, and never overwrites. To start from another example (table below),
add `--from <environment>`.

Why the archetype (see "Terminology to know"): the operations environments,
such as RIL, can change without changing what new environments start from.

Then edit (here `$NEW` is your environment's name):

1. **`plugins/environments/$NEW/__init__.py`**: swap the devices in
   `variables` (each with its hard limits `[lo, hi]`) and `observables`. Delete
   what you don't need: the mults, BulkPS, `w_sumsq` and their code (see
   "Conventions in the code you copied" below for what each piece does).
2. **`plugins/environments/$NEW/README.md`**: the title, the paragraph, and the
   device lists. Operators read it through the GUI's **Open Docs**.
3. **`tuning_templates/development/$NEW.yaml`**: the `description`, the
   `environment.params` (they override the environment's defaults), and
   `vocs`: the variables, objectives, constraints and observables of this one
   task. Every name in `vocs` must be in the environment; every variable needs
   an entry in `vrange_limit_options` (the window around its current value).
4. Run the two checks again (`pixi run python tests/template_lint_test.py` and
   `pixi run python tests/env_smoke_test.py $NEW`), then the whole suite (see
   "Testing").
5. On the machine, read only:
   `pixi run safe-badger mini -t development/$NEW.yaml`. Check the **Current**
   column and the plots. Only when that looks right, set a real role, with the
   operators' OK (see "Testing", step 5).

An easier way to make a template: load an existing one in the GUI, change it,
and **Save as...**. It saves under `tuning_templates/saved/` (git ignores it);
move the file to `tuning_templates/development/` and rename it.

**Which example to start from** (`--from`):

| Start from | When |
|---|---|
| `ZZ_Archetype_Pacsys` (the default) | most tasks: every feature, to keep or delete |
| an operations environment, e.g. `01_Linac_RIL_tuning_Pacsys` | a variant of one that exists, with its devices and limits |
| `ZZ_PacsysTesting` | the smallest; scratch devices only, for learning |

## Terminology to know

- **Environment**: a Python class (one folder in `plugins/environments/`) that
  specifies the devices Badger may change and which it may read, and how to do
  both. The GUI calls it the **Machine Interface**.
- **Interface**: the layer that talks to the control system.
  `BasicPacsysInterface` (ACNET through pacsys) serves every real-machine
  environment; an environment names it in its `configs.yaml`, but it is
  effectively hidden to the users. There are others for use with simulation.
- **Tuning template** (template): a YAML file in `tuning_templates/` that picks
  an environment, sets its parameters, and chooses the variables, objectives,
  constraints, and algorithm for one tuning task. The GUI calls it a
  **Tuning Task**.
- **VOCS** (Variables, Objectives, Constraints, Observables): a Badger term:
  each template's choice of what to vary, what to minimize or maximize, what
  constraints define an acceptable solution, and what else to keep an eye on.
- **Variable**: a device Badger may vary, with **hard limits**: the range the
  environment allows (`variables = {name: [lo, hi]}`). A template's ranges
  must lie inside them.
- **Observable**: anything Badger may read: a device, or a value the
  environment computes. Objectives and constraints are chosen from these.
- **Archetype**: `ZZ_Archetype_Pacsys`, an environment kept only to be copied.
  It holds every feature in "Conventions in the code you copied", with real
  device names, and its template uses them. It never writes (it refuses any
  role but `nosettings`); `new-env` removes that guard from your copy.
  `tests/archetype_test.py` checks every feature.
- **Settings role**: the DPM role used for writing settings; the Kerberos
  principal running Badger must be in the role's users, and the devices must
  be in the role, too. `nosettings` means read only.

## Names

Names follow a convention, so the pickers sort in beam order (README,
"Environment and template naming convention"):

- environment: `<region>_<Descriptive>_Pacsys`, e.g. `01_Linac_RIL_tuning_Pacsys`;
  the folder, `name` in `__init__.py`, and `name` in `configs.yaml` all match;
- template: `<region>_<task>_<env>_Pacsys.yaml` in `tuning_templates/development/`,
  e.g. `01_Linac_OutputTrajectory_RIL_tuning_Pacsys.yaml`, or just
  `<environment name>.yaml` for an environment's general-purpose template.

Region codes: `01` Linac, `02` Xfer400MeV, `03` Booster, `04` BNB, `05`
Xfer8GeV, `06` MIRR, `07` NuMI, `08` P1toDR, `09` DeliveryRing, `10`
MuonCampus, `99` Sim.

## Conventions in the code you copied

### Device names: what the pacsys Interface does for you

A name in `variables` or `observables` can take these forms:

| Form | Meaning |
|---|---|
| `L:ATRMHU` | a plain device: Badger sets it, and reads back its SETTING |
| `L:CDPHAS,L:LDPADJ` | a **read/set pair**: read the first, set the second |
| `L:CDPHAS,L:LDPADJ,tol2@0.1` | a **settle triplet**: the pair, plus a tolerance: after each setting, wait until 2 readings agree within 0.1 |
| `B:400DFT-SETPOINT` | the **squared error** of `B:400DFT` from its setpoint (see `setpoints`), for minimizing |
| `Z:ITGSIG_1_SRS[:]` | an array reading |
| `L:BPMS[:]\|rms` | an array reduced to one number: `mean`, `rms`, `std`, `min`, `max`, `sum`, `absmax` |

### Read/set pairs and settle triplets

Use a pair when the knob you set is not the device that shows its effect: in
the archetype (as in EnergyStabilization), Badger sets the phase adjust
`L:LDPADJ` and reads the measured phase `L:CDPHAS`.

- The variable's value is the **reading** (the first name). Badger writes the
  value it chooses to the **setting** (the second). The two must share units
  and meaning, as a measured and an adjusted phase do.
- After a write, a pair alone is not checked: the interface warns once that
  its reading is not verified.
- A **triplet** `READ,SET,tolN@T` adds a settle wait: after each write, the
  interface reads `READ` until its last **N** readings span no more than **T**
  (in `READ`'s units). `tol2@0.1` means two readings within 0.1. If that does
  not happen within 15 s, the setting fails and the run stops.
- A plain device is checked: its stored SETTING must match the value sent
  (a warning if it doesn't).
- safe-badger records and restores the setting device (the second name).
- In `get_variables`, the archetype reads pairs with `interface.get_values`
  (the reading) and plain devices with `interface.get_settings` (the
  SETTING). Some operations environments read everything one way; if you copy
  one of those and add a pair, read it the archetype's way.

### `-SETPOINT` observables and `setpoints`

`B:400DFT-SETPOINT` reads `B:400DFT` and returns `(reading − target)²`, ready to
minimize. The per-device target comes from the `setpoints` parameter,
`{device: number or 'hold'}`. `'hold'` means "the first reading of the run",
which regulates a quantity back to where it was when the run started.

### Phases: `periods`

`periods` is `{reading device: period}`, e.g. `{'L:RFQPAH': 360.0}`. A phase
comes back wrapped into one period; the interface unwraps it so a pass through
0 is not a 360° jump, and `get_variables` moves it to the branch nearest the
middle of its hard limits. Declare a free-running phase variable two periods
wide (`[0., 720.]`), as the archetype's `L:CDPHAS` pair is; its `L:RFQPAH` has
tight operating limits instead. See the
README, "Periodic (phase, angle) devices".

### Timing and averaging: `sample_events`, `average_events`

- `sample_events`: a dictionary of data request timing: which clock event each reading uses,
  `{device or 'default': '@e,<event>,e,<delay>'}`. The archetype reads on $52,
  `B:BOOEFF` on $1F, and its arrays on $83.
- `average_events`: `{device or 'default': N}`. A reading becomes the mean of N
  fresh events (N > 1 needs an event, not `@i`). It costs N cycles per point
  and gives a smoother objective.

### Mults: several devices on one knob

A **mult** is a console-style knob: one Badger variable that moves several
devices together in fixed proportion. In the archetype (as in RIL), `mult:MUQ`
moves `L:MUQ1` and `L:MUQ2`.

- The variable `mult:<name>` is an integer step count within its hard limits
  (`[-10, 10]`).
- Each member is set to `as_found + coefficient × step × steps`. `as_found` is
  the member's setting the first time the run touches any mult.
- The `mults` parameter holds the knobs:
  `{name: {step: size, members: {DEV: coefficient}}}`. Operators can change it
  in the GUI.
- A member that would leave its own hard limits is clipped, not refused. The
  observable `MultOOB_<name>` reports the fraction of the last step lost (0
  good, 1 = the member could not move); constrain it if that matters.
- Each member must also be a plain variable, with its own hard limits; that is
  also what lets safe-badger restore it.
- The code to keep in a copy: `_as_found`, `_mult_steps`, `_mult_oob`,
  `_capture_as_found`, the mult lines in `get_variables`, `set_variables` and
  `get_observables`. The logic lives in `plugins/mults.py`; `tests/mults_test.py`
  tests it.

### BulkPS: trims that share a power supply

Some trims share one **bulk power supply** (BulkPS), which trips off if they
draw too much together.

- The `BulkPS_Limit` parameter lists each supply: its `devices`, and either
  `limit` (the sum of |I| stays ≤ it) or `positive` and `negative` (the sum of
  positive currents ≤ one, and the magnitude of the sum of negative currents ≤
  the other). The archetype's defaults are in `_BULK_PS` at the top of the file.
- Before every write, `set_variables` checks each budget. If one is over, it
  moves the largest current being set toward zero until it fits. Members not
  being set count at their live setting; if they alone exceed the limit, the
  write is refused.
- Each budget is also an observable, `BulkPS_<group>` (or `_Pos` and `_Neg`),
  so a template can constrain it, as the archetype's does.
- The logic lives in `plugins/supply_limits.py`.

### Computed observables

An observable the interface doesn't read directly. The archetype has three:
`W_SumLosses` (a weighted sum of loss monitors, weights in `w_sumsq`),
`VTrajError_SumSqBPM_calc` (a sum of `-SETPOINT` errors), and
`SpillDutyFactor_calc` (from two whole arrays, with numpy). `get_observables`:

1. copies the list it is given (never modify the caller's list);
2. adds the inputs it needs and removes the computed names;
3. reads, and computes;
4. returns **only the names asked for**, not the inputs. Anything else
   returned would become an unrequested column in Badger's accumulating run
   data.

By convention a computed name ends in `_calc`, or is a plain name that is not a
device (`W_SumLosses`, `TwoWells`). Simpler examples: `ZZ_PacsysTesting`
(`AbsProduct`, `TwoWells`).

### Safety you get for free

- **Environment variable ranges are hard limits**: Badger refuses to set a
  value outside them, and the GUI unticks a variable whose current value is
  outside them. Make them as tight as the hardware needs, but leave room for
  tuning, and check them with the hardware owner.
- **Settings role**: with `nosettings`, nothing is written.
- **safe-badger** snapshots every device the environment can write, and
  restores them if Badger is interrupted (`docs/safe-badger.md`).
- **Bad readings stop the run**: a device error is raised, not passed on as a
  number.

## Make (or modify) an Environment

A folder `plugins/environments/<name>/` with three files:

```
__init__.py    the Environment class
configs.yaml   name, version, dependencies, interface
README.md      what "Open Docs" shows in the GUI
```

`configs.yaml`:

```yaml
name: "01_Linac_MyTask_Pacsys"
version: "0.1"
dependencies:
  - badger-opt
  - numpy
interface:
  - BasicPacsysInterface
```

Operators read the README, so keep it direct. Its sections, as in the existing
environments:

```
# <Readable name> (Pacsys)
One paragraph: what it tunes, and why.
## What it can tune (variables)
## What it can read (objectives, constraints, observables)
## Parameters (Machine Interface)
## Safety
```

Gotchas that have bitten before:

- **All Environment Parameters are pydantic fields with type hints**: Badger
  enforces pydantic strictly. Use simple types (`str`, `int`, `float`, `bool`,
  `list[str]`, `Dict[str, ...]`), and we can add more if you need. The GUI user
  can edit them. Give every field a safe default (like role `fakefake`, not a
  real role).
- Never modify `observable_names`, and return only what was asked for (see
  "Computed observables").

## Make tuning templates for your Environment

The keys; `tests/template_lint_test.py` requires the first group:

| Key | What it holds |
|---|---|
| `name`, `description` | the description is shown to operators: say the goal, objective, variables, windows, and anything unusual (see the archetype's template) |
| `environment` | `name`, and `params` (the environment's parameters, overriding its defaults). `name` should be your new Environment. |
| `vocs` | `variables` (`{name: [lo, hi]}`), `objectives` (`{name: {type: MinimizeObjective}}`, or `MaximizeObjective`), `constraints` (`{name: {type: LessThanConstraint, value: 18.0}}`, or `GreaterThanConstraint`), `observables`. That is the form `Save as` writes; the short forms `MINIMIZE` and `[LESS_THAN, 18.0]` also work |
| `generator` | the algorithm and its settings (`expected_improvement` is the usual choice; see `docs/algorithms/`) |
| `relative_to_current` | `true`: each variable's window is computed around its current value at load, and again at Go; `false`: the `vocs` ranges as written |
| `vrange_limit_options` | per variable, how the window is computed: `limit_option_idx` 1 = ±½·`ratio_full`·(hard-limit span), 2 = ±`delta`. (0 = ±½·`ratio_curr`·\|current\| collapses to nothing at 0, so the lint refuses it when `relative_to_current` is true) |
| `initial_point_actions` | the first points: `add_curr` (current values), `add_rand` (`n_points` random points near the current values, within `fraction` of each range) |
| `critical_constraint_names` | constraints whose violation stops the run |
| `initial_points` (optional) | explicit first points, `{variable: [values]}`; replaces the actions |
| `formulas` (optional) | computed objectives from readings, e.g. `` `L:A` + `L:B` `` (backticks around names; NumPy allowed) |

Where templates live: `simulation/` (no control network), `development/`
(machine templates being worked on), and the top level (operations; the only
level the GUI's dropdown lists). Move a template to the top level only when it
is ready for operators, and drop the `_Pacsys` suffix then.

## Testing

**Never write to real devices from a test.** Tests use pacsys's `FakeBackend`
or a stub interface. From the repo root, in this order:

1. `pixi run python tests/template_lint_test.py`: every template loads as the
   GUI would.
2. `pixi run python tests/env_smoke_test.py <your environment>`: reads and a
   set on a fake ACNET. For mults, pairs, arrays and computed observables,
   copy a focused test: `tests/archetype_test.py` (every feature, on
   `FakeBackend`) or `tests/env_fixes_test.py` (a stub interface).
3. The whole suite:
   `for t in tests/*_test.py; do pixi run python "$t" || echo "FAIL $t"; done`.
   It takes 10 to 20 minutes; GUI tests run offscreen.
4. Live, read only: on the machine, with `settings_role: nosettings`,
   `pixi run safe-badger mini -t development/<your template>.yaml`, and
   watch the Current column and plots. For a first live try of writing, use
   the scratch devices (`development/ZZ_PacsysTesting.yaml`: `G:AMANDA`,
   `Z:CUBE_X/Y/Z`).
5. Live, writing: set the real role in the template, then run it under
   safe-badger, with the operators' OK.

Badger's own code is patched at setup (`patches/`, `pixi_setup.sh`); after
changing a patch, re-run `pixi run setup -- --yes`. Never edit
`.pixi/envs/.../site-packages` by hand. See `patches/README.md`.

## Checklist before a pull request

- [ ] Environment folder, `name`, and template file follow the naming
      convention.
- [ ] Hard limits checked with the hardware owner; defaults are safe
      (`nosettings` role).
- [ ] README with the five sections; template `description` filled in.
- [ ] `template_lint_test.py`, `env_smoke_test.py`, and the full suite pass.
- [ ] Tried read only on the machine; writing only under safe-badger.
- [ ] `docs/log.md` entry for anything non-obvious you found.

## Where to read more

- `README.md` "For Developers": naming, phases, BulkPS, mults, averaged and
  array observables.
- `docs/safe-badger.md`: what is restored, when, and how.
- `docs/guides/minimode.md`: the operator's view (the GUI's "?").
- `patches/README.md`: what each Badger patch changes.
- `docs/log.md`, `docs/progress.md`, `TODO.md`: history, status, open work.
