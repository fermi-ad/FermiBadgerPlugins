"""Offline check of xopt-3.2.2-constraint-risk-tolerance.patch: a generator's
constraint_risk_tolerance (per constraint, the largest modeled probability that a
proposed point violates it) holds for expected improvement, UCB, and MOBO (checked at 0.1 %, where it binds); 0 becomes the
most cautious value allowed (1e-4); and when no point can meet a tolerance, the step
ignores it with a warning instead of failing.

Synthetic data: one variable x in [0, 1], the objective pulls x up, and the constraint
c = x must stay below 0.6, so the best points sit on the constraint's edge.

Run from the repo root:
    pixi run python tests/constraint_risk_tolerance_test.py
"""
import contextlib
import io
import logging
import warnings

import numpy as np
import pandas as pd
import torch
from xopt import VOCS
from xopt.generators.bayesian.bayesian_generator import risk_shortfall
from xopt.generators.bayesian.expected_improvement import ExpectedImprovementGenerator
from xopt.generators.bayesian.mobo import MOBOGenerator
from xopt.generators.bayesian.upper_confidence_bound import UpperConfidenceBoundGenerator

warnings.filterwarnings("ignore")
torch.manual_seed(0)
rng = np.random.default_rng(0)
x = np.linspace(0.02, 0.98, 12)
DATA = pd.DataFrame({"x": x, "f": -x + 0.01 * rng.standard_normal(12),
                     "g": x + 0.01 * rng.standard_normal(12),
                     "c": x + 0.02 * rng.standard_normal(12)})


def p_satisfied(gen, point):
    """The model's probability that c < bound at the proposed x."""
    limits = [(list(gen.model_output_names).index("c"), gen.vocs.constraints["c"].value, 1.0, 1.0)]
    X = torch.tensor([[[point]]], dtype=torch.double)
    with torch.no_grad():
        return 1.0 - float(risk_shortfall(gen.model, X, limits).squeeze())


def propose(cls, tolerance, constraint=("LESS_THAN", 0.6), objectives=None, data=DATA, **kw):
    vocs = VOCS(variables={"x": [0, 1]}, objectives=objectives or {"f": "MINIMIZE"},
                constraints={"c": list(constraint)})
    gen = cls(vocs=vocs, constraint_risk_tolerance=tolerance, **kw)
    gen.add_data(data)
    with contextlib.redirect_stdout(io.StringIO()):
        point = float(gen.generate(1)[0]["x"])
    return gen, point


# validation: 0 -> the most cautious value; above 1 -> no limit
gen = ExpectedImprovementGenerator(vocs=VOCS(variables={"x": [0, 1]}, objectives={"f": "MINIMIZE"},
                                             constraints={"c": ["LESS_THAN", 0.6]}),
                                   constraint_risk_tolerance={"c": 0.0})
assert gen.constraint_risk_tolerance == {"c": 1e-4}, gen.constraint_risk_tolerance
gen.constraint_risk_tolerance = {"c": 5.0}
assert gen.constraint_risk_tolerance == {"c": 1.0}
assert "constraint_risk_tolerance" in gen.model_dump()

# Without a tolerance EI goes close to the edge; with 0.1 % it keeps 99.9 % odds of
# satisfying c. The test is only meaningful if the limit bites, so check that first.
TOL = 0.001
free, x_free = propose(ExpectedImprovementGenerator, None)
safe, x_safe = propose(ExpectedImprovementGenerator, {"c": TOL})
print(f"EI: x={x_free:.3f} (P ok {p_satisfied(free, x_free):.4f}) without; "
      f"x={x_safe:.3f} (P ok {p_satisfied(safe, x_safe):.4f}) at {TOL:.1%}")
assert p_satisfied(free, x_free) < 1 - TOL, 'the tolerance does not bite on this data'
assert p_satisfied(safe, x_safe) >= 1 - TOL - 1e-4, p_satisfied(safe, x_safe)
assert x_safe < x_free, (x_safe, x_free)  # more cautious than without

for cls, kw in ((UpperConfidenceBoundGenerator, {}),
                (MOBOGenerator, {"reference_point": {"f": 0.0, "g": 1.0}})):
    objectives = {"f": "MINIMIZE", "g": "MINIMIZE"} if cls is MOBOGenerator else None
    g, xp = propose(cls, {"c": TOL}, objectives=objectives, **kw)
    print(f"{cls.__name__}: x={xp:.3f}, P ok {p_satisfied(g, xp):.4f}")
    assert p_satisfied(g, xp) >= 1 - TOL - 1e-4, (cls.__name__, p_satisfied(g, xp))

# Nothing can meet it: with c measured at noise 0.5, the model is never 99.99 % sure
# that c < 0.6 anywhere. The step ignores the limit, with a warning, instead of failing.
NOISY = DATA.assign(c=x + 0.5 * rng.standard_normal(12))
records = []


class Catch(logging.Handler):
    def emit(self, record):
        records.append(record.getMessage())


logging.getLogger().addHandler(Catch())
_, x_any = propose(ExpectedImprovementGenerator, {"c": 1e-4}, data=NOISY)
assert 0.0 <= x_any <= 1.0
assert any("ignores them" in r for r in records), records
print("fallback: no point meets the tolerance -> a point anyway, with a warning")
print("CONSTRAINT RISK TOLERANCE TEST PASSED")
