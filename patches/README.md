# Badger Patches

This directory contains patches for the Badger GUI.

## Patches for Badger 1.6.0

### 1. `pydantic_editor-turbo_controller-null-1.6.0.patch`

**Purpose:** Fix turbo_controller null handling in Badger 1.6.0:

1. **turbo_controller null handling**: Prevents warnings when `turbo_controller: null` is set in templates.

2. **Startup validation error**: Fixes validation errors on Badger startup when generator combo box is changed.

**Applies to:**
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

### 2. `pydantic_editor-combo-box-null-fix.patch`

**Purpose:** Fix QComboBox "null" handling in Badger 1.6.0.

**Applies to:**
- `badger/gui/components/pydantic_editor.py`

**Usage:**
```bash
BADGER_DIR=$(python -c "import badger; import os; print(os.path.dirname(badger.__file__))")
cd "$BADGER_DIR"
patch -p1 < /path/to/FermiBadgerPlugins/patches/pydantic_editor-combo-box-null-fix.patch
```

---

## Patches for Badger 1.5.4 (deprecated)

The following patches were created for Badger 1.5.4 and are no longer needed for 1.6.0:

- `pydantic_editor-turbo_controller-string-fix.patch` - Handles string values for turbo_controller
- `pydantic_editor-null-turbo_controller.patch` - Handles null values for turbo_controller

---

## Removed Patches

The following patches are no longer needed because the fixes have been applied directly to the FermiBadgerPlugins repo:

- `pydantic_editor-badger-1.6.0-fixes.patch` - VirtualAccelerator_MADXSuite environment field defaults (now in `plugins/environments/VirtualAccelerator_MADXSuite/__init__.py`)
