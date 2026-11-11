"""Candidate speedups for the Delivery Ring simulation, measured (read only).

1. Twiss shortcuts that keep every observable a template can read (global tunes and
   chromaticities, functions at the ring start, the orbit at any monitor, any
   '<element>.<column>'): seed the closed-orbit search from the previous solution
   (co_guess), compute only at the elements read (at_elements), and both. Each is
   checked against the full twiss to 1e-9.
2. The optimizer step: split into GP fit and acquisition, over a grid of the
   acquisition search's max_time and n_restarts, at 50 points of data.
3. Tuning quality for the cheaper settings: closed-loop runs of the EI template on
   the DR simulation (best qx-SETPOINT after each step), 3 seeds each.

Run from the repo root (no network needed):
    pixi run python scripts/profile_dr_speedups.py
"""
import os
os.environ.setdefault('TQDM_DISABLE', '1')
import contextlib
import copy
import importlib
import io
import logging
import statistics
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

logging.disable(logging.WARNING)
warnings.filterwarnings('ignore')
sys.path.insert(0, 'plugins')
from badger.gui.utils import filter_generator_config  # noqa: E402
from xopt import VOCS  # noqa: E402
from xopt.generators import get_generator  # noqa: E402

Env = importlib.import_module('environments.99_Sim_VirtualAccelerator_MADXSuite').Environment
Intf = importlib.import_module('interfaces.VirtualAccelerator_MADXSuiteInterface').Interface
EI = yaml.safe_load(Path('tuning_templates/simulation/DR_BetatronTunes_sim_VirtualAccelerator_MADXSuite.yaml').read_text())
MOBO = yaml.safe_load(Path('tuning_templates/simulation/DR_BetatronTunes_MOBO_sim_VirtualAccelerator_MADXSuite.yaml').read_text())


def clock(fn, *a, **kw):
    t = time.perf_counter()
    out = fn(*a, **kw)
    return time.perf_counter() - t, out


