"""A pacsys FakeBackend whose readings carry noise, as real ACNET readings do.

Each float reading (scalar or array) is multiplied by 1 + rel_noise * N(0, 1), drawn
fresh per read. Stored settings (.SETTING) stay exact: they are what was written, not
measured. A reading of exactly 0 stays 0 (the noise is relative).

- Seed: new each run, as real runs are not reproducible either. The seed is printed
  to stderr; NOISY_FAKE_SEED=<seed> repeats a run, e.g. to chase a failure.
- Streaming: a subscription (average_events > 1 reads N fresh events through one)
  receives an independently noisy event every event_period seconds for each
  subscribed DRF that has a reading configured, until it is stopped.
- rel_noise defaults to 0.1% (the user's choice, 2026-11-05): enough that code
  relying on exact readings fails, not chosen to match any device.

Used by tests/env_smoke_test.py and tests/archetype_test.py:
    from noisy_fake import NoisyFakeBackend
"""
import itertools
import os
import secrets
import sys
import threading
import time
from dataclasses import replace

import numpy as np
from pacsys.testing import FakeBackend
from pacsys.types import ValueType

SEED = int(os.environ.get('NOISY_FAKE_SEED') or secrets.randbits(32))
print(f'noisy_fake: seed {SEED} (NOISY_FAKE_SEED={SEED} repeats it)', file=sys.stderr)
_instances = itertools.count()


class NoisyFakeBackend(FakeBackend):
    def __init__(self, *args, rel_noise=1e-3, event_period=0.01, **kwargs):
        super().__init__(*args, **kwargs)
        self.rel_noise = rel_noise
        self.event_period = event_period
        self.rng = np.random.default_rng([SEED, next(_instances)])
        self._rng_lock = threading.Lock()  # streaming threads draw too

    def _noisy(self, drf, value):
        if '.SETTING' in drf.upper() or not self.rel_noise:
            return value
        with self._rng_lock:
            if isinstance(value, float):
                return value * (1 + self.rel_noise * self.rng.standard_normal())
            if isinstance(value, np.ndarray) and np.issubdtype(value.dtype, np.floating):
                return value * (1 + self.rel_noise * self.rng.standard_normal(value.shape))
        return value

    def get(self, drf, timeout=None):
        r = super().get(drf, timeout)
        return replace(r, value=self._noisy(drf, r.value)) if r.ok else r

    def subscribe(self, drfs, callback=None, on_error=None):
        handle = super().subscribe(drfs, callback=callback, on_error=on_error)

        def events():  # one noisy event per DRF per period, as on a clock event
            while not handle.stopped:
                for drf in drfs:
                    r = FakeBackend.get(self, drf)
                    if r.ok and not handle.stopped:
                        v = self._noisy(drf, r.value)
                        kind = ValueType.SCALAR_ARRAY if isinstance(v, np.ndarray) else ValueType.SCALAR
                        self.emit_reading(drf, v, value_type=kind)
                time.sleep(self.event_period)

        threading.Thread(target=events, daemon=True).start()
        return handle


if __name__ == '__main__':  # self-check
    from pacsys.exp import read_fresh
    fb = NoisyFakeBackend()
    fb.set_reading('G:X', 100.0)
    fb.set_reading('G:X.SETTING', 5.0)
    xs = np.array([fb.get('G:X').value for _ in range(2000)])
    assert abs(xs.mean() - 100.0) < 0.02 and 0.08 < xs.std() < 0.12, (xs.mean(), xs.std())
    assert fb.get('G:X.SETTING@I').value == 5.0
    fb.set_reading('G:X@e,52,e,0', 100.0)
    (res,) = read_fresh(['G:X@e,52,e,0'], count=5, timeout=2.0, backend=fb)
    events = [r.value for r in res.readings]
    assert len(set(events)) == 5 and all(abs(v - 100.0) < 1.0 for v in events), events
    print('NOISY FAKE OK')
