# Badger Patches

## Summary

### Patches for Badger 1.6.0 and Xopt

| Patch | Description | Required Components |
|-------|-------------|---------------------|
| `pydantic_editor-badger-1.6.0-dict-subtypes.patch` | Fixes "Dict type must have subtypes" error, handles `turbo_controller: null`, and fixes YAML parsing for 'None' strings | Badger 1.6.0 |
| `xopt-3.2.2-turbo-serialization.patch` | Stops the `PydanticSerializationUnexpectedValue` warning Badger logs on every iteration with a TuRBO controller: declares `_initial_state` as a private attribute and stores `best_value` as a plain float | Xopt 3.2.2 |
| `badger-mini-config.patch` | Initializes the settings singleton before template loading in `-mini` | Badger 1.6.0 |
| `badger-mini-var-table-env-configs.patch` | Rebuilds the `-mini` variable table's env configs *and* its rows from the template, so the table lists and queries the template's machine rather than the plugin defaults | Badger 1.6.0 |
| `badger-1.6.0-device-list-gui.patch` | Lists variables in environment (beam) order instead of alphabetical when a template/routine loads; replaces each "Filter…" box and "Show Checked Only" checkbox in `-g` and `-mini` with a search dropdown that opens on focus, lists every item in beam order with a check icon on selected ones, and adds an item when picked; lists always show checked rows; the "Enter new … here" placeholder rows are hidden and all four tables size to their visible rows (zero rows when nothing is checked); variable table sits in a collapsible box. Apply **after** the two `-mini` patches. | Badger 1.6.0 |

## Issues Fixed

1. **"Dict type must have subtypes"** - Occurs when loading templates with dict/list environment params (e.g., `setpoints: {qx: 9.049, qy: 9.035}`)
2. **`turbo_controller: null` handling** - Prevents warnings and ensures correct null serialization
3. **YAML 'None' strings** - Fixes parsing of 'None' strings in flow maps (inline `{}` or `[]` syntax)
4. **VOCs field not found** - Fixes error when VOCs data is stored separately from generator parameters
5. **PydanticSerializationUnexpectedValue warnings** - Every iteration, Badger serializes the whole Xopt object (`Xopt.json()`), and two things in `xopt/generators/bayesian/turbo.py` trip pydantic: `TurboController.__init__` assigns `self._initial_state` without declaring it, so pydantic stores it on the instance and the serializer sees an unexpected field (safety controller); and `OptimizeTurboController.update_state` stores `best_value` as the `numpy.float64` pandas returns, which the Xopt-level serializer rejects (optimize controller). Fixed at the root by `xopt-3.2.2-turbo-serialization.patch` (three lines) rather than by filtering the warning. Verified offline on pristine xopt 3.2.2: 1 warning per `json()` before, 0 after, for both selectable controllers (optimize and safety).
6. **`-mini` variable table lists and queries the wrong machine** - Two caches hold the plugin's `configs.yaml` defaults and are never refreshed when a template points the environment elsewhere: `BadgerVariableTable.configs` (captured in `select_env()`, and the environment is rebuilt from it on every refresh) and `routine_page.vars_env`, the table's *rows*, which come from `configs["variables"]` — computed once by `factory.load_plugin` from an environment built with those same defaults. Loading a template on another lattice therefore reloads the *default* lattice repeatedly, errors on variables only the template's lattice has (e.g. `Cannot read 'iq2'`), and lists thousands of rows belonging to the wrong machine. Fixed by `badger-mini-var-table-env-configs.patch`, which re-runs `add_var()` and rebuilds `vars_env` from an environment carrying the template's params. Measured on `Xfer400MeV_example.yaml`: 2284 default-lattice rows → 124 rows of its own.

7. **Alphabetical device lists / checked and unchecked rows mixed together** - Both routine pages sort the variable dict (`dict(sorted(...))`) when loading a template or routine, so the plugin's beam-order listing is lost (environment selection alone preserved it). The four lists also showed every device with a free-text filter. Fixed by `badger-1.6.0-device-list-gui.patch`: drops the sort (dicts keep insertion order: env variables, then `additional_variables`, hard-limit overrides change values only), adds `gui/components/picker.py` (an editable `QComboBox` + contains-match `QCompleter` rebuilt from the table on focus/open, no signal wiring) in place of each filter box, and wraps the variable table in the existing `CollapsibleBox`. Also wires the `-mini` observables "Show Checked Only" checkbox, which upstream never connected.

## Applying the Patches

