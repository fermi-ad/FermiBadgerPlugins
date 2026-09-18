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
assert '99_Sim_VirtualAccelerator_MADXSuite' in envs

Intf, intf_configs = get_intf('VirtualAccelerator_MADXSuiteInterface')
print(f'interface loaded: {Intf.name}')

Env, configs = get_env('99_Sim_VirtualAccelerator_MADXSuite')

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

# The template's example knobs must be offered to the GUI.  These are the
# supply currents; the quad gradients they drive are expression-driven outputs
# and are deliberately not offered.
for knob in ['i_dqd', 'i_dqf', 'i_dht301']:
    assert knob in names, f'{knob} missing from factory variables'
assert 'q_dq303.k1' not in names, 'expression-driven attribute offered as a knob'
print('template example knobs present')

# Setpoint objectives used by the template must be offered too
for obs in ['qx-SETPOINT', 'qy-SETPOINT', 'qx', 'qy']:
    assert obs in observations, f'{obs} missing from factory observations'
print('template objectives present')

# Every shipped template must be loadable by the GUI.  Badger builds the
# variable table from this cached variable list -- which comes from the FIRST
# env instance, i.e. the default lattice in configs.yaml -- plus the template's
# 'additional_variables'.  A vocs variable in neither is silently dropped from
# the table, and loading the template then dies in xopt's get_local_region with
# "Center point keys must match vocs variable names".  Objective, constraint
# and observable names are looked up in the observation list the same way.
import glob
import yaml

for path in sorted(glob.glob(os.path.join(REPO_ROOT, 'tuning_templates', '*.yaml'))):
    with open(path) as handle:
        try:
            template = yaml.safe_load(handle)
        except yaml.YAMLError as e:
            # Badger's loader is safe_load too, so this one cannot be opened
            # in the GUI either; not our environment's problem.
            print(f'  {os.path.basename(path)}: skipped, not safe-loadable ({type(e).__name__})')
            continue
    if template.get('environment', {}).get('name') != '99_Sim_VirtualAccelerator_MADXSuite':
        continue
    label = os.path.basename(path)
    vocs = template['vocs']
    known_vars = set(names) | set(template.get('additional_variables') or [])
    missing = set(vocs['variables']) - known_vars
    assert not missing, (
        f"{label}: {sorted(missing)} is neither an advertised variable of the "
        "default lattice nor listed in 'additional_variables'"
    )

    # The observation list, unlike the variable list, is the live class-level
    # list, so it does track the template's own lattice -- check against that.
    env = Env(interface=Intf(), **template['environment']['params'])
    known_obs = set(type(env).observables) | set(template.get('formulas') or {})
    missing = set(vocs['variables']) - set(type(env).variables)
    assert not missing, f'{label}: {sorted(missing)} are not knobs of this lattice'
    for section in ('objectives', 'constraints', 'observables'):
        missing = set(vocs.get(section) or {}) - known_obs
        assert not missing, (
            f'{label}: {section} {sorted(missing)} '
            'are not observables of this lattice'
        )
    # patches/badger-mini-var-table-env-configs.patch builds the '-mini'
    # variable table's rows this way -- from an env carrying the template's
    # params -- instead of from the factory's default-lattice list.
    var_bounds = env.get_bounds(type(env).variables)
    for vname in vocs['variables']:
        lo, hi = var_bounds[vname]
        assert lo <= hi and math.isfinite(lo) and math.isfinite(hi), (
            f'{label}: unusable bounds for {vname}: {[lo, hi]}'
        )
    if template['environment']['params']['lattice_filename'] != \
            configs['params']['lattice_filename']:
        assert set(var_bounds) != set(names), (
            f'{label}: rebuilt variable list still matches the default lattice'
        )
    print(f'  {label}: GUI-loadable, {len(var_bounds)} table rows')

print('FACTORY-PATH TEST PASSED')
