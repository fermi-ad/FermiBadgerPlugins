# HANDOFF: VirtualAccelerator_MADXSuite Plugin Development

## Quick Start for New Developers

### Getting Started

1. **Set up your environment**:
   ```bash
   conda activate FermiBadger_env
   cd /Users/stjohn/Development/BayesOptimization_Xopt/FermiBadgerPlugins
   ```

2. **Launch the GUI** (with repo-specific config):
   ```bash
   badger -g --config_filepath config.yaml
   ```

3. **Load a template**:
   - Open `tuning_templates/VirtualAccelerator_MADXSuite_example.yaml`
   - The lattice file path is relative to the repo root

### Version Information

- **Badger**: 1.6.0 (with patches in `patches/pydantic_editor-badger-1.6.0-fixes.patch`)
- **Xopt**: 3.2.1
- **Conda environment**: `FermiBadger_env`

For detailed information on versions and fixes, see `HANDOFF.md` section "Badger 1.6.0 Fixes and Gotchas".

### Key Files to Understand

| File | Purpose |
|------|---------|
| `plugins/environments/VirtualAccelerator_MADXSuite/__init__.py` | Environment plugin - loads MAD-X lattice, deduces vars/observables |
| `plugins/interfaces/VirtualAccelerator_MADXSuiteInterface/__init__.py` | Interface plugin - translates channel names to xtrack operations |
| `tuning_templates/VirtualAccelerator_MADXSuite_example.yaml` | Working example template |
| `sim_configs/DeliveryRing/` | Lattice files for different accelerator configurations |
| `patches/pydantic_editor-badger-1.6.0-fixes.patch` | Pydantic editor patches for Badger 1.6.0 |

For more on patches, see `patches/README.md`.

---

## Critical Gotchas & Design Decisions

### 1. First-Call-Wins Singleton (`init_settings()`)

**Problem**: Badger's `archive.py` calls `init_settings()` at import time. The config singleton is "first call wins."

**Impact**: If the GUI (system config) and your subprocess (project config) have different `BADGER_ARCHIVE_ROOT` paths, files created by one process won't be found by the other.

**Solution**:
- Always use `badger -g --config_filepath config.yaml` from the repo root
- Keep system config (`~/Library/Application Support/Badger/config.yaml`) synchronized with repo `config.yaml`

### 2. Plugin Instantiation Order Trick

Badger 1.5.4's factory binding behavior:
1. Class attrs `variables`/`observables` are aliased **before** environment is instantiated
2. `create_VA()` must populate these in-place (`.clear()`, `.update()`, `[:] =`)

**Why**: This allows factory aliases to see the populated lists when the GUI queries them.

**DON'T do this**:
```python
# WRONG - rebinds the class attr
self.variables = self._deduce_variables()  # Won't reach the GUI!
```

**DO this**:
```python
# CORRECT - modifies in-place
type(self).variables.clear()
type(self).variables.update(self._deduce_variables())
```

See: `plugins/environments/VirtualAccelerator_MADXSuite/__init__.py:52-58, 173-175`

### 3. GUI Param Editor Bug - Dict/List Values Crash

**Problem**: `pydantic_editor.set_params_from_dict` rebuilds a dynamic model from `type(value)`. Any dict- or list-valued param crashes the Badger 1.5.4 GUI.

**Solution**: Structured parameters must be strings parsed by the environment.

**DON'T**:
```python
setpoints: dict[str, float] = {'qx': 9.65, 'qy': 9.74}  # GUI crashes!
```

**DO**:
```python
setpoints: str = '{qx: 9.65, qy: 9.74}'  # Parsed by _parse_setpoints()
```

See: `docs/log.md` line 92-111 for full history.

### 4. Inverted Bounds Bug for Negative Values

**Problem**: The old `±rel_range` calculation produced inverted bounds for negative knob values:
- `value = -10`, `rel_range = 0.1`
- `lo = -10 * 0.9 = -9`, `hi = -10 * 1.1 = -11`
- Result: `[-9, -11]` (wrong - should be `[-11, -9]`)

