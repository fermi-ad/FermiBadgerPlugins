"""Which distribution fits a device's read noise, tails included? Fits candidate families to
the noise in steady stretches of data-logger readings and checks their tail probabilities
on held-out data: the numbers a risk tolerance depends on.

Input: raw pulls cached by `scripts/logger_noise.py` (no network). Steady windows as there
(W readings, von Neumann ratio eta >= eta_min). Each reading's residual from the median
of the other W - 1 readings of its window (not the mean: one dropout would shift every
other reading of its window; not the median of all W: the two middle readings would always
sit near 0, a false cusp that pulls fits toward a Laplace shape), over
sqrt(1 + pi / (2 (W - 1))) (that residual's Gaussian variance, large-W form) times
sigma(level): the median window std of its level bin (6 quantile bins), interpolated. So z
is the noise in units of its typical size at that level, about 1 if it is Gaussian.

Families (scipy.stats, maximum likelihood; location and scale fitted too):
  norm         Gaussian: the GP's assumption
  t            Student-t: symmetric, heavy tails
  skewnorm     skewed, Gaussian tails
  johnsonsu    Johnson SU: skew and heavy tails, 4 parameters
  jf_skew_t    Jones-Faddy skew-t: skew and heavy tails, different tail on each side
  contam       (1 - eps) N(mu, s) + eps N(mu2, s2): Gaussian with an outlier component
               (dropouts, spikes)
  gaussexp     Gaussian core, exponential tail on each side beyond kL and kR sigmas, value
               and first derivative continuous at both splices (two-sided "GaussExp"; the
               classic Crystal Ball has a power-law tail instead)
  crystalball  scipy's classic Crystal Ball: Gaussian core, power-law tail on the low side

Fit on the first half of the steady windows in time, tested on the second half:
  dll          mean log-likelihood per reading vs the Gaussian, on the test half (> 0 better)
  lo/hi alpha  the share of test readings beyond the family's predicted alpha quantile
               (lo: below its alpha quantile; hi: above its 1 - alpha quantile), over alpha.
               1 = calibrated; > 1 means the family understates that tail's risk, the
               dangerous direction for a risk tolerance of alpha.

With --profiles DIR, also writes DIR/<device>.yaml: the GaussExp shape (kL, kR, fitted
to all steady windows, within K_MIN to K_MAX), its standardized moments, sigma vs level, and the
held-out calibration, for the measured-value risk tolerance in Xopt
(xopt-3.2.2-noise-shapes patch; Badger attaches plugins/noise_profiles/<device>.yaml).

Run from the repo root:
    pixi run python scripts/noise_shape_fit.py [files ...] [--out docs/noise-shape-fit.md]
        [--profiles plugins/noise_profiles]
"""
import datetime as dt
import argparse
import os
import sys
import warnings

import numpy as np
import pandas as pd
from scipy import optimize, stats

sys.path.insert(0, os.path.dirname(__file__))
from logger_noise import fmt, windows  # noqa: E402

warnings.filterwarnings("ignore")
FILES = ["logs/logger_noise/L_D7TOR_2026-11-18_1d.csv.gz",
         "logs/logger_noise/B_BLMLAM_2026-11-18_1d.csv.gz",
         "logs/logger_noise/slow14/L_TK1RAD_2026-11-18_14d.csv.gz",
         "logs/logger_noise/slow14/G_LINEFF_2026-11-18_14d.csv.gz",
         "logs/logger_noise/slow14/B_BOOEFF_2026-11-18_14d.csv.gz"]
ALPHAS = (0.001, 0.01, 0.05)
CUT = 8.0  # robust sigmas: profile fits exclude gross outliers beyond (dropouts, trips)
K_MIN, K_MAX = 0.1, 8.0  # splices in sigmas; beyond 8 a tail is Gaussian to 1e-15 (none),
# and below 0.1 the core vanishes (a degenerate Laplace limit)
MAX_FIT = 200_000  # readings per fit; ponytail: a random subsample keeps the generic MLEs fast


