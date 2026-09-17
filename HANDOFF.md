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

## Current State (as of 2026-09-08)

- **Phase 4.3 Complete**: GUI successfully loads template and optimization runs
- **Badger Version**: 1.6.0 with patches applied
- **Xopt Version**: 3.2.1
- **Repository**: `plugins/environments/VirtualAccelerator_MADXSuite/` and `plugins/interfaces/VirtualAccelerator_MADXSuiteInterface/`
- **Lattice**: Delivery Ring (mu2e-dr-model-v2026.03.23.madx)
- **Variables**: 2907 (quad knobs, element attrs)
- **Observables**: 262 (global optics, BPM reads, SETPOINT channels)

### Recent Fixes (2026-09-08)

**PydanticSerializationUnexpectedValue warning for _initial_state**
- Fixed by declaring `_initial_state_value` as a `PrivateAttr` in TurboController
- This prevents pydantic v2 from emitting warnings when serializing the controller
- See `memory/pydantic-turbo-controller-initial-state.md` for full details

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

### TurboController Pydantic Serialization Gotcha

**Problem**: When using the TurboController, pydantic emitted `PydanticSerializationUnexpectedValue` warnings:
```
PydanticSerializationUnexpectedValue(Unexpected field `_initial_state_value`: Expected `OptimizeTurboController`)
```

**Root Cause**: The `_initial_state` attribute was set in `__init__` as a plain attribute (not declared as a pydantic field). Pydantic v2's internal serializer found this extra attribute and emitted warnings.

**Fix**: Declare `_initial_state_value` as a `PrivateAttr`:
```python
class TurboController(XoptBaseModel, ABC):
    _failure_counter: int = PrivateAttr(0)
    _success_counter: int = PrivateAttr(0)
    _initial_state_value: dict[str, Any] = PrivateAttr()  # <-- Declare as PrivateAttr
```

Use a property for the public API:
```python
@property
def _initial_state(self) -> dict[str, Any]:
    """Property to access the initial state."""
    return self._initial_state_value

@_initial_state.setter
def _initial_state(self, value: dict[str, Any]) -> None:
    self._initial_state_value = value
```

**Why this works**: In pydantic v2, `PrivateAttr()` tells pydantic that an attribute is internal and should not be serialized. This prevents the `PydanticSerializationUnexpectedValue` warnings.

**See also**: `memory/pydantic-turbo-controller-initial-state.md` for full details.

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

## BasicAcsysInterface / Physical-Hardware Templates (RIL_tuning, LinacQuadTuning, etc.)

Environments backed by real Fermilab ACNET/DPM hardware (`RIL_tuning`,
`LinacQuadTuning`, and any future environment listing `BasicAcsysInterface`
in its `configs.yaml`) have their own gotchas, distinct from the
`VirtualAccelerator_MADXSuite` simulation plugin most of this doc covers.

### CLI gotcha: template path is relative to `BADGER_TEMPLATE_ROOT`

```bash
badger -mini -cf config.yaml -t RIL_tuning_trims_and_sol_LEBT_MEBTquads.yaml
```

`-t` takes a **bare filename**, resolved against `BADGER_TEMPLATE_ROOT`
(the `tuning_templates/` dir per `config.yaml`) — **not** a path into the
repo. Passing a full/relative repo path here fails to find the template.

### Auto-ranging: `relative_to_current` / `vrange_limit_options`

Setting a template's top-level `relative_to_current: true` pre-checks
"Automatic" in the full GUI (and is what `-mini`'s equivalent switch keys
off of): variable ranges get recomputed from live current values every
load/refresh instead of going stale in the YAML. Per-variable behavior is
controlled by `vrange_limit_options: {<var>: {limit_option_idx, ratio_curr,
ratio_full, delta}}`:

- `limit_option_idx: 0` ("ratio with current value", multiplicative) —
  **has a real bug**: collapses to `[0.0, 0.0]` whenever the live value is
  exactly `0.0` (`np.sign(0.0) == 0.0` zeroes the whole delta). Avoid.
- `limit_option_idx: 1` ("ratio with full range") — additive, safe at any
  current value. `ratio_full` is a fraction of the *hard* bound width.
- `limit_option_idx: 2` ("delta around current value") — additive, safe;
  `delta` is an **absolute half-width in the variable's own units**. This
  is the mechanism to reach for when a per-variable absolute half-width is
  wanted, rather than any ratio — it already exists, no code changes needed.
