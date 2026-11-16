"""Closed-loop check of simulation tuning templates: the template's own generator,
the current point plus 3 nearby random ones, then STEPS optimizer steps (default 20) on
the simulation; prints the start, the best feasible objective, the median step time,
and how many points met every constraint.

Run from the repo root:
    STEPS=30 pixi run python scripts/sim_closed_loop.py tuning_templates/simulation/DR_OrbitH_sim_VirtualAccelerator_MADXSuite.yaml
"""
import contextlib, copy, importlib, io, logging, sys, time, warnings, os
import numpy as np, pandas as pd, yaml
logging.disable(logging.WARNING); warnings.filterwarnings('ignore')
sys.path.insert(0, 'plugins')
from badger.gui.utils import filter_generator_config
from xopt import VOCS
from xopt.generators import get_generator
va = importlib.import_module('environments.99_Sim_VirtualAccelerator_MADXSuite')
from interfaces.VirtualAccelerator_MADXSuiteInterface import Interface
STEPS = int(os.environ.get('STEPS', 20))
for path in sys.argv[1:]:
    t = yaml.safe_load(open(path)); v = copy.deepcopy(t['vocs'])
    vocs = VOCS(variables=v['variables'], objectives=v['objectives'], constraints=v['constraints'], observables=v['observables'])
    cfg = filter_generator_config(t['generator']['name'], copy.deepcopy(t['generator'])); cfg.pop('vocs', None)
    gen = get_generator(t['generator']['name'])(vocs=vocs, **cfg)
    env = va.Environment(interface=Interface(), **t['environment']['params'])
    names = list(dict.fromkeys([*vocs.objectives, *vocs.constraints, *vocs.observables]))
    obj = list(vocs.objectives)[0]
    rng = np.random.default_rng(0)
    cur = env.get_variables(list(vocs.variables))
    pts = [cur] + [{k: float(np.clip(cur[k] + rng.uniform(-0.05, 0.05) * (hi - lo), lo, hi))
                    for k, (lo, hi) in v['variables'].items()} for _ in range(3)]
    rows, steps = [], []
    t0 = time.perf_counter()
    for p in pts:
        env.set_variables(p); rows.append({**p, **env.get_observables(names)})
    gen.add_data(pd.DataFrame(rows))
    start = rows[0][obj]
    for _ in range(STEPS):
        ts = time.perf_counter()
        with contextlib.redirect_stdout(io.StringIO()):
            cand = gen.generate(1)
        x = {k: float(cand[0][k]) for k in vocs.variables}
        env.set_variables(x); gen.add_data(pd.DataFrame([{**x, **env.get_observables(names)}]))
        steps.append(time.perf_counter() - ts)
    d = gen.data
    feas = d[[c for c in vocs.constraints]].apply(lambda r: all(
        (r[c] < vocs.constraints[c].value) if type(vocs.constraints[c]).__name__ == 'LessThanConstraint' else (r[c] > vocs.constraints[c].value)
        for c in vocs.constraints), axis=1)
    best = d.loc[feas, obj].min()
    print(f'{os.path.basename(path).removesuffix(".yaml"):55s} start {start:.4g}  best feasible {best:.4g}  ({100*(1-best/start):.0f}% lower)  '
          f'step median {np.median(steps):.2f} s  feasible {int(feas.sum())}/{len(d)}')
