#!/bin/bash
# Test script for Quick Start instructions
# Creates a fresh clone of FermiBadgerPlugins and verifies setup with a test conda environment

set -e

echo "=========================================="
echo "Testing FermiBadgerPlugins Quick Start"
echo "=========================================="
echo ""

# Configuration
TEST_DIR="/tmp/FermiBadger_envTEST"
ENV_NAME="FermiBadger_envTEST"

# Clean up if test directory already exists
if [[ -d "$TEST_DIR" ]]; then
    echo "Found existing test directory, cleaning up..."
    rm -rf "$TEST_DIR"
fi

# Step 1: Clone the repository
echo "1. Cloning FermiBadgerPlugins repository..."
echo "   Target: $TEST_DIR"

# Clone and capture output to verify success
CLONE_OUTPUT=$(git clone --branch main https://github.com/fermi-ad/FermiBadgerPlugins.git "$TEST_DIR" 2>&1)
CLONE_EXIT_CODE=$?

if [[ $CLONE_EXIT_CODE -ne 0 ]]; then
    echo "   ERROR: Git clone failed with exit code $CLONE_EXIT_CODE!"
    echo "   Output: $CLONE_OUTPUT"
    exit 1
fi

# Verify clone was successful by checking the .git directory exists
if [[ -d "$TEST_DIR/.git" ]] && [[ -d "$TEST_DIR/plugins" ]] && [[ -d "$TEST_DIR/tuning_templates" ]]; then
    echo "   OK: Repository cloned successfully"
else
    echo "   ERROR: Git clone did not complete properly - missing expected directories"
    echo "   Output: $CLONE_OUTPUT"
    exit 1
fi

cd "$TEST_DIR"
echo ""

# Step 2: Create conda environment with test name
echo "2. Creating conda environment: $ENV_NAME"
echo "   (This will take several minutes...)"
echo ""

# Check if environment already exists and remove it
if conda info --envs 2>/dev/null | grep -q " $ENV_NAME$"; then
    echo "   Environment $ENV_NAME already exists, removing..."
    conda env remove -n "$ENV_NAME" --yes 2>&1
fi

# Create the environment and capture output
# Use --no-warn-env-not-found to suppress warnings about missing env
CONDA_OUTPUT=$(conda env create -n "$ENV_NAME" -f environment.yml --yes 2>&1) || {
    echo "   ERROR: Conda environment creation failed!"
    echo "   Last 20 lines of output:"
    echo "$CONDA_OUTPUT" | tail -20
    exit 1
}

# Check for successful creation
if echo "$CONDA_OUTPUT" | grep -q "environment created" || \
   conda env list 2>/dev/null | grep -q "^$ENV_NAME "; then
    echo "   OK: Conda environment created successfully"
else
    echo "   ERROR: Conda environment may not have been created properly"
    echo "   Output preview:"
    echo "$CONDA_OUTPUT" | head -30
    exit 1
fi

# Check that the environment can be activated without errors
ACTIVATION_TEST=$(source "$(conda info --base)/etc/profile.d/conda.sh" && \
    conda activate "$ENV_NAME" 2>&1 && \
    python --version 2>&1) || {
    echo "   ERROR: Could not activate the test environment!"
    echo "   Output: $ACTIVATION_TEST"
    exit 1
}

echo "   OK: Environment activated successfully (Python $(echo "$ACTIVATION_TEST" | grep -o 'Python [0-9.]*' || echo 'unknown'))"
echo ""

# Activate the test environment for subsequent steps
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate "$ENV_NAME"
echo "   Environment '$ENV_NAME' activated"
echo ""

# Step 3: Install the plugin via pip in editable mode
echo "3. Installing plugin in editable mode..."
cd "$TEST_DIR"

# Verify we're in the test environment
echo "   Python: $(which python)"
echo "   pip: $(which pip)"

# Create a minimal setup.py for editable install
cat > setup.py << 'SETUP_EOF'
from setuptools import setup, find_packages

setup(
    name="FermiBadgerPlugins",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "badger-opt>=1.6.0",
        "xopt>=3.2.0",
    ],
)
SETUP_EOF

# Install with verbose output for debugging
INSTALL_OUTPUT=$(pip install -e . 2>&1) || {
    echo "   ERROR: pip install failed!"
    echo "   Output: $INSTALL_OUTPUT"
    exit 1
}

# Verify installation by checking if package is listed
if pip show FermiBadgerPlugins >/dev/null 2>&1; then
    echo "   OK: Plugin installed successfully"
else
    echo "   ERROR: Plugin not found in installed packages!"
    echo "   Output: $INSTALL_OUTPUT"
    exit 1
fi

echo ""
echo "4. Verifying installation..."

# Check if badger is installed
BADGER_VERSION=$(python -c "import badger; print(badger.__version__)" 2>/dev/null || echo "unknown")
echo "   Badger version: $BADGER_VERSION"

# Check if VirtualAccelerator_MADXSuite can be imported
python -c "
import sys
sys.path.insert(0, '$TEST_DIR')
from plugins.environments.VirtualAccelerator_MADXSuite import Environment
print('   VirtualAccelerator_MADXSuite: Import successful')
" || {
    echo "   ERROR: Could not import VirtualAccelerator_MADXSuite!"
    exit 1
}

echo ""
echo "5. Verifying plugin directory structure..."
if [[ -d "plugins/environments/VirtualAccelerator_MADXSuite" ]]; then
    echo "   OK: plugins/environments/VirtualAccelerator_MADXSuite exists"
else
    echo "   ERROR: plugins/environments/VirtualAccelerator_MADXSuite not found!"
    exit 1
fi

if [[ -d "tuning_templates" ]]; then
    echo "   OK: tuning_templates directory exists"
else
    echo "   ERROR: tuning_templates directory not found!"
    exit 1
fi

echo ""
echo "6. Verifying plugin is discoverable by Badger..."
PLUGIN_FOUND=$(python -c "
from badger.factory import list_env
envs = list_env()
if 'VirtualAccelerator_MADXSuite' in envs:
    print('FOUND')
else:
    print('NOT_FOUND')
    print('Available:', envs)
" 2>&1)

if echo "$PLUGIN_FOUND" | grep -q "^FOUND$"; then
    echo "   OK: VirtualAccelerator_MADXSuite found in Badger environment list!"
else
    echo "   WARNING: VirtualAccelerator_MADXSuite not in Badger environment list"
    echo "   Output: $PLUGIN_FOUND"
fi

echo ""
echo "=========================================="
echo "Quick Start test completed successfully!"
echo "=========================================="
echo ""
echo "Test results:"
echo "  - Repository cloned to: $TEST_DIR"
echo "  - Conda environment: $ENV_NAME"
echo "  - Plugin installed: editable mode"
echo ""
echo "To use manually after testing:"
echo "  1. Copy config.yaml from $TEST_DIR to your home or project directory"
echo "  2. Edit config.yaml to set:"
echo "     - BADGER_PLUGIN_ROOT: $TEST_DIR/plugins"
echo "     - BADGER_TEMPLATE_ROOT: $TEST_DIR/tuning_templates"
echo "     - BADGER_ARCHIVE_ROOT: /path/to/archive"
echo "     - BADGER_LOGBOOK_ROOT: /path/to/logbook"
echo "  3. Run: badger -g -cf /path/to/config.yaml"
echo ""
echo "To clean up test environment when done:"
echo "  conda env remove -n $ENV_NAME"
echo "  rm -rf $TEST_DIR"
