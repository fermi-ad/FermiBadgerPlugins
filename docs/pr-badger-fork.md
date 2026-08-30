# PR Description for Badger 1.6.0 Fork

## Title
Fix YAML flow map 'None' parsing causing validation errors

## Problem

When templates with `None` values are loaded in Badger 1.6.0, validation errors appear:

```
Input should be a valid number, unable to parse string as a number [type=float_parsing, input_value='None', input_type=str]
```

## Root Cause

When YAML flow maps (inline `{}`) contain unquoted `None`, `yaml.safe_load()` parses them as the string `'None'` instead of Python `None`. This happens because in YAML flow map syntax, `None` without quotes is treated as a scalar string value, not as YAML null.

The issue occurs in two places:
1. `pydantic_editor.py` - When serializing generator parameters, VOCS fields are output as YAML flow maps like `{'dtype': None, 'default_value': None}`. When parsed back, `None` becomes `'None'`.
2. Generator VOCS in templates - Some templates store VOCS fields as YAML strings. When `yaml.safe_load()` parses these strings, `None` becomes `'None'`.

## Solution

Add string replacement to convert `None` → `null` before YAML parsing:

```python
fixed_parameters = (
    parameters.replace(": None", ": null")
    .replace(", None", ", null")
    .replace("[None", "[null")
    .replace("(None", "(null")
)
defaults = yaml.load(fixed_parameters, Loader=CustomSafeLoader)
```

## Files Changed

1. `badger/gui/components/pydantic_editor.py`
   - 3 locations: `on_radio_changed()`, `update_vocs()`, `validate()` methods

2. `badger/gui/utils.py`
   - Updated `_parse_yaml_strings()` function

## Testing

Template `DR_BetatronTunes_sim.yaml` loaded successfully with:
- `dtype=None` (NoneType, not string)
- `default_value=None` (NoneType, not string)
- `max_travel_distances=None` (NoneType, not string)
- `turbo_controller=None` (NoneType, not string)

Generator validation passes without errors.

## Patch File

A patch file is available at: `badger-1.6.0-none-parsing-fix.patch`

To apply to a fresh environment:
```bash
cd /path/to/badger
patch -p1 < /path/to/badger-1.6.0-none-parsing-fix.patch
```

## Instructions for Fork

To create a fork of Badger 1.6.0 with this fix:

1. Fork https://github.com/xopt-org/Badger
2. Apply the patch to the fork
3. Update fork's version to `1.6.0-p1` (or similar)
4. Publish fork to GitHub
5. Update `environment.yml` in FermiBadgerPlugins to point to your fork

Example environment.yml entry for fork:
```yaml
- badger-opt=1.6.0-p1
```