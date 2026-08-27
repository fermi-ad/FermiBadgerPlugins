# Fix: Handle null turbo_controller gracefully

## Problem
When using a tuning template with `turbo_controller: null` (a valid configuration), Badger generates repeated warnings:
```
Could not find compatible class for  in field turbo_controller
```

The double space in the warning ("for  in") indicates that an empty string is being passed to the logger.

## Root Cause
In `badger/gui/components/pydantic_editor.py`, the `initialize_special_field` method handles `turbo_controller` and `numerical_optimizer` as special fields that can have sub-classes (e.g., different turbo controller implementations).

When `turbo_controller: null` is in the YAML configuration:
1. `defaults.get('turbo_controller')` returns `None`
2. The code checks if the field exists in defaults (it does, with value `None`)
3. However, it then sets `special_item_dict = {}` unconditionally
4. This causes `name` to be set to `"null"` (from the empty dict fallback)
5. `update_params_from_generator_class` is called with `name="null"`
6. `get_compatible_class` cannot find a class named "null" and logs the warning

The issue is that the code didn't distinguish between:
- A field that is truly missing from defaults (should warn)
- A field that is explicitly set to `null` (should be treated as valid, no sub-class to instantiate)

## Solution
Added an `else` branch to handle the case when `special_item_dict is None` but the field **does** exist in defaults (meaning it's explicitly set to null):

```python
if special_item_dict is None:
    if field not in defaults:
        logger.warning(...)
        special_item_dict = {}
    else:
        # Field is explicitly set to null, just set combo box and return
        if (index := widget.findText("null")) >= 0:
            widget.setCurrentIndex(index)
        return
```

When the field is explicitly null:
1. The combo box is set to "null" (the visual representation)
2. The method returns early, skipping `update_params_from_generator_class`
3. No warning is generated because null is a valid value

## Testing
- Verified that the warning no longer appears when loading a template with `turbo_controller: null`
- Verified that normal operation with turbo_controller set to valid values (e.g., "optimizer") continues to work
- Confirmed the fix handles the edge cases correctly

## Files Changed
- `badger/gui/components/pydantic_editor.py` (lines 762-774)
