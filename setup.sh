#!/bin/bash
# One-command setup for a fresh clone of FermiBadgerPlugins:
#   1. create (or reuse) the conda environment from environment.yml
#   2. apply the Badger patches this plugin set needs
#   3. write config.local.yaml with this clone's paths
#   4. check that Badger can actually see the plugins
#
# Safe to re-run: patches already applied are detected and skipped.
#
#   ./setup.sh                          interactive, defaults shown
#   ./setup.sh --yes                    take every default, never prompt
#   ./setup.sh --env-name my_env        use a different environment name
#   ./setup.sh --skip-env               patches + config only
set -euo pipefail

# Where the repo is, regardless of where this was invoked from -- the whole
# point of the script, so never use $PWD.
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ASSUME_YES=0
SKIP_ENV=0
ENV_NAME=""
FAILED=0

usage() {
    sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --yes|-y)   ASSUME_YES=1; shift ;;
        --skip-env) SKIP_ENV=1; shift ;;
        --env-name) ENV_NAME="${2:-}"; shift 2 ;;
        --help|-h)  usage ;;
        *) echo "Unknown option: $1 (try --help)" >&2; exit 2 ;;
    esac
done

# Prompting is pointless without a terminal (CI, pipes), so fall back to
# defaults there just as --yes does.
[[ -t 0 ]] || ASSUME_YES=1

# ask <prompt> <default> -- echoes the answer
ask() {
    local prompt="$1" default="$2" reply
    if [[ $ASSUME_YES -eq 1 ]]; then
        echo "$default"
        return
    fi
    read -r -p "$prompt [$default]: " reply </dev/tty
    echo "${reply:-$default}"
}

echo "=========================================="
echo "FermiBadgerPlugins setup"
echo "  repo: $REPO"
echo "=========================================="

# --------------------------------------------------------------------------
# 1. Conda environment
# --------------------------------------------------------------------------
if ! command -v conda >/dev/null 2>&1; then
    echo "ERROR: conda not found on PATH." >&2
    echo "Install Miniconda first: https://docs.conda.io/en/latest/miniconda.html" >&2
    exit 1
fi

CONDA_BASE="$(conda info --base)"
# The 'conda' shell function is not defined in a non-interactive shell, so
# 'conda activate' fails unless we source this first.
# shellcheck disable=SC1091
source "$CONDA_BASE/etc/profile.d/conda.sh"

if [[ -z "$ENV_NAME" ]]; then
    ENV_NAME="$(awk '/^name:/ {print $2; exit}' "$REPO/environment.yml")"
fi

env_exists() { conda env list | awk '{print $1}' | grep -qx "$1"; }

if [[ $SKIP_ENV -eq 1 ]]; then
    echo
    echo "1. Conda environment: skipped (--skip-env), using '$ENV_NAME'"
    env_exists "$ENV_NAME" || { echo "ERROR: '$ENV_NAME' does not exist." >&2; exit 1; }
else
    echo
    echo "1. Conda environment: $ENV_NAME"

    while env_exists "$ENV_NAME"; do
        echo "   Environment '$ENV_NAME' already exists."
        if [[ $ASSUME_YES -eq 1 ]]; then
            # Never delete an environment unattended.
            choice=k
        else
            echo "     [r] remove and recreate"
            echo "     [n] use a different name"
            echo "     [k] keep it as-is, just patch and configure"
            choice="$(ask "   Choice" k)"
        fi
        case "$choice" in
            r) echo "   Removing '$ENV_NAME'..."
               conda env remove -n "$ENV_NAME" --yes >/dev/null
               ;;
            n) ENV_NAME="$(ask '   New environment name' "${ENV_NAME}_2")" ;;
            *) echo "   Keeping '$ENV_NAME' as-is."
               SKIP_ENV=1
               break
               ;;
        esac
    done

    if [[ $SKIP_ENV -eq 0 ]]; then
        echo "   Creating '$ENV_NAME' (this takes several minutes)..."
        if ! conda env create -n "$ENV_NAME" -f "$REPO/environment.yml" --yes; then
            echo >&2
            echo "ERROR: environment creation failed." >&2
            echo "If the failure mentions 'acsys': that package lives on FNAL's" >&2
            echo "internal pip repository, so you must be on the FNAL network" >&2
            echo "(on-site or VPN) to install it." >&2
            exit 1
        fi
        echo "   OK: environment created"
    fi
fi

conda activate "$ENV_NAME"
PY="$(command -v python)"
echo "   python: $PY"

# --------------------------------------------------------------------------
# 2. Patches
# --------------------------------------------------------------------------
echo
echo "2. Badger patches"

SP="$("$PY" -c "import sysconfig; print(sysconfig.get_paths()['purelib'])")"
echo "   site-packages: $SP"

