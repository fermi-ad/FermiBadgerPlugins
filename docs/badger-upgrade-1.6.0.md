# Badger Upgrade to 1.6.0 - Testing Results

## Summary

Successfully upgraded Badger from 1.5.4 to 1.6.0. Two patches were applied to fix issues introduced in the new version.

---

## Current State

- **Original Version**: Badger 1.5.4
- **Upgraded Version**: Badger 1.6.0
- **Environment**: FermiBadger_env (conda)
- **Xopt**: Upgraded from 3.1.1 to 3.2.1 (required for compatibility)

---

## Known Changes in Badger 1.6.0

### pydantic_editor.py Changes

1. **String import moved** - `from inspect import isclass` now imports from `inspect` directly
2. **New import added** - `from xopt.errors import VOCSError`
3. **Algorithm support added** - BaxGenerator now checks for "algorithm" field
4. **`initialize_special_field` signature change**:
   - Added return type annotation `-> None`
   - Changed `special_item_dict` default from `defaults.get(field, {})` to `defaults.get(field)`
   - Removed string-to-dict conversion logic (patches we created for 1.5.4 are not needed)
   - Changed `name` default from `"null" if not special_item_dict else ""` to `""`

### VOCs Structure Change

Badger 1.6.0 requires the `vocs` section to be properly nested within the generator parameters. Templates with vocs at the root level only (without a `vocs:` key under `generator:`) will fail validation.

---

## Fixes Applied

### Fix 1: turbo_controller null handling

**File**: `badger/gui/components/pydantic_editor.py`

**Issue**: When `turbo_controller: null` was set in templates, the code logged warnings:
```
Generator has turbo_controller set but no compatible turbo_controller exists.
Could not find compatible class for  in field turbo_controller
```

**Root Cause**: The code changed to `defaults.get(field)` instead of `defaults.get(field, {})`. When the key exists with value `null`, it returns `None`, but the code didn't distinguish between "key missing" and "key explicitly null".

**Fix**: Check if the field exists in defaults before warning. If it exists (even with null value), return early without warning.

```python
special_item_dict: dict[str, Any] | None = defaults.get(field)

if special_item_dict is None:
    # Check if key exists in defaults - if not, warn; if yes, it's explicitly null
    if field not in defaults:
        logger.warning(...)
        special_item_dict = {}
    else:
        # Field is explicitly set to null - nothing to initialize, just return
        return
```

**Patch File**: `patches/pydantic_editor-badger-1.6.0-fixes.patch`

### Fix 2: VOCs field not found in parameters

**Issue**: When loading templates, the error occurred:
```
ERROR - 'vocs field is required in parameters'
```

**Root Cause**: The GUI stores VOCs data in `self.vocs` (a separate Python object) and doesn't serialize it to the YAML tree. The new validation in 1.6.0 raised an error when `vocs` wasn't in `parameters_dict`.

**Fix**: If `vocs` is not in `parameters_dict`, use `self.vocs.model_dump()` as the source instead of raising an error.

```python
if "vocs" in parameters_dict:
    # ... convert dict values ...
else:
    # VOCs is not in the parameters dict (from the widget tree), but it's
    # stored in self.vocs. Use it as the source for vocs data.
    parameters_dict["vocs"] = self.vocs.model_dump()
```

### Fix 3: Template VOCs structure

**Issue**: The `DR_BetatronTunes_sim.yaml` template had vocs fields incorrectly nested under `generator:` without a `vocs:` key.

**Fix**: Updated template to have proper structure:
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

---

## Testing Steps Completed

### Step 1: Update environment.yml

Changed line 9:
```yaml
badger-opt=1.5.4
```
to:
```yaml
badger-opt=1.6.0
```

Also updated Xopt version:
```yaml
xopt>=3.2.0
```

### Step 2: Upgrade Xopt

```bash
pip install --upgrade xopt
```

Result: Xopt upgraded from 3.1.1 to 3.2.1

### Step 3: Verify Installation

```bash
conda run -n FermiBadger_env python -c "import badger; print(badger.__version__)"
```
Result: `1.6.0` ✓

### Step 4: GUI Launch Test

```bash
conda run -n FermiBadger_env badger -g -cf config.yaml
```
Result: Badger GUI launches without errors ✓

### Step 5: Load Test Template

1. Loaded `tuning_templates/DR_BetatronTunes_sim.yaml`
2. Template loads without errors or warnings about `turbo_controller`
3. VirtualAccelerator_MADXSuite environment loads correctly

Result: Template loads without errors ✓

### Step 6: Template VOCs Structure Fix

Updated template to have `vocs:` properly nested under `generator:`

---

## Files Modified

### Environment
- `/Users/stjohn/Development/BayesOptimization_Xopt/FermiBadgerPlugins/environment.yml` - Updated badger-opt to 1.6.0, xopt to >=3.2.0

### Badger Source (Applied manually)
- `/Users/stjohn/miniconda3/envs/FermiBadger_env/lib/python3.12/site-packages/badger/gui/components/pydantic_editor.py` - Applied two fixes for turbo_controller and vocs

### Patches
- `/Users/stjohn/Development/BayesOptimization_Xopt/FermiBadgerPlugins/patches/pydantic_editor-badger-1.6.0-fixes.patch` - New patch file
- `/Users/stjohn/Development/BayesOptimization_Xopt/FermiBadgerPlugins/patches/README.md` - Updated documentation

### Templates
- `/Users/stjohn/Development/BayesOptimization_Xopt/FermiBadgerPlugins/tuning_templates/DR_BetatronTunes_sim.yaml` - Fixed vocs structure

---

## Rollback Plan

If issues are found, rollback to 1.5.4:

```bash
# Revert environment.yml
conda env update -n FermiBadger_env -f environment.yml --prune

# Or if pip installed:
pip install badger-opt==1.5.4 xopt==3.1.1
```

---

## Notes

- The patches for 1.5.4 (`pydantic_editor-turbo_controller-string-fix.patch`, `pydantic_editor-null-turbo_controller.patch`) are not needed for 1.6.0
- The new patches address issues introduced in Badger 1.6.0
- Xopt 3.2.1 is required for `get_local_region` function used by Badger 1.6.0
