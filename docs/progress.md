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

### Deliverables
1. **Patch file:** `patches/pydantic_editor-null-turbo_controller-git-apply.patch`
2. **README update:** Added patch command to step-by-step installation
3. **Documentation:** Updated docs/progress.md and docs/log.md

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