class Contam:
    """(1 - eps) N(mu, s) + eps N(mu2, s2), by direct maximum likelihood."""
    name = "contam"

    def fit(self, z):
        def nll(p):
            eps = 1 / (1 + np.exp(-p[0]))
            pdf = (1 - eps) * stats.norm.pdf(z, p[1], np.exp(p[2])) + \
                eps * stats.norm.pdf(z, p[3], np.exp(p[4]))
            return -np.sum(np.log(pdf + 1e-300))
        p = optimize.minimize(nll, [-4.0, 0.0, 0.0, 0.0, np.log(4.0)], method="Nelder-Mead",
                              options={"maxiter": 4000, "xatol": 1e-4, "fatol": 1e-3}).x
        self.eps, self.p = 1 / (1 + np.exp(-p[0])), p
        return self

    def logpdf(self, z):
        p = self.p
        return np.log((1 - self.eps) * stats.norm.pdf(z, p[1], np.exp(p[2]))
                      + self.eps * stats.norm.pdf(z, p[3], np.exp(p[4])) + 1e-300)

    def cdf(self, z):
        p = self.p
        return (1 - self.eps) * stats.norm.cdf(z, p[1], np.exp(p[2])) + \
            self.eps * stats.norm.cdf(z, p[3], np.exp(p[4]))

    def ppf(self, q):
        return optimize.brentq(lambda z: self.cdf(z) - q, -1e3, 1e3)

    def describe(self):
        p = self.p
        return (f"eps {self.eps:.3g}: N({p[1]:.2f}, {np.exp(p[2]):.2f}) + "
                f"N({p[3]:.2f}, {np.exp(p[4]):.2f})")


class GaussExp:
    """Gaussian core on [-kL, kR] (in sigmas from mu), exponential tails beyond, matched in
    value and slope: log f = -z^2/2 inside, kL^2/2 + kL z below -kL, kR^2/2 - kR z above kR."""
    name = "gaussexp"

    def _norm(self, kl, kr):  # integral of the unnormalized density, in z units
        return (np.sqrt(2 * np.pi) * (stats.norm.cdf(kr) - stats.norm.cdf(-kl))
                + np.exp(-kl ** 2 / 2) / kl + np.exp(-kr ** 2 / 2) / kr)

    def _logpdf(self, x, mu, sig, kl, kr):
        z = (x - mu) / sig
        core = np.where(z < -kl, kl ** 2 / 2 + kl * z,
                        np.where(z > kr, kr ** 2 / 2 - kr * z, -z ** 2 / 2))
        return core - np.log(self._norm(kl, kr) * sig)

    def fit(self, x, cut=None):
        """Maximum likelihood; with cut, only readings within cut robust sigmas of the
        median, with the likelihood truncated to that range (gross outliers excluded)."""
        med = np.median(x)
        mad = 1.4826 * np.median(np.abs(x - med))
        lo, hi = np.log(K_MIN), np.log(K_MAX)
        a, b = (med - cut * mad, med + cut * mad) if cut else (-np.inf, np.inf)
        x = x[(x >= a) & (x <= b)]

        def nll(p):
            kl, kr = np.exp(np.clip(p[2:], lo, hi))
            sig = np.exp(p[1])
            mass = (self._cdf(b, p[0], sig, kl, kr) - self._cdf(a, p[0], sig, kl, kr)
                    if cut else 1.0)
            return -np.sum(self._logpdf(x, p[0], sig, kl, kr)) + len(x) * np.log(max(mass, 1e-300))
        p = optimize.minimize(nll, [med, np.log(mad), np.log(2.0), np.log(2.0)],
                              method="Nelder-Mead",
                              options={"maxiter": 4000, "xatol": 1e-5, "fatol": 1e-3}).x
        self.mu, self.sig = p[0], np.exp(p[1])
        self.kl, self.kr = np.exp(np.clip(p[2:], lo, hi))
        return self

    def logpdf(self, x):
        return self._logpdf(x, self.mu, self.sig, self.kl, self.kr)

    def cdf(self, x):
        return self._cdf(x, self.mu, self.sig, self.kl, self.kr)

    def _cdf(self, x, mu, sig, kl, kr):
        if np.isscalar(x) and np.isinf(x):
            return 1.0 if x > 0 else 0.0
        z = (np.asarray(x, float) - mu) / sig
        n = self._norm(kl, kr)
        left = np.exp(kl ** 2 / 2 + kl * np.minimum(z, -kl)) / kl
        core = np.exp(-kl ** 2 / 2) / kl + np.sqrt(2 * np.pi) * (
            stats.norm.cdf(np.clip(z, -kl, kr)) - stats.norm.cdf(-kl))
        right = n - np.exp(kr ** 2 / 2 - kr * np.maximum(z, kr)) / kr
        return np.where(z < -kl, left, np.where(z > kr, right, core)) / n

    def ppf(self, q):
        return optimize.brentq(lambda x: self.cdf(x) - q, self.mu - 1e3 * self.sig,
                               self.mu + 1e3 * self.sig)

    def describe(self):
        return f"mu {self.mu:.3g}, sigma {self.sig:.3g}, kL {self.kl:.3g}, kR {self.kr:.3g}"


