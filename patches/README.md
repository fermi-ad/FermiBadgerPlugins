# Badger Patches

## Summary

### Patches for Badger 1.6.0 and Xopt

| Patch | Description | Required Components |
|-------|-------------|---------------------|
| `pydantic_editor-badger-1.6.0-dict-subtypes.patch` | Fixes "Dict type must have subtypes" error, handles `turbo_controller: null`, and fixes YAML parsing for 'None' strings | Badger 1.6.0 |
| `xopt-pydantic-serialization-fix.patch` | Suppresses `PydanticSerializationUnexpectedValue` warnings during TurboController serialization | Xopt 3.2.0+ |
| `apply_xopt_fix.py` | Python script to apply the Xopt fix automatically | Xopt 3.2.0+ |
| `badger-mini-config.patch` | Initializes the settings singleton before template loading in `-mini` | Badger 1.6.0 |
| `badger-mini-var-table-env-configs.patch` | Rebuilds the `-mini` variable table's env configs *and* its rows from the template, so the table lists and queries the template's machine rather than the plugin defaults | Badger 1.6.0 |

## Issues Fixed

1. **"Dict type must have subtypes"** - Occurs when loading templates with dict/list environment params (e.g., `setpoints: {qx: 9.049, qy: 9.035}`)
2. **`turbo_controller: null` handling** - Prevents warnings and ensures correct null serialization
3. **YAML 'None' strings** - Fixes parsing of 'None' strings in flow maps (inline `{}` or `[]` syntax)
4. **VOCs field not found** - Fixes error when VOCs data is stored separately from generator parameters
5. **PydanticSerializationUnexpectedValue warnings** - Suppresses spurious warnings during TurboController model_dump/model_dump_json operations (every iteration of optimization loop)
6. **`-mini` variable table lists and queries the wrong machine** - Two caches hold the plugin's `configs.yaml` defaults and are never refreshed when a template points the environment elsewhere: `BadgerVariableTable.configs` (captured in `select_env()`, and the environment is rebuilt from it on every refresh) and `routine_page.vars_env`, the table's *rows*, which come from `configs["variables"]` — computed once by `factory.load_plugin` from an environment built with those same defaults. Loading a template on another lattice therefore reloads the *default* lattice repeatedly, errors on variables only the template's lattice has (e.g. `Cannot read 'iq2'`), and lists thousands of rows belonging to the wrong machine. Fixed by `badger-mini-var-table-env-configs.patch`, which re-runs `add_var()` and rebuilds `vars_env` from an environment carrying the template's params. Measured on `Xfer400MeV_example.yaml`: 2284 default-lattice rows → 124 rows of its own.

## Applying the Patches

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

Both `-mini` patches carry `a/badger/...` paths, so apply them from the
`site-packages` directory with `-p1`:

```bash
CONDA_PREFIX=$(conda run -n FermiBadger_env python -c "import sys; print(sys.prefix)")
cd "$CONDA_PREFIX/lib/python3.12/site-packages"
patch -p1 < /path/to/FermiBadgerPlugins/patches/badger-mini-config.patch
patch -p1 < /path/to/FermiBadgerPlugins/patches/badger-mini-var-table-env-configs.patch
```

## Applying the Xopt Patch

> **This patch does not apply to a pristine Xopt 3.2.1, and `setup.sh` skips it.**
> It was generated against an installation that already carried hand-written
> edits to `xopt/pydantic.py` and `xopt/generators/bayesian/turbo.py` (a
> `model_dump` override, an `_initial_state_value` private attribute, a
> `model_dump_json` override) which no file in this directory contains — the
> patch *amends* that code rather than adding it, so its context lines are
> absent from a fresh install. `apply_xopt_fix.py` has the same problem: its
> search strings match nothing in a pristine tree. The patch header is also
> malformed (`patch` rejects it at line 22).
>
> To restore this fix for new clones, the hand-edits need to be captured as a
> real diff against pristine 3.2.1 first.

The Xopt patch fixes the TurboController serialization warnings. Apply it to your conda environment's xopt package:

```bash
CONDA_PREFIX=$(conda run -n FermiBadger_env python -c "import sys; print(sys.prefix)")
cd "$CONDA_PREFIX/lib/python3.12/site-packages"

# Apply the patch to xopt/pydantic.py
patch -p0 < /path/to/FermiBadgerPlugins/patches/xopt-pydantic-serialization-fix.patch
```

**Note:** 
- Replace `/path/to/FermiBadgerPlugins` with the actual path where you cloned the repository.
- The Xopt patch affects `xopt/pydantic.py`, `xopt/__init__.py`, and `xopt/generators/bayesian/turbo.py`
- The Xopt patch also removes an unnecessary warning filter from `badger/core_subprocess.py`


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

### New Patches

- `xopt-pydantic-serialization-fix.patch` - Suppresses `PydanticSerializationUnexpectedValue` warnings during TurboController serialization (applies to xopt package)

## Environment

Patches tested with:
- Badger 1.6.0
- Python 3.12
- Pydantic 2.x
