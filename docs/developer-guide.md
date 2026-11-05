# Developer guide: writing a Badger environment and a tuning template

For new developers. Setup is in the README's Quick Start; this guide starts
once `pixi run setup` has passed.

## Terms

- **Environment**: a Python class (one folder in `plugins/environments/`) that
  says which devices Badger may change and which it may read, and how to do
  both. It is what the GUI calls the **Machine Interface**.
- **Interface**: the layer that actually talks to the control system.
  `BasicPacsysInterface` (pacsys, used by every real-world template) or
  `BasicAcsysInterface` (acsys, kept but unused). An environment names one in
  its `configs.yaml`.
- **Tuning template** (template): a YAML file in `tuning_templates/` that picks
  an environment, sets its parameters, and chooses the variables, objectives,
  constraints, and algorithm for one tuning task. The GUI calls it a
  **Tuning Task**.
- **VOCS** (Variables, Objectives, Constraints, Observables): the template's
  choice of what to vary, what to minimize or maximize, what limits to keep,
  and what else to record.
- **Variable**: a device Badger may set, with **hard limits**, the range the
  environment allows (`variables = {name: [lo, hi]}`). A template's ranges
  must lie inside them.
- **Observable**: anything Badger may read: a device, or a value the
  environment computes. Objectives and constraints are chosen from these.
- **Settings role**: the DPM role used to write settings; the Kerberos
  principal running Badger must hold it. `nosettings` means read only.

## Before you start

- **Never write to real devices from a test.** Tests use pacsys's
  `FakeBackend` or a stub interface. For a live try, use the scratch devices
  (`development/ZZ_PacsysTesting.yaml`: `G:AMANDA`, `Z:CUBE_X/Y/Z`) under
  safe-badger.
- **Copy a working pair.** `01_Linac_EnergyStabilization_Pacsys` (environment)
  and `development/01_Linac_Phases_EnergyStabilization_Pacsys.yaml` (template)
  are short, current, and use most features below. `ZZ_PacsysTesting` is the
  simplest.
- **Names follow a convention**, so the pickers sort in beam order: see the
  README's "Environment and template naming convention". In short,
  environments are `<region>_<Descriptive>_Pacsys`, and templates
  `<region>_<task>_<env>_Pacsys.yaml`.

## An environment

A folder `plugins/environments/<name>/` with three files:

```
__init__.py    the Environment class
configs.yaml   name, version, dependencies, interface
README.md      what "Open Docs" shows in the GUI (see "The README" below)
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

`__init__.py`, the minimal shape (from `01_Linac_EnergyStabilization_Pacsys`):

```python
from typing import Dict
from badger import environment
from badger.errors import BadgerNoInterfaceError


class Environment(environment.Environment):
    name = "01_Linac_MyTask_Pacsys"          # must match the folder
    variables = {                             # devices it may set: hard limits
        "L:V5QSET": [-38.0, -32.0],
    }
    observables = [                           # names it may read
        "B:400DFT",
        "B:400DFT-SETPOINT",
    ]
    # Parameters: pydantic fields, edited in the GUI's Machine Interface panel
    sample_events: Dict[str, str] = {'default': '@e,15,e,0'}
    setpoints: Dict[str, float | str | None] = {'B:400DFT': 'hold'}
    settings_role: str = 'nosettings'
    debug: bool = False

    def get_variables(self, variable_names: list[str]) -> dict:
        if not self.interface:
            raise BadgerNoInterfaceError
        return self.interface.get_values(variable_names, debug=self.debug)

    def set_variables(self, settable_devices: dict[str, float]):
        if not self.interface:
            raise BadgerNoInterfaceError
        self.interface.set_values(settable_devices, settings_role=self.settings_role,
                                  debug=self.debug)

    def get_observables(self, observable_names: list[str]) -> dict:
        if not self.interface:
            raise BadgerNoInterfaceError
        return self.interface.get_values(observable_names, sample_events=self.sample_events,
                                         setpoints=self.setpoints, debug=self.debug)
