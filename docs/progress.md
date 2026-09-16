# Progress Log

## 2026-08-24: turbo_controller null warning investigation

### Problem
Running `badger -g -cf config.yaml` with a tuning template that has `turbo_controller: null` produces repeated warnings:
```
Could not find compatible class for  in field turbo_controller
```

The double space in the warning ("for  in") indicates an empty string is being passed.

### Root Cause
In `badger/gui/components/pydantic_editor.py`, the `initialize_special_field` method handles `turbo_controller` as a special field that can instantiate sub-classes. When the value is `null`:

1. Line 760: `defaults.get('turbo_controller')` returns `None`
2. Line 762-769: Treats it as missing key, sets `special_item_dict = {}`
3. Line 774: `name = "null"` (from empty dict)
4. Line 780: Calls `update_params_from_generator_class` with `name="null"`
5. Line 871-872: Can't find class named "null", logs warning

### Fix Plan
Modify `initialize_special_field` to detect when `turbo_controller` is explicitly set to `null` and skip the subclass initialization. The combo box should be set to "null" and the method should return early.

### Fix Applied
Modified `/Users/stjohn/miniconda3/envs/FermiBadger_env/lib/python3.12/site-packages/badger/gui/components/pydantic_editor.py` in the `initialize_special_field` method (lines 762-774):

**Before:**
```python
if special_item_dict is None:
    # Check if key exists in dict - if not, warn; if yes, it's explicitly null
    if field not in defaults:
        logger.warning(...)
    special_item_dict = {}  # Always sets to empty dict, causing issue
```

**After:**
```python
if special_item_dict is None:
    # Check if key exists in dict - if not, warn; if yes, it's explicitly null
    if field not in defaults:
        logger.warning(...)
        special_item_dict = {}
    else:
        # Field is explicitly set to null - nothing to initialize, just return
        return
```

This handles the case when `turbo_controller: null` is in YAML - the method now returns early, avoiding the `update_params_from_generator_class` call that was causing the warning.

### Status
- [x] Understood root cause
- [x] Implement fix in pydantic_editor.py
- [x] Test the fix (GUI launched, user confirmed warning is gone)
- [x] Created patch file for repository
- [x] Updated README.md with patch instructions

---

## 2026-08-25: Setpoints not updating investigation

### Problem
User changed setpoints in the GUI from `{qx: 9.649, qy: 9.735}` to `{qx: 9.049, qy: 9.035}` and ran the optimizer. The QF/QD variables hit their hard limits but show zero progress.

### Investigation
Added debug logging to the environment and interface to trace:
1. `set_variables` calls
2. `get_variables` calls
3. `get_observables` calls with setpoints

The logs will show whether:
- The variables are being set correctly
- The setpoints used for the objective calculation
- The actual tune values being read from the lattice

### Next Steps
Review the logs after the user runs a test to determine if:
1. The variables are being propagated to the lattice
2. The setpoints are being updated when changed in the GUI
3. The twiss calculation is using the updated values

### Files Modified
- `plugins/environments/VirtualAccelerator_MADXSuite/__init__.py` - Added logging
- `plugins/interfaces/VirtualAccelerator_MADXSuiteInterface/__init__.py` - Added logging

---

## 2026-08-25: Evaluator not being called in subprocess

### Problem
After fixing the setpoints issue, the optimizer was still not making progress. The variable changes (i_dqd, i_dqf) were not affecting the objective (qx-SETPOINT).

### Investigation
Logs showed:
- `Evaluating point` messages appeared (DEBUG level)
- But `set_variables called` and `get_observables called` messages did NOT appear
- The `evaluate_point` function in `routine.py` was being used, but it was created with a different closure

### Root Cause
The evaluator is removed during routine serialization (line 172 of `badger/routine.py`):
```python
fields_to_be_removed = [
    "dump_file",
    "evaluator",  # <-- This is the problem
    ...
]
```

When the routine is loaded in the subprocess via `load_run()`, the environment is recreated but the evaluator was never recreated. The evaluate_point function from `Routine.validate_model` was using the old environment.

### Fix Applied
Modified `/Users/stjohn/miniconda3/envs/FermiBadger_env/lib/python3.12/site-packages/badger/core_subprocess.py` (lines 141-167):

```python
# Recreate the evaluator since it's removed during serialization
logger.info("Recreating evaluator")
env = routine.environment

def evaluate_point(point: dict):
    logger.warning(f"evaluate_point called: {point}")
    logger.warning(f"env: {env}")
    logger.warning(f"env.set_variables: {env.set_variables}")
    logger.warning(f"env.get_observables: {env.get_observables}")
    logger.warning(f"routine.generator.vocs.output_names: {routine.generator.vocs.output_names}")
    try:
        point = DataFrame(point, index=[0]).to_dict("records")[0]
        logger.warning(f"Calling set_variables with: {point}")
        env.set_variables(point)
        logger.warning("set_variables completed")
        obs = env.get_observables(routine.generator.vocs.output_names)
        logger.warning(f"get_observables completed: {obs}")
        ts = curr_ts()
        obs["timestamp"] = ts.timestamp()
        obs["live"] = 1
        logger.warning(f"Evaluation result: {obs}")
        return obs
    except Exception as e:
        logger.error(f"Error in evaluate_point: {type(e).__name__}: {e}", exc_info=True)
        raise

routine.evaluator = Evaluator(function=evaluate_point)
```

### Verification
After the fix, logs showed:
- `evaluate_point called` messages appeared
- `set_variables completed` messages appeared
- `get_observables completed` messages appeared
- The environment used the correct setpoints from the GUI: `{'qx': 9.049, 'qy': 9.135}`
- The qx-SETPOINT and qy-SETPOINT values were correctly computed from the setpoints

### Status
- [x] Identified evaluator removal during serialization
- [x] Implemented evaluator recreation in core_subprocess.py
- [x] Verified environment methods are now being called
- [x] Verified setpoints are correctly propagated from GUI

### Files Modified
- `/Users/stjohn/miniconda3/envs/FermiBadger_env/lib/python3.12/site-packages/badger/core_subprocess.py` - Added evaluator recreation code

---

## 2026-08-25: Variable range windows investigation

### Problem
User observed: "We still see no change to the value of qx (nor qx-SETPOINT) even when the optimization is changing i_dqd and i_dqf to limits of their 'hardcoded' values. Maybe those hardcoded windows are not big enough to have a measurable effect?"

