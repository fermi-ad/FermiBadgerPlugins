"""Read noise of ACNET devices from the data logger: its size, shape, and spikes vs mean level.

READ-ONLY: pacsys's write/subscribe calls are disabled the moment it is imported (below).

Steady stretches are found from the readings alone (the RIL settings are logged too, via
the bare DRF, every 1-15 s; cutting at setting changes as well is untested).
Each device's series is cut at time gaps, then into consecutive windows of W readings. A
window counts as steady when its von Neumann ratio eta (mean squared successive
difference / variance) is at least --eta-min. For independent noise about a constant
level eta averages 2; a step or drift inside the window lowers it, and spikes do not.
Steady windows give the noise statistics; each window's mean is its level.

Per device, binned by level (quantiles of the window means):
  std            median window standard deviation (ddof 1), with its IQR
  rel_std        median std / |mean|
  skew, exkurt   median per-window skewness and excess kurtosis
  tail3, tail4   share of readings beyond 3 and 4 robust sigmas of their window median
                 (robust sigma 1.4826 MAD)
  *_gauss        the same statistics for Gaussian noise of the same W, through the same
                 code: the reference that says what "Gaussian" looks like at this W
  R              variance of a window's mean over s^2/W, its variance if readings were
                 independent. From adjacent windows whose 2W readings together pass the
                 eta cut: per pair r = ((m2 - m1)^2 / 2) / (mean of the two s^2 / W), which
                 follows F(1, 2W - 2) for independent Gaussian noise, so R = median(r) /
                 median(F(1, 2W - 2)): robust to dropouts. Pairs are binned by their own
                 mean (m1 + m2) / 2, which is uncorrelated with m2 - m1 for a stationary
                 series; binning by m1 would bias R by regression to the mean. Level steps
                 small enough to pass the cut inflate s^2 and lower R (by ~10 % in --selftest). R = 1 for independent noise; R > 1 means s^2/N (the planned
                 `_var` from average_events) understates the noise of an N-event average,
                 from correlated readings or wander between windows.
Also: the log-log slope p of std vs |mean| (std ~ |mean|^p: 0 constant, 0.5 Poisson-like,
1 proportional noise; shown only if the window means span a factor of 2 or more), the
reading quantum (smallest step between distinct values; robust-sigma tails are not
meaningful when std is within a few quanta), and the share of flat windows (all readings
equal: noise below the quantum, or the logger repeating a value).

Sampling (dt_s in the summary) differs by device: per pulse for some (consecutive events,
as Badger averages them), every 15-60 s for others, where a window of W readings spans
minutes and slow wander counts as noise unless it lowers eta.

Run from the repo root (on the FNAL network):
    pixi run python scripts/logger_noise.py --end 2026-11-17 --days 7 [--devices L:D7TOR G:LINEFF]
    pixi run python scripts/logger_noise.py --selftest      # offline check on synthetic data
Writes <out>/<device>_<end>_<days>d.csv.gz (raw pull, reused on later runs), <out>/summary.md, and
<out>/<device>.png (std vs level).
"""
import argparse
import datetime as dt
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

# "" (bare DRF) first: it returns the finest logged rate (per pulse for L:D7TOR, B:VIMIN,
# and B:BLMLAM, probed 2026-11-18; every 15-60 s for the others)
EVENTS = ("", "p,15000", "p,1000", "e,52", "e,1f")
# Read by the RIL and Booster environments
DEVICES = ["L:D7TOR", "L:TK4RAD", "L:TUNRAD", "L:TK1RAD", "G:LINEFF", "B:BLMLAM",
           "B:BOOEFF", "B:VIMIN"]
DAY_MS = 86_400_000


def guarded_get_many():
    import pacsys

    def refuse(*a, **k):
        raise RuntimeError("logger_noise is read-only: this call is disabled")
    for name in ("write", "write_many", "subscribe", "WriteSettings", "BasicControl"):
        if hasattr(pacsys, name):
            setattr(pacsys, name, refuse)
    return pacsys.get_many