```

Rules that have bitten us:

- **Parameters are pydantic fields with type hints**: Badger enforces pydantic
  strictly. Use simple types (`str`, `int`, `float`, `bool`, `list[str]`,
  `Dict[str, ...]`); the GUI edits them, and a `{name: value}` field gets an
  **Edit...** table. Give every field a safe default (`nosettings`, not a
  real role).
- **Don't modify `observable_names`**: copy it first if you need to add the
  inputs of a computed observable.
- **Return only what was asked for.** Inputs read just to compute something
  (arrays, loss monitors) must not come back: they become columns in Badger's
  data.
- **Computed observables**: by convention their names end in `_calc`, or are
  plain names the interface doesn't know (`TwoWells`, `W_SumLosses`). Read the
  inputs, compute, and add the result. See `ZZ_PacsysTesting` (`AbsProduct`,
  `TwoWells`).
- **Hard limits are the last line of defense.** Badger refuses to set a value
  outside them, and the GUI unticks a variable whose current value is outside
  them. Make them as tight as the hardware needs.
- **An Acsys twin** (same class, other interface) is optional and no longer
  used by templates. New environments need only the `_Pacsys` one.

## What the Pacsys interface does for you

Names in `variables` and `observables` can use these forms:

| Form | Meaning |
|---|---|
| `L:ATRMHU` | a plain device: set and read back its SETTING |
| `L:CDPHAS,L:LDPADJ` | **read/set pair**: read the first, set the second |
| `L:CDPHAS,L:LDPADJ,tol2@0.1` | the same, and after setting, wait until 2 readings agree within 0.1 |
| `B:400DFT-SETPOINT` | the **squared error** of `B:400DFT` from its setpoint (see `setpoints`) |
| `Z:ITGSIG_1_SRS[:]` | an array reading |
| `L:BPMS[:]\|rms` | an array reduced to one number: `mean`, `rms`, `std`, `min`, `max`, `sum`, `absmax` |

Interface parameters your environment passes through (as in the example):

- `sample_events`: which clock event each reading uses,
  `{device or 'default': '@e,<event>,e,<delay>'}`.
- `setpoints`: targets for `-SETPOINT` observables: a number, or `'hold'` (the
  first reading of the run).
- `periods`: `{reading device: period}` for phases; readings are unwrapped so a
  wrap through 0 is not a jump. Declare such variables two periods wide (README:
  "Periodic (phase) devices").
- `average_events`: `{device or 'default': N}`, the mean of N fresh events.

Plus, in the RIL environments: **mults** (several quads moved together in fixed
proportion) and **BulkPS** (limits on trims sharing a power supply); see the
README's "For Developers".

## The README

The GUI's **Open Docs** (Machine Interface panel) shows the environment's
`README.md`. Operators read it, so keep it plain. Sections, as in the existing
environments:

```
# <Readable name> (Pacsys)
One paragraph: what it tunes, and why.
## What it can tune (variables)
## What it can read (objectives, constraints, observables)
## Parameters (Machine Interface)
## Safety
```

## A tuning template

Easiest: load an existing template in `-mini`, change it, and **Save as...**
(it saves under `tuning_templates/saved/`, which git ignores); then move the
file to `tuning_templates/development/` and edit it there. The keys
(`tests/template_lint_test.py` requires the first group):

| Key | What it holds |
|---|---|
| `name`, `description` | the description is shown to operators: say the goal, objective, variables, windows, and anything unusual (see the EnergyStabilization template) |
| `environment` | `name` and `params` (the parameters above) |
| `vocs` | `variables` (`{name: [lo, hi]}`), `objectives` (`{name: {type: MinimizeObjective}}`, or `MaximizeObjective`), `constraints` (`{name: {type: LessThanConstraint, value: 18.0}}`, or `GreaterThanConstraint`), `observables`. That is the form Save as writes; the short forms `MINIMIZE` and `[LESS_THAN, 18.0]` also work |
| `generator` | the algorithm and its settings (`expected_improvement` is the usual choice; see `docs/algorithms/`) |
| `relative_to_current` | `true`: each variable's window is computed around its current value at load, and again at Go (see below); `false`: the `vocs` ranges as written |
| `vrange_limit_options` | per variable, how the window is computed: `limit_option_idx` 0 = ±½·`ratio_curr`·\|current\|, 1 = ±½·`ratio_full`·(hard-limit span), 2 = ±`delta` |
| `initial_point_actions` | the first points: `add_curr` (current values), `add_rand` (`n_points` random points near the current values, within `fraction` of each range) |
| `critical_constraint_names` | constraints whose violation stops the run |
| `initial_points` (optional) | explicit first points, `{variable: [values]}`; replaces the actions |
| `formulas` (optional) | computed objectives from readings, e.g. `` `L:A` + `L:B` `` (backticks around names; NumPy allowed) |

Where templates live: `simulation/` (no control network), `development/`
(machine templates being worked on), and the top level (operations; the only
level operators should pick from). Move a template to the top level only when
it is ready for operators, and drop the `_Pacsys` suffix then.

## Testing

From the repo root, in this order:

1. `pixi run python tests/template_lint_test.py`: every template loads as the
   GUI would.
2. An offline test of your environment: copy `tests/env_fixes_test.py` (a stub
   interface) or `tests/heteroskd_noise_test.py` (pacsys `FakeBackend`). Check
   `get_observables` returns what was asked, and computed values are right.
3. The whole suite:
   `for t in tests/*_test.py; do pixi run python "$t" || echo "FAIL $t"; done`.
   It takes 10 to 20 minutes; GUI tests run offscreen.
4. Live, read only: load the template with `settings_role: nosettings` and
   watch the Current column and plots.
5. Live, writing: on the machine, under safe-badger, with the operators' OK:
   `pixi run safe-badger mini -t development/<your template>.yaml`.

Badger's own code is patched at setup (`patches/`, `pixi_setup.sh`); after
changing a patch, re-run `pixi run setup -- --yes`. Never edit
`.pixi/envs/.../site-packages` by hand. See `patches/README.md`.

## Checklist before a pull request

- [ ] Environment folder, `name`, and template file follow the naming
      convention.
- [ ] Hard limits checked with the hardware owner; defaults are safe
      (`nosettings` role).
- [ ] README with the five sections; template `description` filled in.
- [ ] `template_lint_test.py`, your offline test, and the full suite pass.
- [ ] Tried read only on the machine; writing only under safe-badger.
- [ ] `docs/log.md` entry for anything non-obvious you found.

## Where to read more

- `README.md` "For Developers": naming, phases, BulkPS, mults, averaged and
  array observables.
- `docs/safe-badger.md`: what is restored, when, and how.
- `docs/guides/minimode.md`: the operator's view (the GUI's "?").
- `patches/README.md`: what each Badger patch changes.
- `docs/log.md`, `docs/progress.md`, `TODO.md`: history, status, open work.
