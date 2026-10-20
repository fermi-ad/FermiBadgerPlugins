#!/bin/bash
# Test script for Quick Start instructions (pixi path).
# Clones a fresh copy of FermiBadgerPlugins and runs ./bootstrap.sh there, in
# its own .pixi/ environment, so it never touches your own config.local.yaml
# or environment. Legacy conda equivalent: test-quick-start-conda.sh.
set -e

echo "=========================================="
echo "Testing FermiBadgerPlugins Quick Start (pixi)"
echo "=========================================="
echo ""

TEST_DIR="/tmp/FermiBadgerPluginsTEST"

if [[ -d "$TEST_DIR" ]]; then
    echo "Found existing test directory, cleaning up..."
    rm -rf "$TEST_DIR"
fi

echo "1. Cloning FermiBadgerPlugins repository..."
echo "   Target: $TEST_DIR"

CLONE_OUTPUT=$(git clone --branch main https://github.com/fermi-ad/FermiBadgerPlugins.git "$TEST_DIR" 2>&1) || {
    echo "   ERROR: Git clone failed!"
    echo "   Output: $CLONE_OUTPUT"
    exit 1
}

if [[ -d "$TEST_DIR/.git" ]] && [[ -d "$TEST_DIR/plugins" ]] && [[ -d "$TEST_DIR/tuning_templates" ]]; then
    echo "   OK: Repository cloned successfully"
else
    echo "   ERROR: Git clone did not complete properly - missing expected directories"
    exit 1
fi

cd "$TEST_DIR"
echo ""

echo "2. Running ./bootstrap.sh --yes..."
echo "   (This will take several minutes the first time pixi resolves the environment...)"
echo ""
./bootstrap.sh --yes

echo ""
echo "=========================================="
echo "Quick Start test completed successfully!"
echo "=========================================="
echo ""
echo "Test results:"
echo "  - Repository cloned to: $TEST_DIR"
echo "  - pixi environment built, patched, and verified"
echo ""
echo "To use manually after testing:"
echo "  cd $TEST_DIR"
echo "  pixi run badger -g -cf config.local.yaml"
echo ""
echo "To clean up test environment when done:"
echo "  rm -rf $TEST_DIR"