def pull(get_many, device, t1_ms, t2_ms):
    """(event used, DataFrame t_s, value): day by day, trying EVENTS in turn."""
    parts, candidates = [], list(EVENTS)
    for t in range(t1_ms, t2_ms, DAY_MS):
        while candidates:
            ev = candidates[0]
            q = f"{device}{'@' + ev if ev else ''}<-LOGGER:{t}:{min(t + DAY_MS, t2_ms)}"
            try:
                r = get_many([q], timeout=120)[0]
                val = r.value if getattr(r, "ok", False) else None
            except Exception as error:  # noqa: BLE001  a failed day is reported, not fatal
                print(f"  {q}: {error}", file=sys.stderr)
                val = None
            if isinstance(val, dict) and len(val.get("data", ())):
                parts.append(pd.DataFrame({"t_s": np.asarray(val["micros"]) / 1e6,
                                           "value": np.asarray(val["data"], float)}))
                candidates = [ev]  # found: keep it for the remaining days
                break
            if parts:  # the event worked on an earlier day: this day just has no data
                break
            candidates = candidates[1:]
    return (candidates[0] if candidates else None,
            pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["t_s", "value"]))


def windows(t, v, w, eta_min, return_x=False):
    """One row per window of w consecutive readings that does not straddle a time gap
    (a gap: more than 3 median sampling intervals); with return_x, also the readings,
    one window per row."""
    t, v = np.asarray(t, float), np.asarray(v, float)
    dt_med = np.median(np.diff(t)) if len(t) > 1 else 1.0
    segs = np.split(v, np.where(np.diff(t) > 3 * dt_med)[0] + 1)
    X = np.concatenate([s[:len(s) // w * w].reshape(-1, w) for s in segs] + [np.empty((0, w))])
    seg_id = np.concatenate([np.full(len(s) // w, i) for i, s in enumerate(segs)] + [[]])
    var = X.var(axis=1, ddof=1)
    flat = var == 0
    with np.errstate(divide="ignore", invalid="ignore"):
        eta = np.mean(np.diff(X, axis=1) ** 2, axis=1) / var
        dev = np.abs(X - np.median(X, axis=1, keepdims=True))
        z = dev / (1.4826 * np.median(dev, axis=1, keepdims=True))
        steady = ~flat & (eta >= eta_min)
        m = X.mean(axis=1)
        # the next window's mean minus this one's, when the 2W readings of both, together,
        # are steady (so no step falls between them) and contiguous
        Y = np.concatenate([X[:-1], X[1:]], axis=1)
        eta2 = np.mean(np.diff(Y, axis=1) ** 2, axis=1) / Y.var(axis=1, ddof=1)
        pair = np.append(steady[:-1] & steady[1:] & (eta2 >= eta_min) & (np.diff(seg_id) == 0),
                         False)
        nan = np.full(len(m), np.nan)
        r = np.where(pair, np.append(np.diff(m) ** 2 / 2 / ((var[:-1] + var[1:]) / 2 / w), nan[:1]), nan)
        mpair = np.where(pair, np.append((m[:-1] + m[1:]) / 2, nan[:1]), nan)
        df = pd.DataFrame({
            "mean": m, "std": np.where(flat, np.nan, np.sqrt(var)), "r": r, "mpair": mpair,
            "eta": eta, "flat": flat, "steady": steady,
            "skew": stats.skew(X, axis=1), "exkurt": stats.kurtosis(X, axis=1),
            "tail3": np.mean(z > 3, axis=1), "tail4": np.mean(z > 4, axis=1)})
    return (df, X) if return_x else df


def gaussian_reference(w, eta_min, n=20000, seed=0):
    """Median statistics of steady windows of pure Gaussian noise, same w and eta_min."""
    x = np.random.default_rng(seed).standard_normal(n * w)
    win = windows(np.arange(n * w), x, w, eta_min)
    win = win[win.steady]
    return {k: win[k].median() for k in ("skew", "exkurt")} | \
        {k: win[k].mean() for k in ("tail3", "tail4")} | {"R": ratio_r(win.r, w)} | \
        {"steady_share": len(win) / n}


def ratio_r(r, w):
    """R from the per-pair ratios r (see the module docstring)."""
    r = np.asarray(r)[~np.isnan(r)]
    return float(np.median(r) / stats.f.median(1, 2 * w - 2)) if len(r) else np.nan


def summarize(device, df, w, eta_min, bins, ref):
    win = windows(df.t_s, df.value, w, eta_min)
    vals = np.unique(df.value)
    quantum = float(np.min(np.diff(vals))) if len(vals) > 1 else np.nan
    if win.empty:
        return {"device": device, "readings": len(df)}, pd.DataFrame(), win
    st = win[win.steady]
    head = {"device": device, "readings": len(df), "dt_s": float(np.median(np.diff(df.t_s))),
            "windows": len(win),
            "steady": len(st), "flat": int(win.flat.sum()), "quantum": quantum,
            "std/quantum": float(st["std"].median() / quantum), "R": ratio_r(st.r, w)}
    if len(st) < 2 * bins:
        return head, pd.DataFrame(), win
    pos = st[np.abs(st["mean"]) > 0]
    lo, hi = np.quantile(np.abs(pos["mean"]), [0.05, 0.95])
    if hi >= 2 * lo:  # ponytail: a narrower span leaves p to the level jitter, not the noise law
        slope, cov = np.polyfit(np.log(np.abs(pos["mean"])), np.log(pos["std"]), 1, cov=True)
        head |= {"p": slope[0], "p_err": np.sqrt(cov[0, 0])}
    level, edges = pd.qcut(st["mean"], bins, duplicates="drop", retbins=True)
    st = st.assign(level=level)
    g = st.groupby("level", observed=True)
    pair_level = pd.cut(st.mpair, edges, include_lowest=True)
    r_by_level = st.r.groupby(pair_level, observed=False).apply(lambda r: ratio_r(r, w))
    table = pd.DataFrame({
        "windows": g.size(), "mean": g["mean"].median(), "std": g["std"].median(),
        "std_iqr": g["std"].quantile(0.75) - g["std"].quantile(0.25),
        "rel_std": g.apply(lambda d: np.median(d["std"] / np.abs(d["mean"])), include_groups=False),
        "skew": g["skew"].median(), "exkurt": g["exkurt"].median(),
        "tail3": g["tail3"].mean(), "tail4": g["tail4"].mean(),
        "R": r_by_level}).reset_index(drop=True)
    for k in ("skew", "exkurt", "tail3", "tail4", "R"):
        table[k + "_gauss"] = ref[k]
    return head, table, win


def plot(path, device, win, table):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    st = win[win.steady]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.scatter(st["mean"], st["std"], s=4, alpha=0.3, label="steady windows")
    if not table.empty:
        ax.plot(table["mean"], table["std"], "o-", color="k", label="bin medians")
    ax.set(xlabel=f"{device} level (window mean)", ylabel="window std", yscale="log",
           title=f"{device}: read noise vs level")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def fmt(df):
    """A pipe table (pandas' to_markdown needs tabulate, not installed here)."""
    cells = [list(map(str, df.columns))] + [[f"{v:.4g}" if isinstance(v, float) else str(v)
                                              for v in r] for r in df.itertuples(index=False)]
    lines = ["| " + " | ".join(r) + " |" for r in cells]
    lines.insert(1, "|" + "---|" * len(df.columns))
    return "\n".join(lines) + "\n"


def selftest(w=20, eta_min=1.3):
    """Synthetic logger series: random level steps and slow drifts, noise std 0.02 +
    0.05 x level, one series with 1 % spikes of +8 sigma. The steady windows must give back
    the noise law, and the spikes must show in tail4 against the Gaussian reference."""
    rng = np.random.default_rng(1)
    n = 60000
    level = np.repeat(rng.uniform(0.5, 10, n // 100 + 1), rng.integers(30, 170, n // 100 + 1).clip(1))[:n]
    level = level + np.cumsum(rng.standard_normal(n)) * 1e-3  # slow drift
    sd = 0.02 + 0.05 * level
    ref = gaussian_reference(w, eta_min)
    for name, spikes in (("clean", 0.0), ("spiky", 0.01)):
        v = level + sd * (rng.standard_normal(n) + 8.0 * (rng.random(n) < spikes))
        head, table, win = summarize(name, pd.DataFrame({"t_s": np.arange(n) * 15.0, "value": v}),
                                     w, eta_min, 6, ref)
        truth = 0.02 + 0.05 * table["mean"]
        err = np.abs(table["std"] / truth - 1)
        print(f"{name}: {head['steady']}/{head['windows']} steady, p={head['p']:.2f}, "
              f"std/truth-1 max {err.max():.3f}, tail4 {table.tail4.mean():.4f} "
              f"(Gaussian {ref['tail4']:.4f}), R {head['R']:.2f}")
        if spikes == 0:
            assert err.max() < 0.1, table  # median of a W=20 std is biased low by ~2 %
            assert table.tail4.mean() < 3 * ref["tail4"] + 1e-3
            assert abs(head["R"] - 1) < 0.15, head  # independent noise, slow drift only
        else:
            assert table.tail4.mean() > 3 * ref["tail4"]
    # AR(1) noise, lag-1 correlation 0.6: R near (1 + 0.6) / (1 - 0.6) = 4 for large W
    e = np.zeros(n)
    for i in range(1, n):
        e[i] = 0.6 * e[i - 1] + np.sqrt(1 - 0.36) * rng.standard_normal()
    head, _, _ = summarize("ar1", pd.DataFrame({"t_s": np.arange(n) * 15.0, "value": 5 + e}),
                           w, 0.0, 6, ref)
    print(f"ar1: R {head['R']:.2f}")
    assert head["R"] > 2.5, head
    print("logger_noise selftest ok")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--devices", nargs="+", default=list(DEVICES))
    ap.add_argument("--end", default=dt.date.today().isoformat(), help="YYYY-MM-DD, local")
    ap.add_argument("--days", type=float, default=7)
    ap.add_argument("--window", type=int, default=20,
                    help="readings per window, W; >= 20 (at 10 the robust-sigma tails are too "
                         "noisy to show 1 %% spikes: --selftest)")
    ap.add_argument("--eta-min", type=float, default=1.3)
    ap.add_argument("--bins", type=int, default=6)
    ap.add_argument("--out", default="logs/logger_noise")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest(a.window, a.eta_min)
    os.makedirs(a.out, exist_ok=True)
    t2 = int(dt.datetime.fromisoformat(a.end).timestamp() * 1000)
    t1 = int(t2 - a.days * DAY_MS)
    get_many, ref = None, gaussian_reference(a.window, a.eta_min)
    heads, md = [], []
    for device in a.devices:
        cache = os.path.join(a.out, f"{device.replace(':', '_')}_{a.end}_{a.days:g}d.csv.gz")
        if os.path.exists(cache):
            df, event = pd.read_csv(cache), "(cached)"
        else:
            get_many = get_many or guarded_get_many()
            event, df = pull(get_many, device, t1, t2)
            df.to_csv(cache, index=False)
        print(f"{device}: {len(df)} readings, event {event!r}", flush=True)
        head, table, win = summarize(device, df, a.window, a.eta_min, a.bins, ref)
        heads.append(head)
        if not table.empty:
            plot(os.path.join(a.out, device.replace(":", "_") + ".png"), device, win, table)
            md.append(f"## {device}\n\n{fmt(table)}")
    with open(os.path.join(a.out, "summary.md"), "w") as f:
        f.write(f"# Logger read noise, {a.days:g} days to {a.end}\n\n"
                f"`scripts/logger_noise.py`, W = {a.window}, eta_min = {a.eta_min}; Gaussian "
                f"noise passes the steadiness cut in {ref['steady_share']:.0%} of windows.\n\n"
                + fmt(pd.DataFrame(heads)) + "\n" + "\n".join(md))
    print(f"wrote {a.out}/summary.md")


if __name__ == "__main__":
    main()
