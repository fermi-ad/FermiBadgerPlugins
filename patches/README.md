# Badger Patches

This directory is now empty - all patches have been applied directly to the codebase.

## Summary

All fixes for Badger 1.6.0 have been implemented in the following files:

### In FermiBadgerPlugins repo:
- `plugins/environments/VirtualAccelerator_MADXSuite/__init__.py` - Uses Pydantic Field defaults
- `plugins/environments/VirtualAccelerator_MADXSuite/configs.yaml` - Updated config

### In Badger installation:
The fixes are already in `badger/gui/components/pydantic_editor.py`:
- `initialize_special_field` method properly handles `turbo_controller: null`
- `validate` method handles missing `vocs` in parameters
- QComboBox correctly returns `None` for "null" values

## Old patches (no longer needed)

The following patches were previously needed but have been superseded:

- `pydantic_editor-badger-1.6.0-fixes.patch` - Applied to repo
- `pydantic_editor-turbo_controller-null-1.6.0.patch` - Applied to Badger
- `pydantic_editor-combo-box-null-fix.patch` - Applied to Badger
- `pydantic_editor-null-turbo_controller-git-apply.patch` - Superseded
- `pydantic_editor-null-turbo_controller.patch` - Superseded
- `pydantic_editor-turbo_controller-string-PR.patch` - Superseded
- `pydantic_editor-turbo_controller-string-fix.patch` - Superseded

## If you encounter issues

If you're seeing pydantic serialization warnings when running Badger:

1. Make sure you're using Badger 1.6.0 (not 1.5.4)
2. Check that the environment variables are set correctly in config.yaml
3. Try running `badger -g -cf config.yaml` from the FermiBadgerPlugins directory
