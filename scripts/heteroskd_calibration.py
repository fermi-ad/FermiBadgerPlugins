"""Calibration of Xopt's heteroskedastic GP against its standard GP (offline mock-up).

Can the noise model's probabilities be trusted, for example a 5 % risk tolerance on a
constraint? One variable x in [0, 1]; a constraint c(x) = 0.6 sin(2 pi x) + x that must
stay below 0.8; at each of n random settings, N noisy draws are averaged, as
average_events would, and recorded with their variance s^2/N (`c_var`). The
heteroskedastic GP gets c and c_var; the standard GP gets c alone. Both are Xopt's own
models (ExpectedImprovementGenerator.train_model, Xopt defaults, as Badger uses them).

Noise scenarios (standard deviation of one draw):
  constant      0.1
  proportional  0.02 + 0.3 x
  bump          0.03 + 0.3 exp(-((x - 0.6) / 0.08)^2)
  step          0.03 below x = 0.5, 0.3 above
  t3, lognormal, spikes: the proportional scale, drawn from a Student-t with 3 degrees
                of freedom, a centered lognormal (skewed), or Gaussian plus a 3 % chance
                of a +8 sigma spike (which also shifts the mean: spikes bias)

Measured over 101 test settings, against 4000 simulated fresh recorded values each:
  cov68/cov95_true    share of settings where the true c lies in the model's 68 % / 95 %
                      interval (latent: model uncertainty only)
  cov68/cov95_meas    share of fresh recorded values inside the predicted 68 % / 95 %
                      interval for a new measurement (model + predicted noise)
  noise_err           median |log10(predicted / actual variance of a recorded value)|
  viol5_meas          among settings the model gives >= 95 % odds that a fresh
                      recorded value satisfies c < 0.8 (a 5 % risk tolerance on the
                      measured value), the actual share that would violate it; honest if
                      <= 0.05. n5_meas: how many settings qualified.
  viol_band_meas      the same, only for settings predicted 95-99 % safe: right at a 5 %
                      tolerance's edge, where calibration matters (honest if 0.01-0.05)
  viol_max_meas       the worst actual violation share among settings predicted >= 95 % safe
  ece_meas            mean |predicted - actual| probability of a fresh recorded value
                      satisfying c < 0.8, over all test settings
  viol5_true          the same as viol5_meas for the true value (the current risk
                      tolerance's view)
  noise_ls, noise_noise  the noise GP's learned length scale (fraction of the range) and
                      its noise on log-variance (heteroskedastic model only)

Run from the repo root (a few minutes at the defaults):
    pixi run python scripts/heteroskd_calibration.py [--seeds 20] [--out docs/heteroskd-calibration]
writes <out>.csv (one row per fit) and <out>.md (median over seeds).

--shapes: does a heavier-tailed noise shape keep a risk tolerance honest? Each scenario's
noise profile is fitted to HISTORY draws of its recorded-value noise in units of its scale
(as the device profiles are fitted to logged readings): Gaussian (no profile), GaussExp
(truncated at 8 robust sigmas, as the profiles are), Student-t, and Jones-Faddy skew-t
(scipy, untruncated). The risk on the measured value is P(f + sigma_n e < 0.8), f the GP's
latent value, sigma_n its noise, e the shape standardized to mean 0 and variance 1 (as in
the xopt noise-shapes patch); computed exactly over f and by Monte Carlo over M_SHAPE
draws of e. Cases: one reading per setting with the standard GP (templates today,
average_events 1), and 5-reading means with the standard and heteroskedastic GPs; 50
points. Scenarios: as above, plus t3_c, lognormal_c, spikes_c: the same shapes at the
constant scale 0.1, so the noise's size is right for the standard GP and only its shape
is at stake. At tolerances 5 % and 1 %:
  edge_viol   actual violation share of the settings predicted at the tolerance's edge
              (P(ok) in [1 - alpha, 1 - alpha/5)); honest if <= alpha
  over        share of fits whose edge violates more than alpha (the number to drive down)
  viol_sel    actual violation share over all settings predicted >= 1 - alpha safe
  n_sel       how many settings qualified
    pixi run python scripts/heteroskd_calibration.py --shapes [--seeds 20]
        [--out docs/heteroskd-shapes-calibration]
"""
import argparse
import contextlib
import io
import logging
import time
import warnings