> **Never edit files under `site-packages` in place.** conda hard-links them to its
> package cache (`~/miniconda3/pkgs/`) and to every other env that installed the same
> build, so an in-place write (`open(path, 'w')`, an edit script, GNU `sed -i`) lands in
> all of them at once and makes conda report `SafetyError` on the next env build.
> Applying a `.patch` with `patch` is safe: it writes a new file. If `SafetyError`
> appears, delete the extracted `pkgs/<pkg>/` directory (keep the `.conda` archive)
> and rebuild the env.
>
> **From-scratch check** (do this before committing a new patch): `rsync` the working
> tree to `/tmp/X` excluding `.git`, then `cd /tmp/X && ./setup.sh --yes --env-name X`.
> Off-site, drop the `acsys` lines from the copy's `environment.yml` first. Expect
> `applied` for every patch and a `badger/` + `xopt/` tree identical to the working env.

### Finding Badger Installation

First, locate your Badger installation in your conda environment:

```bash
# Replace FermiBadger_env with your environment name
conda run -n FermiBadger_env python -c "import badger; import os; print(os.path.dirname(badger.__file__))"
```

**`./setup.sh` applies all of these for you** — the manual steps below are the
fallback.

### Using `patch` Command

This patch carries `a/pydantic_editor.py` paths, so apply it from the
`gui/components` directory with `-p1`:

```bash
BADGER_PATH=$(conda run -n FermiBadger_env python -c "import badger; import os; print(os.path.dirname(badger.__file__))")
cd "$BADGER_PATH/gui/components"
patch -p1 < /path/to/FermiBadgerPlugins/patches/pydantic_editor-badger-1.6.0-dict-subtypes.patch
```

### Using `git apply`

```bash
BADGER_PATH=$(conda run -n FermiBadger_env python -c "import badger; import os; print(os.path.dirname(badger.__file__))")
cd "$BADGER_PATH/gui/components"
git apply /path/to/FermiBadgerPlugins/patches/pydantic_editor-badger-1.6.0-dict-subtypes.patch
```

### The `-mini` Patches

All three of these patches carry `a/badger/...` paths, so apply them from the
`site-packages` directory with `-p1`:

```bash
CONDA_PREFIX=$(conda run -n FermiBadger_env python -c "import sys; print(sys.prefix)")
cd "$CONDA_PREFIX/lib/python3.12/site-packages"
patch -p1 < /path/to/FermiBadgerPlugins/patches/badger-mini-config.patch
patch -p1 < /path/to/FermiBadgerPlugins/patches/badger-mini-var-table-env-configs.patch
patch -p1 < /path/to/FermiBadgerPlugins/patches/badger-1.6.0-device-list-gui.patch
```

## Applying the Xopt Patch

`xopt-3.2.2-turbo-serialization.patch` carries `a/xopt/...` paths and applies from
`site-packages` with `-p1`, like the `-mini` patches; `setup.sh` applies it last.
It touches only `xopt/generators/bayesian/turbo.py`.

```bash
CONDA_PREFIX=$(conda run -n FermiBadger_env python -c "import sys; print(sys.prefix)")
cd "$CONDA_PREFIX/lib/python3.12/site-packages"
patch -p1 < /path/to/FermiBadgerPlugins/patches/xopt-3.2.2-turbo-serialization.patch
```

The same three lines are worth offering upstream to xopt-org/Xopt.


## Patch History

### Superseded Badger Patches

The following patches have been superseded by `pydantic_editor-badger-1.6.0-dict-subtypes.patch`:

- `pydantic_editor-badger-1.6.0-fixes.patch`
- `pydantic_editor-turbo_controller-null-1.6.0.patch`
- `pydantic_editor-combo-box-null-fix.patch`
- `pydantic_editor-null-turbo_controller-git-apply.patch`
- `pydantic_editor-null-turbo_controller.patch`
- `pydantic_editor-turbo_controller-string-PR.patch`
- `pydantic_editor-turbo_controller-string-fix.patch`
- `badger-1.6.0-none-parsing-fix.patch` (deleted 2026-10-07; its `pydantic_editor.py` change is in the dict-subtypes patch and its `gui/utils.py` change is not needed — a pristine 1.6.0 plus the four live patches is byte-identical to the working install)

### Deleted plugin patch

- `simple-virtual-accelerator-plugin-fix.patch` (deleted 2026-10-07): targeted `plugins/environments/SimpleVirtualAccelerator/`, which was renamed `99_Sim_SimpleVirtualAccelerator` with the fix already committed in the plugin itself.

### Retired Xopt patch

- `xopt-pydantic-serialization-fix.patch` and `apply_xopt_fix.py` (deleted 2026-10-08): generated against hand-edited xopt 3.2.1 files that the 2026-09-16 env rebuild replaced with pristine conda-forge xopt 3.2.2, so they could never apply to a fresh install. Replaced by `xopt-3.2.2-turbo-serialization.patch`, which fixes the cause instead of filtering the warning.

## Environment

Patches tested with:
- Badger 1.6.0
- Python 3.12
- Pydantic 2.x