### Investigation
1. Examined the environment's `_bounds_around` method in `plugins/environments/VirtualAccelerator_MADXSuite/__init__.py` (lines 218-225):
   - For non-zero values: `[value * (1 - rel_range), value * (1 + rel_range)]`
   - For zero values: `[-zero_half_range, zero_half_range]`

2. Default values in the environment:
   - `rel_range: float = 0.1` (10%)
   - `zero_half_range: float = 0.1`

3. Current lattice settings file shows:
   - `i_dqd: 240.6`
   - `i_dqf: 241.2`

4. With `rel_range: 0.1`, the bounds were:
   - `i_dqd`: [240.6 * 0.9, 240.6 * 1.1] = [216.54, 264.66]
   - `i_dqf`: [241.2 * 0.9, 241.2 * 1.1] = [217.08, 265.32]

5. The tuning template `DR_BetatronTunes_Sim_MADXSuite.yaml` had:
   - `rel_range: 0.1`
   - `zero_half_range: -1.9` (this negative value is invalid, was probably a bug)

### Root Cause
The 10% range was likely too narrow to produce measurable changes in the betatron tunes (qx, qy). Quadrupole currents in the Mu2e DR have a small effect on tunes, requiring larger current changes to produce measurable tune shifts.

### Fix Applied
Updated `/Users/stjohn/Development/BayesOptimization_Xopt/FermiBadgerPlugins/tuning_templates/DR_BetatronTunes_Sim_MADXSuite.yaml`:

**Before:**
```yaml
rel_range: 0.1
zero_half_range: -1.9
```

**After:**
```yaml
rel_range: 0.3
zero_half_range: 10.0
```

**New bounds with 30% range:**
- `i_dqd`: [240.6 * 0.7, 240.6 * 1.3] = [168.42, 312.78]
- `i_dqf`: [241.2 * 0.7, 241.2 * 1.3] = [168.84, 313.56]

This gives a range of ~144A for each variable, which should allow the optimizer to find measurable changes in the tunes.

### Status
- [x] Identified how range windows are calculated in `_bounds_around` method
- [x] Found that `rel_range: 0.1` (10%) may be too narrow
- [x] Updated tuning template to use `rel_range: 0.3` (30%)
- [x] Fixed `zero_half_range` from invalid negative value to valid positive value

### Notes
The `rel_range` parameter is specific to the VirtualAccelerator_MADXSuite environment and controls the automatic bounds deduction for variables. Users can:
1. Modify the template YAML file to change `rel_range`
2. Or manually set variable bounds in the GUI's variable table

### Follow-up: Root cause identified - variables don't control optics

After testing with wider ranges (`rel_range: 0.3`), discovered that `i_dqd` and `i_dqf` **do not affect the tunes at all**. Investigation revealed:

1. `i_dqd` and `i_dqf` are power supply current regulators (read-only)
2. Quadrupole strengths (`k1`) are hardcoded constants with no deferred expressions
3. Changing `i_dqd`/`i_dqf` has no effect on optics because they're disconnected

**Solution**: User should either:
1. Use actual quadrupole strengths as variables (e.g., `q_dq303.k1`)
2. Add expressions in the MAD-X lattice to connect power supply currents to quadrupoles

### Files Modified
- `plugins/environments/VirtualAccelerator_MADXSuite/__init__.py` - Added logging for twiss failures
- `tuning_templates/DR_BetatronTunes_Sim_MADXSuite.yaml` - Updated to wider ranges

---

## 2026-08-25: Variable changes not affecting objectives

### Problem
User: "When the qx setpoint value was changed in the GUI, the data being shown in the GUI reflect a change to the value of qx-SETPOINT. But still the changes to the variables i_dqd and i_dqf being tried by the optimization process are not affecting the value of the objective qx-SETPOINT."

After testing with wider ranges, the issue persisted: variable changes were not propagating to the objectives.

### Investigation
1. The `VirtualAccelerator_MADXSuite` environment uses xtrack's `Line.from_madx_sequence()` with `deferred_expressions=True`
2. xtrack evaluates MAD-X deferred expressions at conversion time, storing static numpy.float64 values
3. When xtrack variables are updated (e.g., `line.vars['i_dqd'] = 250.6`), the dependent expressions like `G_DQ206 = F_DQ206 * F_SQD * (C0_SQD + C1_SQD * (FI_DQD * I_DQD - FI_DQS206 * I_DQS206))` are NOT re-evaluated
4. The element `k1` values remain static, so twiss calculations use unchanged optics

### Root Cause
xtrack's deferred expression system evaluates expressions at conversion time and doesn't maintain dynamic dependencies. This is a fundamental limitation of the xtrack approach.

> **CORRECTED 2026-09-14.** The root cause above is wrong, and the rest of this
> section describes a workaround for a problem that was never xtrack's. xtrack's
> expression engine (xdeps) *does* maintain a live dependency graph and
> recomputes only the affected subtree on a write to `line.vars`. What was
> missing were the expressions themselves: the Delivery Ring lattice uses MAD-X
> **immediate** assignment (`=`) for 2486 of its 2488 statements, and MAD-X
> evaluates `=` at parse time and keeps no expression, so cpymad reports
> `expr is None` and there is nothing for xtrack to build a graph from.
> Rewriting the source `=` → `:=` once at load fixes it; see the 2026-09-14
> entry below. The temp-file rebuild described here survives only as a
> fallback for a lattice the rewriter cannot handle.

### Solution Applied
Modified `_update_madx_variables` in `plugins/environments/VirtualAccelerator_MADXSuite/__init__.py` to use MAD-X directly:

1. **Read the original lattice file** line by line
2. **Find each variable's definition** using regex matching (e.g., `I_DQD = 240.6;`)
3. **Replace the numerical value** with the new value from `variable_inputs`
4. **Write a temporary MAD-X file** with the updated values
5. **Create a new MAD-X instance** from the temporary file
6. **Rebuild the xtrack Line** from the updated MAD-X sequence
7. **Re-compute twiss** using the updated xtrack Line

This approach ensures MAD-X properly evaluates all deferred expressions with the new variable values before xtrack converts the sequence.

### Verification
Test results confirmed the fix works:
- Setting `i_dqd = 220`: `qx = 10.024228`
- Setting `i_dqd = 230`: `qx = 9.843706`
- Setting `i_dqd = 240`: `qx = 9.659982`
- Setting `i_dqd = 250`: `qx = 9.474853`
- Setting `i_dqd = 260`: `qx = 9.285527`

The qx value changes monotonically as i_dqd is varied, proving the deferred expressions are now being re-evaluated correctly.

