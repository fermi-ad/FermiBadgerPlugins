# Badger Patches

## Summary

### Patch for Badger 1.6.0

The following patch is required to fix known issues in Badger 1.6.0:

| Patch | Description |
|-------|-------------|
| `pydantic_editor-badger-1.6.0-dict-subtypes.patch` | Fixes "Dict type must have subtypes" error, handles `turbo_controller: null`, and fixes YAML parsing for 'None' strings |

### Issues Fixed

1. **"Dict type must have subtypes"** - Occurs when loading templates with dict/list environment params (e.g., `setpoints: {qx: 9.049, qy: 9.035}`)
2. **`turbo_controller: null` handling** - Prevents warnings and ensures correct null serialization
3. **YAML 'None' strings** - Fixes parsing of 'None' strings in flow maps (inline `{}` or `[]` syntax)
4. **VOCs field not found** - Fixes error when VOCs data is stored separately from generator parameters

## Applying the Patch

### Finding Badger Installation

First, locate your Badger installation in your conda environment:

```bash
# Replace FermiBadger_env with your environment name
conda run -n FermiBadger_env python -c "import badger; import os; print(os.path.dirname(badger.__file__))"
```

### Using `patch` Command

```bash
BADGER_PATH=$(conda run -n FermiBadger_env python -c "import badger; import os; print(os.path.dirname(badger.__file__))")
cd "$BADGER_PATH/gui/components"
patch -p0 < /path/to/FermiBadgerPlugins/patches/pydantic_editor-badger-1.6.0-dict-subtypes.patch
```

### Using `git apply`

```bash
BADGER_PATH=$(conda run -n FermiBadger_env python -c "import badger; import os; print(os.path.dirname(badger.__file__))")
cd "$BADGER_PATH/gui/components"
git apply /path/to/FermiBadgerPlugins/patches/pydantic_editor-badger-1.6.0-dict-subtypes.patch
```

**Note:** 
- Replace `/path/to/FermiBadgerPlugins` with the actual path where you cloned the repository.
- Do NOT use the `--directory` option with `git apply` - the patch is designed to be applied from within the `badger/gui/components/` directory.

## Patch History

The following patches have been superseded by `pydantic_editor-badger-1.6.0-dict-subtypes.patch`:

- `pydantic_editor-badger-1.6.0-fixes.patch`
- `pydantic_editor-turbo_controller-null-1.6.0.patch`
- `pydantic_editor-combo-box-null-fix.patch`
- `pydantic_editor-null-turbo_controller-git-apply.patch`
- `pydantic_editor-null-turbo_controller.patch`
- `pydantic_editor-turbo_controller-string-PR.patch`
- `pydantic_editor-turbo_controller-string-fix.patch`

## Environment

Patches tested with:
- Badger 1.6.0
- Python 3.12
- Pydantic 2.x
