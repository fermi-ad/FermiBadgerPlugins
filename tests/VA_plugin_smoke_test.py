"""Headless smoke test for the VirtualAccelerator_MADXSuite plugins.

Constructs the Interface and Environment directly (no Badger GUI) against the
Mu2e Delivery Ring lattice and exercises the full read/write API.

Run from the repo root:
    ~/miniconda3/envs/Badger_154_VirtAcc/bin/python tests/VA_plugin_smoke_test.py
"""
import importlib
import math
import os
import sys
import time

sys.path.insert(0, 'plugins')

t0 = time.time()
# Digit-leading module name ("99_Sim_...") is not a valid `from x import y`
# target, so load it via importlib instead.
va = importlib.import_module('environments.99_Sim_VirtualAccelerator_MADXSuite')
Environment = va.Environment
MADX_PREDEFINED_CONSTANTS = va.MADX_PREDEFINED_CONSTANTS
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

env = Environment(
    interface=Interface(),
    lattice_filename='sim_configs/DeliveryRing/mu2e-dr-model-v2026.03.23.madx',
    sequence_name='full',
    bpm_name_pattern='^p_d[hv]p',  # optional extra filter on top of base type
)
assert env._use_deferred, 'the := rewrite failed verification on this lattice'

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
assert elem_knobs, 'no free element attributes found'
# The main quad gradients are driven by expressions off the supply currents
# after the ':=' rewrite, so they are read-only: tune with 'i_dqd' instead.
assert 'q_dq303.k1' not in vars_alias, 'expression-driven attribute exposed as a knob'
assert 'i_dqd' in vars_alias

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

# A monitor centroid advertised by the environment gets a design setpoint...
assert f'{bpm_obs}-SETPOINT' in obs_alias
assert env.get_observables([f'{bpm_obs}-SETPOINT'])[f'{bpm_obs}-SETPOINT'] < 1e-12

# ...while an unadvertised channel is readable but has no setpoint, which must
# raise a clear error rather than silently returning junk.
extra = f'{bpm_obs.split(".")[0]}.betx'
print(f'unadvertised twiss column {extra}: {env.get_observables([extra])[extra]:.4f}')
try:
    env.get_observables([f'{extra}-SETPOINT'])
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
assert env._twiss is None, 'twiss should be invalidated, not recomputed, on set'
env.get_observables(['qx'])
assert env._twiss is not None, 'twiss not recomputed on demand'

# ---------------------------------------------------------------------- #
# Supply current knob: the whole expression chain must stay live, so the
# optics respond without reloading MAD-X
# ---------------------------------------------------------------------- #
qx_before = env.get_observables(['qx'])['qx']
t0 = time.time()
env.set_variables({'i_dqd': 250.0})
after = env.get_observables(['qx', 'qx-SETPOINT'])
dt = time.time() - t0
print(f'i_dqd -> 250: qx {qx_before:.6f} -> {after["qx"]:.6f} in {dt*1e3:.0f} ms')
assert abs(after['qx'] - 9.474853) < 1e-5, 'slow-path tune not reproduced'
assert dt < 1.0, f'iteration took {dt:.2f}s; the deferred path is not being used'
assert after['qx-SETPOINT'] > 1e-9, 'setpoint error should grow off-design'

# ---------------------------------------------------------------------- #
# optics_stable: 1 while the twiss solves, 0 where it does not, so a template
# can constrain it instead of feeding the generator NaN objectives
# ---------------------------------------------------------------------- #
assert 'optics_stable' in obs_alias, 'optics_stable not advertised'
assert 'optics_stable-SETPOINT' not in obs_alias, 'flag should have no setpoint'
assert env.get_observables(['optics_stable'])['optics_stable'] == 1.0

dqd_bounds = vars_alias['i_dqd']
vars_alias['i_dqd'] = [0.0, 500.0]  # widen past Badger's bounds check
env.set_variables({'i_dqd': 0.0})  # no focusing -> no periodic solution
unstable = env.get_observables(['optics_stable', 'qx'])
print(f'i_dqd -> 0: optics_stable={unstable["optics_stable"]}, qx={unstable["qx"]}')
assert unstable['optics_stable'] == 0.0, 'unstable optics not flagged'
assert math.isnan(unstable['qx']), 'twiss channels should read NaN there'

env.set_variables({'i_dqd': 250.0})
vars_alias['i_dqd'] = dqd_bounds
assert env.get_observables(['optics_stable'])['optics_stable'] == 1.0