### Files Modified
- `plugins/environments/VirtualAccelerator_MADXSuite/__init__.py` - Complete rewrite of `_update_madx_variables` method

### Trade-offs
- **Pros**: Simple, general solution that works with any MAD-X lattice; correctly handles deferred expressions
- **Cons**: Each variable change requires:
  1. Reading the original lattice file
  2. Creating a temporary file
  3. Loading into new MAD-X instance
  4. Converting to xtrack Line
  5. Cleaning up temporary file
  
  This adds I/O overhead but is acceptable for the correctness it provides.

### Afterthought: Removed lattice_settings_filename

After implementing the temporary file approach, the `lattice_settings_filename` feature was found to be redundant for the optimization workflow:

**Original purpose:** Save/load knob values to a YAML file for persistence across Badger GUI sessions.

**Why it's now redundant:**
- The environment loads the original lattice file with its default parameter values
- During optimization, variable changes use temporary files that are cleaned up
- Cross-session persistence is less critical since the original lattice values are always available

**Removed:**
- `lattice_settings_filename` parameter from `plugins/environments/VirtualAccelerator_MADXSuite/__init__.py`
- `_save_settings_to_file()` method
- `_load_settings_from_file()` method
- `_apply_settings()` method
- `_randomize_settings()` method
- `randomize_settings` and `randomize_amount` parameters
- `lattice_settings_filename` from all tuning template YAML files

**Note:** If cross-session persistence becomes important, it could be re-added later using the same temporary file approach (read original → apply settings via MAD-X → save as default for next session).

---

## 2026-08-28: README streamlined

### Problem
The README had several issues:
- Installation steps were mixed together (git clone, conda env, pip installs, patches)
- `requirements.txt` was empty and redundant with `environment.yml`
- FNAL network requirement for `acsys` was buried in a note
- Patches were not prominent (only mentioned in old quick start)
- Container section had duplicate `docker run` commands

### Solution Applied

**Rewrote README.md with streamlined structure:**

1. **Quick Start** - Five clear steps:
   - Clone repo
   - Create conda env from `environment.yml` (with FNAL network prerequisite)
   - Apply patches to Badger 1.5.4
   - Configure `config.yaml`
   - Launch Badger GUI

2. **Environment Setup Details** - New section explaining what's in `environment.yml`

3. **First-Time GUI Setup** - Dedicated section for critical early steps

4. **Removed**:
   - `requirements.txt` (empty file deleted)
   - Duplicate Docker commands
   - Confusing mixed instruction blocks

### Files Modified

- `README.md` - Completely rewritten
- `requirements.txt` - Deleted

### Status

- [x] Analyzed current README issues
- [x] Designed improved structure
- [x] Rewrote README with new organization
- [x] Removed requirements.txt
- [x] Updated MEMORY.md with new entry

---

## 2026-08-28: Badger 1.6.0 upgrade

### Problem
Badger 1.5.4 had known issues that needed fixing, and Badger 1.6.0 was released with improvements.

### Investigation

**Badger 1.6.0 changes:**
- `initialize_special_field` changed: `defaults.get(field, {})` → `defaults.get(field)`
- VOCs validation requires vocs field in parameters
- `get_local_region` function added to xopt.vocs (requires xopt>=3.2.0)

### Issues Found

1. **turbo_controller null warning**: When `turbo_controller: null` was set, Badger 1.6.0 logged warnings because it couldn't distinguish between "key missing" and "key explicitly null"

2. **vocs field required error**: Badger 1.6.0 raised `KeyError: 'vocs field is required in parameters'` because vocs data is stored in `self.vocs` separately from the YAML tree

3. **Template structure issue**: Some templates had vocs keys directly under `generator:` without a `vocs:` key

### Fixes Applied

**Fix 1: pydantic_editor.py - turbo_controller null handling**
- Modified `initialize_special_field()` to check if field exists in defaults before warning
- If field exists with null value, return early without warning

**Fix 2: pydantic_editor.py - vocs field not found**
- Modified `validate()` to use `self.vocs.model_dump()` when vocs is not in parameters_dict

**Fix 3: Template VOCs structure**
- Updated `DR_BetatronTunes_sim.yaml` to have vocs properly nested under `generator:`

### Testing

- Badger GUI launched successfully with version 1.6.0
- Template loaded without `turbo_controller` warnings
- Environment (VirtualAccelerator_MADXSuite) works correctly
- Xopt upgraded to 3.2.1 for compatibility

### Additional Fix: Badger 1.6.0 Startup Validation Error

**Problem:** When starting Badger or switching generators, validation errors appeared:
```
turbo_controller.vocs: Value error, optimize turbo controller must have an objective specified
turbo_controller.failure_tolerance: Value error, vocs must be set before inferring tolerances
turbo_controller.success_tolerance: Value error, vocs must be set before inferring tolerances
```

**Root Cause:** 
1. When `turbo_controller: null` is in the defaults, `initialize_special_field()` returned early without setting the combo box to "null"
2. The combo box was still showing "OptimizeTurboController" as the selected value
3. When `get_parameters_yaml()` was called, the combo box returned "OptimizeTurboController" (string) instead of "null"
4. The string "null" in YAML is parsed as the string "null", not the null value `None`
5. Pydantic tried to validate "OptimizeTurboController" as a TurboController, which failed because it has an empty vocs

**Fixes Applied:**

**Fix 4: pydantic_editor.py - QComboBox "null" handling**
- Modified `_qt_widget_to_yaml_value()` to return `None` when `currentText() == "null"`
- This ensures YAML null is output instead of the string "null"

**Fix 5: pydantic_editor.py - TurboController combo box initialization**
- Modified `initialize_special_field()` to set combo box to "null" before returning early
- This ensures the combo box shows "null" when `turbo_controller: null` is in defaults

### Files Modified

- `environment.yml` - Updated badger-opt to 1.6.0, xopt to >=3.2.0
- `README.md` - Updated version references and patch instructions
- `patches/pydantic_editor-badger-1.6.0-fixes.patch` - Updated with new fixes
- `patches/README.md` - Updated documentation
- `tuning_templates/DR_BetatronTunes_sim.yaml` - Fixed vocs structure
- `docs/badger-upgrade-1.6.0.md` - New testing documentation

### Status

- [x] Identified Badger 1.6.0 issues
- [x] Applied pydantic_editor.py fixes
- [x] Updated environment.yml with new versions
- [x] Fixed template VOCs structure
- [x] Tested template loading (no warnings)
- [x] Fixed startup validation errors
- [x] Updated documentation

---

