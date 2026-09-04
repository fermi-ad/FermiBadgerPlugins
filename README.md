# FermiBadgerPlugins - Use Badger to run Xopt at Fermilab

This repository contains plugins and configuration for using [Badger](https://github.com/xopt-org/Badger) (the Bayesian optimization GUI frontend) with [Xopt](https://github.com/xopt-org/Xopt) at Fermilab. It includes:

- **VirtualAccelerator_MADXSuite** - A virtual accelerator environment that uses MAD-X lattice files with XSuite for rapid simulation
- **Tuning templates** - Pre-configured optimization setups for various accelerator configurations
- **Test script** - `test-quick-start.sh` to verify your installation

## Quick Start

### 1. Clone this repository

```bash
git clone git@github.com:fermi-ad/FermiBadgerPlugins.git
cd FermiBadgerPlugins
```

### 2. Set up the conda environment

**Prerequisite**: You must be on the FNAL private network (on-site or via VPN). The `acsys` package requires access to FNAL's internal pip repository.

```bash
# Create and activate the environment
conda env create -n FermiBadger_env -f environment.yml
conda activate FermiBadger_env
```

### 3. Apply patches for Badger 1.6.0

**A patch is required** to fix known issues in Badger 1.6.0 that affect template loading and the `turbo_controller: null` configuration.

**Patched file:** `badger/gui/components/pydantic_editor.py`

**Issues fixed:**
1. "Dict type must have subtypes" error when loading templates with dict/list environment params (e.g., `setpoints: {qx: 9.049, qy: 9.035}`)
2. `turbo_controller: null` handling - prevents warnings and ensures correct null serialization
3. YAML parsing of 'None' strings in flow maps (inline `{}` or `[]` syntax)
4. VOCs field not found when it's stored separately from generator parameters

#### Applying the patch

**Check if the patch is needed:**
1. Create a clean conda environment
2. Launch Badger with `badger -g -cf config.yaml`
3. Load the `DR_BetatronTunes_sim.yaml` template

**If you see "Dict type must have subtypes" error, apply the patch using one of the methods below:**

**Method 1: Using `patch` command (standard):**

```bash
# Navigate to your Badger installation
cd /path/to/conda/env/lib/python3.x/site-packages/badger/gui/components/

# Apply the patch
patch -p0 < /path/to/FermiBadgerPlugins/patches/pydantic_editor-badger-1.6.0-dict-subtypes.patch
```

**Method 2: Using `git apply` (if `patch` is not available):**

```bash
# Navigate to your Badger installation
cd /path/to/conda/env/lib/python3.x/site-packages/badger/gui/components/

# Apply the patch using git
git apply --directory=badger/gui/components /path/to/FermiBadgerPlugins/patches/pydantic_editor-badger-1.6.0-dict-subtypes.patch
```

**Method 3: Manual application (if neither tool is available):**

Edit `pydantic_editor.py` and apply these key changes:

1. **`set_params_from_dict` method** (around line 718) - Replace with:
   ```python
   def set_params_from_dict(self, params: dict[str, Any]) -> None:
       self.clear()
       # For dict and list types without subtypes, store as YAML strings.
       field_definitions: dict[str, tuple[type, FieldInfo]] = {}
       for k, v in params.items():
           if isinstance(v, dict):
               yaml_str = yaml.dump(v, default_flow_style=True).strip()
               field_definitions[k] = (str, Field(default=yaml_str))
           elif isinstance(v, list):
               if all(isinstance(item, str) for item in v):
                   field_definitions[k] = (list[str], Field())
               elif all(isinstance(item, (int, float)) for item in v):
                   field_definitions[k] = (list[float], Field())
               else:
                   field_definitions[k] = (list, Field())
           else:
               field_definitions[k] = (type(v), Field())
       # ... rest of method
   ```

2. **`initialize_special_field` method** (around line 815) - Fix `turbo_controller: null` handling
3. **YAML parsing fixes** - Add 'None' to 'null' replacement in `on_radio_changed`, `update_vocs`, and `validate` methods
4. **`_qt_widget_to_yaml_value` and `_qt_widget_to_value` functions** - Handle YAML dict strings

See [`patches/README.md`](patches/README.md) for the complete patch content.

See [`patches/README.md`](patches/README.md) for detailed documentation of each fix.

### 4. Configure Badger

Edit the `config.yaml` file to set the `*_ROOT` directories:

- `BADGER_ARCHIVE_ROOT` and `BADGER_LOGBOOK_ROOT` - Location for data and logs (can be the same)
- `BADGER_PLUGIN_ROOT` - Set to the `plugins` directory of this repo
- `BADGER_TEMPLATE_ROOT` - Set to the `tuning_templates` directory of this repo

### 5. Launch the Badger GUI

```bash
badger -g -cf config.yaml
```

### 6. Verify your installation (optional)

Run the test script to verify everything is set up correctly:

```bash
./test-quick-start.sh
```

This script:
- Clones a fresh copy of the repository to `/tmp/FermiBadger_envTEST`
- Creates a new conda environment named `FermiBadger_envTEST`
- Installs the plugin and verifies it's discoverable by Badger

**Note:** The test uses a separate environment (`FermiBadger_envTEST`) to avoid conflicts with your main `FermiBadger_env`.

**Important:** The test environment uses a clean conda installation of Badger 1.6.0. If you encounter a "Dict type must have subtypes" error when loading templates in the test environment, apply the patch:

```bash
cd /Users/stjohn/miniconda3/envs/FermiBadger_envTEST/lib/python3.12/site-packages
patch -p0 < /path/to/FermiBadgerPlugins/patches/pydantic_editor-badger-1.6.0-fixes.patch
```

See `patches/pydantic_editor-badger-1.6.0-fixes.patch` for the full fix documentation.

---

## Environment Setup Details

### Conda Environment (`environment.yml`)

The `environment.yml` file defines the complete `FermiBadger_env` environment with:

- **Python**: 3.12.1
- **Badger**: 1.6.0
- **Xopt**: 3.2.1 (required for Badger 1.6.0 compatibility)
- **XSuite packages**: xtrack, xobjects, xfields, xcoll, xsuite
- **FNAL packages**: acsys, cpymad (requires FNAL network)

### Why Patches Are Required

The patches fix issues in Badger that affect the VirtualAccelerator plugins:

**For Badger 1.6.0:**
1. **turbo_controller null handling** - Prevents warnings when `turbo_controller: null` is set and ensures correct serialization to YAML null
2. **vocs field not found** - Fixes error when VOCs data is stored separately from generator parameters
3. **Startup validation errors** - Fixes validation errors on Badger startup when generator combo box is changed
4. **Environment config params** - Fixes issue where Badger factory overwrites `configs.yaml` params with model schema defaults

**For Badger 1.5.4 (deprecated):**
1. **turbo_controller null handling** - Prevents warnings when `turbo_controller: null` is set
2. **turbo_controller string values** - Fixes TypeError when turbo_controller is specified as a string

**Applies to:**
- `badger/gui/components/pydantic_editor.py` - Fixes 1-3
- `plugins/environments/VirtualAccelerator_MADXSuite/__init__.py` - Fix 4 (Environment field defaults)

See `patches/README.md` for detailed documentation of each fix.

---

## First-Time GUI Setup

When you first launch Badger:

1. **UNCHECK the "Automatic VARIABLES CHECKBOX"** - There is a known bug that requires this
2. **Load a tuning template** - Use `File > Open Template` and select one from `tuning_templates/`.  The relevant Environment loads along with preset parameter and algorithm values. 
   - `TuneQx.yaml` - Quick-start example (simulation; fictional storage ring)
   - `DR_BetatronTunes_sim.yaml` - Delivery ring tune optimization (simulation of Delivery Ring)
   - Templates for physical-system tuning require valid kerberos credentials AND settings role combination.

---

## Using the VirtualAccelerator_MADXSuite Environment Plugin

The VirtualAccelerator_MADXSuite environment:

1. Loads a MAD-X lattice file (specified by `lattice_filename` parameter)
2. Automatically deduces variables (knobs, element attributes) and observables (optics, BPM reads) from element names
3. Uses XSuite for fast re-simulation when variables are changed
4. Supports MAD-X deferred expressions that are re-evaluated on each iteration

### Lattice Files

Lattice files are stored in `sim_configs/`. 

### Configuration Parameters

This simulation-tuning environment accepts these parameters in its tuning templates:

| Parameter | Description |
|-----------|-------------|
| `lattice_filename` | Path to MAD-X lattice file (relative to repo root) |
| `sequence_name` | MAD-X sequence name to use |
| `sequence_name_matched` | Matched sequence name for tuning |
| `rel_range` | Range for auto-deducing variable bounds (default: 0.1) |
| `zero_half_range` | Half-range for zero-valued variables (default: 0.1) |

---

## Troubleshooting

###FNAL Network Required

The `acsys` package is hosted on FNAL's internal pip repository (`https://www-bd.fnal.gov/pip3`). You must be on the FNAL network (on-site or VPN) to install it.

**Error if off-network**:
```
ERROR: Could not find a version that satisfies the requirement acsys
```

### libGL.so.1 Missing

On headless systems or some Docker configurations, Badger may fail with:
```
ImportError: libGL.so.1: cannot open shared object file
```

**Fix**:
```bash
conda install -c conda-forge mesa-libgl-cos7-x86_64
# or on Ubuntu/Debian:
sudo apt-get install libgl1-mesa-glx
```

### OMP_NUM_THREADS on EAF

When running on the EAF (Experimental Accelerator Facility), set:
```bash
export OMP_NUM_THREADS=8
```
to prevent slow performance from thread contention.

### Environment Not Found

If `conda activate FermiBadger_env` fails:
```bash
conda env list  # Verify the environment exists
conda create -n FermiBadger_env -f environment.yml  # Recreate if missing
```

### Dict type must have subtypes Error

When loading a template (e.g., `DR_BetatronTunes_sim.yaml`), you may see:
```
ValueError: Dict type must have subtypes
```

**Cause:** Badger 1.6.0 has a bug where dict/list environment parameters without type subtypes cause this error.

**Fix:** Apply the patch from `patches/pydantic_editor-badger-1.6.0-dict-subtypes.patch`:

**Using `patch` command:**
```bash
cd /path/to/conda/env/lib/python3.x/site-packages/badger/gui/components/
patch -p0 < /path/to/FermiBadgerPlugins/patches/pydantic_editor-badger-1.6.0-dict-subtypes.patch
```

**Using `git apply` (if `patch` is not available):**
```bash
cd /path/to/conda/env/lib/python3.x/site-packages/badger/gui/components/
git apply --directory=badger/gui/components /path/to/FermiBadgerPlugins/patches/pydantic_editor-badger-1.6.0-dict-subtypes.patch
```

See the [Quick Start guide](#3-apply-patches-for-badger-160) for more details.

---

## Repository Structure

```
FermiBadgerPlugins/
├── patches/                    # Badger bug fixes
│   ├── pydantic_editor-badger-1.6.0-dict-subtypes.patch
│   └── README.md
├── test-quick-start.sh         # Quick Start verification script
├── plugins/
│   ├── environments/           # Badger Environment plugins
│   │   └── VirtualAccelerator_MADXSuite/
│   └── interfaces/             # Badger Interface plugins
│       └── VirtualAccelerator_MADXSuiteInterface/
├── tuning_templates/           # Pre-configured optimization setups
│   ├── VirtualAccelerator_MADXSuite_example.yaml
│   └── DR_BetatronTunes_Sim_MADXSuite.yaml
├── sim_configs/                # MAD-X lattice files and settings
│   └── DeliveryRing/
├── docs/                       # Development documentation
│   ├── progress.md
│   └── log.md
├── config.yaml                 # Badger configuration
├── environment.yml             # Conda environment definition
└── CLAUDE.md                   # Project context and session history
```

---

## Related Documentation

- [CLAUDE.md](CLAUDE.md) - Project overview and standards
- [HANDOFF.md](HANDOFF.md) - Developer handoff guide with critical gotchas
- [docs/progress.md](docs/progress.md) - Current development status
- [docs/log.md](docs/log.md) - Session history
