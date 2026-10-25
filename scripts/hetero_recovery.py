"""Score how well a GP recovers known heteroskedastic noise, from a Badger run of
ZZ_PacsysTesting_Heteroskedastic (or any run whose data has an objective, its
`<objective>_var` and a `<objective>_true_var` column).

Fits Xopt's heteroskedastic GP (given `<objective>_var`) and its standard GP
(without it), then compares each model's predicted noise variance with the true
one: at the run's points, and, for a run over two variables, as maps over their
ranges. Prints a score per model and writes a PNG.

    pixi run python scripts/hetero_recovery.py <run.yaml> [--out report.png]

Score: median |log10(predicted / true)| at the run's points (0 = perfect; 1 =
off by a factor of 10 typically), and the correlation of the logs (1 = the
model has the right shape, whatever the scale; undefined for a constant).
"""
import argparse
import importlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import yaml
from xopt.generators.bayesian.models.standard import StandardModelConstructor

OBJECTIVE = "Hetero_f"


def fit(data, input_names, input_bounds, objective=OBJECTIVE, heteroskedastic=True):
    """Xopt's model for `objective` (a botorch model), trained on `data`."""
    cols = input_names + [objective] + ([f"{objective}_var"] if heteroskedastic else [])
    model = StandardModelConstructor().build_model(
        input_names, [objective], data[cols].copy(), input_bounds
    )
    return model.models[0]


def noise_variance(model, X):
    """Predicted observation-noise variance at points X (n x d tensor)."""
    with torch.no_grad():
        noisy = model.posterior(X, observation_noise=True).variance
        clean = model.posterior(X).variance
    return (noisy - clean).squeeze(-1).clamp_min(1e-300).numpy()


def score(predicted, true):
    """(median |log10 ratio|, correlation of log10s or nan for a constant)."""
    lp, lt = np.log10(predicted), np.log10(true)
    corr = np.corrcoef(lp, lt)[0, 1] if np.std(lp) > 0 and np.std(lt) > 0 else np.nan
    return float(np.median(np.abs(lp - lt))), float(corr)


def recover(data, input_names, input_bounds, objective=OBJECTIVE):
    """{model name: (model, predicted noise variance at the data's points, score)}."""
    X = torch.tensor(data[input_names].to_numpy(dtype="double").copy())
    true = data[f"{objective}_true_var"].to_numpy(dtype="double")
    out = {}
    for name, hetero in (("heteroskedastic", True), ("standard", False)):
        model = fit(data, input_names, input_bounds, objective, hetero)
        predicted = noise_variance(model, X)
        out[name] = (model, predicted, score(predicted, true))
    return out


def load_run(path):
    """(data, input names, input bounds, environment params) from a run file."""
    run = yaml.safe_load(Path(path).read_text())
    data = pd.DataFrame(run["data"])
    data.index = data.index.astype(int)
    variables = run["generator"]["vocs"]["variables"]
    bounds = {
        n: (v["domain"] if isinstance(v, dict) else v) for n, v in variables.items()
    }
    return data.sort_index(), list(bounds), bounds, run["environment"]


def true_map(env_params, names, grid):
    """True noise variance of the mean over grid points, or None when a device
    defining the noise is not one of the run's variables (its value unknown)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins"))
    env = importlib.import_module("environments.ZZ_PacsysTesting_Heteroskedastic")
    p = {k: f.default for k, f in env.Environment.model_fields.items()} | env_params
    devices = p["hetero_devices"]
    if not set(devices) <= set(names):
        return None
    out = []
    for point in grid:
        x = np.array([point[names.index(d)] for d in devices])
        f = float(np.sum((x - env._SQ_OFFSET) ** 2))
        sigma = env.true_sigma(
            x, f, p["noise_shape"], p["noise_sigma0"], p["noise_scale"],
            p["noise_center"], p["noise_width"],
        )
        out.append(sigma**2 / p["n_samples"])
    return np.array(out)


def report(path, out_png):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    data, names, bounds, env_params = load_run(path)
    data = data.dropna(subset=[OBJECTIVE, f"{OBJECTIVE}_var", f"{OBJECTIVE}_true_var"])
    results = recover(data, names, bounds)
    true = data[f"{OBJECTIVE}_true_var"].to_numpy()

    print(f"{path}: {len(data)} points, variables {names}")
    for name, (_, _, (err, corr)) in results.items():
        print(f"  {name:16s} median |log10(pred/true)| = {err:.3f}   log corr = {corr:.3f}")

    two_d = len(names) == 2
    if two_d:
        (x0, x1), (y0, y1) = bounds[names[0]], bounds[names[1]]
        gx, gy = np.meshgrid(np.linspace(x0, x1, 60), np.linspace(y0, y1, 60))
        grid = np.column_stack([gx.ravel(), gy.ravel()])
        truth = true_map(env_params, names, grid)
        two_d = truth is not None
    fig, axes = plt.subplots(1, 3 if two_d else 1, figsize=(15 if two_d else 5, 4.5))
    axes = np.atleast_1d(axes)
    ax = axes[0]
    for name, (_, predicted, (err, _)) in results.items():
        ax.loglog(true, predicted, "o", ms=4, label=f"{name} ({err:.2f})")
    lo, hi = true.min() / 2, true.max() * 2
    ax.loglog([lo, hi], [lo, hi], "k--", lw=1, label="perfect")
    ax.set_xlabel("true noise variance of the mean")
    ax.set_ylabel("predicted noise variance")
    ax.set_title("At the run's points (median |log10 error|)")
    ax.legend(fontsize=8)

    if two_d:
        learned = noise_variance(results["heteroskedastic"][0], torch.tensor(grid))
        vmin = np.log10(min(learned.min(), truth.min()))
        vmax = np.log10(max(learned.max(), truth.max()))
        for ax, z, title in ((axes[1], truth, "true"), (axes[2], learned, "heteroskedastic GP")):
            im = ax.pcolormesh(gx, gy, np.log10(z).reshape(gx.shape), vmin=vmin, vmax=vmax, shading="auto")
            ax.plot(data[names[0]], data[names[1]], "w.", ms=3)
            ax.set_xlabel(names[0])
            ax.set_ylabel(names[1])
            ax.set_title(f"log10 noise variance: {title}")
        fig.colorbar(im, ax=axes[1:].tolist())
    fig.savefig(out_png, dpi=120, bbox_inches="tight")
    print(f"  wrote {out_png}")
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run", help="a Badger run file (archive .yaml)")
    ap.add_argument("--out", help="PNG to write (default: <run name>.hetero.png here)")
    a = ap.parse_args()
    # not next to the run: keep the archive to run files
    report(a.run, a.out or f"{Path(a.run).stem}.hetero.png")