## 2026-08-28: YAML flow map 'None' parsing fix

### Problem
When templates with `None` values were loaded, validation errors appeared:
```
Input should be a valid number, unable to parse string as a number [type=float_parsing, input_value='None', input_type=str]
```

### Root Cause
When YAML flow maps (inline `{}`) contain unquoted `None`, `yaml.safe_load()` parses them as the string `'None'` instead of Python `None`. This happened in:

1. **pydantic_editor.py** - `get_parameters_yaml()` outputs YAML with single-quoted flow maps like `{'dtype': None, 'default_value': None}`. When parsed, `None` becomes `'None'`.

2. **Generator vocs in templates** - Some templates store vocs fields as YAML strings (e.g., `vocs.variables: "{'i_dqd': {'dtype': None, ...}}"`). When `yaml.safe_load()` parses this string, `None` becomes `'None'`.

### Fix Applied

**In `badger/gui/components/pydantic_editor.py` (3 locations):**
- Added string replacement before `yaml.load()`:
  ```python
  fixed_parameters = (
      parameters.replace(": None", ": null")
      .replace(", None", ", null")
      .replace("[None", "[null")
      .replace("(None", "(null")
  )
  defaults = yaml.load(fixed_parameters, Loader=CustomSafeLoader)
  ```

**In `badger/gui/utils.py` - `_parse_yaml_strings` function:**
- Same string replacement before `yaml.safe_load()`:
  ```python
  fixed_obj = (
      obj.replace(": None", ": null")
      .replace(", None", ", null")
      .replace("[None", "[null")
      .replace("(None", "(null")
  )
  return yaml.safe_load(fixed_obj)
  ```

### Testing

Template `DR_BetatronTunes_sim.yaml` loaded successfully with:
- `dtype=None` (NoneType, not string)
- `default_value=None` (NoneType, not string)
- `max_travel_distances=None` (NoneType, not string)
- `turbo_controller=None` (NoneType, not string)

Generator validation passed without errors.

### Files Modified

- `/Users/stjohn/miniconda3/envs/FermiBadger_env/lib/python3.12/site-packages/badger/gui/components/pydantic_editor.py` - Added string replacement before yaml.load() calls
- `/Users/stjohn/miniconda3/envs/FermiBadger_env/lib/python3.12/site-packages/badger/gui/utils.py` - Updated _parse_yaml_strings function
- `/Users/stjohn/Development/BayesOptimization_Xopt/FermiBadgerPlugins/badger-1.6.0-none-parsing-fix.patch` - Patch file created for distribution

### Status

- [x] Identified root cause (YAML flow map 'None' parsed as string)
- [x] Implemented fix in pydantic_editor.py (3 locations)
- [x] Implemented fix in utils.py
- [x] Tested template loading (no validation errors)
- [x] Created patch file for distribution
- [x] Updated MEMORY.md

---

## 2026-09-08: PydanticSerializationUnexpectedValue warning for _initial_state

### Problem
When running the Badger mini GUI with TurboController, pydantic emitted warnings:
```
PydanticSerializationUnexpectedValue(Unexpected field `_initial_state_value`: Expected `OptimizeTurboController`)
```

The warning appeared when the optimization run started (clicking "Play" in the mini GUI).

### Root Cause
The `TurboController` class in Xopt stored `_initial_state` in `__init__` as a plain attribute (not declared as a pydantic field). When pydantic v2 tried to serialize the object, it found this extra attribute in `__dict__` and emitted `PydanticSerializationUnexpectedValue` warnings.

### Investigation
Multiple approaches were attempted:
1. **model_dump override** - The parent `XoptBaseModel.model_dump()` excluded private attrs starting with `_`, but pydantic's internal serializer still saw the attribute
2. **model_serializer with wrap** - Caused RecursionError when calling `serializer(self)` which triggered the serializer again
3. **__getstate__/__setstate__ for pickle** - Only affected pickle, not pydantic's internal serializer
4. **Using a property** - The property returned a computed dict, but the underlying `_initial_state_value` was still in `__dict__`

### Solution Applied

**File:** `/Users/stjohn/miniconda3/envs/FermiBadger_env/lib/python3.12/site-packages/xopt/generators/bayesian/turbo.py`

**Fix:** Declare `_initial_state_value` as a `PrivateAttr`:

```python
class TurboController(XoptBaseModel, ABC):
    _failure_counter: int = PrivateAttr(0)
    _success_counter: int = PrivateAttr(0)
    _initial_state_value: dict[str, Any] = PrivateAttr()  # <-- Added
```

And use a property for the public API:

```python
@property
def _initial_state(self) -> dict[str, Any]:
    """Property to access the initial state."""
    return self._initial_state_value

@_initial_state.setter
def _initial_state(self, value: dict[str, Any]) -> None:
    """Setter to allow setting the initial state during initialization."""
    self._initial_state_value = value
```

**Why this works:** In pydantic v2, `PrivateAttr()` is the proper way to declare attributes that should not be serialized as part of the model. Pydantic knows these attributes are internal and won't emit warnings about them.

### Testing
- TurboController instantiation works correctly
- `model_dump()` excludes `_initial_state_value`
- `pickle` serialization/deserialization works
- `reset()` method works correctly
- No pydantic serialization warnings appear in Badger mini GUI

### Files Modified
- `/Users/stjohn/miniconda3/envs/FermiBadger_env/lib/python3.12/site-packages/xopt/generators/bayesian/turbo.py` - Added `PrivateAttr` declaration and simplified property-based access

### Status
- [x] Identified root cause (_initial_state not declared as pydantic field)
- [x] Applied PrivateAttr fix in TurboController
- [x] Verified no pydantic warnings in Badger GUI
- [x] Updated MEMORY.md

---

## 2026-08-28: PR preparation for Badger fork

### Context
For future fresh conda environments with Badger 1.6.0, a patch file is needed to apply all the fixes.

### Created Files

1. **`badger-1.6.0-none-parsing-fix.patch`** - Single patch file with all None parsing fixes

2. **`docs/pr-badger-fork.md`** - PR description and instructions for forking Badger 1.6.0

### Instructions for New PR

**To apply to a fresh environment:**
```bash
cd /path/to/badger
patch -p1 < /path/to/badger-1.6.0-none-parsing-fix.patch
```

**To create a fork of Badger 1.6.0 with fixes:**
1. Fork https://github.com/xopt-org/Badger
2. Apply the patch to the fork
3. Update fork's version to `1.6.0-p1`
4. Publish fork and update environment.yml

### Files Created

