# Badger Patches

This directory contains patches for the Badger GUI and VirtualAccelerator plugins.

## Patches for Badger 1.6.0

### 1. `pydantic_editor-badger-1.6.0-fixes.patch`

**Purpose:** Fix issues in the VirtualAccelerator_MADXSuite environment plugin (NOT Badger itself):

1. **Environment field defaults** - Uses Pydantic `Field(default=...)` instead of bare assignment for better validation.

**Applies to (run from FermiBadgerPlugins repo directory):**
- `plugins/environments/VirtualAccelerator_MADXSuite/__init__.py`
- `plugins/environments/VirtualAccelerator_MADXSuite/configs.yaml`

**Usage:**
```bash
# From the FermiBadgerPlugins repo directory
patch -p1 < patches/pydantic_editor-badger-1.6.0-fixes.patch
```

---

### 2. `pydantic_editor-turbo_controller-null-1.6.0.patch`

**Purpose:** Fix turbo_controller null handling in Badger 1.6.0:

1. **turbo_controller null handling**: Prevents warnings when `turbo_controller: null` is set in templates.

2. **Startup validation error**: Fixes validation errors on Badger startup when generator combo box is changed.

**Applies to (run from Badger installation directory):**
- `badger/gui/components/pydantic_editor.py`

**Usage:**
```bash
# Find your Badger installation directory
BADGER_DIR=$(python -c "import badger; import os; print(os.path.dirname(badger.__file__))")

# Apply with -p2 to strip 'a/src/' from patch path (file is at badger/gui/...)
cd "$BADGER_DIR"
patch -p2 < /path/to/FermiBadgerPlugins/patches/pydantic_editor-turbo_controller-null-1.6.0.patch
```

**Explanation of -p flag:**
- Patch path: `a/src/badger/gui/components/pydantic_editor.py`
- `-p1` would give: `src/badger/gui/components/pydantic_editor.py` (wrong - file doesn't exist here)
- `-p2` gives: `badger/gui/components/pydantic_editor.py` (correct!)

---

### 3. `pydantic_editor-combo-box-null-fix.patch`

**Purpose:** Fix QComboBox "null" handling in Badger 1.6.0:

**Applies to:**
- `badger/gui/components/pydantic_editor.py`

**Usage:**
```bash
BADGER_DIR=$(python -c "import badger; import os; print(os.path.dirname(badger.__file__))")
cd "$BADGER_DIR"
patch -p1 < /path/to/FermiBadgerPlugins/patches/pydantic_editor-combo-box-null-fix.patch
```

---

## Template VOCs Structure Fix

The `DR_BetatronTunes_sim.yaml` template has been updated to have proper vocs structure:

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
