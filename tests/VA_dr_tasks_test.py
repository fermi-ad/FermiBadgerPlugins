"""The simulation features behind the Delivery Ring task templates (2026-11-16), on the
DR lattice:

- computed channels: '<stat>(<column>@<regex>)', the beta beat columns, 'phase_x(a,b)',
  and 'sum(...)', checked against the twiss table directly;
- design values as the default target of any '-SETPOINT' channel;
- machine_errors (lattice variables and element attributes) make an imperfect machine,
  with the design still the target;
- truth_errors and 'orm_rms': zero when the model matches the hidden machine, and the
  orbit response linear at the default kick.

Run from the repo root:
    pixi run python tests/VA_dr_tasks_test.py
"""
import importlib
import os
import sys

import numpy as np

os.environ.setdefault('TQDM_DISABLE', '1')
sys.path.insert(0, 'plugins')
va = importlib.import_module('environments.99_Sim_VirtualAccelerator_MADXSuite')
from interfaces.VirtualAccelerator_MADXSuiteInterface import Interface  # noqa: E402

LAT = 'sim_configs/DeliveryRing/mu2e-dr-model-v2026.03.23.madx'


def env(**params):
    e = va.Environment(interface=Interface(), lattice_filename=LAT, **params)
    e._ensure_lattice()
    return e


# --- computed channels on the design lattice
e = env()
tw = e._design_twiss
names = np.array(tw.name)
hbpm = np.array([n.startswith('p_dhp') for n in names])
kick = np.array([n.startswith('d_dkk') for n in names])
out = e.get_observables(['rms(betx@^p_dhp)', 'max(bety@^d_dkk)', 'maxabs(dx@^p_dhp)',
                         'rms(bbetx@^p_d[hv]p)', 'phase_x(m0_dsx602,m0_dsx502)',
                         'sum(qx,qy)', 'rms(x@^p_dhp)-SETPOINT'])
assert np.isclose(out['rms(betx@^p_dhp)'], np.sqrt(np.mean(tw.betx[hbpm] ** 2)))
assert np.isclose(out['max(bety@^d_dkk)'], tw.bety[kick].max())
assert np.isclose(out['maxabs(dx@^p_dhp)'], np.abs(tw.dx[hbpm]).max())
assert out['rms(bbetx@^p_d[hv]p)'] == 0.0, 'the design has no beta beat'
assert np.isclose(out['phase_x(m0_dsx602,m0_dsx502)'], 360 * (tw['mux', 'm0_dsx502'] - tw['mux', 'm0_dsx602']))
assert np.isclose(out['sum(qx,qy)'], tw.qx + tw.qy)
assert out['rms(x@^p_dhp)-SETPOINT'] < 1e-18, 'a computed channel aims at its design value'
try:
    e.get_observables(['rms(x@^no_such_element)'])
    raise AssertionError('an empty match must fail loudly')
except ValueError:
    pass
print('computed channels: ok')

# --- an imperfect machine; the design stays the target
errors = {'q_dq303.shift_x': 2e-4, 'f_dq105': 1.02}
m = env(machine_errors=errors)
got = m.get_observables(['rms(x@^p_dhp)', 'rms(bbetx@^p_d[hv]p)', 'qx-SETPOINT', 'sum(dqx-SETPOINT,dqy-SETPOINT)'])
assert got['rms(x@^p_dhp)'] > 1e-4, got  # an offset quad steers the orbit
assert got['rms(bbetx@^p_d[hv]p)'] > 1e-3, got  # a strength error beats beta
assert m._setpoints['qx'] == e._setpoints['qx'], 'the target moved with the errors'
assert got['qx-SETPOINT'] > 0 and got['sum(dqx-SETPOINT,dqy-SETPOINT)'] > 0, got
assert env()._line['q_dq303'].shift_x == 0, 'errors leaked into the shared lattice'
try:
    env(machine_errors={'no_such_knob': 1.0})
    raise AssertionError('an unknown error name must fail loudly')
except ValueError:
    pass
print('machine_errors: ok')

# --- model fitting against a hidden machine
truth = {'f_dq105': 1.02, 'f_dq309': 0.975}
f = env(truth_errors=truth)
mismatch = f.get_observables(['orm_rms'])['orm_rms']
assert mismatch > 1e-4, mismatch
f.set_variables(truth)
assert f.get_observables(['orm_rms'])['orm_rms'] < 1e-9, 'model = truth must match exactly'
# Linear at the default kick: half the kick gives the same response per amp.
full = f._orbit_response(f._line)
f.orm_kick = 0.05
half = f._orbit_response(f._line)
rel = np.max(np.abs(full - half)) / np.max(np.abs(full))
assert rel < 1e-3, f'orbit response not linear at 0.1 A: {rel:.1e}'  # 7e-5 measured 2026-11-16
print(f'truth_errors and orm_rms: ok (start mismatch {mismatch:.4f} mm/A; nonlinearity {rel:.1e})')
print('VA DR TASKS TEST PASSED')
