"""A pacsys FakeBackend whose readings carry noise, as real ACNET readings do.

Each float reading (scalar or array) is multiplied by 1 + rel_noise * N(0, 1), drawn
fresh per read from a seeded generator, so a test sees the same noise every run.
Stored settings (.SETTING) stay exact: they are what was written, not measured.

rel_noise defaults to 0.1% (the user's choice, 2026-11-05): enough that code relying
on exact readings fails, not chosen to match any device. A reading of exactly 0
stays 0 (the noise is relative).

ponytail: only get()/get_many() are noisy; read_fresh (average_events > 1) streams
through other FakeBackend paths and stays exact.

Used by tests/env_smoke_test.py and tests/archetype_test.py:
    from noisy_fake import NoisyFakeBackend
"""
from dataclasses import replace

import numpy as np
from pacsys.testing import FakeBackend


class NoisyFakeBackend(FakeBackend):
    def __init__(self, *args, rel_noise=1e-3, seed=0, **kwargs):
        super().__init__(*args, **kwargs)
        self.rel_noise = rel_noise
        self.rng = np.random.default_rng(seed)

    def get(self, drf, timeout=None):
        r = super().get(drf, timeout)
        v = r.value
        if not r.ok or '.SETTING' in drf.upper() or not self.rel_noise:
            return r
        if isinstance(v, float):
            v = v * (1 + self.rel_noise * self.rng.standard_normal())
        elif isinstance(v, np.ndarray) and np.issubdtype(v.dtype, np.floating):
            v = v * (1 + self.rel_noise * self.rng.standard_normal(v.shape))
        else:
            return r
        return replace(r, value=v)


if __name__ == '__main__':  # self-check
    fb = NoisyFakeBackend()
    fb.set_reading('G:X', 100.0)
    fb.set_reading('G:X.SETTING', 5.0)
    xs = np.array([fb.get('G:X').value for _ in range(2000)])
    assert abs(xs.mean() - 100.0) < 0.02 and 0.08 < xs.std() < 0.12, (xs.mean(), xs.std())
    assert fb.get('G:X.SETTING@I').value == 5.0
    print('NOISY FAKE OK')
