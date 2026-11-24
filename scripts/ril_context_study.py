"""Do the ion sources' parameters (parameter page L48, sub-page <1>, tabs SRC_A and SRC_B)
and the Booster's injection turns per cycle type predict what the RIL's objectives reach?

Data: 5-minute bins of logged history (scripts/logger_series.py; the beam-on median of
each bin), bins with beam only (L:D7TOR above BEAM_ON mA). Targets: the losses L:TK4RAD,
L:TUNRAD, L:TK1RAD (lower is better), the output toroid L:D7TOR and G:LINEFF (higher is
better). Predictor groups: source A, source B, turns (G:TURN13..1D), beam cycles (per bin,
from the clock-event history, scripts/event_counts.py: all beam cycles $10, each type: $1D
to BNB, $19 NuMI (via the Main Injector; much higher intensity), $17 Booster studies, $13
fixed target, $14/$15/$16 MI studies, $1C 8 GeV to Muon; NTF parasitic beam $1A; and
the turn-weighted rate, sum over types of cycles x G:TURN<type>, a proxy for the Linac
charge delivered, which drives the integrating loss monitors), the active source (src_B:
1 when source B fed the RIL, from the Linac/PreAcc/Operations logbook's own account,
SOURCE_SWAPS: source B until the swap to A on 2026-09-15 08:39-11:23, source A after;
the swap itself unknown. The data agree: L:SRCNOW, "source now in use" (logged from
2026-10-17), matches source A's toroid except during the 10-22 site power outage. The
larger-toroid rule is not used: the source not in use is often run (A from 08-21 to 09-14
before the swap, B after it), and on 09-09..14 A ran at full current while B fed the RIL.
Each source parameter is also taken from the source in use, active_<param>), the RIL template's own knobs (settings), and combinations.

Models: gradient-boosted trees (scikit-learn HistGradientBoostingRegressor, defaults:
untested choices), scored out of sample with whole weeks held out (GroupKFold by ISO week:
bins next to each other in time cannot leak into the test set).
  R2      share of the target's variance across held-out weeks the group explains
  skill   for the attainable level: a quantile model (10th percentile of losses, 90th of
          toroid and efficiency), 1 - pinball loss / pinball loss of the training weeks'
          constant quantile; > 0 means the group predicts the attainable level
  top     permutation importance (drop in held-out R2 when one predictor is shuffled) for
          the context model (active source + turns + beam cycles), top 8
Correlation is not cause: operators retune sources and the RIL together, and switching
sources changes many predictors at once.

Run from the repo root, after the pull:
    pixi run python scripts/ril_context_study.py [--series logs/logger_series]
        [--out docs/ril-source-context-results.md] [--learning-rate 0.1]
    pixi run python scripts/ril_context_study.py --select [--targets ...]  # see select()
    pixi run python scripts/ril_context_study.py --ranges EXTSV ...  # context-variable ranges
    pixi run python scripts/ril_context_study.py --selftest   # offline, synthetic
"""
import argparse
import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.model_selection import GroupKFold, LeaveOneGroupOut
from math import comb

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from logger_series import load  # noqa: E402
from event_counts import load as load_events  # noqa: E402

TYPES = ["13", "14", "15", "16", "17", "19", "1C", "1D"]
# The source feeding the RIL, from the logbook (entry ids 301867, 301917, 301993, 302280: on
# B; 303026, 303044: swap to A, 2026-09-15 08:39 to 11:23; 306982: on A, 2026-11-06).
# (start, end, source), local time; None = open-ended; outside every interval: unknown.
SOURCE_SWAPS = [(None, "2026-09-15 08:39", "B"), ("2026-09-15 11:23", None, "A")]