**Fix**: Always order low-to-high:
```python
def _bounds_around(self, value: float) -> list[float]:
    if value == 0.0:
        return [-self.zero_half_range, self.zero_half_range]
    lo = value * (1 - self.rel_range)
    hi = value * (1 + self.rel_range)
    return [min(lo, hi), max(lo, hi)]  # CRITICAL: swap for negatives
```

See: `plugins/environments/VirtualAccelerator_MADXSuite/__init__.py:218-225`

### 5. No `line.update()` Method

**Problem**: The old interface used `line.update(...)` which doesn't exist in xtrack.

**Fix**: Use `line.vars.update(...)` for variable knobs. Direct `setattr()` works for expression-free element attributes.

See: `plugins/interfaces/VirtualAccelerator_MADXSuiteInterface/__init__.py:167-212`

### 6. MAD-X BEAM Statement Requirement

**Problem**: `mad.use()` requires a beam to be defined. A bare lattice may not have one.

**Fix**: Call `mad.beam()` before `mad.use()` to ensure a beam exists:
```python
mad.beam()  # Keeps values from BEAM statement in lattice, or uses defaults
mad.use(sequence=matched)
```

See: `plugins/environments/VirtualAccelerator_MADXSuite/__init__.py:149-150`

---

## Development Patterns

### Adding a New Accelerator Configuration

1. Place the MAD-X lattice file in `sim_configs/<MachineName>/`
2. Add machine-specific settings to `sim_configs/<MachineName>/settings.yaml`
3. Create a template in `tuning_templates/` referencing the new lattice

### Testing Changes

```bash
# Run all tests
cd /Users/stjohn/Development/BayesOptimization_Xopt/FermiBadgerPlugins
conda activate FermiBadger_env
python tests/VA_plugin_smoke_test.py
python tests/VA_template_integration_test.py
python tests/VA_gui_param_editor_test.py
```

### Applying Pydantic Editor Patches

The `pydantic_editor.py` file is located in the conda environment at:
```
/Users/stjohn/miniconda3/envs/FermiBadger_env/lib/python3.12/site-packages/badger/gui/components/pydantic_editor.py
```

**Manual patch application** (recommended for conda environment):
```bash
cd /Users/stjohn/miniconda3/envs/FermiBadger_env/lib/python3.12/site-packages/badger/gui/components/

# Backup original file
cp pydantic_editor.py pydantic_editor.py.backup

# Apply the fixes manually (see patches/pydantic_editor-badger-1.6.0-fixes.patch):
# 1. Line ~376: Return None instead of "null" in _qt_widget_to_yaml_value()
# 2. Lines ~833-836: Set combo box to "null" before returning in initialize_special_field()
# 3. Lines ~1175-1179: Use self.vocs.model_dump() when vocs is not in parameters_dict
```

**Apply patch file** (if source is available):
```bash
cd /path/to/badger/source
patch -p1 < /Users/stjohn/Development/BayesOptimization_Xopt/FermiBadgerPlugins/patches/pydantic_editor-badger-1.6.0-fixes.patch
```

See `patches/README.md` for detailed documentation of each fix.

### Important Command Reference

| Command | Purpose |
|---------|---------|
| `badger -g --config_filepath config.yaml` | Launch GUI with repo config |
| `python -c "from plugins.environments.VirtualAccelerator_MADXSuite import Environment; print(len(Environment.variables), len(Environment.observables))"` | Quick sanity check |
| `grep -n "TODO\|FIXME\|XXX" plugins/` | Find pending work |

---

## Current State (as of 2026-08-28)

- **Phase 4.3 Complete**: GUI successfully loads template and optimization runs
- **Badger Version**: 1.6.0 with patches applied
- **Xopt Version**: 3.2.1
- **Repository**: `plugins/environments/VirtualAccelerator_MADXSuite/` and `plugins/interfaces/VirtualAccelerator_MADXSuiteInterface/`
- **Lattice**: Delivery Ring (mu2e-dr-model-v2026.03.23.madx)
- **Variables**: 2907 (quad knobs, element attrs)
- **Observables**: 262 (global optics, BPM reads, SETPOINT channels)

