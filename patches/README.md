# Badger Patches

This directory contains patches for the Badger GUI to fix issues specific to our VirtualAccelerator_MADXSuite environment.

## Patches

### 1. `pydantic_editor-turbo_controller-string-fix.patch`
**Purpose:** Fix TypeError when `turbo_controller` or `numerical_optimizer` is specified as a string in templates.

**Problem:** In Badger 1.5.4, the `initialize_special_field` method in `pydantic_editor.py` assumes special fields are always dicts. When a template specifies `turbo_controller: OptimizeTurboController` as a string, the code fails with `TypeError: 'str' object does not support item assignment`.

**Fix:** Modify `initialize_special_field` to detect string values and convert them to dicts with a `name` key before proceeding.

**Usage:**
```bash
cd /path/to/badger/source
patch -p1 < pydantic_editor-turbo_controller-string-fix.patch
```

### 2. `pydantic_editor-turbo_controller-string-PR.patch`
**Purpose:** Same fix as above, but formatted as a GitHub PR-ready diff.

**Usage:** For submitting to xopt-org/Badger repository.

### 3. `pydantic_editor-null-turbo_controller.patch` (existing)
**Purpose:** Fix warning when `turbo_controller` is explicitly set to `null` in templates.

### 4. `pydantic_editor-null-turbo_controller-git-apply.patch` (existing)
**Purpose:** Same as above, but in git-apply compatible format.

## Applying Patches

For Badger 1.5.4 installed via conda:
1. Find the installed badger source: `find ~ -name "pydantic_editor.py" -path "*/badger/gui/components/*" 2>/dev/null`
2. Apply the patch relative to the `src/badger` directory