- `badger-1.6.0-none-parsing-fix.patch` - Patch file
- `docs/pr-badger-fork.md` - PR description and instructions

---

## 2026-08-29: List type subtype fix

### Problem
When loading the `TuneQx.yaml` template with `SimpleVirtualAccelerator` environment, we got:
```
ValueError: List type must have a subtype
```

The error occurred in `pydantic_editor.py` when the pydantic editor tried to create a widget for the `quad_k_list` field.

### Root Cause

1. **Union type resolution**: When `Union[List[str], str]` was resolved, the `main` was set to `Union` instead of the primary type (`list`). This caused `resolve_qt` to not match any of the type checks.

2. **List type inference**: In `set_params_from_dict`, when creating field definitions from template values, plain `list` was used instead of `list[str]`, which doesn't have subtypes required by pydantic_editor.

### Fixes Applied

**Fix 1: BadgerResolvedType.resolve (line ~180-186)**
```python
# Before:
return BadgerResolvedType(main=origin, subtype=primary)

# After:
return BadgerResolvedType(main=primary.main, subtype=primary.subtype)
```

**Fix 2: set_params_from_dict (line ~755-777)**
```python
elif isinstance(v, list):
    if all(isinstance(item, str) for item in v):
        field_definitions[k] = (list[str], Field())
    elif all(isinstance(item, (int, float)) for item in v):
        field_definitions[k] = (list[float], Field())
    else:
        field_definitions[k] = (list, Field())
```

### Testing

- `SimpleVirtualAccelerator` template `TuneQx.yaml` loads successfully
- Environment instantiated with dict/list values from template
- pydantic_editor validates without errors

### 2026-08-29: Double pydantic warning fix

**Problem:** Running `TuneQx.yaml` template produced double warning every iteration:
```
PydanticSerializationUnexpectedValue(Unexpected Value)
PydanticSerializationUnexpectedValue(Unexpected Value)
```

**Root Cause:** In `set_params_from_dict`, dict values were stored as YAML strings using `yaml.dump()` which produces block format (e.g., `qx: 2.05015\nqy: 1.20948`). When the model was serialized, pydantic expected a dict but found a string.

**Fix:** Changed `yaml.dump(v).strip()` to `yaml.dump(v, default_flow_style=True).strip()` to produce flow maps (e.g., `{qx: 2.05015, qy: 1.20948}`) that match template format.

**Files Modified**

- `badger/gui/components/pydantic_editor.py` - Updated `set_params_from_dict` to use `default_flow_style=True`

### Additional Changes

- `plugins/environments/SimpleVirtualAccelerator/__init__.py` - Updated type annotations:
  - `quad_k_list: Union[List[str], str]`
  - `setpoints: Union[Dict[str, float], str, None]`
  - Updated `__init__` to handle both list/string and dict/string types

### Patch Files Created

- `badger-1.6.0-none-parsing-fix.patch` - Updated with all fixes
- `simple-virtual-accelerator-plugin-fix.patch` - Plugin patch

### Status

- [x] Identified root causes
- [x] Fixed Union type resolution
- [x] Fixed list subtype inference
- [x] Fixed dict YAML format (flow maps)
- [x] Updated SimpleVirtualAccelerator plugin
- [x] Tested template loading (no pydantic warnings)
- [x] Updated MEMORY.md

---

## 2026-09-08: PydanticSerializationUnexpectedValue warning every iteration

### Problem
User reported: "After half a dozen iterations (when the initial data points have been checked), we still get this warning every iteration:"

```
PydanticSerializationUnexpectedValue(Unexpected Value)
PydanticSerializationUnexpectedValue(Unexpected Value)
```

This warning appeared every iteration of the optimization loop, not just at startup.

### Investigation

1. **Previous fix**: The `_initial_state_value` warning was fixed by declaring it as `PrivateAttr()` in the TurboController class. However, this fix only addressed warnings for that specific field name.

2. **Root cause**: The `PydanticSerializationUnexpectedValue(Unexpected Value)` warning without a field name was occurring during `model_dump()` calls in the pydantic editor's `validate()` method. The existing warning filter at lines 1225-1239 only covered the `convert_dict` function definition but NOT the `model_validate()` and `model_dump()` calls that happen later in the method (at lines 1280 and 1282).

3. **Code flow**: The `with warnings.catch_warnings()` context at lines 1227-1239 was too narrow - it didn't extend to cover:
   - `model_validate()` call at line 1280
   - `model_dump()` call at line 1282

### Solution Applied

**File:** `/Users/stjohn/miniconda3/envs/FermiBadger_env/lib/python3.12/site-packages/badger/gui/components/pydantic_editor.py`

**Fix:** Added a new warning filter at lines 1281-1292 that covers both `model_validate()` and `model_dump()` calls:

```python
# Filter out PydanticSerializationUnexpectedValue warnings from TurboController
# These warnings are expected and harmless, occurring during both validation
# and serialization of models with private attributes like _initial_state_value
with warnings.catch_warnings():
    warnings.filterwarnings(
        "ignore",
        category=UserWarning,
        message=".*PydanticSerializationUnexpectedValue.*",
    )
    model = self.model_class.model_validate(parameters_dict)

    defaults = model.model_dump()
```

The filter uses a broad pattern `.*PydanticSerializationUnexpectedValue.*` to catch all such warnings that may occur during TurboController serialization, including both `_initial_state` and general "Unexpected Value" warnings.

### Testing

The fix was tested with:
1. Direct Python test of TurboController serialization - no warnings
2. The warning filter now covers both critical paths where pydantic serialization occurs:
   - `model_validate()` - validation of incoming parameters
   - `model_dump()` - serialization of validated model for GUI updates

### Files Modified

- `/Users/stjohn/miniconda3/envs/FermiBadger_env/lib/python3.12/site-packages/badger/gui/components/pydantic_editor.py` - Added warning filter covering `model_validate()` and `model_dump()` calls

### Status

- [x] Identified that warning filter was too narrow (not covering `model_dump()` path)
- [x] Added new warning filter at correct location
- [x] Verified fix addresses the iterative warning

---

## 2026-09-14: Deferred-expression rewrite — ~150x faster iterations, plus transfer-line support

### Problem
Every optimizer iteration rewrote the lattice source to a temp file, spawned a
fresh `Madx`, and rebuilt the whole xtrack `Line` (`_update_madx_variables`).
Measured on the Delivery Ring: `Madx()` + `call` 0.41 s, `from_madx_sequence`
**3.41 s**, twiss 0.10 s — about **4 s per iteration**.