---

## Badger 1.6.0 Fixes and Gotchas

### Pydantic Editor Patches

The following patches have been applied to `pydantic_editor.py` in the FermiBadger_env conda environment:

**Fix 1: QComboBox "null" serialization** (`_qt_widget_to_yaml_value()` line ~376)
- When combo box shows "null", return `None` instead of `"null"` string
- This ensures YAML output is `null` (null value) instead of `"null"` (string)

**Fix 2: TurboController combo box initialization** (`initialize_special_field()` lines ~833-836)
- When `turbo_controller: null` is in defaults, set combo box to "null" before returning early
- This ensures the GUI correctly displays null as the selected value

**Fix 3: VOCs field not found** (`validate()` lines ~1175-1179)
- When vocs is not in parameters_dict, use `self.vocs.model_dump()` as the source
- This handles the case where VOCs is stored separately in `self.vocs`

### TurboController Gotchas

1. **turbo_controller: null**: When `turbo_controller` is explicitly set to `null`:
   - The combo box must show "null"
   - YAML must serialize to `"turbo_controller": null` (not `"turbo_controller": "null"`)
   - Validation errors appear if the string "null" is passed to Pydantic

2. **TurboController validation requires vocs**:
   - `failure_tolerance` and `success_tolerance` require vocs to be set first
   - OptimizeTurboController requires at least one objective in vocs
   - Empty vocs causes validation errors on startup

3. **Generator compatibility**:
   - Only Bayesian generators (`expected_improvement`, `upper_confidence_bound`) support turbo_controller
   - Other generators (e.g., `random`, `neldermead`) do not have this field

### VOCs Gotchas

1. **Structure in templates**: VOCs must be properly nested under `generator:`:
   ```yaml
   generator:
     name: expected_improvement
     turbo_controller: null
     vocs:
       constants: '{}'
       constraints: '{}'
       objectives: '{...}'
       observables: '{...}'
       variables: '{...}'
   ```

2. **VOCs storage separation**: Badger stores VOCs in `self.vocs` separately from the YAML tree. When validating, the vocs must be added from `self.vocs.model_dump()`.

### Template Gotchas

1. **Badger version**: Check the `badger_version` field in templates. Templates from different versions may have compatibility issues.

2. **Setpoints format**: Complex dictionaries (like setpoints) are serialized as strings:
   ```yaml
   params:
     setpoints: '{qx: 9.65, qy: 9.74}'
   ```
   The environment must parse this with `_parse_setpoints()`.

### Development Gotchas

1. **Patches are applied to conda environment**: The fixed `pydantic_editor.py` is at:
   ```
   /Users/stjohn/miniconda3/envs/FermiBadger_env/lib/python3.12/site-packages/badger/gui/components/pydantic_editor.py
   ```

2. **Patches should be maintained**: The `patches/pydantic_editor-badger-1.6.0-fixes.patch` file should be kept up-to-date for reproducibility.

3. **Testing requires GUI**: Some functionality can only be tested with the GUI running. Do not set sleep/timeout limits during testing.

---

## Environment Plugin Gotchas

### Badger Factory Bug - Params Overwriting

**Problem:** Badger's factory overwrites the `configs["params"]` from `configs.yaml` with the model schema defaults when loading an environment. This means that if a field has a `None` default in the model, it will overwrite the value from `configs.yaml`.

**Fix:** Use Pydantic's `Field(default='...')` to set proper defaults in the Environment class:

```python
from pydantic import Field

# WRONG - defaults to None, which overwrites configs.yaml
lattice_filename: str | None = None

# CORRECT - uses Field with proper default
lattice_filename: str = Field(default='sim_configs/DeliveryRing/mu2e-dr-model-v2026.03.23.madx')
```

**See also:** `plugins/environments/VirtualAccelerator_MADXSuite/__init__.py` for the fix.

---

## Related Documentation

- [progress.md](docs/progress.md) - Current phase status
- [log.md](docs/log.md) - Chronological session log
- [CLAUDE.md](CLAUDE.md) - Project overview
