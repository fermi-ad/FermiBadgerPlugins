"""Headless smoke test for the VirtualAccelerator_MADXSuite plugins.

Constructs the Interface and Environment directly (no Badger GUI) against the
Mu2e Delivery Ring lattice and exercises the full read/write API.

Run from the repo root:
    ~/miniconda3/envs/Badger_154_VirtAcc/bin/python tests/VA_plugin_smoke_test.py
"""
import math
import os
import sys
import time

sys.path.insert(0, 'plugins')

t0 = time.time()
from environments.VirtualAccelerator_MADXSuite import (
    Environment,
    MADX_PREDEFINED_CONSTANTS,
)
from interfaces.VirtualAccelerator_MADXSuiteInterface import Interface
t_import = time.time() - t0
print(f'import time: {t_import:.2f}s (must be fast: no MAD-X load at import)')
assert t_import < 5, 'import too slow - MAD-X load leaked into import time?'

# ---------------------------------------------------------------------- #
# Instantiation via the factory-style alias trick
# ---------------------------------------------------------------------- #
# Bind the class attrs BEFORE instantiation, as badger.factory.load_plugin
# does, then check that in-place population is visible through the aliases.
vars_alias = Environment.variables
obs_alias = Environment.observables
assert vars_alias == {} and obs_alias == []

settings_file = '/tmp/va_smoke_settings.yaml'
if os.path.exists(settings_file):
    os.remove(settings_file)

env = Environment(
    interface=Interface(),
    lattice_filename='sim_configs/DeliveryRing/mu2e-dr-model-v2026.03.23.madx',
    sequence_name='full',
    bpm_name_pattern='^p_d[hv]p',
    lattice_settings_filename=settings_file,
)

print(f'variables deduced: {len(vars_alias)} (via pre-bound alias)')
print(f'observables deduced: {len(obs_alias)} (via pre-bound alias)')
assert len(vars_alias) > 0 and len(obs_alias) > 0, 'alias trick failed'

# ---------------------------------------------------------------------- #
# Variable list sanity
# ---------------------------------------------------------------------- #
junk = [v for v in vars_alias
        if v.startswith('__') or v == 't_turn_s'
        or v in MADX_PREDEFINED_CONSTANTS]
assert not junk, f'junk vars leaked: {junk}'
print('junk vars (xtrack internals + MAD-X constants): none')

bad = {k: b for k, b in vars_alias.items() if b[0] > b[1]}
assert not bad, f'unordered bounds: {list(bad)[:3]}'
print('bounds all ordered lo <= hi')

elem_knobs = [v for v in vars_alias if '.' in v]
print(f'element-attr knobs: {len(elem_knobs)}, e.g. {elem_knobs[:3]}')
assert 'q_dq303.k1' in vars_alias

# ---------------------------------------------------------------------- #
# get_bounds: known, on-the-fly, and refused channels
# ---------------------------------------------------------------------- #
from badger.errors import BadgerEnvVarError

some_var = next(v for v in vars_alias if '.' not in v)
b = env.get_bounds([some_var])
print(f'get_bounds known: {some_var} -> {b[some_var]}')
try:
    env.get_bounds(['__0__'])
    raise SystemExit('FAIL: junk var accepted by get_bounds')
except BadgerEnvVarError:
    print('get_bounds refuses internal var: ok')

# ---------------------------------------------------------------------- #
# Observable readback at the design point
# ---------------------------------------------------------------------- #
bpm_obs = next(o for o in obs_alias if o.endswith('.x'))
obs = env.get_observables(['qx', 'qy', 'dqx', 'beta_x', bpm_obs, 'qx-SETPOINT'])
print(f'observables at design: { {k: round(v, 6) for k, v in obs.items()} }')
assert all(isinstance(v, float) and math.isfinite(v) for v in obs.values())
assert abs(obs['qx'] - 9.6489) < 0.01
assert obs['qx-SETPOINT'] < 1e-12, 'setpoint error should be ~0 at design'