### Root cause
Not an xtrack limitation (see the correction added to the 2026-08-25 entry).
The lattice assigns with MAD-X immediate `=`, which is evaluated at parse time
and discarded; only 2 statements in 5236 lines use deferred `:=`. cpymad
therefore reports `mad.elements['q_dq206'].cmdpar['k1'].expr is None`, and the
`Line` arrives frozen.

### Solution
New module `plugins/environments/VirtualAccelerator_MADXSuite/madx_deferred.py`
rewrites `=` → `:=` in the source once at load, so the formulas survive into
xtrack's xdeps graph. `set_variables()` is then just `line.vars.update()`.
The rewrite is conservative — it skips loop/macro bodies, self-referential and
reassigned names, volatile right-hand sides (`ranf`/`gauss`/`tgauss`/`table`),
booleans, and string/keyword attributes — and `create_VA()` verifies it by
loading the original into a throwaway `Madx` and comparing every global and
element attribute at `rtol=1e-12`. On any mismatch it logs loudly, sets
`_use_deferred = False`, and falls back to the old per-iteration rebuild.

### Verified
| lattice | globals | element attrs | now expression-driven |
|---|---|---|---|
| Delivery Ring | 2510 agree | 4405 agree | 1850 |
| Xfer400MeV | 111 agree | 803 agree | 115 |

Tune sweep reproduces the 2026-08-25 slow-path table to the digit
(220 → 10.024228, 230 → 9.843706, 240 → 9.659982, 250 → 9.474853,
260 → 9.285527). Per-iteration cost **23-32 ms** (tunes) / **75 ms** (with
chromaticity), against ~4000 ms.

### Also in this change
- **Chromaticity on demand.** `get_observables()` decides `chrom=` from the
  requested channel names, and `set_variables()` only invalidates the cached
  twiss instead of recomputing it. That removes one wasted twiss per iteration.
- **Free knobs only.** `line.vars` entries carrying an expression are now
  derived outputs (the 359 `g_*` gradients on the Delivery Ring); assigning one
  would overwrite its formula and sever the dependence for the session, so they
  are no longer offered as variables. Tune with the currents (`i_dqd`) instead
  of the gradients (`q_dq303.k1`).
- **Transfer lines.** New `twiss_init` parameter (betx, alfx, bety, alfy, and
  optionally the incoming centroid x, px, y, py). When set, the twiss runs open
  from START to END and the ring-only observables (qx, qy, dqx, dqy) are not
  advertised. `sim_configs/Xfer400MeV/B400tracking.madx` runs through the same
  Environment and Interface at ~5 ms per iteration.
- **Monitors by element type.** `hmonitor`/`vmonitor`/`monitor` base types
  instead of a name regex: 124 monitors on the Delivery Ring (59 h / 60 v / 5
  both), 36 on Xfer400MeV, with no per-lattice configuration. Each advertises
  only the plane it measures, so the old half-invalid `.y`-on-an-`hmonitor`
  channels are gone. `bpm_name_pattern` survives as an optional extra filter,
  defaulting to None, and was dropped from `configs.yaml` and both DR templates
  (where it read `bpm` and matched nothing).
- **Any twiss column.** The interface's `<element>.<attr>` branch accepts any
  column on the twiss table, not just `x`/`y`, so `bphq2.betx` works — needed
  on a transfer line, where `qx`/`qy` mean nothing.
- **Design setpoints** are recorded for every advertised observable, skipping
  any that reads back non-finite, rather than only for global optics.

### Known, pre-existing
Changing a main bend *angle* moves neither the orbit nor the tune: xtrack's
`Bend` carries the reference trajectory with the geometry. Confirmed identical
on the old slow path, so it is an xtrack modelling property, not a regression.
Steer with corrector currents (`i_dht*`).

### Files Modified
- `plugins/environments/VirtualAccelerator_MADXSuite/madx_deferred.py` — new
- `plugins/environments/VirtualAccelerator_MADXSuite/__init__.py`
- `plugins/environments/VirtualAccelerator_MADXSuite/configs.yaml`
- `plugins/interfaces/VirtualAccelerator_MADXSuiteInterface/__init__.py`
- `tuning_templates/Xfer400MeV_example.yaml` — new
- `tuning_templates/DR_BetatronTunes_sim.yaml`, `DR_BetatronTunes_MOBO_sim.yaml`
- `tests/VA_deferred_expressions_test.py` — new
- `tests/VA_plugin_smoke_test.py`, `tests/VA_template_integration_test.py`

### Status
- [x] Rewriter + self-check (`python .../madx_deferred.py`)
- [x] Equivalence + liveness over both lattices (`tests/VA_deferred_expressions_test.py`)
- [x] Smoke, factory-path and GUI-editor tests pass
- [ ] End-to-end in the Badger GUI with both templates

---

## 2026-09-14 (later): GUI run findings

First end-to-end GUI run of the two templates surfaced two things.

### Unstable optics returned NaN with no way to fence them off
`DR_BetatronTunes_sim.yaml` ran, but the optimizer wandered into currents where
the periodic twiss has no solution. `_compute_twiss()` catches that and returns
None, so every twiss-derived channel reads NaN — including the objective, which
the generator cannot learn from. (Not hit in `-g` mode, hit readily in `-mini`.)

New observable `optics_stable`: 1.0 while the twiss solves, 0.0 when it does
not. Advertised on every lattice, deliberately with **no `-SETPOINT` twin** —
it is a flag to constrain, not a quantity to steer. Both DR templates now carry
`optics_stable > 0.5` as a non-critical constraint.

Still open: the objective itself is still NaN at those points, and xopt does
not drop NaN rows before fitting the GP. The constraint keeps the acquisition
away from the region but does not sanitize the training data.

### Xfer400MeV template died in `get_local_region`
`KeyError: 'Center point keys must match vocs variable names'`. Root cause is
in Badger, not here: `factory.load_plugin` builds `configs['variables']` once,
from the first env instance — which uses the **default** lattice in the
plugin's `configs.yaml` (the Delivery Ring) — and caches it in
`BADGER_FACTORY`. `configs['observations']` is the same list object as
`Environment.observables` and therefore does track the template's lattice, but
`configs['variables']` is a freshly built list and never refreshes. So
`iq2`/`iq3`/`iq74` were absent from the GUI variable table, nothing got
selected, and `env.get_variables([])` returned `{}` against a three-variable
vocs.

