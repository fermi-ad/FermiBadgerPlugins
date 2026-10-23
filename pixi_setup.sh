#!/bin/bash
# Run via `pixi run setup` (or `pixi run -e onsite setup` on the MCR host):
#   1. apply the Badger patches to this pixi environment
#   2. write config.local.yaml with this clone's paths
#   2b. sync those same paths into Badger's own per-user settings file,
#       which some code paths (e.g. the "Go" run subprocess) read instead
#   3. check that Badger can actually see the plugins
#
# Safe to re-run: patches already applied are detected and skipped.
#
#   pixi run setup -- --yes      take every default, never prompt
#   pixi run setup -- --config   rewrite config.local.yaml only (no patches)
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ASSUME_YES=0
[[ -t 0 ]] || ASSUME_YES=1
SKIP_PATCHES=0
for arg in "$@"; do
    case "$arg" in
        --yes|-y) ASSUME_YES=1 ;;
        --config) SKIP_PATCHES=1 ;;
    esac
done
FAILED=0

ask() {
    local prompt="$1" default="$2" reply
    if [[ $ASSUME_YES -eq 1 ]]; then
        echo "$default"
        return
    fi
    read -r -p "$prompt [$default]: " reply </dev/tty
    echo "${reply:-$default}"
}

PY="$(command -v python)"
echo "=========================================="
echo "FermiBadgerPlugins pixi setup"
echo "  repo:   $REPO"
echo "  python: $PY"
echo "=========================================="

# --------------------------------------------------------------------------
# 1. Patches
# --------------------------------------------------------------------------
echo
echo "1. Badger patches"

if [[ $SKIP_PATCHES -eq 1 ]]; then
    echo "   skipped (--config)"
else
    SP="$("$PY" -c "import sysconfig; print(sysconfig.get_paths()['purelib'])")"
    echo "   site-packages: $SP"

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

    # Per-patch "already applied?" (reverse dry-run) can't see a patch whose
    # lines a later patch rewrote, so a re-run would report it FAILED. A
    # stamp of the whole patch set, written after a clean apply, is what
    # makes re-running safe; when the set changes (a pull brought new or
    # edited patches), Badger and Xopt are first put back as installed.
    STAMP="$SP/.fermibadger-patches"
    WANT="$("$PY" -c "import hashlib, glob, sys
h = hashlib.sha256()
for p in sorted(glob.glob(sys.argv[1] + '/*.patch')):
    h.update(open(p, 'rb').read())
