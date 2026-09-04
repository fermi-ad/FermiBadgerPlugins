# Badger Patches

## Summary

### Patches for Badger 1.6.0 installation

The following patch is required to fix known issues in Badger 1.6.0:

| Patch | Description | Applied |
|-------|-------------|---------|
| `pydantic_editor-badger-1.6.0-dict-subtypes.patch` | Fixes "Dict type must have subtypes" error, handles `turbo_controller: null`, and fixes YAML parsing for 'None' strings | **Currently applied** |

### Patch history

The following patches have been superseded by `pydantic_editor-badger-1.6.0-dict-subtypes.patch`:

- `pydantic_editor-badger-1.6.0-fixes.patch` - Superseded (contains same fixes in separate patches)
- `pydantic_editor-turbo_controller-null-1.6.0.patch` - Superseded
- `pydantic_editor-combo-box-null-fix.patch` - Superseded
- `pydantic_editor-null-turbo_controller-git-apply.patch` - Superseded
- `pydantic_editor-null-turbo_controller.patch` - Superseded
- `pydantic_editor-turbo_controller-string-PR.patch` - Superseded
- `pydantic_editor-turbo_controller-string-fix.patch` - Superseded

## Applying patches to Badger 1.6.0

The patches modify `badger/gui/components/pydantic_editor.py` in your Badger installation.

```bash
# Navigate to your Badger installation directory
cd /path/to/badger/installation/lib/python3.x/site-packages/badger/gui/components/

# Apply the patches
patch -p0 < /path/to/FermiBadgerPlugins/patches/pydantic_editor-dict-subtypes-fix.patch
patch -p0 < /path/to/FermiBadgerPlugins/patches/pydantic_editor-turbo_controller-null-fix.patch

# Or apply both at once using the combined patch
patch -p0 < /path/to/FermiBadgerPlugins/patches/pydantic_editor-all-fixes.patch
```

## If you encounter issues

If you're seeing pydantic serialization warnings or "Dict type must have subtypes" errors:

1. Make sure you're using Badger 1.6.0 (not 1.5.4)
2. Check that the patches are applied correctly
3. Verify your conda environment has all dependencies installed

## Environment

Patches tested with:
- Badger 1.6.0
- Python 3.12
- Pydantic 2.x

## If you encounter issues

If you're seeing pydantic serialization warnings when running Badger:

1. Make sure you're using Badger 1.6.0 (not 1.5.4)
2. Check that the environment variables are set correctly in config.yaml
3. Try running `badger -g -cf config.yaml` from the FermiBadgerPlugins directory