# apply_patch <dir-to-apply-from> <strip-level> <patch-file>
# The patches were generated against different roots, so each carries its own
# directory and strip level rather than sharing one recipe.
# --force keeps patch from prompting ("Assume -R? [y]") and hanging a --yes run.
apply_patch() {
    local dir="$1" strip="$2" file="$3" name
    name="$(basename "$file")"

    if [[ ! -d "$dir" ]]; then
        echo "   FAILED  $name (no such directory: $dir)"
        FAILED=1
        return
    fi

    if patch -d "$dir" -p"$strip" -R --dry-run --force < "$file" >/dev/null 2>&1; then
        echo "   skipped $name (already applied)"
    elif patch -d "$dir" -p"$strip" --dry-run --force < "$file" >/dev/null 2>&1; then
        patch -d "$dir" -p"$strip" --force < "$file" >/dev/null
        echo "   applied $name"
    else
        echo "   FAILED  $name"
        FAILED=1
    fi
}

apply_patch "$SP/badger/gui/components" 1 \
    "$REPO/patches/pydantic_editor-badger-1.6.0-dict-subtypes.patch"
apply_patch "$SP" 1 "$REPO/patches/badger-mini-config.patch"
apply_patch "$SP" 1 "$REPO/patches/badger-mini-var-table-env-configs.patch"

# ponytail: xopt-pydantic-serialization-fix.patch is deliberately not applied.
# Its context lines assume hand-edits that are not in a pristine xopt 3.2.1, so
# it cannot apply to a fresh install.  See patches/README.md.
echo "   skipped xopt-pydantic-serialization-fix.patch (does not apply to a"
echo "           pristine xopt 3.2.1 -- see patches/README.md)"

# --------------------------------------------------------------------------
# 3. config.local.yaml
# --------------------------------------------------------------------------
echo
echo "3. Badger configuration"

CONFIG_OUT="$REPO/config.local.yaml"
if [[ -e "$CONFIG_OUT" && $ASSUME_YES -eq 0 ]]; then
    overwrite="$(ask "   config.local.yaml exists. Overwrite? [y/N]" "N")"
    case "$overwrite" in
        [yY]*) ;;
        *) echo "   Keeping the existing config.local.yaml."; CONFIG_OUT="" ;;
    esac
fi

if [[ -n "$CONFIG_OUT" ]]; then
    ARCHIVE_ROOT="$(ask '   Archive root (optimization run data)' "$HOME/BadgerArchive")"
    LOGBOOK_ROOT="$(ask '   Logbook root (GUI logs)' "$HOME/BadgerLogs")"

    # Rewriting YAML with sed is asking for trouble; PyYAML is already a Badger
    # dependency, so use it.
    ARCHIVE_ROOT="$ARCHIVE_ROOT" LOGBOOK_ROOT="$LOGBOOK_ROOT" \
    REPO="$REPO" CONFIG_OUT="$CONFIG_OUT" "$PY" - <<'PYEOF'
import os
from pathlib import Path
import yaml

repo = Path(os.environ['REPO'])
out = Path(os.environ['CONFIG_OUT'])

def resolve(p):
    return str(Path(p).expanduser().resolve())

paths = {
    'BADGER_PLUGIN_ROOT': str(repo / 'plugins'),
    'BADGER_TEMPLATE_ROOT': str(repo / 'tuning_templates'),
    'BADGER_LOG_DIRECTORY': str(repo / 'logs'),
    'BADGER_ARCHIVE_ROOT': resolve(os.environ['ARCHIVE_ROOT']),
    'BADGER_LOGBOOK_ROOT': resolve(os.environ['LOGBOOK_ROOT']),
}

config = yaml.safe_load((repo / 'config.yaml').read_text())
for key, value in paths.items():
    config[key]['value'] = value   # only the value; keep description/is_path
    Path(value).mkdir(parents=True, exist_ok=True)

out.write_text(yaml.safe_dump(config, sort_keys=True, default_flow_style=False))

for key in paths:
    print(f'   {key}: {config[key]["value"]}')
PYEOF
    echo "   wrote $CONFIG_OUT"
fi

# --------------------------------------------------------------------------
# 4. Verify
# --------------------------------------------------------------------------
echo
echo "4. Verifying"

if REPO="$REPO" "$PY" - <<'PYEOF'
import os, sys
from badger.settings import init_settings

# init_settings is first-call-wins and factory reads the plugin root at import
# time, so the settings must be initialized before badger.factory is imported.
init_settings(os.path.join(os.environ['REPO'], 'config.local.yaml'))
from badger.factory import list_env

envs = list_env()
if '99_Sim_VirtualAccelerator_MADXSuite' not in envs:
    print(f'   plugin not discovered; Badger sees: {envs}')
    sys.exit(1)
import badger
print(f'   badger {badger.__version__}, 99_Sim_VirtualAccelerator_MADXSuite discovered')
PYEOF
then
    echo "   OK"
else
    echo "   FAILED: Badger cannot load the plugins from this config."
    FAILED=1
fi

# --------------------------------------------------------------------------
echo
echo "=========================================="
if [[ $FAILED -eq 0 ]]; then
    echo "Setup complete."
else
    echo "Setup finished WITH ERRORS (see FAILED lines above)."
fi
echo "=========================================="
cat <<EOF

To use it:

    conda activate $ENV_NAME
    cd $REPO
    badger -g -cf config.local.yaml

Or load a template straight into the compact GUI:

    badger -mini -cf config.local.yaml -t Xfer400MeV_example.yaml
EOF

exit $FAILED
