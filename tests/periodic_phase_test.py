"""Offline check of periodic (phase) handling, no control network needed.

Drives BasicPacsysInterface and the EnergyStabilization_Pacsys environment
through pacsys.testing.FakeBackend. BasicAcsysInterface carries the identical
unwrap code but has no fake backend, so it is covered by the shared helper only.

Run from the repo root:
    python tests/periodic_phase_test.py
"""
import importlib
import math
import sys

sys.path.insert(0, 'plugins')

from pacsys.testing import FakeBackend
from periodic import unwrap
from interfaces.BasicPacsysInterface import Interface

PAIR = 'L:CDPHAS,L:LDPADJ,tol2@0.1'

# --- the helper itself -------------------------------------------------------
assert unwrap(5.0, 350.0, 360.0) == 365.0
assert unwrap(355.0, 10.0, 360.0) == -5.0
assert unwrap(350.0, 350.0, 360.0) == 350.0
assert math.isclose(unwrap(0.1, 6.2, 2 * math.pi), 0.1 + 2 * math.pi)

# --- plain reading: branch nearest the first reading of the run ---------------
fb = FakeBackend()
intf = Interface(); intf._backend_override = fb
fb.set_reading('L:CDPHAS', 350.0)
assert intf.get_values(['L:CDPHAS'], periods={'L:CDPHAS': 360.0}) == {'L:CDPHAS': 350.0}
fb.set_reading('L:CDPHAS', 5.0)
assert intf.get_values(['L:CDPHAS'], periods={'L:CDPHAS': 360.0}) == {'L:CDPHAS': 365.0}
# without a period nothing changes
assert intf.get_values(['L:CDPHAS']) == {'L:CDPHAS': 5.0}

# --- -SETPOINT error measured on the branch nearest the setpoint --------------
fb.set_reading('L:CDPHAS', 5.0)
out = Interface(); out._backend_override = fb
err = out.get_values(['L:CDPHAS-SETPOINT'], setpoints={'L:CDPHAS': 350.0}, periods={'L:CDPHAS': 360.0})
assert err == {'L:CDPHAS-SETPOINT': 225.0}, err          # (365-350)^2, not (5-350)^2

# --- environment: current value sits near the middle of the declared bounds ---
env_mod = importlib.import_module('environments.01_Linac_EnergyStabilization_Pacsys')
env = env_mod.Environment(interface=Interface())
env.interface._backend_override = fb
fb.set_reading('L:CDPHAS', 5.0)
assert env.get_variables([PAIR]) == {PAIR: 365.0}
fb.set_reading('L:CDPHAS', 350.0)
assert env.get_variables([PAIR]) == {PAIR: 350.0}
# a window around 365 fits inside the declared [0, 720], so Badger's bounds
# validator accepts a setting past the wrap (settings_role is nosettings: no write)
env.set_variables({PAIR: 375.0})
assert fb.writes == []

# --- RIL_tuning: RF phase settings are periodic but keep their tight operating bounds;
# a setting reported on the other branch is unwrapped to the branch nearest the bounds' midpoint
ril_mod = importlib.import_module('environments.01_Linac_RIL_tuning_Pacsys')
fb2 = FakeBackend()
ril = ril_mod.Environment(interface=Interface())
ril.interface._backend_override = fb2
fb2.set_reading('L:RFBPAH.SETTING@I', -179.0)     # same physics as 181, inside [100, 300]
fb2.set_reading('L:ATRMHU.SETTING@I', -1.5)       # not periodic: untouched
assert ril.get_variables(['L:RFBPAH', 'L:ATRMHU']) == {'L:RFBPAH': 181.0, 'L:ATRMHU': -1.5}

print('PERIODIC PHASE TEST PASSED')
