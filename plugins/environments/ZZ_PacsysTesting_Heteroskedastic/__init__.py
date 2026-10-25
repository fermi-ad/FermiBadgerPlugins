"""ZZ_PacsysTesting plus a noisy objective whose noise is known and varies with
position: a testbed for heteroskedastic GP modeling.

Xopt fits a heteroskedastic GP for an objective whenever the data also has a
`<objective>_var` column; this environment supplies one.

    Hetero_f           f(x) = sum over hetero_devices of (reading - 0.5)**2,
                       plus synthetic noise of known sigma(x), averaged over
                       n_samples draws (as averaging over pulses would be on
                       the machine)
    Hetero_f_var       the variance of that mean, estimated from the draws
                       (sample variance / n_samples): what a model is given
    Hetero_f_true_var  the true variance of the mean, sigma(x)**2 / n_samples:
                       logged only, to score how well a model recovers it
                       (scripts/hetero_recovery.py)

sigma(x), with r = |x - noise_center| over hetero_devices:

    proportional  noise_sigma0 + noise_scale * |f|        (multiplicative)
    distance      noise_sigma0 + noise_scale * r          (worse far from nominal)
    bump          noise_sigma0 + noise_scale * exp(-r**2 / (2 noise_width**2))
                                                          (a localized noisy region)

The devices are the same ACNET test/scratch devices as ZZ_PacsysTesting (same
`testing` settings role); their readbacks have no noise of their own.
"""
import numpy as np
from pydantic import PrivateAttr

from environments.ZZ_PacsysTesting import _SQ_OFFSET
from environments.ZZ_PacsysTesting import Environment as PacsysTesting

NOISY = ("Hetero_f", "Hetero_f_var", "Hetero_f_true_var")
SHAPES = ("proportional", "distance", "bump")


def true_sigma(x, f, shape, sigma0, scale, center, width):
    """Noise sigma of one draw at device readings x (array), clean value f."""
    r = np.linalg.norm(np.asarray(x, dtype=float) - center)
    if shape == "proportional":
        return sigma0 + scale * abs(f)
    if shape == "distance":
        return sigma0 + scale * r
    if shape == "bump":
        return sigma0 + scale * np.exp(-0.5 * (r / width) ** 2)
    raise ValueError(f"noise_shape must be one of {SHAPES}, not {shape!r}")


class Environment(PacsysTesting):
    name = "ZZ_PacsysTesting_Heteroskedastic"
    observables = PacsysTesting.observables + list(NOISY)

    hetero_devices: list[str] = ["Z:CUBE_X", "Z:CUBE_Y"]
    noise_shape: str = "proportional"  # proportional, distance or bump
    noise_sigma0: float = 0.1
    noise_scale: float = 0.1
    noise_center: float = 3.0  # same value on every hetero device
    noise_width: float = 2.0
    n_samples: int = 10  # draws averaged per point (>= 2, for a variance)
    seed: int = -1  # -1: a fresh random stream each run
    _rng = PrivateAttr(default=None)

    @property
    def rng(self):
        if self._rng is None:
            self._rng = np.random.default_rng(None if self.seed < 0 else self.seed)
        return self._rng

    def noisy_values(self, x):
        """{Hetero_f, Hetero_f_var, Hetero_f_true_var} at device readings x."""
        if self.n_samples < 2:
            raise ValueError("n_samples must be at least 2 to estimate a variance")
        f = float(np.sum((np.asarray(x, dtype=float) - _SQ_OFFSET) ** 2))
        sigma = true_sigma(
            x, f, self.noise_shape, self.noise_sigma0, self.noise_scale,
            self.noise_center, self.noise_width,
        )
        draws = f + self.rng.normal(0.0, sigma, self.n_samples)
        return {
            "Hetero_f": float(draws.mean()),
            "Hetero_f_var": float(draws.var(ddof=1) / self.n_samples),
            "Hetero_f_true_var": float(sigma**2 / self.n_samples),
        }

    def get_observables(self, observable_names: list[str]) -> dict:
        noisy = [n for n in observable_names if n in NOISY]
        fetch = [n for n in observable_names if n not in NOISY]
        if noisy:
            fetch += [d for d in self.hetero_devices if d not in fetch]
        result = super().get_observables(fetch) if fetch else {}
        if noisy:
            values = self.noisy_values([result[d] for d in self.hetero_devices])
            result |= {n: values[n] for n in noisy}
            for d in self.hetero_devices:  # fetched only to compute the above
                if d not in observable_names:
                    result.pop(d, None)
        return result