Fix is per template, using Badger's supported escape hatch:
`additional_variables: [iq2, iq3, iq74]` in `Xfer400MeV_example.yaml`. That
path calls `env.get_bounds()` on an env built from the *template's* params, so
the bounds and the variable table come out right. Any future template on a
non-default lattice needs the same list.

`tests/VA_template_integration_test.py` now walks every shipped template and
checks exactly this: each vocs variable is either in the cached default-lattice
list or in `additional_variables`, each vocs variable is a real knob of that
template's own lattice, and every objective/constraint/observable is advertised
by that lattice.

### Files
- `plugins/environments/VirtualAccelerator_MADXSuite/__init__.py` — `OPTICS_STABLE`
- `plugins/interfaces/VirtualAccelerator_MADXSuiteInterface/__init__.py` — channel
- `tuning_templates/DR_BetatronTunes_sim.yaml`, `DR_BetatronTunes_MOBO_sim.yaml`
- `tuning_templates/Xfer400MeV_example.yaml`
- `tests/VA_plugin_smoke_test.py`, `tests/VA_template_integration_test.py`

---

## 2026-09-14 (round 2) — lattice cache + `-mini` patch

`-mini` loading a non-default-lattice template re-loaded the Delivery Ring
several times and died with `ValueError: Cannot read 'iq2'`. Root cause is the
same family as the `additional_variables` issue but a different cache:
`BadgerVariableTable.configs` is set only in `select_env()`, from the plugin's
`configs.yaml` defaults, and `refresh_current_values()` rebuilds an env from it
every time (Badger's own `# TODO: Use a cached env` in `add_var`).

Fixed on three fronts, as chosen:

1. **Badger patch** `patches/badger-mini-var-table-env-configs.patch` — refresh
   `var_table.env_class/configs` via `add_var()` immediately after the template's
   params land in the editor, and clear `var_table.env`. Applied to
   FermiBadger_env; listed in `patches/README.md`.
2. **Tolerant reads** — `Interface._read_setting` returns NaN with a warning for
   a channel the lattice does not have. Reads only; `set_values` still raises.
3. **`_LATTICE_CACHE`** in the environment module, keyed on (resolved lattice
   path, sequence name), storing the `Madx` and a pristine design `Line`. Every
   instance takes `design_line.copy()` — the xdeps expression graph copies with
   it — so repeated GUI rebuilds cost 1.3 s instead of 9.9 s and no instance can
   perturb another. Only verified-deferred lattices are cached, so the fallback
   reload path (which replaces `self._madx`) never touches a cached entry.

Verified: all five checks pass, including a new smoke-test assertion that the
second instance is both fast and at design optics after the first was detuned.

### Files
- `plugins/environments/VirtualAccelerator_MADXSuite/__init__.py` — `_LATTICE_CACHE`,
  `_reuse_cached_lattice()`, `_load_lattice()`
- `plugins/interfaces/VirtualAccelerator_MADXSuiteInterface/__init__.py` — NaN reads
- `patches/badger-mini-var-table-env-configs.patch`, `patches/README.md`
- `tests/VA_plugin_smoke_test.py` — cache hit + independence

---

## 2026-09-14 (round 3) — lazy load + sidecar cache of the deduced lists

`factory.load_plugin` builds one environment per process from the plugin
defaults just to read the variable list (`env.get_bounds(m_env.variables)`).
That was a 9.3 s Delivery Ring parse in the GUI process and another in the run
subprocess, regardless of which lattice the template names.

The environment now:
- writes `{stamp, variables, observables}` to
  `<lattice>.<param-hash>.varcache.json` whenever it deduces them,
- populates the class lists from that sidecar at construction and **defers the
  MAD-X parse** to `_ensure_lattice()`, called by `get_variables`,
  `set_variables`, `get_observables` and `_read_channel_value`,
- re-deduces when the lattice's mtime/size changes; the param hash covers
  sequence, `rel_range`, `zero_half_range`, `bpm_name_pattern` and the
  `twiss_init` keys, so param sets do not invalidate each other.

Measured in a fresh process: `get_env(...)` 9.3 s → 1.2 s with no lattice parse.
Sidecars are ~84 KB (Delivery Ring) and gitignored, along with the MAD-X output
files (`madx.ps`, `sectormap`, `optics_*.dat`, `checkpoint_restart.dat`).

Also: `_bounds_around()` now takes `abs(zero_half_range)`, and
`DR_BetatronTunes_sim.yaml`'s `zero_half_range: -1.9` is corrected to `1.9` —
it was handing Badger `[1.9, -1.9]` for every zero-valued knob.

### Files
- `plugins/environments/VirtualAccelerator_MADXSuite/__init__.py` — `create_VA()`,
  `_ensure_lattice()`, `_varcache_params/_path/_stamp/_read/_write`
- `tests/VA_plugin_smoke_test.py`, `tests/VA_deferred_expressions_test.py`
- `tuning_templates/DR_BetatronTunes_sim.yaml`, `.gitignore`

---

## 2026-09-14 (rounds 4-5) — quiet reads, and the `-mini` table lists the template's lattice

Round 4: the interface's NaN-tolerant read path logged one warning per unknown
channel per refresh, which is thousands of lines under a cross-lattice template.
`_read_setting` now returns `None` and `get_settings` emits a single DEBUG line
summarising the unknown names. Values and error behaviour unchanged.

Round 5: the remaining wrong-lattice rows. `routine_page.vars_env` — the `-mini`
variable table's rows — is built in `select_env()` from `configs["variables"]`,
which `factory.load_plugin` computed once from an environment carrying the
plugin defaults. `badger-mini-var-table-env-configs.patch` now also rebuilds it
inside `set_options_from_template()`, from `instantiate_env()` on the template's
params plus `get_bounds(type(env).variables)` — the same construction the
factory uses. On failure it logs and keeps the cached list, so a template on the
default lattice is unaffected.

Measured: `Xfer400MeV_example.yaml` 2284 Delivery Ring rows → **124** of its own.
With the sidecar cache warm that rebuild parses nothing.

Verified: all five checks pass;
`tests/VA_template_integration_test.py` now performs the patch's own
construction per template and asserts a non-default lattice yields a different
variable list.

### Files
- `patches/badger-mini-var-table-env-configs.patch`, `patches/README.md`
- `plugins/interfaces/VirtualAccelerator_MADXSuiteInterface/__init__.py` — `_read_setting`
- `tests/VA_template_integration_test.py`

---

## 2026-09-15: `setup.sh` — one-command setup for a fresh clone

Plan written first: [docs/2026-09-15-setup-script-plan.md](2026-09-15-setup-script-plan.md).

Added `setup.sh` at the repo root: creates/reuses the `FermiBadger_env` conda
env, applies the three Badger patches (idempotent, per-patch directory and
strip level — they don't share one recipe), writes `config.local.yaml` with
the clone's own paths (gitignored, so `config.yaml` stays a clean tracked
template), and verifies Badger discovers `VirtualAccelerator_MADXSuite`.
`xopt-pydantic-serialization-fix.patch` is deliberately skipped — it amends
hand-written code that exists only in this machine's env, not in a pristine
xopt 3.2.1 install, so it can't apply to a fresh clone (see the plan for the
full diagnosis). Corrected the `-p0`→`-p1` patch instructions in `README.md`
and `patches/README.md` along the way. `VirtualAccelerator_MADXSuite` now
falls back to a repo-root-relative lattice path when the CWD-relative one
isn't found, so Badger no longer has to be launched from the repo root.

