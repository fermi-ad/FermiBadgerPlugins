# Badger Patches

This directory contains patches for the Badger GUI to fix issues specific to our VirtualAccelerator_MADXSuite environment.

## Patches for Badger 1.6.0

### 1. `pydantic_editor-badger-1.6.0-fixes.patch`

**Purpose:** Fix multiple issues in Badger 1.6.0:

1. **turbo_controller null handling**: Prevents warnings when `turbo_controller: null` is set in templates.

2. **vocs field in parameters**: Avoids `KeyError: 'vocs field is required in parameters'` when vocs is stored separately in `self.vocs`.

3. **QComboBox "null" handling**: Ensures YAML null is output instead of string "null".

4. **Startup validation error**: Fixes validation errors on Badger startup when generator combo box is changed.

**Problem:** In Badger 1.6.0:
- `turbo_controller: null` caused repeated warnings
- `vocs` was not found in parameters, causing errors
- QComboBox returned string "null" instead of actual null value
- TurboController validation errors on startup due to incorrect YAML serialization

**Fix:** 
- In `_qt_widget_to_yaml_value()`: Return `None` when combo box shows "null"
- In `initialize_special_field()`: Check if field exists in defaults before warning; if it exists with value null, set combo box to "null" and return early
- In `validate()`: If `vocs` is not in parameters_dict, use `self.vocs.model_dump()` as the source

**Usage:**
```bash
cd /path/to/badger/source
patch -p1 < pydantic_editor-badger-1.6.0-fixes.patch
```

For conda-installed Badger (FermiBadger_env):
```bash
# The pydantic_editor.py file is located at:
# /Users/stjohn/miniconda3/envs/FermiBadger_env/lib/python3.12/site-packages/badger/gui/components/pydantic_editor.py

# Apply the fixes directly:
sed -i.bak 's/return "null"/return None/' pydantic_editor.py
# Then manually update initialize_special_field() to set combo box to "null" before returning
```

### 2. Template VOCs Structure Fix

**Issue:** The `DR_BetatronTunes_sim.yaml` template had vocs fields incorrectly nested under `generator:` without a `vocs:` key. Badger 1.6.0 validation requires vocs to be properly structured.

**Fix:** Updated template to have:
```yaml
generator:
  ...
  turbo_controller: null
  vocs:
    constants: '{}'
    constraints: '{}'
    objectives: '{...}'
    observables: '{...}'
    variables: '{...}'
```

## Patches for Badger 1.5.4 (deprecated)

The following patches were created for Badger 1.5.4 and are no longer needed for 1.6.0:

- `pydantic_editor-turbo_controller-string-fix.patch` - Handles string values for turbo_controller
- `pydantic_editor-null-turbo_controller.patch` - Handles null values for turbo_controller