import numpy as np
import pandas as pd
import torch
from scipy import stats
from scipy.special import ndtr
from scipy.stats import norm
from xopt import VOCS
from xopt.generators.bayesian.expected_improvement import ExpectedImprovementGenerator

logging.disable(logging.WARNING)
warnings.filterwarnings("ignore")

BOUND = 0.8
XT = np.linspace(0.0, 1.0, 101)          # test settings
M_FRESH = 4000                           # simulated fresh recorded values per test setting
NS = (2, 3, 5, 10, 20)
POINTS = (20, 50)


def g(x):
    return 0.6 * np.sin(2 * np.pi * x) + x


def sigma(scenario, x):
    if scenario == "constant" or scenario.endswith("_c"):
        return 0.1 + 0 * x
    if scenario == "bump":
        return 0.03 + 0.3 * np.exp(-(((x - 0.6) / 0.08) ** 2))
    if scenario == "step":
        return np.where(x < 0.5, 0.03, 0.3)
    return 0.02 + 0.3 * x  # proportional, and the scale of the non-Gaussian ones


SCENARIOS = ("constant", "proportional", "bump", "step", "t3", "lognormal", "spikes")


def draws(scenario, x, n_draws, rng):
    """Noise for n_draws readings at each x: array (len(x), n_draws)."""
    s = sigma(scenario, x)[:, None]
    shape = (len(x), n_draws)
    scenario = scenario.removesuffix("_c")  # the same shapes at a constant scale
    if scenario == "t3":
        return s * rng.standard_t(3, shape) / np.sqrt(3.0)  # unit variance
    if scenario == "lognormal":
        z = rng.lognormal(0.0, 0.75, shape)
        mean, std = np.exp(0.75**2 / 2), np.sqrt((np.exp(0.75**2) - 1) * np.exp(0.75**2))
        return s * (z - mean) / std
    if scenario == "spikes":
        return s * (rng.standard_normal(shape) + 8.0 * (rng.random(shape) < 0.03))
    return s * rng.standard_normal(shape)


def fresh(scenario, n_draws, rng):
    """M_FRESH fresh recorded values (means of n_draws) at each test setting."""
    out = np.empty((len(XT), M_FRESH))
    for j in range(0, M_FRESH, 500):  # in chunks, to bound memory at N = 20
        k = min(500, M_FRESH - j)
        noise = draws(scenario, np.repeat(XT, k), n_draws, rng).mean(axis=1).reshape(len(XT), k)
        out[:, j:j + k] = g(XT)[:, None] + noise
    return out


def fit(data, heteroskd):
    vocs = VOCS(variables={"x": [0.0, 1.0]}, objectives={"c": "MINIMIZE"})
    gen = ExpectedImprovementGenerator(vocs=vocs)
    gen.add_data(data if heteroskd else data.drop(columns="c_var"))
    with contextlib.redirect_stdout(io.StringIO()):
        return gen.train_model().models[0]


