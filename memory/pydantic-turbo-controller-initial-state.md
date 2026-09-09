---
name: pydantic-turbo-controller-initial-state
description: Fix for PydanticSerializationUnexpectedValue warning for _initial_state_value
metadata:
  type: project
---

# Fix for `_initial_state` PydanticSerializationUnexpectedValue Warning

## Problem
When running the Badger mini GUI with the TurboController, pydantic emitted warnings:
```
PydanticSerializationUnexpectedValue(Unexpected field `_initial_state_value`: Expected `OptimizeTurboController`)
```

The warning appeared twice per serialization event - once from the TurboController's internal serialization and once from pydantic's base serializer.

## Root Cause
The `TurboController` class in Xopt stored `_initial_state` to preserve the controller's state for the `reset()` method. This attribute was set in `__init__` using `self._initial_state = self.model_dump()`, but it was not declared as a pydantic field. When pydantic tried to serialize the object, it found this extra attribute and emitted `PydanticSerializationUnexpectedValue` warnings.

## Solution Applied

**File:** `/Users/stjohn/miniconda3/envs/FermiBadger_env/lib/python3.12/site-packages/xopt/generators/bayesian/turbo.py`

### 1. Declare `_initial_state_value` as a PrivateAttr
```python
# Added to class attributes:
_initial_state_value: dict[str, Any] = PrivateAttr()
```

### 2. Simplified property-based access
```python
@property
def _initial_state(self) -> dict[str, Any]:
    """Property to access the initial state."""
    return self._initial_state_value

@_initial_state.setter
def _initial_state(self, value: dict[str, Any]) -> None:
    """Setter to allow setting the initial state during initialization."""
    self._initial_state_value = value
```

### 3. Updated model_dump to exclude the private attr
```python
def model_dump(self, **kwargs) -> dict[str, Any]:
    """Override to exclude _initial_state from serialization."""
    dump = super(XoptBaseModel, self).model_dump(**kwargs)
    dump.pop("_initial_state", None)
    dump.pop("_initial_state_value", None)
    return dump
```

## Why This Works
In pydantic v2, `PrivateAttr()` is the proper way to declare attributes that should not be serialized as part of the model. By declaring `_initial_state_value` as a `PrivateAttr`:
- Pydantic knows it's an internal attribute
- It won't emit `PydanticSerializationUnexpectedValue` warnings
- It's still accessible for the controller's internal use (reset functionality)

## Key Insight
The naming was intentionally kept as `_initial_state_value` internally (not `_initial_state`) because:
1. The property `_initial_state` provides the public API for accessing the initial state
2. The actual storage `_initial_state_value` is a pydantic `PrivateAttr`
3. The `model_dump()` override removes both names to ensure clean serialization

## Testing
- TurboController instantiation works correctly
- `model_dump()` excludes `_initial_state_value`
- `pickle` serialization/deserialization works
- `reset()` method works correctly
- No pydantic serialization warnings appear in Badger mini GUI

## Status
- [x] Identified root cause (_initial_state not declared as field)
- [x] Applied PrivateAttr fix in TurboController
- [x] Verified no pydantic warnings in Badger GUI
- [x] Updated MEMORY.md
