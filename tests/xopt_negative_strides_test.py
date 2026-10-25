"""Regression check for xopt-3.2.2-negative-strides.patch: a BO step must work
when the run's data holds its variable columns in another order than the VOCS
(pandas then returns a reversed view, which torch.tensor rejects). Seen live on
2026-10-25 with TuneQx_SimpleVirtualAccelerator.yaml: the first step after the
initial points failed in TuRBO's get_data_in_trust_region.

Run from the repo root:
    pixi run python tests/xopt_negative_strides_test.py
"""
import numpy as np
import pandas as pd
from xopt import VOCS
from xopt.generators.bayesian import ExpectedImprovementGenerator

vocs = VOCS(variables={"kqd": [-0.9, -0.7], "kqf": [0.7, 0.9]}, objectives={"f": "MINIMIZE"})
rng = np.random.default_rng(0)
data = pd.DataFrame(rng.uniform(size=(4, 3)) * [0.2, 0.2, 1] + [0.7, -0.9, 0], columns=["kqf", "kqd", "f"])
assert data[vocs.variable_names].to_numpy().strides[1] < 0  # the layout that failed

g = ExpectedImprovementGenerator(
    vocs=vocs, turbo_controller={"name": "OptimizeTurboController", "restrict_model_data": True}
)
g.add_data(data)
x = g.generate(1)[0]
assert -0.9 <= x["kqd"] <= -0.7 and 0.7 <= x["kqf"] <= 0.9, x
print("XOPT NEGATIVE STRIDES TEST PASSED")
