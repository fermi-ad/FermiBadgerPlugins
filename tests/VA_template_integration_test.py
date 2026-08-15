"""Template integration test: load plugins and templates like the Badger GUI.

Initializes Badger settings from the repo config.yaml (the headless
equivalent of `badger --config_filepath config.yaml`), then loads the
environment through badger.factory.get_env, which exercises the
plugin-discovery path and the in-place class-attribute population.
Also tests template loading and options configuration.

Run from the repo root:
    ~/miniconda3/envs/Badger_154_VirtAcc/bin/python tests/VA_template_integration_test.py
"""
import math
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Must run BEFORE importing badger.factory: the settings singleton is
# first-call-wins, and factory.py reads BADGER_PLUGIN_ROOT at import time.
from badger.settings import init_settings
init_settings(os.path.join(REPO_ROOT, 'config.yaml'))

from badger.factory import get_env, get_intf, list_env

envs = list_env()
print(f'environments discovered: {envs}')
assert 'VirtualAccelerator_MADXSuite' in envs

Intf, intf_configs = get_intf('VirtualAccelerator_MADXSuiteInterface')
print(f'interface loaded: {Intf.name}')

Env, configs = get_env('VirtualAccelerator_MADXSuite')

variables = configs['variables']
observations = configs['observations']
print(f"factory configs: {len(variables)} variables, "
      f"{len(observations)} observations")
assert len(variables) > 2000, 'variables not populated through the factory path'
assert len(observations) > 200, 'observations not populated through the factory path'

# Each variables entry is {name: [lo, hi]} with ordered numeric bounds
for entry in variables[:50]:
    ((name, bounds),) = entry.items()
    assert len(bounds) == 2 and bounds[0] <= bounds[1], f'bad bounds for {name}'
sample = [list(e.keys())[0] for e in variables[:3]]
print(f'sample variables: {sample}')

# Junk must not reach the GUI lists
names = [list(e.keys())[0] for e in variables]
assert not any(n.startswith('__') or n in ('t_turn_s', 'pi', 'version')
               for n in names), 'junk variables reached the factory configs'

# The GUI param editor (pydantic_editor.set_params_from_dict) rebuilds a
# dynamic model from type(value) of each param and crashes on dict- or
# list-valued params ("Dict type must have subtypes").  Env params must
# therefore be scalars; represent structured params as strings parsed by
# the environment (e.g. the 'setpoints' inline-YAML string).
for pname, pval in configs['params'].items():
    assert isinstance(pval, (str, int, float, bool, type(None))), (
        f"env param '{pname}' has a {type(pval).__name__} value; the Badger "
        '1.5.4 GUI param editor only supports scalar param values'
    )
print('all env param values are scalars (GUI editor safe)')

# The template's example knobs must be offered to the GUI
for knob in ['q_dq303.k1', 'q_dq304.k1', 'q_dq305.k1', 'q_dq306.k1']:
    assert knob in names, f'{knob} missing from factory variables'
print('template example knobs present')

# Setpoint objectives used by the template must be offered too
for obs in ['qx-SETPOINT', 'qy-SETPOINT', 'qx', 'qy']:
    assert obs in observations, f'{obs} missing from factory observations'
print('template objectives present')

print('FACTORY-PATH TEST PASSED')
