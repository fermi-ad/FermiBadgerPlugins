"""Offline check of badger-1.6.0-context-variables.patch, Badger's run path: a routine whose
VOCS has a context variable (Xopt ContextualVariable: modeled, never moved).

03_Booster_Pacsys on pacsys's FakeBackend (nothing reaches ACNET), knob B:MH1, context
B:MV1, objective B:BOOEFF:
- initial points (current, random) leave the context variable out;
- evaluating them and three optimizer steps never writes B:MV1, and every data row carries
  B:MV1's reading at that step (it drifts between steps);
- the generator saw a ContextualVariable, and its candidates leave it out;
- recomputing the variable ranges at Go keeps it contextual;
- the helpers (context_names, settable_vocs, without_context, template_context_names) and
  the bounds rounding the mini GUI uses accept it.

Run from the repo root:
    pixi run python tests/context_variables_test.py
"""
import contextlib
import importlib
import io
import sys
import warnings

import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, "plugins")
from pacsys.testing import FakeBackend  # noqa: E402
from interfaces.BasicPacsysInterface import Interface  # noqa: E402

from badger.routine import Routine, calculate_initial_points, calculate_variable_bounds  # noqa: E402
from badger.utils import (  # noqa: E402
    _round_bounds_inward,
    context_names,
    settable_vocs,
    template_context_names,
    without_context,
)
from xopt.generators.bayesian.expected_improvement import ExpectedImprovementGenerator  # noqa: E402
from xopt.vocs import VOCS, ContextualVariable  # noqa: E402


def quiet(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


E = importlib.import_module("environments.03_Booster_Pacsys").Environment
env = E(interface=Interface())
fb = env.interface._backend_override = FakeBackend()
env.interface._timeout = 5.0
object.__setattr__(env, "settings_role", "testing")  # a writing role, for the fake only

MV1 = [375.0]  # the context device's reading; drifts between steps


def readings(mh1=352.0):
    fb.set_reading("B:MH1.SETTING", mh1)
    fb.set_reading("B:MV1.SETTING", MV1[0])
    fb.set_reading("B:BOOEFF", 92.0)


readings()
vocs = VOCS(variables={"B:MH1": [345.0, 360.0], "B:MV1": ContextualVariable(domain=[365.0, 387.0])},
            objectives={"B:BOOEFF": "MAXIMIZE"})
assert context_names(vocs) == ["B:MV1"]
assert settable_vocs(vocs).variable_names == ["B:MH1"]
assert without_context(vocs, {"B:MH1": 1.0, "B:MV1": 2.0, "x": 3}) == {"B:MH1": 1.0, "x": 3}
assert template_context_names({"a": [0, 1], "b": {"type": "ContextualVariable", "domain": [0, 1]},
                               "c": "CONTEXTUAL"}) == ["b", "c"]
assert _round_bounds_inward(vocs.variables["B:MV1"]) == [365.0, 387.0]

# initial points: current and random, without the context variable
init = calculate_initial_points([{"type": "add_curr"},
                                 {"type": "add_rand", "config": {"n_points": 2, "fraction": 0.1}}],
                                vocs, env)
assert set(init) == {"B:MH1"} and len(init["B:MH1"]) == 3, init

gen = ExpectedImprovementGenerator(vocs=vocs)
routine = Routine(name="ctx", generator=gen, environment=env, initial_points=pd.DataFrame(init))
quiet(routine.evaluate_data, pd.DataFrame(init))
for step in range(3):
    MV1[0] += 1.5  # the context drifts; the optimizer must read it, not set it
    readings(mh1=float(routine.data["B:MH1"].iloc[-1]))
    cand = quiet(routine.generator.generate, 1)
    assert "B:MV1" not in cand[0], cand
    quiet(routine.evaluate_data, pd.DataFrame(cand))
    assert routine.data["B:MV1"].iloc[-1] == MV1[0], (routine.data["B:MV1"].iloc[-1], MV1[0])

written = [d for d, _ in fb.writes]
assert not any(d.startswith("B:MV1") for d in written), written
assert any(d.startswith("B:MH1") for d in written), written
assert len(routine.data) == 6 and routine.data["B:MV1"].notna().all(), routine.data
assert isinstance(routine.generator.vocs.variables["B:MV1"], ContextualVariable)

# range recomputation at Go keeps the type (and drops nothing)
updated = calculate_variable_bounds({"B:MH1": {"limit_option_idx": 1, "ratio_full": 0.1, "ratio_curr": 0.1},
                                     "B:MV1": {"limit_option_idx": 1, "ratio_full": 0.1, "ratio_curr": 0.1}},
                                    vocs, env)
assert isinstance(updated["B:MV1"], ContextualVariable) and isinstance(updated["B:MH1"], list), updated
updated = calculate_variable_bounds({"B:MH1": {"limit_option_idx": 1, "ratio_full": 0.1, "ratio_curr": 0.1}},
                                    vocs, env)
assert updated["B:MV1"] is vocs.variables["B:MV1"], updated  # no limit option: kept as is
print(f"context: B:MV1 read at every step ({routine.data['B:MV1'].tolist()}), never written; "
      f"{len(written)} writes, all B:MH1")
print("CONTEXT VARIABLES TEST PASSED")
