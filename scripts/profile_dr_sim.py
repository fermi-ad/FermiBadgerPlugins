"""Where a Delivery Ring simulation evaluation spends its time (read only).

For each DR simulation template: the cold lattice load and a warm (cached) one, which
set_variables path is taken, set_variables, twiss with and without the chromatic pass,
a full evaluation as Badger makes it, the optimizer's own step (GP fit plus
acquisition, on synthetic data, so no simulation time), and a cProfile of the
evaluations.

Run from the repo root (no network needed):
    pixi run python scripts/profile_dr_sim.py [N]      # N repeats per phase, default 20
"""
import os
os.environ.setdefault('TQDM_DISABLE', '1')  # xtrack's conversion progress bar
import cProfile
import importlib
import io
import logging
import platform
import pstats
import statistics
import sys
import time
import warnings
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

logging.disable(logging.WARNING)
warnings.filterwarnings('ignore')
sys.path.insert(0, 'plugins')
N = int(sys.argv[1]) if len(sys.argv) > 1 else 20  # untested whether results depend on N
TEMPLATES = sorted(Path('tuning_templates/simulation').glob('DR_*.yaml'))

env_mod = importlib.import_module('environments.99_Sim_VirtualAccelerator_MADXSuite')
Env = env_mod.Environment
Intf = importlib.import_module('interfaces.VirtualAccelerator_MADXSuiteInterface').Interface

# Time the environment's internal steps wherever they are called from.
inner = defaultdict(list)
for meth in ('_load_lattice', '_load_deferred', '_verify_rewrite', '_reuse_cached_lattice',
             '_deduce_variables', '_deduce_observables', '_write_varcache', '_compute_twiss',
             '_update_madx_variables'):
    orig = getattr(Env, meth)

    def timed(*a, _orig=orig, _name=meth, **kw):
        t = time.perf_counter()
        try:
            return _orig(*a, **kw)
        finally:
            inner[_name].append(time.perf_counter() - t)
    setattr(Env, meth, staticmethod(timed) if isinstance(Env.__dict__[meth], staticmethod) else timed)


def clock(fn, *a, **kw):
    t = time.perf_counter()
    out = fn(*a, **kw)
    return time.perf_counter() - t, out


def stats(xs):
    xs = sorted(xs)
    return statistics.median(xs), xs[0], xs[-1]


def row(label, xs, total=None):
    med, lo, hi = stats(xs)
    share = f'{100 * med / total:5.1f}%' if total else '      '
    print(f'  {label:44s} {med * 1e3:9.1f} ms  [{lo * 1e3:8.1f} – {hi * 1e3:8.1f}]  {share}  n={len(xs)}')


def quiet(fn, *a, **kw):
    import contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


def optimizer_step(t):
    """GP fit plus acquisition for one new point, at 10, 50, and 100 points of data."""
    from badger.gui.utils import filter_generator_config
    from xopt import VOCS
    from xopt.generators import get_generator
    v = t['vocs']
    vocs = VOCS(variables=v['variables'], objectives=v['objectives'],
                constraints=v.get('constraints') or {}, observables=v.get('observables') or [])
    name = t['generator']['name']
    import copy
    cfg = filter_generator_config(name, copy.deepcopy(t['generator']))
    cfg.pop('vocs', None)
    rng = np.random.default_rng(0)
    out = {}
    for n in (10, 50, 100):
        dom = {k: list(getattr(d, 'domain', d)) for k, d in vocs.variables.items()}
        df = pd.DataFrame({k: rng.uniform(lo, hi, n) for k, (lo, hi) in dom.items()})
        z = sum((df[k] - np.mean(d)) / np.ptp(d) for k, d in dom.items())
        for i, obj in enumerate(vocs.objectives):
            df[obj] = (z - 0.1 * i) ** 2 + 0.01 * rng.standard_normal(n)
        for c in [*vocs.constraints, *vocs.observables]:
            df[c] = 1.0 + 0.01 * rng.standard_normal(n)
        times = []
        for _ in range(3):
            gen = get_generator(name)(vocs=vocs, **copy.deepcopy(cfg))  # it pops 'name' in place
            gen.add_data(df)
            dt, _ = clock(quiet, gen.generate, 1)
            times.append(dt)
        out[n] = times
    return name, out


print(f'Machine: {platform.node()} ({platform.machine()}, {platform.processor() or "?"}), '
      f'Python {platform.python_version()}; N = {N}')

for path in TEMPLATES:
    t = yaml.safe_load(path.read_text())
    params = dict(t['environment']['params'])
    v = t['vocs']
    names = [*v['objectives'], *(v.get('constraints') or {}), *(v.get('observables') or {})]
    print(f'\n=== {path.name}\n  variables {list(v["variables"])}; reads {names}')

    inner.clear()
    env_mod._LATTICE_CACHE.clear()
    dt_init, env = clock(Env, interface=Intf(), **params)
    dt_cold, _ = clock(env._ensure_lattice)
    print(f'  set_variables path: {"deferred (xdeps)" if env._use_deferred else "REBUILD the Line every set"}')
    row('construct Environment (cold process)', [dt_init])
    row('first lattice load, cold (total)', [dt_cold])
    for k in ('_load_lattice', '_load_deferred', '_verify_rewrite', '_reuse_cached_lattice',
              '_deduce_variables', '_deduce_observables', '_write_varcache', '_compute_twiss'):
        if inner[k]:
            row(f'  of which {k}', inner[k], dt_cold)
    warm = []
    for _ in range(3):
        t0 = time.perf_counter()
        Env(interface=Intf(), **params)._ensure_lattice()
        warm.append(time.perf_counter() - t0)
    row('new Environment + lattice, warm (cache hit)', warm)

    lo_hi = {k: d['domain'] if isinstance(d, dict) else d for k, d in v['variables'].items()}
    rng = np.random.default_rng(1)
    points = [{k: float(rng.uniform(*d)) for k, d in lo_hi.items()} for _ in range(N)]

    inner.clear()
    t_set, t_get, t_eval = [], [], []
    for p in points:
        t0 = time.perf_counter()
        t_set.append(clock(env.set_variables, p)[0])
        t_get.append(clock(env.get_observables, list(names))[0])
        t_eval.append(time.perf_counter() - t0)
    total = statistics.median(t_eval)
    row('one evaluation: set_variables + get_observables', t_eval, total)
    row('  set_variables', t_set, total)
    if inner['_update_madx_variables']:
        row('    of which Line rebuild (_update_madx_variables)', inner['_update_madx_variables'], total)
    row('  get_observables', t_get, total)
    row('    of which twiss', inner['_compute_twiss'], total)
    t4 = [clock(env._compute_twiss, False)[0] for _ in range(N)]
    tc = [clock(env._compute_twiss, True)[0] for _ in range(N)]
    row('twiss 4d alone (no chromatic pass)', t4)
    row('twiss 4d with chromatic pass', tc)

    name, opt = optimizer_step(t)
    for n, xs in opt.items():
        row(f'optimizer step ({name}), {n} points of data', xs)

    prof = cProfile.Profile()
    prof.enable()
    for p in points:
        env.set_variables(p)
        env.get_observables(list(names))
    prof.disable()
    s = io.StringIO()
    pstats.Stats(prof, stream=s).sort_stats('cumulative').print_stats(25)
    print('  cProfile of the evaluations (top 25, cumulative):')
    print('\n'.join('    ' + line for line in s.getvalue().splitlines()[6:34]))