- **Trap**: any variable *missing* from `vrange_limit_options` silently
  falls back to the GUI's hardcoded default, which is `limit_option_idx: 0`
  — the unsafe one. Always give every declared variable an explicit entry.

All 9 physical templates in `tuning_templates/` currently use
`relative_to_current: true` with idx 1 (or idx 2 where a per-variable
absolute half-width made more sense), and none are on idx 0. See
`memory/auto-ranging-physical-templates.md` for the full audit and per-file
rationale.

### DPM hang on an empty device list

`plugins/scanner.py`'s `read_once()`/`set_once()` open an ACNET DPM session
and wait for replies. If called with an **empty** device list — which
happens routinely, e.g. Badger's full GUI calling
`select_env() → set_vrange() → update_init_table() → fill_curr_in_init_table()`
right after an environment is (re)selected but before any variables are
checked into the routine yet — a DPM session with zero registered entries
never gets a reply, so the code would hang forever waiting for one. Both
functions now guard on `if not drf_list: return` (`[]`/`None`) before ever
opening a session. This is generic to any `BasicAcsysInterface` environment,
not specific to one plugin — don't remove the guard when touching this file.
See `memory/RIL_tuning-live-bounds-and-dpm-hang.md` for the related fix
(moving `dpm.start()` outside the per-device loop — a *different*, earlier
DPM hang in the same file) and `memory/auto-ranging-physical-templates.md`
for this one.

### Template-authoring gotcha: declared `vocs.variables` bounds must bracket the live value

Badger validates that a variable's current live value falls inside its
declared `vocs.variables` bounds at load time (`VariableRangeError`/
pydantic `value[1] > value[0]`). A one-sided declared range (e.g.
`[0.0, 2.0]` for a trim that can read negative) will fail to load the
moment the live value goes negative, or block `add_rand_in_init_table()`'s
clipped sampling from ever producing a valid initial point. When adding a
new physical template, check whether a sibling template already has a
correctly two-sided range for the same device (e.g. `L:ATRMVU`'s `[-4, 1]`
in the RIL_tuning templates) and mirror it, rather than leaving a stale
one-sided range from an earlier, differently-signed operating point.

## `BasicPacsysInterface` (pacsys port of `BasicAcsysInterface`)

`plugins/interfaces/BasicPacsysInterface/` is a new interface plugin with
the same feature set as `BasicAcsysInterface` above, but built on
[pacsys](https://github.com/fermi-ad/pacsys) instead of
`acsys`/`plugins/scanner.py`. `BasicAcsysInterface` is untouched; no
environment currently points its `configs.yaml` `interface:` at the new one
— it exists alongside the old one, not yet load-bearing.

**Key difference from `BasicAcsysInterface`**: pacsys is natively
synchronous, so there's no `scanner.py` equivalent — `pacsys.get_many()` /
`write_many()` / `dpm(auth=, role=)` replace the whole
asyncio/`DPMContext`/timeout-guard layer directly.

**Not yet done**: a live, Kerberos-authenticated write against a real DPM
role (e.g. `ril_tuning_fake`, `linac_quads`) — only verified offline against
`pacsys.testing.FakeBackend` so far (no controls-network access from the
environment that wrote this). Do that live test before switching any
environment's `interface:` over to it.

See `memory/basic-pacsys-interface-port.md` for the full API mapping and two
latent bugs in `BasicAcsysInterface` that were found (and fixed, in the new
interface only) while porting: a `sample_events={}` default that `KeyError`s
on the common no-sample-events read path, and a missing `self.` in the
settle-to-tolerance loop that's currently masked by a second, canceling bug.

## Related Documentation

- [progress.md](docs/progress.md) - Current phase status
- [log.md](docs/log.md) - Chronological session log
- [CLAUDE.md](CLAUDE.md) - Project overview
- [memory/RIL_tuning-live-bounds-and-dpm-hang.md](memory/RIL_tuning-live-bounds-and-dpm-hang.md) - turbo_controller/bounds/DPM-hang fixes for RIL_tuning physical templates
- [memory/auto-ranging-physical-templates.md](memory/auto-ranging-physical-templates.md) - relative_to_current rollout, vrange_limit_options modes, zero-current edge case, empty-device-list DPM hang
- [memory/basic-pacsys-interface-port.md](memory/basic-pacsys-interface-port.md) - BasicAcsysInterface ported to pacsys as BasicPacsysInterface; API mapping, bugs found, verification status
