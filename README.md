# FermiBadgerPlugins - Use Badger to run Xopt at Fermilab

This repository contains plugins and configuration for using [Badger](https://github.com/xopt-org/Badger) (the Bayesian optimization GUI frontend) with [Xopt](https://github.com/xopt-org/Xopt) at Fermilab. It includes:

- **99_Sim_VirtualAccelerator_MADXSuite** - A virtual accelerator environment that uses MAD-X lattice files with XSuite for rapid simulation
- **Tuning templates** - Pre-configured optimization setups for various accelerator configurations
- **Test script** - `test-quick-start.sh` to verify your installation

## Quick Start

### 1. Clone this repository

```bash
git clone git@github.com:fermi-ad/FermiBadgerPlugins.git
cd FermiBadgerPlugins
```

### 2. Run the setup script

**Prerequisite**: You must be on the FNAL private network (on-site or via VPN). The `acsys` package requires access to FNAL's internal pip repository.

```bash
./setup.sh
```

This does everything in steps 3 and 4 below:

1. Creates the `FermiBadger_env` conda environment from `environment.yml`. If an environment of that name already exists, it asks whether to remove and recreate it, use a different name, or keep it as-is.
2. Applies the Badger patches to that environment.
3. Writes `config.local.yaml` with this clone's paths — it works no matter where you cloned the repo, `/tmp` included. Your archive and logbook directories default to `~/BadgerArchive` and `~/BadgerLogs`; press Enter to accept or type your own.
4. Verifies that Badger can discover the plugins.

It is safe to re-run: patches already applied are detected and skipped.

```bash
./setup.sh --help          # options
./setup.sh --yes           # take every default, no prompts
./setup.sh --env-name foo  # different environment name
./setup.sh --skip-env      # patches and config only
```

Then launch:

```bash
conda activate FermiBadger_env
badger -g -cf config.local.yaml
```

`config.local.yaml` is gitignored, so the tracked `config.yaml` stays a clean template and `git pull` never conflicts with your local paths.

Steps 3 and 4 below document what the script does, for anyone who needs to do it by hand.

### 3. Apply patches for Badger 1.6.0 (done by `setup.sh`)

**A patch is required** to fix known issues in Badger 1.6.0 that affect template loading and the `turbo_controller: null` configuration.

**Patched file:** `badger/gui/components/pydantic_editor.py`

**Issues fixed:**
1. "Dict type must have subtypes" error when loading templates with dict/list environment params (e.g., `setpoints: {qx: 9.049, qy: 9.035}`)
2. `turbo_controller: null` handling - prevents warnings and ensures correct null serialization
3. YAML parsing of 'None' strings in flow maps (inline `{}` or `[]` syntax)
4. VOCs field not found when it's stored separately from generator parameters

#### Finding your Badger installation

First, locate your Badger installation in your conda environment. Run this command (substitute your environment name):

```bash
# Replace FermiBadger_env with your environment name
conda run -n FermiBadger_env python -c "import badger; import os; print(os.path.dirname(badger.__file__))"
```

The output will be a path like:
```
/Users/yourname/miniconda3/envs/FermiBadger_env/lib/python3.12/site-packages/badger
```

Navigate to the `gui/components` directory within that path to apply the patch.

#### Applying the patch

**Check if the patch is needed:**
1. Launch Badger with `badger -g -cf config.yaml`
2. Load the `99_Sim_DR_BetatronTunes_sim_VirtualAccelerator_MADXSuite.yaml` template
3. If you see "Dict type must have subtypes" error, apply the patch

**Method 1: Using `patch` command (standard):**

```bash
BADGER_PATH=$(conda run -n FermiBadger_env python -c "import badger; import os; print(os.path.dirname(badger.__file__))")
FERMIBADGERPLUGINS_PATH=`pwd`
cd "$BADGER_PATH/gui/components"
patch -p1 < "$FERMIBADGERPLUGINS_PATH/patches/pydantic_editor-badger-1.6.0-dict-subtypes.patch"
```

The `-mini` patches carry `a/badger/...` paths instead, so they apply from
`site-packages` with `-p1`:

```bash
SITE_PACKAGES=$(conda run -n FermiBadger_env python -c "import sysconfig; print(sysconfig.get_paths()['purelib'])")
cd "$SITE_PACKAGES"
patch -p1 < "$FERMIBADGERPLUGINS_PATH/patches/badger-mini-config.patch"
patch -p1 < "$FERMIBADGERPLUGINS_PATH/patches/badger-mini-var-table-env-configs.patch"
```

**Method 2: Using `git apply` (if `patch` is not available):**

```bash
BADGER_PATH=$(conda run -n FermiBadger_env python -c "import badger; import os; print(os.path.dirname(badger.__file__))")
cd "$BADGER_PATH/gui/components"
git apply "$FERMIBADGERPLUGINS_PATH/patches/pydantic_editor-badger-1.6.0-dict-subtypes.patch"
```

**Note:** Replace `FermiBadger_env` with your actual conda environment name. Replace `/path/to/FermiBadgerPlugins` with the actual path where you cloned the repository.

For detailed documentation of each fix, see [`patches/README.md`](patches/README.md).

### 4. Configure Badger (done by `setup.sh`)

Copy `config.yaml` to `config.local.yaml` (which is gitignored) and set the `*_ROOT` directories to absolute paths:

- `BADGER_PLUGIN_ROOT` - the `plugins` directory of this repo
- `BADGER_TEMPLATE_ROOT` - the `tuning_templates` directory of this repo
- `BADGER_LOG_DIRECTORY` - the `logs` directory of this repo
- `BADGER_ARCHIVE_ROOT` and `BADGER_LOGBOOK_ROOT` - where run data and logs go (can be the same, and need not be inside the repo)

Create each of those directories if it does not exist.

### 5. Launch the Badger GUI

```bash
badger -g -cf config.local.yaml
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

See [`patches/README.md`](patches/README.md) for detailed documentation of each fix.

---

## First-Time GUI Setup

When you first launch Badger:

1. **UNCHECK the "Automatic VARIABLES CHECKBOX"** - There is a known bug that requires this
2. **Load a tuning template** - Use `File > Open Template` and select one from `tuning_templates/`.  The relevant Environment loads along with preset parameter and algorithm values. 
   - `99_Sim_TuneQx_SimpleVirtualAccelerator.yaml` - Quick-start example (simulation; fictional storage ring)
   - `99_Sim_DR_BetatronTunes_sim_VirtualAccelerator_MADXSuite.yaml` - Delivery ring tune optimization (simulation of Delivery Ring)
   - Templates for physical-system tuning require valid kerberos credentials AND settings role combination.

---

## Using the 99_Sim_VirtualAccelerator_MADXSuite Environment Plugin

The 99_Sim_VirtualAccelerator_MADXSuite environment:

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

### FNAL Network Required

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

When loading a template (e.g., `99_Sim_DR_BetatronTunes_sim_VirtualAccelerator_MADXSuite.yaml`), you may see:
```
ValueError: Dict type must have subtypes
```

**Cause:** Badger 1.6.0 has a bug where dict/list environment parameters without type subtypes cause this error.

**Fix:** Apply the patch from `patches/pydantic_editor-badger-1.6.0-dict-subtypes.patch`.

See [`patches/README.md`](patches/README.md) for patch instructions.

---

## Repository Structure

```
FermiBadgerPlugins/
├── patches/                    # Badger bug fixes
│   ├── pydantic_editor-badger-1.6.0-dict-subtypes.patch
│   └── README.md
├── test-quick-start.sh         # Quick Start verification script
├── plugins/
│   ├── environments/           # Badger Environment plugins (see naming convention below)
│   │   ├── 01_Linac_RIL_tuning_Acsys/
│   │   ├── 09_DeliveryRing_Muon_PID_tune_Acsys/
│   │   ├── 99_Sim_VirtualAccelerator_MADXSuite/
│   │   └── ...
│   └── interfaces/             # Badger Interface plugins
│       └── VirtualAccelerator_MADXSuiteInterface/
├── tuning_templates/           # Pre-configured optimization setups (see naming convention below)
│   ├── 99_Sim_Xfer400MeV_example_VirtualAccelerator_MADXSuite.yaml
│   └── 99_Sim_DR_BetatronTunes_sim_VirtualAccelerator_MADXSuite.yaml
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

## For Developers

### Environment and template naming convention

`plugins/environments/*` folders and `tuning_templates/*.yaml` files are named so they alpha-sort in the Badger GUI's picker in physical beam order, not plain alphabetical order:

```
<region>_<Descriptive>[_Acsys|_Pacsys]
```

`<region>` is a zero-padded two-digit code, chosen so digit-first names sort ahead of any unprefixed legacy name and leave room to insert new regions later without renumbering:

| Code | Region |
|------|--------|
| `01` | Linac |
| `02` | Xfer400MeV |
| `03` | Booster |
| `04` | BoosterNuStub |
| `05` | Xfer8GeV |
| `06` | MIRR (Main Injector/Recycler Ring) |
| `07` | NuMIStub |
| `08` | P1toDR (the P1+P2+M1+M2/3 extraction line to the Delivery Ring) |
| `09` | DeliveryRing |
| `10` | MuonCampus |
| `99` | Sim (simulation environments — always sorts last, regardless of how many real regions exist) |

Every real-machine environment (backed by an actual control-system interface, not a simulation) carries an explicit `_Acsys` or `_Pacsys` suffix naming which control system it talks to — even when only one variant currently exists, so the interface choice stays visible to the next developer ahead of the day a second variant needs picking. Drop any part of the descriptive name that would otherwise just repeat the region name (e.g. `LinacQuadTuning` under `01_Linac` becomes `01_Linac_QuadTuning_Acsys`, not `01_Linac_LinacQuadTuning_Acsys`).

A tuning template's filename follows its own token order, `<region>_<tuning_task>_<env_plugin>[_Acsys|_Pacsys]`, so templates still group and sort by region the same way the environment picker does, while leading with the descriptive part instead of repeating the full environment name up front:

```
01_Linac_trims_and_sol_RIL_tuning_Acsys.yaml
```

Here `01_Linac` is the region code, `trims_and_sol` is the tuning task, `RIL_tuning` is the `env_plugin` (the parent environment's own name, with its region prefix and interface suffix stripped — i.e. `01_Linac_RIL_tuning_Acsys` minus `01_Linac_` and `_Acsys`), and `Acsys` is the interface suffix. Simulation templates omit the interface suffix, since their parent sim environments don't carry one either, e.g. `99_Sim_TuneQx_SimpleVirtualAccelerator.yaml`.

When a region assignment is ambiguous — an environment that varies a parameter in one region but reads a diagnostic from another — ask before guessing; Fermilab device-prefix meanings require domain knowledge.

**Gotcha:** `badger.factory.load_plugin` loads environment modules via `importlib.import_module(f"environments.{name}")`, which works fine with digit-leading folder names. But a literal `from environments.01_Linac_RIL_tuning_Acsys import X` is a `SyntaxError` — any ad hoc script or test that needs to import a renamed environment module directly must use `importlib.import_module(...)` instead (see `tests/VA_deferred_expressions_test.py` and `tests/VA_plugin_smoke_test.py` for the pattern).

---

## Related Documentation

- [CLAUDE.md](CLAUDE.md) - Project overview and standards
- [HANDOFF.md](HANDOFF.md) - Developer handoff guide with critical gotchas
- [docs/progress.md](docs/progress.md) - Current development status
- [docs/log.md](docs/log.md) - Session history
