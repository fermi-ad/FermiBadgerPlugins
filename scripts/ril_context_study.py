"""Do the ion sources' parameters (parameter page L48, sub-page <1>, tabs SRC_A and SRC_B)
and the Booster's injection turns per cycle type predict what the RIL's objectives reach?

Data: 5-minute bins of logged history (scripts/logger_series.py; the beam-on median of
each bin), bins with beam only (L:D7TOR above BEAM_ON mA). Targets: the losses L:TK4RAD,
L:TUNRAD, L:TK1RAD (lower is better), the output toroid L:D7TOR and G:LINEFF (higher is
better). Predictor groups: source A, source B, turns (G:TURN13..1D), the RIL template's
own knobs (settings), and combinations.

Models: gradient-boosted trees (scikit-learn HistGradientBoostingRegressor, defaults:
untested choices), scored out of sample with whole weeks held out (GroupKFold by ISO week:
bins next to each other in time cannot leak into the test set).
  R2      share of the target's variance across held-out weeks the group explains
  skill   for the attainable level: a quantile model (10th percentile of losses, 90th of
          toroid and efficiency), 1 - pinball loss / pinball loss of the training weeks'
          constant quantile; > 0 means the group predicts the attainable level
  top     permutation importance (drop in held-out R2 when one predictor is shuffled) for
          the all-context model (sources + turns), top 8
Correlation is not cause: operators retune sources and the RIL together, and switching
sources changes many predictors at once.

Run from the repo root, after the pull:
    pixi run python scripts/ril_context_study.py [--series logs/logger_series]
        [--out docs/ril-source-context-results.md] [--learning-rate 0.1]
    pixi run python scripts/ril_context_study.py --selftest   # offline, synthetic
"""
import argparse
import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.model_selection import GroupKFold

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from logger_series import load  # noqa: E402

warnings.filterwarnings("ignore")
BEAM_ON = 5.0  # mA on L:D7TOR; untested choice (the running level is about 25)
TARGETS = {"L:TK4RAD": 0.1, "L:TUNRAD": 0.1, "L:TK1RAD": 0.1, "L:D7TOR": 0.9, "G:LINEFF": 0.9}
SOURCE = ["EXTI", "EXTV", "EXTSV", "EXTON", "EXTPW", "TOR", "ARCSI", "ARCV", "ARCI", "ARCZ",
          "ARCON", "ARCPW", "GASV", "GASON", "GASOW", "IG", "LCC", "CTEMP", "STEMP", "TTEMP",
          "VTEMP", "BTEMP", "RACKT", "SRCI", "TUBEI", "VLVI", "BOILI", "BSP", "EVS", "EIS"]
GROUPS = {
    "source A": [f"L:A{x}" for x in SOURCE] + ["L:AWRVG"],
    "source B": [f"L:B{x}" for x in SOURCE] + ["L:BGASI"],
    "turns": [f"G:TURN{e}" for e in ("13", "14", "15", "16", "17", "19", "1C", "1D")],
    "RIL knobs": ["L:ASOL.SETTING", "L:ATRMHD.SETTING", "L:ATRMHU.SETTING", "L:ATRMVD.SETTING",
                  "L:ATRMVU.SETTING", "L:LSOL.SETTING", "L:LTRMH.SETTING", "L:LTRMV.SETTING",
                  "L:MDQ1H.SETTING", "L:MDQ1V.SETTING", "L:MDQ2H.SETTING", "L:MDQ2V.SETTING",
                  "L:RFBPAH.SETTING", "L:RFQPAH.SETTING"],
}
SETS = {
    "source A": ["source A"], "source B": ["source B"], "turns": ["turns"],
    "sources": ["source A", "source B"], "sources + turns": ["source A", "source B", "turns"],
    "RIL knobs": ["RIL knobs"], "all": ["source A", "source B", "turns", "RIL knobs"],
}


def pinball(y, q_pred, q):
    d = y - q_pred
    return float(np.mean(np.maximum(q * d, (q - 1) * d)))


LEARNING_RATE = 0.1  # scikit-learn's default; --learning-rate for the sensitivity check


def evaluate(X, y, weeks, q):
    """Out-of-fold R2 and quantile skill, whole weeks held out."""
    folds = GroupKFold(n_splits=min(6, len(np.unique(weeks))))
    pred, qpred, qconst = np.full(len(y), np.nan), np.full(len(y), np.nan), np.full(len(y), np.nan)
    for tr, te in folds.split(X, y, weeks):
        m = HistGradientBoostingRegressor(learning_rate=LEARNING_RATE, random_state=0)
        pred[te] = m.fit(X.iloc[tr], y.iloc[tr]).predict(X.iloc[te])
        mq = HistGradientBoostingRegressor(loss="quantile", quantile=q,
                                           learning_rate=LEARNING_RATE, random_state=0)
        qpred[te] = mq.fit(X.iloc[tr], y.iloc[tr]).predict(X.iloc[te])
        qconst[te] = np.quantile(y.iloc[tr], q)
    r2 = 1 - np.sum((y - pred) ** 2) / np.sum((y - y.mean()) ** 2)
    skill = 1 - pinball(y.to_numpy(), qpred, q) / pinball(y.to_numpy(), qconst, q)
    return float(r2), float(skill)


