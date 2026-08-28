# HANDOFF: VirtualAccelerator_MADXSuite Plugin Development

## Quick Start for New Developers

### Getting Started

1. **Set up your environment**:
   ```bash
   conda activate Badger_154_VirtAcc
   cd /Users/stjohn/Development/BayesOptimization_Xopt/Badger_154_VirtAcc
   ```

2. **Launch the GUI** (with repo-specific config):
   ```bash
   badger -g --config_filepath config.yaml
   ```

3. **Load a template**:
   - Open `tuning_templates/VirtualAccelerator_MADXSuite_example.yaml`
   - The lattice file path is relative to the repo root

### Key Files to Understand

| File | Purpose |
|------|---------|
| `plugins/environments/VirtualAccelerator_MADXSuite/__init__.py` | Environment plugin - loads MAD-X lattice, deduces vars/observables |
| `plugins/interfaces/VirtualAccelerator_MADXSuiteInterface/__init__.py` | Interface plugin - translates channel names to xtrack operations |
| `tuning_templates/VirtualAccelerator_MADXSuite_example.yaml` | Working example template |
| `sim_configs/DeliveryRing/` | Lattice files for different accelerator configurations |

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
cd /Users/stjohn/Development/BayesOptimization_Xopt/BayesOptimization_Xopt/FermiBadgerPlugins
conda activate FermiBadger_env
python tests/VA_plugin_smoke_test.py
python tests/VA_template_integration_test.py
python tests/VA_gui_param_editor_test.py
```

### Important Command Reference

| Command | Purpose |
|---------|---------|
| `badger -g --config_filepath config.yaml` | Launch GUI with repo config |
| `python -c "from plugins.environments.VirtualAccelerator_MADXSuite import Environment; print(len(Environment.variables), len(Environment.observables))"` | Quick sanity check |
| `grep -n "TODO\|FIXME\|XXX" plugins/` | Find pending work |

---

## Current State (as of 2026-08-14)

- **Phase 4.3 Complete**: GUI successfully loads template and optimization runs
- **Repository**: `plugins/environments/VirtualAccelerator_MADXSuite/` and `plugins/interfaces/VirtualAccelerator_MADXSuiteInterface/`
- **Lattice**: Delivery Ring (mu2e-dr-model-v2026.03.23.madx)
- **Variables**: 2907 (quad knobs, element attrs)
- **Observables**: 262 (global optics, BPM reads, SETPOINT channels)

---

## Related Documentation

- [progress.md](docs/progress.md) - Current phase status
- [log.md](docs/log.md) - Chronological session log
- [CLAUDE.md](CLAUDE.md) - Project overview
