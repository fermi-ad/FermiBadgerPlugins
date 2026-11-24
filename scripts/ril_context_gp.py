"""Are the ion-source parameters contextual variables for RIL tuning: do they only shift
an objective's level, or change how it responds to the RIL knobs? GP kernels on logged
history decide (data and targets as scripts/ril_context_study.py).

Inputs: x = the RIL template's knob settings (14), c = context: the CONTEXT_K source
parameters of the source in use (and which source), turns, and beam-cycle counts
(with the turn-weighted rate) ranked highest by the boosted-tree study's permutation importance
(a data-driven, untested choice of how many; c is kept small so an ARD kernel stays
fittable). Models, each an exact GP (botorch SingleTaskGP, standardized outputs,
inputs scaled to [0, 1]):
  M0 knobs          RBF-ARD over x
  M1 additive       RBF-ARD(x) + RBF-ARD(c): context shifts the level only
  M2 interacting    RBF-ARD over (x, c): context may change the response to the knobs
  M3 context        RBF-ARD over c
Scored on held-out weeks (GroupKFold by ISO week; each fold fits on N_TRAIN bins drawn
from the other weeks and tests on up to N_TEST bins of the held-out week):
  R2     share of the held-out variance the GP mean explains
  lpd    mean log predictive density per bin (the GP's noise included), higher is better
M2 clearly above M1 means interaction: contextual BO (context measured each step and
held fixed while the acquisition is optimized) would help. M1 or M2 above M0 means the
context explains level changes the knobs do not. Caveat: the knobs move only in tuning
sessions, so the data may say little about the response to them at all; the knobs'
spread over the span is printed. Correlation is not cause.

Run from the repo root, after the pull:
    pixi run python scripts/ril_context_gp.py [--series logs/logger_series]
        [--out docs/ril-source-context-gp.md] [--context-k 10] [--n-train 1000]
    pixi run python scripts/ril_context_gp.py --selftest   # offline, synthetic
"""
import argparse
import os
import sys
import warnings

import numpy as np
import pandas as pd
import torch
from botorch.fit import fit_gpytorch_mll
from botorch.models import SingleTaskGP
from botorch.models.transforms import Normalize, Standardize
from gpytorch.kernels import AdditiveKernel, RBFKernel, ScaleKernel
from gpytorch.mlls import ExactMarginalLogLikelihood
from sklearn.model_selection import GroupKFold

sys.path.insert(0, os.path.dirname(__file__))
from logger_series import load  # noqa: E402
from ril_context_study import BEAM_ON, GROUPS, importance, load_all  # noqa: E402

warnings.filterwarnings("ignore")
TARGETS = ["L:TK4RAD", "L:TUNRAD", "L:D7TOR", "G:LINEFF"]
CONTEXT_K = 10
N_TRAIN, N_TEST = 1000, 500


def gp(X, y, kind, nx):
    """kind: 'joint' (one ARD RBF over all columns) or 'additive' (first nx columns + rest)."""
    d = X.shape[1]
    if kind == "additive":
        covar = AdditiveKernel(ScaleKernel(RBFKernel(ard_num_dims=nx, active_dims=list(range(nx)))),
                               ScaleKernel(RBFKernel(ard_num_dims=d - nx, active_dims=list(range(nx, d)))))
    else:
        covar = ScaleKernel(RBFKernel(ard_num_dims=d))
    m = SingleTaskGP(X, y, covar_module=covar, input_transform=Normalize(d),
                     outcome_transform=Standardize(1))
    fit_gpytorch_mll(ExactMarginalLogLikelihood(m.likelihood, m))
    return m


def fit_score(Xtr, ytr, Xte, yte, kind, nx):
    """(R2, lpd) on the test set, or NaN when the fit fails (botorch's ModelFittingError)."""
    try:
        return score(gp(Xtr, ytr, kind, nx), Xte, yte)
    except Exception as error:  # noqa: BLE001  one failed fit is a result, not an abort
        print(f"  {kind} fit failed: {type(error).__name__}", flush=True)
        return float("nan"), float("nan")


def score(m, X, y):
    with torch.no_grad():
        post = m.posterior(X, observation_noise=True)
    mu, var = post.mean.squeeze(-1), post.variance.squeeze(-1).clamp_min(1e-12)
    r2 = 1 - float(((y.squeeze(-1) - mu) ** 2).sum() / ((y - y.mean()) ** 2).sum())
    lpd = float((-0.5 * torch.log(2 * torch.pi * var) - 0.5 * (y.squeeze(-1) - mu) ** 2 / var).mean())
    return r2, lpd


def compare(X_all, y_all, w, nx, rng, n_train=N_TRAIN):
    """Held-out (R2, lpd) per model, averaged over week folds."""
    res = {k: [] for k in ("M0", "M1", "M2", "M3")}
    for tr, te in GroupKFold(n_splits=min(6, len(np.unique(w)))).split(X_all, y_all, w):
        tr = rng.choice(tr, min(n_train, len(tr)), replace=False)
        te = rng.choice(te, min(N_TEST, len(te)), replace=False)
        Xtr, ytr, Xte, yte = X_all[tr], y_all[tr], X_all[te], y_all[te]
        res["M0"].append(fit_score(Xtr[:, :nx], ytr, Xte[:, :nx], yte, "joint", nx))
        res["M1"].append(fit_score(Xtr, ytr, Xte, yte, "additive", nx))
        res["M2"].append(fit_score(Xtr, ytr, Xte, yte, "joint", nx))
        res["M3"].append(fit_score(Xtr[:, nx:], ytr, Xte[:, nx:], yte, "joint", nx))
    return {k: (float(np.nanmean([r for r, _ in v])), float(np.nanmean([l for _, l in v])))
            for k, v in res.items()}