def evaluate(model, truth_fresh):
    X = torch.tensor(XT, dtype=torch.double).unsqueeze(-1)
    with torch.no_grad():
        latent = model.posterior(X)
        meas = model.posterior(X, observation_noise=True)
    mu = latent.mean.detach().squeeze(-1).numpy()
    sf = latent.variance.detach().clamp_min(1e-15).sqrt().squeeze(-1).numpy()
    so = meas.variance.detach().clamp_min(1e-15).sqrt().squeeze(-1).numpy()
    true, F = g(XT), truth_fresh
    row = {}
    for level, z in ((68, norm.ppf(0.84)), (95, norm.ppf(0.975))):
        row[f"cov{level}_true"] = float(np.mean(np.abs(true - mu) <= z * sf))
        row[f"cov{level}_meas"] = float(np.mean(np.abs(F - mu[:, None]) <= z * so[:, None]))
    noise_pred = np.clip(so**2 - sf**2, 1e-15, None)
    row["noise_err"] = float(np.median(np.abs(np.log10(noise_pred / F.var(axis=1)))))
    p_meas = norm.cdf((BOUND - mu) / so)
    p_true = norm.cdf((BOUND - mu) / sf)
    actual_meas_ok = np.mean(F <= BOUND, axis=1)
    sel = p_meas >= 0.95
    row["n5_meas"] = int(sel.sum())
    row["viol5_meas"] = float(np.mean(1 - actual_meas_ok[sel])) if sel.any() else np.nan
    band = (p_meas >= 0.95) & (p_meas < 0.99)  # right at a 5 % tolerance's edge
    row["viol_band_meas"] = float(np.mean(1 - actual_meas_ok[band])) if band.any() else np.nan
    sel = p_meas >= 0.95
    row["viol_max_meas"] = float(np.max(1 - actual_meas_ok[sel])) if sel.any() else np.nan
    row["ece_meas"] = float(np.mean(np.abs(p_meas - actual_meas_ok)))
    sel = p_true >= 0.95
    row["n5_true"] = int(sel.sum())
    row["viol5_true"] = float(np.mean(true[sel] > BOUND)) if sel.any() else np.nan
    noise_model = getattr(getattr(model.likelihood, "noise_covar", None), "noise_model", None)
    if noise_model is not None:
        row["noise_ls"] = float(noise_model.covar_module.lengthscale.detach().squeeze())
        row["noise_noise"] = float(noise_model.likelihood.noise.detach().squeeze())
    return row


HISTORY = 20_000   # 'logged' noise draws each profile is fitted to
M_SHAPE = 50_000   # standardized draws of each fitted shape (Monte Carlo over the noise)
SHAPE_SCENARIOS = ("constant", "t3", "lognormal", "spikes", "t3_c", "lognormal_c", "spikes_c")
SHAPE_CASES = ((1, "standard"), (5, "standard"), (5, "heteroskd"))
ALPHAS = (0.05, 0.01)


def fit_shapes(scenario, n_draws, rng):
    """{shape: standardized noise draws (mean 0, variance 1), None for Gaussian, or a
    reason}: each family fitted to HISTORY draws of the recorded-value noise / its scale."""
    import sys
    sys.path.insert(0, "scripts")
    from noise_shape_fit import GaussExp, gaussexp_moments, gaussexp_sample
    x = rng.random(HISTORY)
    z = draws(scenario, x, n_draws, rng).mean(axis=1) / sigma(scenario, x)
    out = {"gaussian": None}
    ge = GaussExp().fit(z, cut=8)
    m, sd = gaussexp_moments(ge.kl, ge.kr)
    out["gaussexp"] = (gaussexp_sample(ge.kl, ge.kr, M_SHAPE, rng) - m) / sd
    for name, dist in (("t", stats.t), ("skew_t", stats.jf_skew_t)):
        par = dist.fit(z)
        mean, var = (float(v) for v in dist.stats(*par, moments="mv"))
        out[name] = ((dist.rvs(*par, size=M_SHAPE, random_state=rng) - mean) / np.sqrt(var)
                     if np.isfinite(var) else "infinite variance")
    return out


def p_ok(mu, sf, sn, e):
    """P(f + sn e < BOUND), f ~ N(mu, sf^2): Gaussian e in closed form, else exact over f
    and Monte Carlo over the draws e."""
    if e is None:
        return ndtr((BOUND - mu) / np.sqrt(sf ** 2 + sn ** 2))
    return np.array([ndtr((BOUND - m - n * e) / max(f, 1e-12)).mean() for m, f, n in zip(mu, sf, sn)])