def importance(X, y, weeks):
    """Permutation importance on held-out weeks, averaged over folds."""
    folds = GroupKFold(n_splits=min(6, len(np.unique(weeks))))
    total = pd.Series(0.0, index=X.columns)
    for tr, te in folds.split(X, y, weeks):
        m = HistGradientBoostingRegressor(random_state=0).fit(X.iloc[tr], y.iloc[tr])
        r = permutation_importance(m, X.iloc[te], y.iloc[te], n_repeats=3, random_state=0)
        total += pd.Series(r.importances_mean, index=X.columns)
    return (total / folds.get_n_splits()).sort_values(ascending=False)


def selftest():
    """Synthetic, 6 'weeks': y = 2 d1 + sin(3 d2) + noise. The driving group must explain
    most of y held out (R2 > 0.5, quantile skill > 0.3); a pure-noise group must not
    (R2 < 0.1); the drivers must top the importance ranking."""
    rng = np.random.default_rng(0)
    n = 3000
    X = pd.DataFrame(rng.random((n, 4)), columns=["d1", "d2", "noise1", "noise2"])
    y = pd.Series(2 * X.d1 + np.sin(3 * X.d2) + 0.1 * rng.standard_normal(n))
    weeks = np.repeat(np.arange(6), n // 6)
    driver, noise = evaluate(X[["d1", "d2"]], y, weeks, 0.1), evaluate(X[["noise1", "noise2"]], y, weeks, 0.1)
    top = list(importance(X, y, weeks).index[:2])
    print("driver (R2, skill):", np.round(driver, 3), "noise:", np.round(noise, 3), "top:", top)
    assert driver[0] > 0.5 and driver[1] > 0.3 and noise[0] < 0.1, (driver, noise)
    assert set(top) == {"d1", "d2"}, top
    print("ril_context_study selftest ok")


def main():
    global LEARNING_RATE
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--series", default="logs/logger_series")
    ap.add_argument("--out", default="docs/ril-source-context-results.md")
    ap.add_argument("--learning-rate", type=float, default=LEARNING_RATE)
    ap.add_argument("--targets", nargs="+", default=list(TARGETS))
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    LEARNING_RATE = a.learning_rate
    devices = list(TARGETS) + [d for g in GROUPS.values() for d in g]
    df = load(a.series, devices)
    span = f"{pd.to_datetime(df.index.min(), unit='s'):%Y-%m-%d} to {pd.to_datetime(df.index.max(), unit='s'):%Y-%m-%d}"
    df = df[df["L:D7TOR"] > BEAM_ON]
    weeks = pd.to_datetime(df.index, unit="s").isocalendar().week.to_numpy()
    groups = {k: [d for d in v if d in df and df[d].notna().mean() > 0.5] for k, v in GROUPS.items()}
    lines = [f"# RIL objectives vs source parameters and turns: results\n",
             f"Generated by `scripts/ril_context_study.py`; {span}, {len(df)} five-minute bins "
             f"with beam (L:D7TOR > {BEAM_ON} mA), {len(np.unique(weeks))} weeks. Predictors "
             "logged in fewer than half the bins are dropped: "
             + ", ".join(d for k, v in GROUPS.items() for d in v if d not in groups[k]) + ".\n",
             "| target | " + " | ".join(SETS) + " |", "|---|" + "---|" * len(SETS)]
    tops = []
    for t in a.targets:
        q = TARGETS[t]
        ok = df[t].notna()
        cells = []
        for name, members in SETS.items():
            cols = [d for g in members for d in groups[g]]
            r2, skill = evaluate(df.loc[ok, cols], df.loc[ok, t], weeks[ok.to_numpy()], q)
            cells.append(f"{r2:.2f} / {skill:.2f}")
        lines.append(f"| {t} | " + " | ".join(cells) + " |")
        cols = [d for g in ("source A", "source B", "turns") for d in groups[g]]
        imp = importance(df.loc[ok, cols], df.loc[ok, t], weeks[ok.to_numpy()]).head(8)
        tops.append(f"- {t}: " + ", ".join(f"{d} {v:.3f}" for d, v in imp.items()))
        print(lines[-1], flush=True)
    lines += ["", "Cells: held-out R2 / quantile skill (q = 0.1 for losses, 0.9 for L:D7TOR "
              "and G:LINEFF).", "", "Top predictors (sources + turns; drop in held-out R2 "
              "when shuffled):", ""] + tops
    with open(a.out, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("wrote", a.out)


if __name__ == "__main__":
    main()