Verified: fresh-clone setup (copied to `/tmp`, both `--yes` and idempotent
re-run), the existing-env "keep as-is" path against the real `FermiBadger_env`,
lattice resolution from another directory, and all four VA tests still pass.

## 2026-09-16: RIL_tuning physical templates — pydantic load errors, stale bounds, and the `-g` "Automatic" hang

Working through `badger -mini -cf config.yaml -t RIL_tuning_trims_and_sol_LEBT_MEBTquads.yaml`
(BasicAcsysInterface, real hardware, not a sim) failing outright, in three
successive layers.

**1. `generator.turbo_controller: safety`** — a bare string, left over from a
pre-1.4 Badger/Xopt template. Current `pydantic_editor.initialize_special_field()`
does `special_item_dict: dict | None = defaults.get(field)` then
`special_item_dict["vocs"] = ...`; a bare string there crashes with
`TypeError: 'str' object does not support item assignment`. The documented,
tested convention for this exact scenario is already `turbo_controller: null`
(see "Fix 1" above, and `DR_BetatronTunes_sim.yaml`) — not a hand-authored
`SafetyTurboController` object, which the code only exercises with live,
mid-run state, not a clean starting config. Applied `null` to the template;
loads past this point.

**2. Static `vocs.variables` bounds stale vs. live hardware.** Next error was
`VariableRangeError: Current value is not within variable range!` from
`routine_page.add_rand_in_init_table()` → `xopt.vocs.clip_variable_bounds()` →
`ValueError: Bounds specified for 'L:ATRMHD' do not satisfy value[1] > value[0]`.
Root cause: `-mini` always auto-fills the init table on load
(`update_init_table(force=True)`), sampling a region around each variable's
*live* current value (`env.get_variables()` via `BasicAcsysInterface`) and
clipping it to the template's declared hard bounds with `np.clip`. If the live
value sits far enough outside those declared bounds, both ends of the clip
land on the same boundary → a zero-width range → the `value[1] > value[0]`
check fails. Wrote `check_RIL_tuning_live_bounds.py` (repo root, read-only —
only calls `get_variables`/`get_settings`, never `set_variables`/`set_values`)
to dump every template variable's live value next to its declared bounds in
one shot instead of crashing on them one at a time. Found `L:ATRMHD`,
`L:ATRMHU`, `L:ATRMVD` declared one-sided `[0, upper]` but reading modestly-
to-significantly negative, while sibling `L:ATRMVU` already had a correct
two-sided `[-4, 1]` bound. Mirrored that style per user direction:
`L:ATRMHD [0,2]→[-2,2]`, `L:ATRMHU [0,4]→[-4,4]`, `L:ATRMVD [0,1]→[-1,1]`.
Confirmed against the environment's own class-level hard bounds
(`plugins/environments/RIL_tuning/__init__.py`, `[-4.0, 4.0]` for all four
ATRM trims) — the new sub-ranges are safely inside those.

Longer-term: Badger's `relative_to_current` ("Automatic" checkbox / config's
`AUTO_REFRESH`) exists to recompute `vocs.variables` from live values against
the *environment's* hard bounds every load, instead of hand-typed numbers
going stale — see item 3, this is now viable.

**3. `-g` full GUI hang: checking "Automatic" for a RIL_tuning template stalled
forever, no error, had to be force-quit.** Traced `toggle_relative_to_curr(True)`
→ `calc_auto_bounds()` (one live read) → `try_populate_init_table()` →
`update_init_table()` → `add_rand_in_init_table()` (a second, independent live
read, via a fresh `create_env()`/`Interface()`/ACNET `Connection` each time).
Found a real bug in `plugins/scanner.py`'s `read_once()`: `await dpm.start()`
was called *inside* the per-device loop (once per device) instead of once
after all entries are registered — unlike the write path `set_once()` in the
same file, which does it correctly. A single one-shot read tolerates this
fine (that's why `-mini` and the diagnostic script worked), but back-to-back
DPM sessions — exactly what "Automatic" mode triggers — did not. Fixed by
moving `dpm.start()` out of the loop. Also added a 15s `asyncio.wait_for(...)`
around the reply-wait in `read_once()` as a safety net, since nothing in this
path had a timeout before — a stuck DPM session would otherwise hang the Qt
GUI thread forever with zero diagnostic trace. **User-confirmed: "Automatic"
now completes without hanging** (the timeout never triggered — the
`dpm.start()` fix was the actual root cause).

### Files
- `tuning_templates/RIL_tuning_trims_and_sol_LEBT_MEBTquads.yaml` — `turbo_controller: null`;
  `L:ATRMHD`/`L:ATRMHU`/`L:ATRMVD` bounds widened to two-sided, mirroring `L:ATRMVU`
- `plugins/scanner.py` — `read_once()`: `dpm.start()` moved outside the per-device
  loop; wrapped in `asyncio.wait_for(timeout=15.0)` with a diagnostic `TimeoutError`
  naming any device(s) that never replied
- `check_RIL_tuning_live_bounds.py` (new, repo root) — read-only live-vs-declared-bounds
  diagnostic for any RIL_tuning template

### Still open
- `RIL_tuning_trims_and_sol.yaml` and `templates.yaml` carry the same stale
  `turbo_controller: safety`/`optimize` bare strings and old singular
  `sample_event`/`setpoint` environment params (harmless — pydantic's default
  `extra='ignore'` on `Environment` silently drops them — but worth cleaning
  up for clarity). Not yet swept.
- Whether to turn on `relative_to_current: true` in these templates now that
  the underlying hang is fixed, so bounds self-heal from live values against
  the environment's hard limits instead of going stale again — not yet
  decided/applied.
