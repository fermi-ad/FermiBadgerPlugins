The patch converts FermiBadger_envTEST to match FermiBadger_env's pydantic_editor.py:
- Line 183: `main=primary.main` (was `main=origin`)
- Line 185: `subtype=primary.subtype` (was `subtype=primary`)
- Line 752: Added YAML string storage code for dict types

The patch must be applied after installing badger-opt from conda to avoid package corruption issues.

---

# Session Log - 2026-09-08

## PydanticSerializationUnexpectedValue warning for _initial_state

### 10:30 - Initial problem report
User asked about the origin of the warning message that appears after clicking "play" in the Badger mini GUI:
```
PydanticSerializationUnexpectedValue(Unexpected field `_initial_state_value`: Expected `OptimizeTurboController`)
```

### 10:35 - Initial investigation
Examined the TurboController class in Xopt:
- The `_initial_state` attribute stores the initial state for the `reset()` method
- It's set in `__init__` using `self._initial_state = self.model_dump()`
- It's not declared as a pydantic field

### 10:40 - Tested approaches
1. **model_dump override** - Added override in TurboController to exclude `_initial_state` from serialization. This worked for `model_dump()` but the pydantic internal serializer still saw the attribute.

2. **model_serializer with wrap** - Tried using `@model_serializer(mode="wrap")` to exclude the field. This caused RecursionError because calling `serializer(self)` triggers the serializer again.

3. **__getstate__/__setstate__** - Added pickle hooks to exclude `_initial_state_value` from pickle serialization. This only affected pickle, not pydantic's internal serializer.

4. **Using a property** - Tried using a property to compute `_initial_state` dynamically. The underlying `_initial_state_value` was still in `__dict__` and pydantic saw it.

### 10:45 - Solution identified
The correct solution is to use pydantic v2's `PrivateAttr()`:

```python
class TurboController(XoptBaseModel, ABC):
    _failure_counter: int = PrivateAttr(0)
    _success_counter: int = PrivateAttr(0)
    _initial_state_value: dict[str, Any] = PrivateAttr()  # <-- Declare as PrivateAttr
```

And use a property for the public API:

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

### 10:50 - Fix applied
Modified `/Users/stjohn/miniconda3/envs/FermiBadger_env/lib/python3.12/site-packages/xopt/generators/bayesian/turbo.py`:
1. Added `_initial_state_value: dict[str, Any] = PrivateAttr()` to class attributes
2. Simplified the `_initial_state` property to use normal attribute access
3. Updated `model_dump()` to also exclude `_initial_state_value`

### 10:55 - Testing
```
$ /Users/stjohn/miniconda3/envs/FermiBadger_env/bin/python -c "
from xopt import VOCS
from xopt.generators.bayesian import TurboController

class SimpleTurboController(TurboController):
    def update_state(self, data):
        pass

vocs = VOCS(variables={'kqd': [-0.9, -0.7], 'kqf': [0.7, 0.9]}, objectives={'beam_size': 'MINIMIZE'})
tc = SimpleTurboController(vocs=vocs)

import pickle
pickled = pickle.dumps(tc)
unpickled = pickle.loads(pickled)
unpickled.reset()

dump = unpickled.model_dump()
print('_initial_state in dump:', '_initial_state' in dump)
print('_initial_state_value in dump:', '_initial_state_value' in dump)
print('reset works:', unpickled._initial_state is not None)
"
```
Output: All tests passed, no warnings.

### 11:00 - Badger GUI verification
```
timeout 60 /Users/stjohn/miniconda3/envs/FermiBadger_env/bin/python -m badger -mini -cf config.yaml -t TuneQx.yaml -ar
```
Result: No `PydanticSerializationUnexpectedValue` warnings appeared. The remaining errors (sys.excepthook, atexit callback) are unrelated cleanup errors that occur during shutdown.

### 11:05 - Documentation updated
- Created `memory/pydantic-turbo-controller-initial-state.md`
- Updated `MEMORY.md` index
- Updated `docs/progress.md`
- Updated `docs/log.md`

### 11:10 - Status
- [x] Identified root cause (_initial_state not declared as pydantic field)
- [x] Applied PrivateAttr fix in TurboController
- [x] Verified no pydantic warnings in Badger GUI
- [x] Updated MEMORY.md, docs/progress.md, docs/log.md