# Missing setpoint must raise a clear error, not silently return junk
try:
    env.get_observables([f'{bpm_obs}-SETPOINT'])
    raise SystemExit('FAIL: missing setpoint did not raise')
except ValueError as e:
    print(f'missing setpoint raises: ok ({e})')

# Formula observables (backtick syntax, handled by Badger's env metaclass)
formula = env.get_observables(['`qx` + `qy`'])
assert abs(formula['`qx` + `qy`'] - (obs['qx'] + obs['qy'])) < 1e-9
print('formula observable `qx` + `qy`: ok')

# ---------------------------------------------------------------------- #
# Set/get round trip: line var knob (vars.update pathway)
# ---------------------------------------------------------------------- #
val0 = env.get_variables([some_var])[some_var]
lo, hi = vars_alias[some_var]
target = val0 + 0.05 * (hi - lo)
env.set_variables({some_var: target})
val1 = env.get_variables([some_var])[some_var]
print(f'var round trip {some_var}: {val0:.6g} -> set {target:.6g} -> read {val1:.6g}')
assert abs(val1 - target) < 1e-12
assert env._twiss is not None, 'twiss not refreshed after set'

# ---------------------------------------------------------------------- #
# Set/get round trip: element-attr knob (direct setattr pathway),
# and the optics must respond
# ---------------------------------------------------------------------- #
quad_knob = 'q_dq303.k1'
qx_before = env.get_observables(['qx'])['qx']
k1_0 = env.get_variables([quad_knob])[quad_knob]
k1_lo, k1_hi = vars_alias[quad_knob]
k1_target = k1_0 + 0.5 * (k1_hi - k1_0)
env.set_variables({quad_knob: k1_target})
k1_1 = env.get_variables([quad_knob])[quad_knob]
assert abs(k1_1 - k1_target) < 1e-12
after = env.get_observables(['qx', 'qx-SETPOINT'])
print(f'quad knob {quad_knob}: {k1_0:.6g} -> {k1_1:.6g}; '
      f'qx: {qx_before:.4f} -> {after["qx"]:.4f}')
assert abs(after['qx'] - qx_before) > 1e-4, 'optics did not respond to quad change'
assert after['qx-SETPOINT'] > 1e-9, 'setpoint error should grow off-design'

# Out-of-bounds set must be rejected by Badger's bounds validation
try:
    env.set_variables({quad_knob: k1_hi * 2})
    raise SystemExit('FAIL: out-of-bounds set accepted')
except BadgerEnvVarError:
    print('out-of-bounds set rejected: ok')

# ---------------------------------------------------------------------- #
# Settings file: written clean, and the reload path works
# ---------------------------------------------------------------------- #
import yaml
with open(settings_file) as f:
    saved = yaml.safe_load(f)
assert saved and not any(k.startswith('_') for k in saved)
print(f'settings file: {len(saved)} clean entries')

env2 = Environment(
    interface=Interface(),
    lattice_filename='sim_configs/DeliveryRing/mu2e-dr-model-v2026.03.23.madx',
    sequence_name='full',
    bpm_name_pattern='^p_d[hv]p',
    lattice_settings_filename=settings_file,
    setpoints='{qx: 9.60}',  # inline-YAML string, as the GUI/template pass it
)
obs2 = env2.get_observables(['qx', 'qx-SETPOINT', 'qy-SETPOINT'])
qx2 = obs2['qx']
print(f'second instance (settings reloaded from file): qx={qx2:.4f}')
assert abs(qx2 - 9.6489) < 0.01, 'reloaded design settings should give design qx'

# The string-supplied setpoint must override the recorded design value...
assert abs(obs2['qx-SETPOINT'] - (qx2 - 9.60) ** 2) < 1e-9
# ...while unlisted observables keep their design-value setpoint defaults
assert obs2['qy-SETPOINT'] < 1e-12
print('setpoints string param parsed and applied: ok')

print('SMOKE TEST PASSED')