print(h.hexdigest())" "$REPO/patches")"

    if [[ -f "$STAMP" && "$(cat "$STAMP")" == "$WANT" ]]; then
        echo "   skipped (this patch set is already applied)"
    else
        # Start from pristine Badger and Xopt: reinstall them from pixi's
        # package cache and remove the files our patches create (a new file's
        # "from" date is the epoch: 1969-12-31 or 1970-01-01 by time zone),
        # then apply the whole set.
        if [[ -n "${PIXI_ENVIRONMENT_NAME:-}" ]] && pixi reinstall \
                --manifest-path "$REPO/pixi.toml" -e "$PIXI_ENVIRONMENT_NAME" \
                badger-opt xopt >/dev/null 2>&1; then
            for f in $(sed -nE 's#^--- a/([^[:space:]]+)[[:space:]]+(1969-12-31|1970-01-01).*#\1#p' "$REPO"/patches/*.patch); do
                rm -f "$SP/$f"
            done
            echo "   reset Badger and Xopt to their installed state"
        else
            echo "   (could not reset Badger/Xopt with pixi reinstall; patching what is there)"
        fi
        apply_patch "$SP/badger/gui/components" 1 \
            "$REPO/patches/pydantic_editor-badger-1.6.0-dict-subtypes.patch"
        apply_patch "$SP" 1 "$REPO/patches/badger-mini-config.patch"
        apply_patch "$SP" 1 "$REPO/patches/badger-mini-var-table-env-configs.patch"
        # must come after the two -mini patches: it was diffed against that tree
        apply_patch "$SP" 1 "$REPO/patches/badger-1.6.0-device-list-gui.patch"
        apply_patch "$SP" 1 "$REPO/patches/badger-1.6.0-full-gui-template-option.patch"
        apply_patch "$SP" 1 "$REPO/patches/badger-1.6.0-spinbox-wheel-guard.patch"
        apply_patch "$SP" 1 "$REPO/patches/badger-1.6.0-revert-settings.patch"
        apply_patch "$SP" 1 "$REPO/patches/badger-1.6.0-plugin-docs.patch"
        # must come after revert-settings: diffed against that tree
        apply_patch "$SP" 1 "$REPO/patches/badger-1.6.0-param-validation.patch"
        apply_patch "$SP" 1 "$REPO/patches/badger-1.6.0-param-table-editor.patch"

        apply_patch "$SP" 1 "$REPO/patches/xopt-3.2.2-turbo-serialization.patch"

        if [[ $FAILED -eq 0 ]]; then
            echo "$WANT" > "$STAMP"
        else
            echo "   If this environment was patched by a different patch set,"
            echo "   rebuild it first: rm -rf .pixi/envs/<env> && pixi install"
        fi
    fi
fi

# --------------------------------------------------------------------------
# 2. config.local.yaml
# --------------------------------------------------------------------------
echo
echo "2. Badger configuration"

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
    config[key]['value'] = value
    Path(value).mkdir(parents=True, exist_ok=True)

out.write_text(yaml.safe_dump(config, sort_keys=True, default_flow_style=False))

for key in paths:
    print(f'   {key}: {config[key]["value"]}')
PYEOF
    echo "   wrote $CONFIG_OUT"
fi

# --------------------------------------------------------------------------
# 2b. Sync Badger's own per-user config
# --------------------------------------------------------------------------
# Badger keeps a separate, per-OS-user settings file outside this repo
# (get_user_config_folder(), e.g. ~/.config/config.yaml on Linux,
# ~/Library/Application Support/Badger/config.yaml on macOS). Some code
# paths (notably the run subprocess started by "Go") read path settings
# from THAT file instead of -cf config.local.yaml, so a stale per-user
# file (e.g. from an old clone that's since moved or been deleted)
# silently breaks live runs. Keep it in sync on every setup so it can
# never drift out from under this clone's actual paths.
echo
echo "2b. Syncing Badger's per-user config"
REPO="$REPO" "$PY" - <<'PYEOF'
import os
from pathlib import Path
import yaml
from badger.settings import init_settings

repo = Path(os.environ['REPO'])
local = yaml.safe_load((repo / 'config.local.yaml').read_text())

config_singleton = init_settings()  # no args: targets the per-user file
for key in ('BADGER_PLUGIN_ROOT', 'BADGER_TEMPLATE_ROOT', 'BADGER_LOG_DIRECTORY',
            'BADGER_ARCHIVE_ROOT', 'BADGER_LOGBOOK_ROOT'):
    value = local[key]['value']
    config_singleton.write_value(key, value)
    print(f'   {key}: {value}')
PYEOF

# --------------------------------------------------------------------------
# 2c. Badger's own guides (the "Open Docs" and "?" buttons)
# --------------------------------------------------------------------------
# Badger's docs window reads documentation/docs/guides/ beside its own
# source, but the installed package does not ship that folder. Fetch it
# from GitHub for the installed version, once; without it those buttons
# fall back to this repo's own pages only. Python, not curl, so it works
# wherever the environment does.
echo
echo "2c. Badger documentation"
"$PY" - <<'PYEOF'
import io, tarfile, urllib.request
from importlib.metadata import version
from pathlib import Path
import badger

ver = version("badger-opt")
# Where badger/factory.py looks: Path(factory.py).parent.parent.parent
documentation = Path(badger.__file__).resolve().parents[2] / "documentation"
stamp = documentation / ".badger-version"
# The guides, and the screenshots they show (/img/... -> static/img/...).
wanted = ("docs/guides/", "static/img/gui/", "static/img/guides/")
if stamp.exists() and stamp.read_text().strip() == ver:
    print(f"   skipped (guides for Badger {ver} already present)")
else:
    url = f"https://codeload.github.com/xopt-org/Badger/tar.gz/refs/tags/v{ver}"
    prefix = f"Badger-{ver}/documentation/"
    try:
        data = urllib.request.urlopen(url, timeout=60).read()
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            members = []
            for m in tar.getmembers():
                rel = m.name[len(prefix):]
                if m.name.startswith(prefix) and rel.startswith(wanted):
                    m.name = rel
                    members.append(m)
            tar.extractall(documentation, members=members, filter="data")
        stamp.write_text(ver)
        print(f"   fetched {len(members)} files for Badger {ver} into {documentation}")
    except Exception as e:
        print(f"   WARNING: could not fetch Badger's guides ({e}).")
        print("   Open Docs will show this repo's pages only; re-run setup when online.")
PYEOF

# --------------------------------------------------------------------------
# 3. Verify
# --------------------------------------------------------------------------
echo
echo "3. Verifying"

if REPO="$REPO" "$PY" - <<'PYEOF'
import os, sys
from badger.settings import init_settings

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

echo
echo "=========================================="
if [[ $FAILED -eq 0 ]]; then
    echo "Setup complete."
else
    echo "Setup finished WITH ERRORS (see FAILED lines above)."
fi
echo "=========================================="
ENV_FLAG=""
[[ -n "${PIXI_ENVIRONMENT_NAME:-}" && "$PIXI_ENVIRONMENT_NAME" != "default" ]] && \
    ENV_FLAG="-e $PIXI_ENVIRONMENT_NAME "
cat <<EOF

To use it:

    cd $REPO
    pixi run ${ENV_FLAG}badger -g -cf config.local.yaml

Or load a template straight into the compact GUI:

    pixi run ${ENV_FLAG}badger -mini -cf config.local.yaml -t Xfer400MeV_example.yaml
EOF

exit $FAILED
