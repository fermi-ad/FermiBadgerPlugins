"""Offline checks of ZZ_PacsysTesting_Heteroskedastic and scripts/heteroskd_recovery.py,
no control network needed (pacsys FakeBackend; nothing is written).

Covers: the noisy observables come back without the devices fetched to compute
them; each noise shape's sigma; the variance estimate is unbiased; and, on
synthetic runs, Xopt's heteroskedastic GP recovers the noise better than the
standard GP for each shape, writing the PNG report.

Run from the repo root:
    pixi run python tests/heteroskd_noise_test.py
"""
import importlib
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, "plugins")
sys.path.insert(0, "scripts")

from pacsys.testing import FakeBackend  # noqa: E402
from interfaces.BasicPacsysInterface import Interface  # noqa: E402
import heteroskd_recovery  # noqa: E402

env_mod = importlib.import_module("environments.ZZ_PacsysTesting_Heteroskedastic")
Env, true_sigma = env_mod.Environment, env_mod.true_sigma

# --- through the interface: noisy values, no leaked devices ---------------------------
fb = FakeBackend()
for d, v in {"G:AMANDA": 1.0, "Z:CUBE_X": 2.0, "Z:CUBE_Y": -1.0, "Z:CUBE_Z": 0.0}.items():
    for drf in (d, f"{d}.READING", f"{d}.SETTING"):
        fb.set_reading(drf, v)
intf = Interface()
intf._backend_override = fb
intf._timeout = 1.0
env = Env(interface=intf, seed=1)
names = ["Heteroskd_f", "Heteroskd_f_var", "Heteroskd_f_true_var", "CUBE_Z_sq"]
obs = env.get_observables(names)
assert sorted(obs) == sorted(names), obs
f = (2.0 - 0.5) ** 2 + (-1.0 - 0.5) ** 2  # clean value at CUBE_X = 2, CUBE_Y = -1
assert obs["Heteroskd_f_true_var"] == (0.1 + 0.1 * f) ** 2 / 10, obs
assert abs(obs["Heteroskd_f"] - f) < 6 * np.sqrt(obs["Heteroskd_f_true_var"]), obs
assert obs["CUBE_Z_sq"] == 0.25 and not fb.writes

# --- the shapes ------------------------------------------------------------------------
x = np.array([3.0, 7.0])  # r = 4 from a center of 3 along CUBE_Y
assert true_sigma(x, 5.0, "proportional", 0.1, 0.2, 3.0, 2.0) == 0.1 + 0.2 * 5.0
assert true_sigma(x, 5.0, "distance", 0.1, 0.2, 3.0, 2.0) == 0.1 + 0.2 * 4.0
assert np.isclose(true_sigma(x, 5.0, "bump", 0.1, 0.2, 3.0, 2.0), 0.1 + 0.2 * np.exp(-2.0))
try:
    true_sigma(x, 5.0, "wobbly", 0.1, 0.2, 3.0, 2.0)
    raise AssertionError("unknown shape accepted")
except ValueError:
    pass
try:
    Env(n_samples=1).noisy_values([0.0, 0.0])
    raise AssertionError("n_samples=1 accepted")
except ValueError:
    pass

# --- the variance estimate is unbiased -------------------------------------------------
env = Env(seed=2, noise_shape="distance", noise_scale=0.5)
v = [env.noisy_values([4.0, 4.0]) for _ in range(4000)]
ratio = np.mean([e["Heteroskd_f_var"] for e in v]) / v[0]["Heteroskd_f_true_var"]
assert abs(ratio - 1) < 0.05, ratio


# --- recovery, per shape, on synthetic runs over CUBE_X, CUBE_Y in [-5, 5] -------------
def synthetic_run(shape, n=80, seed=3, **params):
    env = Env(seed=seed, noise_shape=shape, **params)
    rng = np.random.default_rng(seed)
    pts = rng.uniform(-5, 5, size=(n, 2))
    rows = [{"Z:CUBE_X": a, "Z:CUBE_Y": b, **env.noisy_values([a, b])} for a, b in pts]
    return pd.DataFrame(rows), env


bounds = {"Z:CUBE_X": [-5.0, 5.0], "Z:CUBE_Y": [-5.0, 5.0]}
names = list(bounds)
cases = {
    "proportional": {},
    "distance": {"noise_scale": 0.5, "noise_center": 0.0},
    "bump": {"noise_sigma0": 0.5, "noise_scale": 2.0, "noise_center": 2.0, "noise_width": 1.5},
}
for shape, params in cases.items():
    data, env = synthetic_run(shape, **params)
    res = heteroskd_recovery.recover(data, names, bounds)
    (h_err, h_corr), (s_err, _) = res["heteroskedastic"][2], res["standard"][2]
    print(f"{shape:12s} heteroskedastic err {h_err:.2f} corr {h_corr:.2f}   standard err {s_err:.2f}")
    assert h_err < s_err and h_corr > 0.6, (shape, h_err, h_corr, s_err)

# The model's noise floor (MIN_INFERRED_NOISE_LEVEL = 1e-4, after standardizing the
# objective): a background far quieter than that is overstated, here ~35x, while the
# noisy region is still right. Documented in the environment's README.
data, env = synthetic_run("bump", **(cases["bump"] | {"noise_sigma0": 0.05}))
res = heteroskd_recovery.recover(data, names, bounds)
q = np.log10(res["heteroskedastic"][1] / data["Heteroskd_f_true_var"].to_numpy())
quiet = data["Heteroskd_f_true_var"] < data["Heteroskd_f_true_var"].median()
assert np.median(q[quiet]) > 1 and abs(np.median(q[~quiet])) < 0.5, q

# --- the report, from a run file as Badger archives it ---------------------------------
data, env = synthetic_run("distance", **cases["distance"])
run = {
    "data": {c: {str(i): float(v) for i, v in data[c].items()} for c in data},
    "generator": {"vocs": {"variables": {n: {"domain": b} for n, b in bounds.items()}}},
    "environment": {"name": env.name, **env.model_dump(exclude={"interface"})},
}
tmp = Path(tempfile.mkdtemp())
(tmp / "run.yaml").write_text(yaml.safe_dump(run))
heteroskd_recovery.report(str(tmp / "run.yaml"), str(tmp / "run.png"))
assert (tmp / "run.png").stat().st_size > 10_000

print("HETEROSKD NOISE TEST PASSED")