def load_all(series, events, devices):
    """Logged bins joined with the beam-cycle counts per bin and the turn-weighted rate."""
    df = load(series, devices)
    ev = load_events(events)
    if len(ev):
        df = df.join(ev, how="left")
        df[list(ev.columns)] = df[list(ev.columns)].fillna(0)
        turns = [(f"${e}", f"G:TURN{e}") for e in TYPES if f"${e}" in df and f"G:TURN{e}" in df]
        df["turn_weighted_rate"] = sum(df[c].fillna(0) * df[t].ffill().fillna(0) for c, t in turns)
    # the source feeding the RIL (logbook), and its parameters
    t = pd.to_datetime(df.index, unit="s", utc=True).tz_convert("America/Chicago").tz_localize(None)
    b = pd.Series(np.nan, index=df.index)
    for t0, t1, src in SOURCE_SWAPS:
        inside = np.ones(len(df), bool)
        if t0:
            inside &= t >= pd.Timestamp(t0)
        if t1:
            inside &= t < pd.Timestamp(t1)
        b[inside] = 1.0 if src == "B" else 0.0
    df["src_B"] = b
    for x in SOURCE:
        if f"L:A{x}" in df and f"L:B{x}" in df:
            df[f"active_{x}"] = np.where(df["src_B"] == 1, df[f"L:B{x}"],
                                         np.where(df["src_B"] == 0, df[f"L:A{x}"], np.nan))
    return df

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
    "active source": ["src_B"] + [f"active_{x}" for x in SOURCE],
    "beam cycles": ["$10"] + [f"${e}" for e in ("13", "14", "15", "16", "17", "19", "1A", "1C", "1D")]
                   + ["turn_weighted_rate"],
    "RIL knobs": ["L:ASOL.SETTING", "L:ATRMHD.SETTING", "L:ATRMHU.SETTING", "L:ATRMVD.SETTING",
                  "L:ATRMVU.SETTING", "L:LSOL.SETTING", "L:LTRMH.SETTING", "L:LTRMV.SETTING",
                  "L:MDQ1H.SETTING", "L:MDQ1V.SETTING", "L:MDQ2H.SETTING", "L:MDQ2V.SETTING",
                  "L:RFBPAH.SETTING", "L:RFQPAH.SETTING"],
}
SETS = {
    "source A": ["source A"], "source B": ["source B"], "turns": ["turns"],
    "beam cycles": ["beam cycles"], "sources": ["source A", "source B"],
    "active source": ["active source"],
    "active + beam": ["active source", "turns", "beam cycles"],
    "sources + beam": ["source A", "source B", "turns", "beam cycles"],
    "RIL knobs": ["RIL knobs"], "all": ["source A", "source B", "turns", "beam cycles", "RIL knobs"],
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


def interaction_test(X, y, weeks, knob_cols, q):
    """Do the knobs' effects depend on the context? Held-out (R2, quantile skill) of trees
    whose knob and context features may only add up (interaction_cst: interactions inside
    each group, none across) against unconstrained trees. Unconstrained clearly better:
    the context changes how the target responds to the knobs."""
    groups = [[i for i, c in enumerate(X.columns) if c in knob_cols],
              [i for i, c in enumerate(X.columns) if c not in knob_cols]]
    folds = GroupKFold(n_splits=min(6, len(np.unique(weeks))))
    out = {}
    for name, cst in (("additive", groups), ("interacting", None)):
        pred, qpred, qconst = (np.full(len(y), np.nan) for _ in range(3))
        for tr, te in folds.split(X, y, weeks):
            kw = dict(learning_rate=LEARNING_RATE, random_state=0, interaction_cst=cst)
            pred[te] = HistGradientBoostingRegressor(**kw).fit(X.iloc[tr], y.iloc[tr]).predict(X.iloc[te])
            qpred[te] = HistGradientBoostingRegressor(loss="quantile", quantile=q, **kw).fit(
                X.iloc[tr], y.iloc[tr]).predict(X.iloc[te])
            qconst[te] = np.quantile(y.iloc[tr], q)
        r2 = 1 - np.sum((y - pred) ** 2) / np.sum((y - y.mean()) ** 2)
        skill = 1 - pinball(y.to_numpy(), qpred, q) / pinball(y.to_numpy(), qconst, q)
        out[name] = (float(r2), float(skill))
    return out


def week_errors(X, y, weeks):
    """Leave-one-week-out: the mean squared error on each held-out week, and the pooled R2."""
    pred, mse = np.full(len(y), np.nan), []
    for tr, te in LeaveOneGroupOut().split(X, y, weeks):
        m = HistGradientBoostingRegressor(learning_rate=LEARNING_RATE, random_state=0)
        pred[te] = m.fit(X.iloc[tr], y.iloc[tr]).predict(X.iloc[te])
        mse.append(float(np.mean((y.iloc[te] - pred[te]) ** 2)))
    return np.array(mse), float(1 - np.sum((y - pred) ** 2) / np.sum((y - y.mean()) ** 2))


def sign_p(wins, n):
    """One-sided sign test: P(at least `wins` of `n` weeks better by chance)."""
    return sum(comb(n, k) for k in range(wins, n + 1)) / 2 ** n


def interaction_weeks(X, y, weeks, knob_cols):
    """The interaction test week by week: leave-one-week-out mean squared error of free
    trees over that of additive ones (interaction_cst), per held-out week."""
    cst = [[i for i, c in enumerate(X.columns) if c in knob_cols],
           [i for i, c in enumerate(X.columns) if c not in knob_cols]]
    mse = {}
    for name, c in (("additive", cst), ("free", None)):
        e = []
        for tr, te in LeaveOneGroupOut().split(X, y, weeks):
            m = HistGradientBoostingRegressor(learning_rate=LEARNING_RATE, random_state=0,
                                              interaction_cst=c).fit(X.iloc[tr], y.iloc[tr])
            e.append(float(np.mean((y.iloc[te] - m.predict(X.iloc[te])) ** 2)))
        mse[name] = np.array(e)
    return mse["free"] / mse["additive"]


def select(X, y, weeks, base, candidates, max_steps=4, alpha=0.05):
    """Forward selection of context features that predict y on held-out weeks beyond `base`.
    Each step adds the candidate with the best pooled R2, if it lowers the error in enough
    held-out weeks: a one-sided sign test over the weeks at alpha / (candidates left)
    (Bonferroni: the best of many is picked). Stops at the first step that fails.
    Returns (chosen, rows of (candidate, R2 before, R2 after, weeks better, weeks, p))."""
    chosen, rows, left = [], [], list(candidates)
    mse0, r20 = week_errors(X[base], y, weeks)
    n = len(mse0)
    for _ in range(max_steps):
        if not left:
            break
        res = {c: week_errors(X[base + chosen + [c]], y, weeks) for c in left}
        best = max(res, key=lambda c: res[c][1])
        wins = int(np.sum(res[best][0] < mse0))
        p = sign_p(wins, n)
        rows.append((best, r20, res[best][1], wins, n, p))
        print(f"  {best}: R2 {r20:.3f} -> {res[best][1]:.3f}, better in {wins}/{n} weeks, "
              f"p {p:.4f} (needs <= {alpha / len(left):.4f})", flush=True)
        if p > alpha / len(left):
            break
        chosen.append(best)
        left.remove(best)
        mse0, r20 = res[best]
    return chosen, rows


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
    # the interaction test: knob k, context c; additive y gains nothing from interactions,
    # interacting y gains clearly
    K = pd.DataFrame({"k": rng.random(n), "c": rng.random(n)})
    for name, yy in (("additive", np.sin(6 * K.k) + 2 * K.c), ("interacting", np.sin(6 * K.k) * (1 + 2 * K.c))):
        r = interaction_test(K, pd.Series(yy + 0.05 * rng.standard_normal(n)), weeks, ["k"], 0.1)
        ratio = (1 - r["interacting"][0]) / (1 - r["additive"][0])  # unexplained variance kept
        print(f"interaction test, {name}: additive R2 {r['additive'][0]:.3f}, interacting "
              f"{r['interacting'][0]:.3f}, unexplained ratio {ratio:.2f}")
        assert (ratio < 0.5) if name == "interacting" else (0.7 < ratio < 1.3), (name, r)
    # selection: y depends on knob k through context c1; c2 is noise. 14 'weeks'.
    m = 2800
    S = pd.DataFrame(rng.random((m, 3)), columns=["k", "c1", "c2"])
    ys = pd.Series(np.sin(6 * S.k) * (1 + 2 * S.c1) + 0.05 * rng.standard_normal(m))
    chosen, _ = select(S, ys, np.repeat(np.arange(14), m // 14), ["k"], ["c1", "c2"])
    assert chosen == ["c1"], chosen
    print("ril_context_study selftest ok")


def main():
    global LEARNING_RATE
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--series", default="logs/logger_series")
    ap.add_argument("--events", default="logs/event_counts")
    ap.add_argument("--out", default="docs/ril-source-context-results.md")
    ap.add_argument("--learning-rate", type=float, default=LEARNING_RATE)
    ap.add_argument("--targets", nargs="+", default=list(TARGETS))
    ap.add_argument("--interactions", action="store_true",
                    help="only the knobs-x-context interaction test (trees), appended to --out")
    ap.add_argument("--weekly", action="store_true",
                    help="with --interactions: leave-one-week-out, each held-out week's error "
                         "ratio (free / additive), for all context and for source parameters only")
    ap.add_argument("--select", action="store_true",
                    help="forward selection of the in-use source's parameters (select()), "
                         "beyond the knobs, beam rate, and which source; appended to --out")
    ap.add_argument("--ranges", nargs="+", metavar="PARAM",
                    help="for each source parameter (e.g. EXTSV), L:A<p> and L:B<p>: min and max "
                         "of the 5-minute medians over the bins with beam while that source fed "
                         "the RIL (the context variables' ranges)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    LEARNING_RATE = a.learning_rate
    devices = list(TARGETS) + ["L:SRCNOW"] + [d for g in GROUPS.values() for d in g if ":" in d]
    df = load_all(a.series, a.events, devices)
    span = f"{pd.to_datetime(df.index.min(), unit='s'):%Y-%m-%d} to {pd.to_datetime(df.index.max(), unit='s'):%Y-%m-%d}"
    df = df[df["L:D7TOR"] > BEAM_ON]
    if a.ranges:
        med = load(a.series, [f"L:{s}{x}" for x in a.ranges for s in "AB"], stat="median").reindex(df.index)
        print(f"{span}; 5-minute medians, bins with beam, source in use")
        for x in a.ranges:
            for src, b in (("A", 0), ("B", 1)):
                v = med.loc[df["src_B"] == b, f"L:{src}{x}"].dropna()
                print(f"L:{src}{x}: [{v.min():.6g}, {v.max():.6g}]  p0.5 {v.quantile(0.005):.6g}, "
                      f"p50 {v.median():.6g}, p99.5 {v.quantile(0.995):.6g}, bins {len(v)}")
        return
    weeks = pd.to_datetime(df.index, unit="s").isocalendar().week.to_numpy()
    groups = {k: [d for d in v if d in df and df[d].notna().mean() > 0.5] for k, v in GROUPS.items()}
    if a.select:
        base = groups["RIL knobs"] + groups["turns"] + groups["beam cycles"] + ["src_B"]
        # candidates: parameters that vary while one source is in use (the others only
        # say which source, which src_B already does)
        cands = [c for c in groups["active source"] if c != "src_B"
                 and any(np.ptp(df.loc[df.src_B == b, c].dropna().quantile([0.01, 0.99])) > 0
                         for b in (0, 1))]
        lines = ["", "## Which source parameters matter? (forward selection, trees)", "",
                 "Leave-one-week-out; base: RIL knobs, turns, beam cycles, and which source. "
                 f"Candidates (parameters of the source in use that vary within a source): "
                 + ", ".join(c.removeprefix("active_") for c in cands) + ". A candidate is "
                 "added if it lowers the error in enough held-out weeks (one-sided sign test, "
                 "Bonferroni over the candidates left, 0.05).", "",
                 "| target | step | added | R2 before | R2 after | weeks better | p | kept |",
                 "|---|---|---|---|---|---|---|---|"]
        for t in a.targets:
            print(t, flush=True)
            ok = df[t].notna()
            chosen, rows = select(df.loc[ok], df.loc[ok, t], weeks[ok.to_numpy()], base, cands)
            for i, (c, r0, r1, w, n, p) in enumerate(rows, 1):
                lines.append(f"| {t} | {i} | {c.removeprefix('active_')} | {r0:.3f} | {r1:.3f} | "
                             f"{w}/{n} | {p:.4f} | {'yes' if c in chosen else 'no'} |")
        with open(a.out, "a") as f:
            f.write("\n".join(lines) + "\n")
        return
    if a.interactions and a.weekly:
        knobs = groups["RIL knobs"]
        sets = {"all context": [d for g in ("active source", "turns", "beam cycles") for d in groups[g]],
                "source parameters": [c for c in groups["active source"] if c != "src_B"]}
        wk = np.unique(weeks)
        lines = ["", "## The interaction test week by week (trees)", "",
                 "Leave-one-week-out; each held-out week's mean squared error, trees free to "
                 "combine knobs and context over trees where they only add (below 1: combining "
                 "helped that week). Weeks better: of " + str(len(wk)) + ", with a one-sided "
                 "sign-test p.", "",
                 "| target | context | weeks better | p | " + " | ".join(f"w{k}" for k in wk) + " |",
                 "|---|---|---|---|" + "---|" * len(wk)]
        for t in a.targets:
            ok = df[t].notna()
            for label, ctx in sets.items():
                r = interaction_weeks(df.loc[ok, knobs + ctx], df.loc[ok, t], weeks[ok.to_numpy()], knobs)
                wins = int(np.sum(r < 1))
                lines.append(f"| {t} | {label} | {wins}/{len(r)} | {sign_p(wins, len(r)):.3f} | "
                             + " | ".join(f"{x:.2f}" for x in r) + " |")
                print(lines[-1], flush=True)
        with open(a.out, "a") as f:
            f.write("\n".join(lines) + "\n")
        return
    if a.interactions:
        knobs = groups["RIL knobs"]
        cols = knobs + [d for g in ("active source", "turns", "beam cycles") for d in groups[g]]
        lines = ["", "## Do the knobs' effects depend on the context? (trees)", "",
                 "Held-out R2 / quantile skill of trees on RIL knobs + context (source in use, "
                 "turns, beam cycles): knob and context features only adding up (interaction_cst) "
                 "vs free to interact; ratio: the interacting model's unexplained variance over the "
                 "additive one's (well below 1: the context changes the knobs' effect).", "",
                 "| target | additive | interacting | ratio |", "|---|---|---|---|"]
        for t in a.targets:
            ok = df[t].notna()
            r = interaction_test(df.loc[ok, cols], df.loc[ok, t], weeks[ok.to_numpy()], knobs, TARGETS[t])
            ratio = (1 - r["interacting"][0]) / (1 - r["additive"][0])
            lines.append(f"| {t} | {r['additive'][0]:.2f} / {r['additive'][1]:.2f} | "
                         f"{r['interacting'][0]:.2f} / {r['interacting'][1]:.2f} | {ratio:.2f} |")
            print(lines[-1], flush=True)
        with open(a.out, "a") as f:
            f.write("\n".join(lines) + "\n")
        return
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
        cols = [d for g in ("active source", "turns", "beam cycles") for d in groups[g]]
        imp = importance(df.loc[ok, cols], df.loc[ok, t], weeks[ok.to_numpy()]).head(8)
        tops.append(f"- {t}: " + ", ".join(f"{d} {v:.3f}" for d, v in imp.items()))
        print(lines[-1], flush=True)
    lines += ["", "Cells: held-out R2 / quantile skill (q = 0.1 for losses, 0.9 for L:D7TOR "
              "and G:LINEFF).", "", "Top predictors (active source + turns + beam cycles; drop in held-out R2 "
              "when shuffled):", ""] + tops
    with open(a.out, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("wrote", a.out)


if __name__ == "__main__":
    main()