def shape_rows(model, truth_fresh, shapes):
    X = torch.tensor(XT, dtype=torch.double).unsqueeze(-1)
    with torch.no_grad():
        lat, meas = model.posterior(X), model.posterior(X, observation_noise=True)
    mu = lat.mean.detach().squeeze(-1).numpy()
    sf = lat.variance.detach().clamp_min(1e-15).sqrt().squeeze(-1).numpy()
    sn = np.sqrt(np.clip(meas.variance.detach().squeeze(-1).numpy() - sf ** 2, 1e-15, None))
    actual_bad = np.mean(truth_fresh > BOUND, axis=1)
    rows = []
    for name, e in shapes.items():
        if isinstance(e, str):
            continue
        p = p_ok(mu, sf, sn, e)
        for alpha in ALPHAS:
            sel, edge = p >= 1 - alpha, (p >= 1 - alpha) & (p < 1 - alpha / 5)
            ev = float(np.mean(actual_bad[edge])) if edge.any() else np.nan
            rows.append({"shape": name, "alpha": alpha, "n_sel": int(sel.sum()),
                         "viol_sel": float(np.mean(actual_bad[sel])) if sel.any() else np.nan,
                         "edge_viol": ev, "over": float(ev > alpha) if edge.any() else np.nan})
    return rows


