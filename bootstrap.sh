#!/bin/bash
# One-command setup for a fresh clone of FermiBadgerPlugins, using pixi:
#   1. install pixi itself, if it's not already on PATH
#   2. pixi install (resolves and builds the environment from pixi.toml)
#   3. pixi run setup (patches, config.local.yaml, discoverability check)
#
#   ./bootstrap.sh                 default: adds acsys (needs the FNAL network); use on the MCR host
#   ./bootstrap.sh --offsite       off-site/dev: no acsys, no FNAL network needed
#   ./bootstrap.sh --yes           never prompt during the setup step
set -euo pipefail

# macOS ships bash 3.2, which errors on an empty array under 'set -u'; plain
# strings avoid that rather than guarding every array expansion.
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_NAME=""
ENV_FLAG=""
SETUP_YES=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --offsite)  ENV_NAME="offsite"; ENV_FLAG="-e offsite"; shift ;;
        --onsite)   shift ;;  # now the default; accepted as a no-op for anyone who already typed it
        --yes|-y)   SETUP_YES="--yes"; shift ;;
        --help|-h)  sed -n '2,8p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown option: $1 (try --help)" >&2; exit 2 ;;
    esac
done

echo "=========================================="
echo "FermiBadgerPlugins bootstrap (pixi)"
echo "  repo: $REPO"
echo "=========================================="

echo
echo "1. pixi"
if command -v pixi >/dev/null 2>&1; then
    echo "   OK: $(pixi --version)"
else
    echo "   installing pixi..."
    curl -fsSL https://pixi.sh/install.sh | bash
    export PATH="$HOME/.pixi/bin:$PATH"
    command -v pixi >/dev/null 2>&1 || {
        echo "ERROR: pixi install succeeded but 'pixi' is not on PATH." >&2
        echo "Open a new shell (or source your profile) and re-run this script." >&2
        exit 1
    }
fi

echo
echo "2. pixi environment${ENV_NAME:+ ($ENV_NAME)}"
cd "$REPO"
pixi install $ENV_FLAG

echo
echo "3. Patches, config, verify"
pixi run $ENV_FLAG setup -- $SETUP_YES
