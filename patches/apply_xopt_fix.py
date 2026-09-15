#!/usr/bin/env python
"""
Script to apply the Xopt pydantic serialization fix.
This suppresses PydanticSerializationUnexpectedValue warnings during TurboController serialization.

Usage:
    python apply_xopt_fix.py

The script will modify the following files:
- xopt/pydantic.py
- xopt/generators/bayesian/turbo.py

Note: Badger 1.6.0 already has a fix for pydantic_editor.py that handles
some of these warnings, but the Xopt fix ensures warnings are suppressed
during routine serialization and optimization loop iterations.
"""

import os
import sys

def apply_fix():
    """Apply the Xopt pydantic serialization fix."""
    # Find xopt installation
    try:
        import xopt
        xopt_path = os.path.dirname(xopt.__file__)
    except ImportError:
        print("ERROR: xopt is not installed in the current environment")
        sys.exit(1)

    print(f"Found xopt at: {xopt_path}")

    # Fix xopt/pydantic.py
    pydantic_path = os.path.join(xopt_path, "pydantic.py")
    if not os.path.exists(pydantic_path):
        print(f"ERROR: {pydantic_path} not found")
        sys.exit(1)

    print(f"\nApplying fix to {pydantic_path}...")

    with open(pydantic_path, 'r') as f:
        content = f.read()

    # Fix 1: Add warnings=False parameter to model_dump
    old_model_dump = '''    def model_dump(self, **kwargs) -> dict[str, Any]:
        """
        Override model_dump to exclude private attributes (starting with `_`).

        This prevents warnings like PydanticSerializationUnexpectedValue for
        attributes like `_initial_state` in TurboController.
        """
        result = super().model_dump(**kwargs)

        # Remove private attributes (keys starting with `_`)
        return {k: v for k, v in result.items() if not k.startswith("_")}'''

    new_model_dump = '''    def model_dump(self, **kwargs) -> dict[str, Any]:
        """
        Override model_dump to exclude private attributes (starting with `_`).

        This prevents warnings like PydanticSerializationUnexpectedValue for
        attributes like `_initial_state` in TurboController.
        """
        # Pass warnings=False to pydantic's model_dump to suppress serialization warnings
        # These warnings are expected and harmless for XoptBaseModel subclasses
        # Note: pydantic v2's Rust code emits warnings that bypass Python's warnings module,
        # so we must use warnings=False parameter
        if "warnings" not in kwargs:
            kwargs["warnings"] = False

        result = super().model_dump(**kwargs)

        # Remove private attributes (keys starting with `_`)
        return {k: v for k, v in result.items() if not k.startswith("_")}'''

    if old_model_dump in content:
        content = content.replace(old_model_dump, new_model_dump)
        print("  - Added warnings=False parameter to model_dump()")
    else:
        print("  - warnings=False parameter already present or pattern not found")

    # Fix 2: Update TurboController.model_dump to use super() instead of super(XoptBaseModel, self)
    turbo_path = os.path.join(xopt_path, "generators/bayesian/turbo.py")
    if os.path.exists(turbo_path):
        print(f"\nApplying fix to {turbo_path}...")

        with open(turbo_path, 'r') as f:
            turbo_content = f.read()

        old_turbo = '''        # Get raw dict from pydantic (includes private attrs)
        dump = super(XoptBaseModel, self).model_dump(**kwargs)'''

        new_turbo = '''        # Get raw dict from pydantic (includes private attrs)
        # Note: we must call super() not super(XoptBaseModel, self) to ensure
        # XoptBaseModel.model_dump() warning filter is applied
        dump = super().model_dump(**kwargs)'''

        if old_turbo in turbo_content:
            turbo_content = turbo_content.replace(old_turbo, new_turbo)
            print("  - Updated TurboController.model_dump() to use super()")
        else:
            print("  - TurboController.model_dump() already updated or pattern not found")

        with open(turbo_path, 'w') as f:
            f.write(turbo_content)

    # Write the updated pydantic.py
    with open(pydantic_path, 'w') as f:
        f.write(content)

    print("\nFix applied successfully!")
    print("\nNote: The warning filter in badger/core_subprocess.py was removed in the")
    print("current codebase as the Xopt fix (warnings=False parameter) is now sufficient.")

if __name__ == "__main__":
    apply_fix()
