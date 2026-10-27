"""Checks of ZZ_PacsysTesting's TwoWells demonstration objective, no control
network needed (pacsys FakeBackend; nothing is written): the global minimum -6.0
at G:AMANDA=3, Z:CUBE_X=-4, Z:CUBE_Y=2, Z:CUBE_Z=5; a shallower local minimum
(the decoy) near (-6, 5, -5, -3); plain descent from all zeros finds the global
one; and the environment returns TwoWells from the devices' readings.

Run from the repo root:
    pixi run python tests/zz_two_wells_test.py
"""
import importlib
import sys

import numpy as np
from scipy.optimize import minimize

sys.path.insert(0, "plugins")
from pacsys.testing import FakeBackend  # noqa: E402
from interfaces.BasicPacsysInterface import Interface  # noqa: E402

zz = importlib.import_module("environments.ZZ_PacsysTesting")
f = zz.two_wells

assert np.isclose(f([3, -4, 2, 5]), -6.0)
decoy = minimize(f, [-6, 5, -5, -3], method="Nelder-Mead", options={"xatol": 1e-6, "fatol": 1e-9})
assert np.allclose(decoy.x, [-5.93, 4.97, -4.98, -2.90], atol=0.02), decoy.x
assert -3.2 < decoy.fun < -2.9, decoy.fun  # a real minimum, shallower than -6
best = minimize(f, [0, 0, 0, 0], method="Nelder-Mead", options={"xatol": 1e-6, "fatol": 1e-9})
assert np.allclose(best.x, [3, -4, 2, 5], atol=1e-3) and np.isclose(best.fun, -6.0), best

fb = FakeBackend()
for d, v in {"G:AMANDA": 3.0, "Z:CUBE_X": -4.0, "Z:CUBE_Y": 2.0, "Z:CUBE_Z": 5.0}.items():
    for drf in (d, f"{d}.READING", f"{d}.SETTING"):
        fb.set_reading(drf, v)
intf = Interface()
intf._backend_override = fb
intf._timeout = 1.0
obs = zz.Environment(interface=intf).get_observables(["TwoWells", "CUBE_X_sq"])
assert sorted(obs) == ["CUBE_X_sq", "TwoWells"] and np.isclose(obs["TwoWells"], -6.0), obs
assert not fb.writes

print("ZZ TWO WELLS TEST PASSED")