def selftest():
    """Synthetic: knobs x (2), context c (2), 6 'weeks'. Additive: y = sin(6 x1) + x2 +
    2 c1; interacting: y = sin(6 x1) (1 + 2 c1). Additive: context helps on its own (M1
    clearly above M0) and the joint kernel adds nothing (M2 about M1). Interacting: context
    has no effect averaged over the knob, so M1 = M0, and only the joint kernel finds it
    (M2 clearly above M1)."""
    rng = np.random.default_rng(0)
    n = 1800
    x, c = rng.random((n, 2)), rng.random((n, 2))
    w = np.repeat(np.arange(6), n // 6)
    noise = 0.05 * rng.standard_normal(n)
    X = torch.tensor(np.hstack([x, c]), dtype=torch.double)
    for name, y in (("additive", np.sin(6 * x[:, 0]) + x[:, 1] + 2 * c[:, 0] + noise),
                    ("interacting", np.sin(6 * x[:, 0]) * (1 + 2 * c[:, 0]) + noise)):
        r = compare(X, torch.tensor(y[:, None], dtype=torch.double), w, 2, rng, n_train=500)
        print(name, {k: (round(a, 3), round(b, 3)) for k, (a, b) in r.items()})
        gap = r["M2"][1] - r["M1"][1]
        if name == "additive":
            assert r["M1"][1] > r["M0"][1] + 0.3 and gap < 0.1, (name, r)
        else:
            assert gap > 0.3, (name, r)
    print("ril_context_gp selftest ok")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--series", default="logs/logger_series")
    ap.add_argument("--events", default="logs/event_counts")
    ap.add_argument("--out", default="docs/ril-source-context-gp.md")
    ap.add_argument("--context-k", type=int, default=CONTEXT_K)
    ap.add_argument("--n-train", type=int, default=N_TRAIN)
    ap.add_argument("--targets", nargs="+", default=TARGETS)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    knobs = GROUPS["RIL knobs"]
    ctx_all = GROUPS["active source"] + GROUPS["turns"] + GROUPS["beam cycles"]
    src = [d for g in ("source A", "source B") for d in GROUPS[g]] + ["L:SRCNOW"]
    df = load_all(a.series, a.events, list(dict.fromkeys(  # L:D7TOR always: the beam-on cut
        ["L:D7TOR"] + a.targets + knobs + src + [c for c in ctx_all if ":" in c])))
    df = df[df["L:D7TOR"] > BEAM_ON]
    knobs = [k for k in knobs if k in df and df[k].notna().mean() > 0.9]
    ctx_all = [c for c in ctx_all if c in df and df[c].notna().mean() > 0.9]
    weeks = pd.to_datetime(df.index, unit="s").isocalendar().week.to_numpy()
    rng = np.random.default_rng(0)
    spread = (df[knobs].quantile(0.95) - df[knobs].quantile(0.05)).round(4)
    lines = ["# RIL objectives: are the source parameters contextual? GP kernels\n",
             f"Generated by `scripts/ril_context_gp.py`: {len(df)} five-minute bins with beam, "
             f"{len(np.unique(weeks))} weeks; {len(knobs)} knob settings, context = top "
             f"{a.context_k} of {len(ctx_all)} source and turns parameters by boosted-tree importance "
             f"(per target). Cells: held-out R2 / mean log predictive density.\n",
             "| target | M0 knobs | M1 additive | M2 interacting | M3 context | context used |",
             "|---|---|---|---|---|---|"]
    for t in a.targets:
        sub = df.dropna(subset=[t] + knobs + ctx_all)
        w = weeks[df.index.isin(sub.index)]
        ctx = list(importance(sub[ctx_all], sub[t], w).head(a.context_k).index)
        # a constant column (a setting never changed) cannot be scaled to [0, 1]: drop it
        kn = [k for k in knobs if sub[k].std() > 0]
        ctx = [c for c in ctx if sub[c].std() > 0]
        X_all = torch.tensor(sub[kn + ctx].to_numpy(), dtype=torch.double)
        y_all = torch.tensor(sub[[t]].to_numpy(), dtype=torch.double)
        res = compare(X_all, y_all, w, len(kn), rng, a.n_train)
        cell = {k: f"{r2:.2f} / {lpd:.2f}" for k, (r2, lpd) in res.items()}
        lines.append(f"| {t} | {cell['M0']} | {cell['M1']} | {cell['M2']} | {cell['M3']} | "
                     + ", ".join(ctx) + " |")
        print(lines[-1], flush=True)
    lines += ["", "Knob spread over the span (p95 - p5 of the 5-minute values):", "",
              ", ".join(f"{k} {v}" for k, v in spread.items())]
    with open(a.out, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("wrote", a.out)


if __name__ == "__main__":
    main()