# ---------------------------------------------------------------------- #
# Set/get round trip: element-attr knob (direct setattr pathway)
# ---------------------------------------------------------------------- #
quad_knob = elem_knobs[0]
k1_0 = env.get_variables([quad_knob])[quad_knob]
k1_lo, k1_hi = vars_alias[quad_knob]
k1_target = k1_0 + 0.5 * (k1_hi - k1_0)
env.set_variables({quad_knob: k1_target})
k1_1 = env.get_variables([quad_knob])[quad_knob]
print(f'element-attr knob {quad_knob}: {k1_0:.6g} -> {k1_1:.6g}')
assert abs(k1_1 - k1_target) < 1e-12

# Out-of-bounds set must be rejected by Badger's bounds validation
try:
    env.set_variables({quad_knob: k1_hi * 2 + 1})
    raise SystemExit('FAIL: out-of-bounds set accepted')
except BadgerEnvVarError:
    print('out-of-bounds set rejected: ok')

# ---------------------------------------------------------------------- #
# A second instance comes from the lattice cache: fast, but a private copy,
# so it sees the design optics even though 'env' has been detuned above
# ---------------------------------------------------------------------- #
t0 = time.time()
env2 = Environment(
    interface=Interface(),
    lattice_filename='sim_configs/DeliveryRing/mu2e-dr-model-v2026.03.23.madx',
    sequence_name='full',
    bpm_name_pattern='^p_d[hv]p',
    setpoints='{qx: 9.60}',  # inline-YAML string, as the GUI/template pass it
)
dt_cached = time.time() - t0
obs2 = env2.get_observables(['qx', 'qx-SETPOINT', 'qy-SETPOINT'])
qx2 = obs2['qx']
print(f'second instance (cached load, {dt_cached:.2f}s): qx={qx2:.4f}')
assert dt_cached < 3.0, f'second load took {dt_cached:.1f}s; the cache was missed'
assert abs(qx2 - 9.6489) < 0.01, 'cached copy inherited the first instance\'s detuning'
assert abs(env.get_observables(['qx'])['qx'] - qx2) > 1e-6, \
    'the second instance reset the first one\'s optics'

# The string-supplied setpoint must override the recorded design value...
assert abs(obs2['qx-SETPOINT'] - (qx2 - 9.60) ** 2) < 1e-9
# ...while unlisted observables keep their design-value setpoint defaults
assert obs2['qy-SETPOINT'] < 1e-12
print('setpoints string param parsed and applied: ok')

# ---------------------------------------------------------------------- #
# Sidecar cache: a fresh process must be able to advertise the variables
# without parsing the lattice, which is what Badger's per-process env probe
# needs.  Simulated here by clearing the in-process cache.
# ---------------------------------------------------------------------- #
assert env._varcache_path().is_file(), 'no sidecar cache written'
va._LATTICE_CACHE.clear()

t0 = time.time()
env3 = Environment(
    interface=Interface(),
    lattice_filename='sim_configs/DeliveryRing/mu2e-dr-model-v2026.03.23.madx',
    sequence_name='full',
    bpm_name_pattern='^p_d[hv]p',  # part of the cache stamp: it picks monitors
)
dt_lazy = time.time() - t0
print(f'lazy construction from sidecar: {dt_lazy:.2f}s, {len(vars_alias)} variables')
assert env3._line is None, 'lattice parsed despite a valid sidecar cache'
assert dt_lazy < 1.0, f'lazy construction took {dt_lazy:.1f}s'
assert 'i_dqd' in vars_alias and 'qx' in obs_alias, 'sidecar lists not advertised'
assert env3.get_bounds(['i_dqd'])['i_dqd'] == vars_alias['i_dqd']
assert env3._line is None, 'known-variable bounds should not need the lattice'

# ...and the parse happens on the first call that actually needs the Line.
assert abs(env3.get_observables(['qx'])['qx'] - 9.6489) < 0.01
assert env3._line is not None, 'lattice not parsed on first observable read'

# The stamp must record every param that shapes the lists, or a changed param
# would be served a cache deduced under the old one.
import json

stamp = json.loads(env3._varcache_path().read_text())['stamp']
assert stamp['bpm_name_pattern'] == '^p_d[hv]p'
assert stamp['rel_range'] == env3.rel_range
assert stamp['mtime'] == env3._lattice_path.stat().st_mtime
print(f'sidecar cache: advertises lazily, parses on first use, stamp {sorted(stamp)}')

print('SMOKE TEST PASSED')
