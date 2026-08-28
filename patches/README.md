# Badger Patches

This directory contains patches for the Badger GUI to fix issues specific to our VirtualAccelerator_MADXSuite environment.

## Patches for Badger 1.6.0

### 1. `pydantic_editor-badger-1.6.0-fixes.patch`

**Purpose:** Fix two issues in Badger 1.6.0:

1. **turbo_controller null handling**: Prevents warnings when `turbo_controller: null` is set in templates. In Badger 1.6.0, the code changed to use `defaults.get(field, {})` which returns `None` when the key exists with value `null`, but the code then logged a warning. The fix checks if the key exists before warning.

2. **vocs field in parameters**: The GUI was raising `KeyError: 'vocs field is required in parameters'` because the vocs data is stored separately in `self.vocs` and not serialized to the YAML tree. The fix adds `self.vocs.model_dump()` to the parameters dict when vocs is missing.

**Problem:** In Badger 1.6.0:
- `turbo_controller: null` caused repeated warnings
- `vocs` was not found in parameters, causing errors

**Fix:** 
- In `initialize_special_field()`: Check if field exists in defaults before warning; if it exists with value null, return early
- In `validate()`: If `vocs` is not in parameters_dict, use `self.vocs.model_dump()` as the source

**Usage:**
```bash
cd /path/to/badger/source
patch -p1 < pydantic_editor-badger-1.6.0-fixes.patch
```

For conda-installed Badger:
```bash
BADGER_DIR=$(python -c "import badger; import os; print(os.path.dirname(badger.__file__))")
# The patch applies to the source structure, so we need to manually apply
# the changes to pydantic_editor.py
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
