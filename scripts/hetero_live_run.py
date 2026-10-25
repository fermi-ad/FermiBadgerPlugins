"""Live run of ZZ_PacsysTesting_Heteroskedastic, headless, with the template's
settings: 8 random points, then 32 expected-improvement steps, seed 7.

WRITES TO ACNET (the scratch devices Z:CUBE_X and Z:CUBE_Y; needs the VPN and a
Kerberos ticket with the  role); their settings are read first and
written back at the end, also on failure. Saves
logs/hetero_runs/<time>-<shape>.yaml, then score it:

    pixi run python scripts/hetero_live_run.py [proportional|distance|bump]
    pixi run python scripts/hetero_recovery.py logs/hetero_runs/<file>.yaml
"""
import importlib
import sys
import time
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, "plugins")
from xopt import Evaluator, VOCS, Xopt  # noqa: E402
from xopt.generators.bayesian import ExpectedImprovementGenerator  # noqa: E402
from interfaces.BasicPacsysInterface import Interface  # noqa: E402

shape = sys.argv[1] if len(sys.argv) > 1 else "distance"
n_random, n_steps = 8, 32
tmpl = yaml.safe_load(Path("tuning_templates/development/ZZ_PacsysTesting_Heteroskedastic.yaml").read_text())
params = tmpl["environment"]["params"] | {"seed": 7, "noise_shape": shape}
Env = importlib.import_module("environments.ZZ_PacsysTesting_Heteroskedastic").Environment
env = Env(interface=Interface(), **params)
vocs = VOCS(
    variables=tmpl["vocs"]["variables"],
    objectives=tmpl["vocs"]["objectives"],
    observables=tmpl["vocs"]["observables"],
)
devices = list(vocs.variables)


def evaluate(point):
    env.set_variables({d: float(point[d]) for d in devices})
    out = env.get_observables(vocs.output_names)
    out["timestamp"] = time.time()
    return out


original = env.get_variables(devices)
print("original settings:", original, flush=True)
try:
    X = Xopt(vocs=vocs, generator=ExpectedImprovementGenerator(vocs=vocs), evaluator=Evaluator(function=evaluate))
    X.random_evaluate(n_random)
    print(f"{n_random} random points done", flush=True)
    for i in range(n_steps):
        X.step()
        row = X.data.iloc[-1]
        print(f"step {i + 1:2d}: x={row['Z:CUBE_X']:+.3f} y={row['Z:CUBE_Y']:+.3f} f={row['Hetero_f']:.3f} var={row['Hetero_f_var']:.2e} true={row['Hetero_f_true_var']:.2e}", flush=True)
finally:
    env.set_variables(original)
    print("restored:", env.get_variables(devices), flush=True)

data = X.data.drop(columns=[c for c in ("xopt_runtime", "xopt_error") if c in X.data])
out = Path("logs/hetero_runs")
out.mkdir(parents=True, exist_ok=True)
path = out / f"{time.strftime('%Y-%m-%d-%H%M%S')}-{shape}.yaml"
path.write_text(yaml.safe_dump({
    "data": {c: {str(i): float(v) for i, v in data[c].items()} for c in data},
    "generator": {"vocs": {"variables": {n: {"domain": list(b)} for n, b in zip(devices, vocs.bounds)}}},
    "environment": {"name": env.name, **env.model_dump(exclude={"interface"})},
}))
print("saved", path, flush=True)
