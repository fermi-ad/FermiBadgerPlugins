"""Offline check of xopt-3.2.2-noise-shapes.patch:

1. P(a fresh reading < bound) for latent N(mean, s^2) plus GaussExp noise, by quadrature,
   against Monte Carlo, for s/sigma_n on both sides of the quadrature's switch.
2. The measured-value risk tolerance with a noise shape: a constraint c = x + noise with a
   heavy upper tail (kR = 0.5), c < 0.6, tolerance 1 %. Told the shape, the generator
   stays further from the edge than when it assumes Gaussian noise, and the true chance of
   a violating reading there is near 1 %; assuming Gaussian noise, it is several times 1 %.
3. robust_outcomes: one gross outlier pulls the standard GP's mean; the robust GP's
   (botorch's RobustRelevancePursuitSingleTaskGP) stays near the truth, and a generator
   proposes a point with it.
4. The staleness check: a run whose noise has 10 % gross outliers, against a Gaussian
   profile, logs a warning; against matching data, nothing.
5. The Jones-Faddy skew-t shape (2026-11-24): its tabulated CDF against scipy; the
   quadrature against Monte Carlo; the risk tolerance with a heavy power-law upper tail
   (Gaussian assumed: several times the tolerance; the skew-t told: near it); its spec
   round-trips, a, b <= 1 is refused; Badger reads a skew-t profile.

Run from the repo root:
    pixi run python tests/noise_shapes_test.py
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
from scipy import stats
from xopt.generators.bayesian.noise_shape import NoiseShape, SkewTShape, make_shape, p_below

warnings.filterwarnings("ignore")
torch.manual_seed(0)
rng = np.random.default_rng(0)


def draw(shape, n):
    """Standardized noise of this shape, by inverting its cdf on a fine grid."""
    zg = np.linspace(-80, 80, 400_001)
    cg = shape.cdf_unit(torch.tensor(zg)).numpy()
    return (np.interp(rng.random(n), cg, zg) - shape.mean) / shape.std


# 1. quadrature vs Monte Carlo
shape = NoiseShape(0.7, 1.2)
e = draw(shape, 2_000_000)
for ratio in (0.1, 1.0, 1.05, 10.0):
    T = rng.standard_normal(e.size) * ratio + e
    for b in np.quantile(T, [0.001, 0.05, 0.5, 0.99]):
        mc = np.mean(T < b)
        q = float(p_below(torch.tensor(b), torch.tensor(0.0), torch.tensor(ratio),
                          torch.tensor(1.0), shape))
        assert abs(q - mc) < max(5 * np.sqrt(mc * (1 - mc) / e.size), 2e-5), (ratio, b, q, mc)
print("1. quadrature agrees with Monte Carlo")

# 2. measured-value risk with a heavy upper tail
heavy = NoiseShape(8.0, 0.5)
SIGMA, BOUND, TOL = 0.03, 0.6, 0.01
x = np.linspace(0.0, 1.0, 60)
DATA = pd.DataFrame({"x": x, "f": -x + 0.01 * rng.standard_normal(60),
                     "c": x + SIGMA * draw(heavy, 60)})


def propose(shapes):
    vocs = VOCS(variables={"x": [0, 1]}, objectives={"f": "MINIMIZE"},
                constraints={"c": ["LESS_THAN", BOUND]})
    gen = ExpectedImprovementGenerator(vocs=vocs, constraint_risk_tolerance={"c": TOL},
                                       constraint_noise_shapes=shapes)
    gen.add_data(DATA)
    with contextlib.redirect_stdout(io.StringIO()):
        return gen, float(gen.generate(1)[0]["x"])


def true_violation(xp):
    """P(c(xp) + noise > BOUND), the noise as drawn: heavy upper tail, SIGMA."""
    return 1 - float(heavy.cdf(torch.tensor((BOUND - xp) / SIGMA)))


gauss_gen, x_gauss = propose(None)
shape_gen, x_shape = propose({"c": {"kL": 8.0, "kR": 0.5}})
v_gauss, v_shape = true_violation(x_gauss), true_violation(x_shape)
print(f"2. Gaussian assumed: x={x_gauss:.4f}, true violation {v_gauss:.2%}; "
      f"shape known: x={x_shape:.4f}, true violation {v_shape:.2%} (tolerance {TOL:.0%})")
assert x_shape < x_gauss, (x_shape, x_gauss)
assert v_gauss > 2 * TOL, v_gauss  # the Gaussian assumption understates this tail
assert v_shape < 2 * TOL, v_shape  # the shape keeps it near the tolerance (the GP's
#                                    noise size and mean are estimates, so not exactly)
assert shape_gen.model_dump()["constraint_noise_shapes"] == {"c": {"kL": 8.0, "kR": 0.5}}
clamped = ExpectedImprovementGenerator(
    vocs=shape_gen.vocs, constraint_noise_shapes={"c": {"kL": 0.0, "kR": 99}})
assert clamped.constraint_noise_shapes == {"c": {"kL": 0.1, "kR": 8.0}}

# 3. robust GP against one gross outlier
xr = np.linspace(0, 1, 25)
yr = np.sin(3 * xr) + 0.02 * rng.standard_normal(25)
yr[12] += 3.0  # a dropout-sized excursion, 150 noise sigmas
ROBUST = pd.DataFrame({"x": xr, "f": yr})


def fit(robust):
    vocs = VOCS(variables={"x": [0, 1]}, objectives={"f": "MINIMIZE"})
    gen = ExpectedImprovementGenerator(
        vocs=vocs, gp_constructor={"name": "standard", "robust_outcomes": ["f"] if robust else []})
    gen.add_data(ROBUST)
    with contextlib.redirect_stdout(io.StringIO()):
        model = gen.train_model()
        point = gen.generate(1)
    with torch.no_grad():
        mean = model.posterior(torch.tensor([[xr[12]]], dtype=torch.double)).mean.item()
    return type(model.models[0]).__name__, abs(mean - np.sin(3 * xr[12])), point


name_s, err_s, _ = fit(False)
name_r, err_r, point = fit(True)
print(f"3. at the outlier: {name_s} misses the truth by {err_s:.3f}, {name_r} by {err_r:.3f}")
assert name_r == "RobustRelevancePursuitSingleTaskGP", name_r
assert err_r < 0.1 < err_s, (err_r, err_s)
assert 0 <= float(point[0]["x"]) <= 1

# 4. staleness check
records = []


class Catch(logging.Handler):
    def emit(self, record):
        records.append(record.getMessage())


logging.getLogger().addHandler(Catch())
xs = np.linspace(0, 1, 80)
spiky = 0.02 * rng.standard_normal(80) + 0.2 * (rng.random(80) < 0.1)
clean = 0.02 * rng.standard_normal(80)
for label, noise, expect in (("spiky", spiky, True), ("clean", clean, False)):
    records.clear()
    vocs = VOCS(variables={"x": [0, 1]}, objectives={"f": "MINIMIZE"},
                constraints={"c": ["LESS_THAN", 0.6]})
    gen = ExpectedImprovementGenerator(vocs=vocs, constraint_risk_tolerance={"c": 0.05},
                                       constraint_noise_shapes={"c": {"kL": 8, "kR": 8}})
    gen.add_data(pd.DataFrame({"x": xs, "f": -xs, "c": xs + noise}))
    with contextlib.redirect_stdout(io.StringIO()):
        gen.generate(1)
    warned = any("heavier tails than the profile" in r for r in records)
    print(f"4. {label} data against a Gaussian profile: warning {'logged' if warned else 'none'}")
    assert warned == expect, records

# 5. skew-t
sk = make_shape({"family": "jf_skew_t", "a": 1.6, "b": 3.0})
dist = stats.jf_skew_t(1.6, 3.0)
m, v = (float(x) for x in dist.stats(moments="mv"))
grid = np.linspace(-30, 30, 2001)
exact = dist.cdf(m + np.sqrt(v) * grid)
table = sk.cdf(torch.tensor(grid)).numpy()
tail = exact < 1e-3
assert np.max(np.abs(table - exact)) < 1e-6, np.max(np.abs(table - exact))
assert np.max(np.abs(table[tail] / exact[tail] - 1)) < 1e-3  # relative, in the far tail
e = (dist.rvs(size=2_000_000, random_state=rng) - m) / np.sqrt(v)
for ratio in (0.1, 1.0, 1.05, 10.0):
    T = rng.standard_normal(e.size) * ratio + e
    for b in np.quantile(T, [0.001, 0.05, 0.5, 0.99]):
        mc = np.mean(T < b)
        q = float(p_below(torch.tensor(b), torch.tensor(0.0), torch.tensor(ratio),
                          torch.tensor(1.0), sk))
        assert abs(q - mc) < max(5 * np.sqrt(mc * (1 - mc) / e.size), 2e-5), (ratio, b, q, mc)
print("5. skew-t: table agrees with scipy, quadrature with Monte Carlo")

heavy_t = stats.jf_skew_t(8.0, 1.3)  # a heavy power-law upper tail
mt, vt = (float(x) for x in heavy_t.stats(moments="mv"))
DATA = pd.DataFrame({"x": x, "f": -x + 0.01 * rng.standard_normal(60),
                     "c": x + SIGMA * (heavy_t.rvs(size=60, random_state=rng) - mt) / np.sqrt(vt)})


def true_violation_t(xp):
    return float(heavy_t.sf(mt + np.sqrt(vt) * (BOUND - xp) / SIGMA))


_, x_gauss = propose(None)
skew_gen, x_skew = propose({"c": {"family": "jf_skew_t", "a": 8.0, "b": 1.3}})
v_gauss, v_skew = true_violation_t(x_gauss), true_violation_t(x_skew)
print(f"5. Gaussian assumed: x={x_gauss:.4f}, true violation {v_gauss:.2%}; "
      f"skew-t known: x={x_skew:.4f}, true violation {v_skew:.2%} (tolerance {TOL:.0%})")
assert x_skew < x_gauss and v_gauss > 1.5 * TOL > v_skew, (x_skew, x_gauss, v_gauss, v_skew)
assert skew_gen.model_dump()["constraint_noise_shapes"] == {
    "c": {"family": "jf_skew_t", "a": 8.0, "b": 1.3}}
try:
    ExpectedImprovementGenerator(vocs=skew_gen.vocs, constraint_noise_shapes={
        "c": {"family": "jf_skew_t", "a": 0.9, "b": 3.0}})
    raise AssertionError("a skew-t with a <= 1 (no finite variance) was accepted")
except ValueError:
    pass
assert isinstance(sk, SkewTShape) and make_shape({"kL": 1, "kR": 2}).spec() == {"kL": 1.0, "kR": 2.0}

import os  # noqa: E402
import tempfile  # noqa: E402
from badger.gui.components.noise_profiles import noise_shapes  # noqa: E402
root = tempfile.mkdtemp()
os.makedirs(os.path.join(root, "noise_profiles"))
with open(os.path.join(root, "noise_profiles", "L_X.yaml"), "w") as f:
    f.write("device: L:X\nfamily: jf_skew_t\nkL: 1.5\nkR: 2.0\njf_skew_t: {a: 2.5, b: 1.8}\n")
with open(os.path.join(root, "noise_profiles", "L_Y.yaml"), "w") as f:
    f.write("device: L:Y\nfamily: gaussexp\nkL: 1.5\nkR: 2.0\n")
assert noise_shapes(root, ["L:X", "L:Y"]) == {
    "L:X": {"family": "jf_skew_t", "a": 2.5, "b": 1.8}, "L:Y": {"kL": 1.5, "kR": 2.0}}
print("NOISE SHAPES TEST PASSED")