def shapes_main(seeds, out):
    # check: Monte Carlo over Gaussian draws matches the closed form
    rng = np.random.default_rng(0)
    e = rng.standard_normal(M_SHAPE)
    mu, sf, sn = np.array([0.5, 0.7, 0.75]), np.array([0.01, 0.05, 0.2]), np.array([0.1, 0.05, 0.02])
    assert np.allclose(p_ok(mu, sf, sn, e), p_ok(mu, sf, sn, None), atol=0.004)
    rows, t0, fitted = [], time.time(), []
    for scenario in SHAPE_SCENARIOS:
        for n_draws, model_name in SHAPE_CASES:
            rng = np.random.default_rng(7)
            shapes = fit_shapes(scenario, n_draws, rng)
            fitted.append(f"- {scenario}, N = {n_draws}: " + ", ".join(
                f"{k} {v}" for k, v in shapes.items() if isinstance(v, str)) if any(
                isinstance(v, str) for v in shapes.values()) else "")
            truth_fresh = fresh(scenario, n_draws, np.random.default_rng(1000 + n_draws))
            for seed in range(seeds):
                rng = np.random.default_rng(seed)
                x = rng.random(50)
                d = draws(scenario, x, n_draws, rng)
                data = pd.DataFrame({"x": x, "c": g(x) + d.mean(axis=1),
                                     "c_var": d.var(axis=1, ddof=1) / n_draws if n_draws > 1 else np.nan})
                torch.manual_seed(seed)
                try:
                    model = fit(data, model_name == "heteroskd")
                except Exception as error:  # noqa: BLE001  a failed fit is reported
                    rows.append({"scenario": scenario, "N": n_draws, "model": model_name,
                                 "seed": seed, "error": f"{type(error).__name__}"})
                    continue
                for r in shape_rows(model, truth_fresh, shapes):
                    rows.append({"scenario": scenario, "N": n_draws, "model": model_name,
                                 "seed": seed, **r})
            print(f"{scenario:10s} N={n_draws} {model_name:9s} done ({time.time() - t0:4.0f} s)", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(out + ".csv", index=False)
    summary = (df.dropna(subset=["shape"]).groupby(["scenario", "N", "model", "alpha", "shape"], sort=False)
               .agg(edge_viol=("edge_viol", "median"), over=("over", "mean"),
                    viol_sel=("viol_sel", "median"), n_sel=("n_sel", "median"))
               .round(3).reset_index())
    with open(out + ".md", "w") as f:
        f.write(f"# Noise shapes and risk-tolerance calibration: {seeds} seeds, 50 points\n\n"
                "Generated by `scripts/heteroskd_calibration.py --shapes`; column meanings in its "
                "docstring. edge_viol, viol_sel, n_sel: medians over seeds; over: share of fits "
                "whose edge violates more than alpha (lower is better).\n\n")
        f.write(markdown_table(summary))
        notes = [n for n in fitted if n]
        if notes:
            f.write("\nShapes not used:\n\n" + "\n".join(notes) + "\n")
        if "error" in df:
            f.write(f"\nFailed fits: {int(df['error'].notna().sum())}\n")
    print(f"wrote {out}.csv and {out}.md ({time.time() - t0:.0f} s)")


def markdown_table(df):
    """A pipe table (pandas' to_markdown needs tabulate, not installed here)."""
    cells = [[str(c) for c in df.columns]] + [
        ["" if (isinstance(v, float) and np.isnan(v)) else str(v) for v in row]
        for row in df.itertuples(index=False)]
    lines = ["| " + " | ".join(r) + " |" for r in cells]
    lines.insert(1, "|" + "---|" * len(df.columns))
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--out", default=None)
    ap.add_argument("--shapes", action="store_true", help="noise shapes vs risk calibration")
    a = ap.parse_args()
    if a.shapes:
        return shapes_main(a.seeds, a.out or "docs/heteroskd-shapes-calibration")
    a.out = a.out or "docs/heteroskd-calibration"
    rows, t0 = [], time.time()
    for scenario in SCENARIOS:
        for n_draws in NS:
            truth_fresh = fresh(scenario, n_draws, np.random.default_rng(1000 + n_draws))
            for n_points in POINTS:
                for seed in range(a.seeds):
                    rng = np.random.default_rng(seed)
                    x = rng.random(n_points)
                    d = draws(scenario, x, n_draws, rng)
                    data = pd.DataFrame({"x": x, "c": g(x) + d.mean(axis=1),
                                         "c_var": d.var(axis=1, ddof=1) / n_draws})
                    torch.manual_seed(seed)
                    for model_name, heteroskd in (("heteroskd", True), ("standard", False)):
                        try:
                            row = evaluate(fit(data, heteroskd), truth_fresh)
                        except Exception as error:  # a failed fit is a result too
                            row = {"error": f"{type(error).__name__}: {error}"[:120]}
                        rows.append({"scenario": scenario, "N": n_draws, "points": n_points,
                                     "seed": seed, "model": model_name, **row})
            print(f"{scenario:12s} N={n_draws:2d} done ({time.time() - t0:5.0f} s)", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(a.out + ".csv", index=False)
    metrics = ["cov68_true", "cov95_true", "cov68_meas", "cov95_meas", "noise_err",
               "viol5_meas", "n5_meas", "viol_band_meas", "viol_max_meas", "ece_meas",
               "viol5_true", "n5_true", "noise_ls", "noise_noise"]
    summary = (df.groupby(["scenario", "points", "N", "model"], sort=False)[metrics]
               .median().round(3).reset_index())
    with open(a.out + ".md", "w") as f:
        f.write("# Heteroskedastic GP calibration: medians over "
                f"{a.seeds} seeds\n\nGenerated by `scripts/heteroskd_calibration.py`; "
                "column meanings in its docstring. Ideal: cov68 0.68, cov95 0.95, "
                "noise_err 0, viol5 <= 0.05.\n\n")
        f.write(markdown_table(summary))
        if "error" in df:
            f.write(f"\nFailed fits: {int(df['error'].notna().sum())} of {len(df)}\n")
    print(f"wrote {a.out}.csv and {a.out}.md ({time.time() - t0:.0f} s)")


if __name__ == "__main__":
    main()