class Scipy:
    def __init__(self, dist):
        self.dist, self.name = dist, dist.name

    def fit(self, z):
        self.params = self.dist.fit(z)
        return self

    def logpdf(self, z):
        return self.dist.logpdf(z, *self.params)

    def cdf(self, z):
        return self.dist.cdf(z, *self.params)

    def ppf(self, q):
        return self.dist.ppf(q, *self.params)

    def describe(self):
        return ", ".join(f"{v:.3g}" for v in self.params)


def families():
    return [Scipy(stats.norm), Scipy(stats.t), Scipy(stats.skewnorm), Scipy(stats.johnsonsu),
            Scipy(stats.jf_skew_t), Contam(), GaussExp(), Scipy(stats.crystalball)]


def residuals(df, w, eta_min, bins=6):
    """z per reading of each steady window, and each window's time order."""
    win, X = windows(df.t_s, df.value, w, eta_min, return_x=True)
    keep = win.steady.values
    win, X = win[keep], X[keep]
    level = pd.qcut(win["mean"], bins, duplicates="drop")
    sig = win["std"].groupby(level, observed=True).median()
    centers = win["mean"].groupby(level, observed=True).median()
    sigma = np.interp(win["mean"], centers.values, sig.values)
    # median of the other w - 1: the upper middle value for readings in the lower half
    order = np.sort(X, axis=1)
    lower_half = np.argsort(np.argsort(X, axis=1), axis=1) < w // 2
    others = np.where(lower_half, order[:, [w // 2]], order[:, [(w - 1) // 2]])
    z = (X - others) / np.sqrt(1 + np.pi / (2 * (w - 1))) / sigma[:, None]
    return z


def fit_device(path, w, eta_min, rng, df=None, z=None):
    df = pd.read_csv(path) if df is None else df
    z = residuals(df, w, eta_min) if z is None else z
    half = len(z) // 2
    train, test = z[:half].ravel(), z[half:].ravel()
    if len(train) > MAX_FIT:
        train = rng.choice(train, MAX_FIT, replace=False)
    rows, ll_norm = [], None
    for fam in families():
        try:
            fam.fit(train)
        except Exception as error:  # noqa: BLE001  a failed fit is reported
            rows.append({"family": fam.name, "params": f"failed: {error}"[:60]})
            continue
        ll = float(np.mean(fam.logpdf(test)))
        ll_norm = ll if fam.name == "norm" else ll_norm
        row = {"family": fam.name, "dll": ll - ll_norm}
        for a in ALPHAS:
            row[f"lo {a:g}"] = np.mean(test < fam.ppf(a)) / a
        for a in ALPHAS:
            row[f"hi {a:g}"] = np.mean(test > fam.ppf(1 - a)) / a
        row["params"] = fam.describe()
        rows.append(row)
    obs = {"family": "test readings", "params": f"n = {len(test)}"}
    return pd.DataFrame(rows + [obs])


def gaussexp_moments(kl, kr):
    """Mean and standard deviation of the unit GaussExp(kL, kR) (mu 0, sigma 1), in closed
    form: the core's Gaussian moments over [-kL, kR] plus each exponential tail's."""
    el, er = np.exp(-kl ** 2 / 2), np.exp(-kr ** 2 / 2)
    core = np.sqrt(2 * np.pi) * (stats.norm.cdf(kr) - stats.norm.cdf(-kl))
    n = core + el / kl + er / kr
    m1 = -el / kl ** 2 + er / kr ** 2
    m2 = core + el * (2 / kl + 2 / kl ** 3) + er * (2 / kr + 2 / kr ** 3)
    mean = m1 / n
    return mean, np.sqrt(m2 / n - mean ** 2)


def write_profile(directory, device, path, df, z, w, eta_min, table):
    """plugins/noise_profiles/<device>.yaml, from all steady windows of this pull."""
    import yaml
    flat = z.ravel()
    sub = flat if flat.size <= MAX_FIT else np.random.default_rng(0).choice(flat, MAX_FIT, replace=False)
    g = GaussExp().fit(sub, cut=CUT)
    kl, kr = g.kl, g.kr
    med = np.median(flat)
    mad = 1.4826 * np.median(np.abs(flat - med))
    outside = np.abs(flat - med) > CUT * mad
    # held-out calibration of the truncated fit: first half fits, second half tests
    half = len(z) // 2
    train, test = z[:half].ravel(), z[half:].ravel()
    train = train if train.size <= MAX_FIT else np.random.default_rng(1).choice(train, MAX_FIT, replace=False)
    gh = GaussExp().fit(train, cut=CUT)
    test = test[np.abs(test - med) <= CUT * mad]
    a, b = med - CUT * mad, med + CUT * mad
    mass_lo, mass = gh.cdf(a), gh.cdf(b) - gh.cdf(a)

    def q(p):  # quantile of the fit truncated to [a, b]
        return optimize.brentq(lambda x: (gh.cdf(x) - mass_lo) / mass - p, a, b)
    heldout = {f"lo {p:g}": round(float(np.mean(test < q(p)) / p), 3) for p in (0.01, 0.05)}
    heldout |= {f"hi {p:g}": round(float(np.mean(test > q(1 - p)) / p), 3) for p in (0.01, 0.05)}
    mean, std = gaussexp_moments(kl, kr)
    win = windows(df.t_s, df.value, w, eta_min)
    st = win[win.steady]
    level = pd.qcut(st["mean"], 6, duplicates="drop")
    sig = st.groupby(level, observed=True).agg(level=("mean", "median"), std=("std", "median"))
    profile = {
        "device": device,
        "family": "gaussexp",
        "kL": round(float(kl), 4), "kR": round(float(kr), 4),
        "unit_mean": round(float(mean), 5), "unit_std": round(float(std), 5),
        "note": "noise = sigma(level) * (Z - unit_mean) / unit_std, Z ~ GaussExp(kL, kR): "
                "Gaussian core, exponential tails beyond -kL and +kR sigmas. Xopt's "
                "measured-value risk takes only the shape (kL, kR); the scale comes from "
                "the run's own GP.",
        "source": os.path.basename(path),
        "logged_every_s": round(float(np.median(np.diff(df.t_s))), 3),
        "steady_readings": int(z.size),
        "window": w, "eta_min": eta_min,
        "sigma_vs_level": [[round(float(a), 6), round(float(b), 6)]
                           for a, b in zip(sig["level"], sig["std"])],
        "gross_outlier_cut_sigmas": CUT,
        "gross_outlier_rate": float(f"{outside.mean():.3g}"),
        "heldout_exceedance_over_alpha": heldout,
        "fitted": dt.date.today().isoformat(),
        "by": "scripts/noise_shape_fit.py",
    }
    os.makedirs(directory, exist_ok=True)
    out = os.path.join(directory, device.replace(":", "_") + ".yaml")
    with open(out, "w") as f:
        yaml.safe_dump(profile, f, sort_keys=False, width=88)
    return out


def gaussexp_sample(kl, kr, n, rng):
    """Draws from the unit GaussExp(kL, kR), by inverting its cdf on a fine grid."""
    g = GaussExp()
    g.mu, g.sig, g.kl, g.kr = 0.0, 1.0, kl, kr
    x = np.linspace(-40, 40, 400_001)
    return np.interp(rng.random(n), g.cdf(x), x)


def selftest():
    """Synthetic noise with known tails: the matching family must fit best, and be calibrated."""
    rng = np.random.default_rng(0)
    for name, z in (("t4", stats.t.rvs(4, size=200_000, random_state=rng)),
                    ("contam", np.where(rng.random(200_000) < 0.01, rng.normal(-6, 1, 200_000),
                                        rng.normal(0, 1, 200_000))),
                    ("gaussexp", gaussexp_sample(1.2, 2.0, 200_000, rng))):
        half = len(z) // 2
        res = {}
        for fam in families():
            fam.fit(z[:half])
            res[fam.name] = float(np.mean(fam.logpdf(z[half:])))
            if fam.name == {"t4": "t", "contam": "contam", "gaussexp": "gaussexp"}[name]:
                ratio = np.mean(z[half:] < fam.ppf(0.001)) / 0.001
                assert 0.8 < ratio < 1.25, (name, ratio)
        best = max(res, key=res.get)
        print(f"{name}: best {best}; norm dll {res['norm'] - res[best]:.4f}")
        assert res["norm"] < res[best] - 0.005, res
        assert best in {"t4": ("t", "johnsonsu", "jf_skew_t", "gaussexp"),
                        "contam": ("contam", "johnsonsu", "jf_skew_t"),
                        "gaussexp": ("gaussexp",)}[name], best
        if name == "gaussexp":
            g = GaussExp().fit(z[:half])
            assert abs(g.kl - 1.2) < 0.1 and abs(g.kr - 2.0) < 0.15, g.describe()
            x = np.linspace(-6, 6, 2001)  # the density integrates to 1, and the cdf agrees
            m, sd = gaussexp_moments(g.kl, g.kr)
            xs = np.linspace(-60, 60, 200_001)
            pdf = np.exp(g.logpdf(xs))
            num_m = np.trapezoid(xs * pdf, xs)
            num_sd = np.sqrt(np.trapezoid((xs - num_m) ** 2 * pdf, xs))
            assert abs(g.mu + g.sig * m - num_m) < 1e-4 and abs(g.sig * sd - num_sd) < 1e-4
            assert abs(np.trapezoid(np.exp(g.logpdf(x)), x) - 1) < 1e-3
            assert abs(g.cdf(0.7) - np.trapezoid(np.exp(g.logpdf(x[x <= 0.7])), x[x <= 0.7])) < 2e-3
    print("noise_shape_fit selftest ok")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("files", nargs="*", default=FILES)
    ap.add_argument("--window", type=int, default=20)
    ap.add_argument("--eta-min", type=float, default=1.3)
    ap.add_argument("--out", default="docs/noise-shape-fit.md")
    ap.add_argument("--profiles", help="also write <dir>/<device>.yaml noise profiles")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    rng = np.random.default_rng(0)
    parts = [f"# Read-noise shape fits\n\nGenerated by `scripts/noise_shape_fit.py` (column "
             f"meanings in its docstring), W = {a.window}, eta_min = {a.eta_min}.\n"]
    for path in a.files:
        device = os.path.basename(path).split("_20")[0].replace("_", ":", 1)
        df = pd.read_csv(path)
        z = residuals(df, a.window, a.eta_min)
        table = fit_device(path, a.window, a.eta_min, rng, df, z)
        if a.profiles:
            print("wrote", write_profile(a.profiles, device, path, df, z, a.window,
                                         a.eta_min, table))
        print(device, flush=True)
        print(table.drop(columns="params").round(3).to_string(index=False), flush=True)
        parts.append(f"## {device}\n\n`{path}`\n\n{fmt(table)}")
    with open(a.out, "w") as f:
        f.write("\n".join(parts))
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