def quiet(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


def ms(xs):
    return f'{statistics.median(xs) * 1e3:8.1f} ms [{min(xs) * 1e3:7.1f} – {max(xs) * 1e3:7.1f}]'


def vocs_of(t):
    v = copy.deepcopy(t['vocs'])  # VOCS pops 'type' out of the dicts it is given
    return VOCS(variables=v['variables'], objectives=v['objectives'],
                constraints=v.get('constraints') or {}, observables=v.get('observables') or [])


def generator(t, **override):
    name = t['generator']['name']
    cfg = filter_generator_config(name, copy.deepcopy(t['generator']))
    cfg.pop('vocs', None)
    cfg['numerical_optimizer'].update(override)
    return get_generator(name)(vocs=vocs_of(t), **cfg)


SECTIONS = os.environ.get('SECTIONS', '1234')  # e.g. SECTIONS=3 runs only the closed loop

# --- 1. twiss shortcuts ---------------------------------------------------------------
env = Env(interface=Intf(), **EI['environment']['params'])
env._ensure_lattice()
line = env._line
monitors = list(env._monitor_planes)
read_at = monitors[:10] + [line.element_names[0]]  # a template reading 10 monitors
rng = np.random.default_rng(1)
points = [{'i_dqd': rng.uniform(228.6, 252.6), 'i_dqf': rng.uniform(229.1, 253.3)} for _ in range(20)]
if '1' in SECTIONS: print(f'1. Twiss shortcuts ({len(line.element_names)} elements, {len(monitors)} monitors; '
      f'at_elements = {len(read_at)} of them)')
variants = {
    'full (now)': lambda prev: line.twiss(method='4d', chrom=False),
    'co_guess': lambda prev: line.twiss(method='4d', chrom=False, co_guess=prev.particle_on_co),
    'at_elements': lambda prev: line.twiss(method='4d', chrom=False, at_elements=read_at),
    'co_guess + at_elements': lambda prev: line.twiss(method='4d', chrom=False, at_elements=read_at,
                                                       co_guess=prev.particle_on_co),
}
times = {k: [] for k in variants}
if '1' not in SECTIONS:
    points = []
worst = {k: 0.0 for k in variants}
prev = line.twiss(method='4d', chrom=False)
for p in points:
    line.vars.update(p)
    ref = line.twiss(method='4d', chrom=False)
    for k, f in variants.items():
        dt, tw = clock(f, prev)
        times[k].append(dt)
        err = max(abs(tw.qx - ref.qx), abs(tw.qy - ref.qy),
                  *(abs(tw[c, e] - ref[c, e]) for e in read_at[:3] for c in ('betx', 'bety', 'x', 'dx')))
        worst[k] = max(worst[k], err)
    prev = ref
for k in variants if '1' in SECTIONS else ():
    print(f'  {k:26s} {ms(times[k])}   worst |difference| vs full: {worst[k]:.1e}')

# --- 2. optimizer step: fit vs acquisition, over max_time x n_restarts -----------------
print('\n2. Optimizer step at 50 points of data (3 repeats each): GP fit, then whole step')
rng = np.random.default_rng(0)


def synthetic(t, n=50):
    vocs = vocs_of(t)
    dom = {k: list(d.domain) for k, d in vocs.variables.items()}
    df = pd.DataFrame({k: rng.uniform(lo, hi, n) for k, (lo, hi) in dom.items()})
    z = sum((df[k] - np.mean(d)) / np.ptp(d) for k, d in dom.items())
    for i, o in enumerate(vocs.objectives):
        df[o] = (z - 0.1 * i) ** 2 + 0.01 * rng.standard_normal(n)
    for c in [*vocs.constraints, *vocs.observables]:
        df[c] = 1.0 + 0.01 * rng.standard_normal(n)
    return df


for label, t in (('EI', EI), ('MOBO', MOBO)) if '2' in SECTIONS else ():
    df = synthetic(t)
    for max_time in (5.0, 2.0, 1.0, 0.5):
        for n_restarts in (20, 10, 5):
            fit, step = [], []
            for _ in range(3):
                gen = generator(t, max_time=max_time, n_restarts=n_restarts)
                gen.add_data(df)
                fit.append(clock(quiet, gen.train_model, gen.data)[0])
                gen = generator(t, max_time=max_time, n_restarts=n_restarts)
                gen.add_data(df)
                step.append(clock(quiet, gen.generate, 1)[0])
            print(f'  {label:4s} max_time {max_time:3.1f} s, n_restarts {n_restarts:2d}:  '
                  f'fit {ms(fit)}   step {ms(step)}')

# --- 3. tuning quality, closed loop on the simulation ---------------------------------
print('\n3. Closed-loop EI on the DR simulation: best qx-SETPOINT (lower is better), '
      '4 initial points + 20 steps, 3 seeds')
v = EI['vocs']
names = list(dict.fromkeys([*v['objectives'], *(v.get('constraints') or {}), *(v.get('observables') or {})]))
dom = {k: d['domain'] for k, d in EI['vocs']['variables'].items()}  # also used by section 4
for max_time, n_restarts in ((5.0, 20), (1.0, 5), (0.5, 5)) if '3' in SECTIONS else ():
    bests, step_times = [], []
    for seed in range(3):
        r = np.random.default_rng(100 + seed)
        gen = generator(EI, max_time=max_time, n_restarts=n_restarts)
        rows = []
        for _ in range(4):  # initial points: random in the template's window
            x = {k: float(r.uniform(*d)) for k, d in dom.items()}
            env.set_variables(x)
            rows.append({**x, **env.get_observables(list(names))})
        gen.add_data(pd.DataFrame(rows))
        for _ in range(20):
            dt, cand = clock(quiet, gen.generate, 1)
            step_times.append(dt)
            x = {k: float(v) for k, v in cand[0].items() if k in dom}
            env.set_variables(x)
            gen.add_data(pd.DataFrame([{**x, **env.get_observables(list(names))}]))
        bests.append(gen.data['qx-SETPOINT'].min())
    print(f'  max_time {max_time:3.1f} s, n_restarts {n_restarts:2d}:  step {ms(step_times)}   '
          f'best qx-SETPOINT per seed: {", ".join(f"{b:.1e}" for b in bests)}')

# --- 4. the template's observables: does the optimizer model them? -------------------
# Xopt fits a GP to every output in the VOCS, observables included. Compared: the EI
# template as written, and with only its objective and constraint.
if '4' in SECTIONS:
    print('\n4. Closed-loop EI step with and without the VOCS observables '
          '(max_time 0.5 s, n_restarts 5; 4 initial points + 20 steps, 3 seeds)')
    lean = copy.deepcopy(EI)
    lean['vocs']['observables'] = {}
    for label, t in (('as written', EI), ('objective + constraint only', lean)):
        v = t['vocs']
        names = list(dict.fromkeys([*v['objectives'], *(v.get('constraints') or {}),
                                    *(v.get('observables') or {})]))
        bests, step_times = [], []
        for seed in range(3):
            r = np.random.default_rng(100 + seed)
            gen = generator(t, max_time=0.5, n_restarts=5)
            rows = []
            for _ in range(4):
                x = {k: float(r.uniform(*d)) for k, d in dom.items()}
                env.set_variables(x)
                rows.append({**x, **env.get_observables(list(names))})
            gen.add_data(pd.DataFrame(rows))
            for _ in range(20):
                dt, cand = clock(quiet, gen.generate, 1)
                step_times.append(dt)
                x = {k: float(val) for k, val in cand[0].items() if k in dom}
                env.set_variables(x)
                gen.add_data(pd.DataFrame([{**x, **env.get_observables(list(names))}]))
            bests.append(gen.data['qx-SETPOINT'].min())
        print(f'  {label:28s} outputs modeled {len(gen.vocs.output_names)}:  step {ms(step_times)}   '
              f'best qx-SETPOINT per seed: {", ".join(f"{b:.1e}" for b in bests)}')
