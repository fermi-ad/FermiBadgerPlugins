"""Offline checks of mults (console-style fixed-proportion knobs), no control network needed.

The pure helper first, then the RIL Pacsys environment driven through
pacsys.testing.FakeBackend. The Acsys environment shares the same helper and the same
method bodies but has no fake backend.

Run from the repo root:
    conda run -n FermiBadger_env python tests/mults_test.py
"""
import contextlib
import importlib
import io
import sys

sys.path.insert(0, 'plugins')

from badger.errors import BadgerEnvVarError
from pacsys.testing import FakeBackend
from interfaces.BasicPacsysInterface import Interface
from mults import expand_mults, parse_mult, mult_members


def quiet(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


# --- helper --------------------------------------------------------------------------
assert parse_mult('L:MUQ1*20,L:MUQ2*20') == {'L:MUQ1': 20.0, 'L:MUQ2': 20.0}
assert parse_mult('L:A*-2, L:B') == {'L:A': -2.0, 'L:B': 1.0}
MULTS = {'MUQ': 'L:MUQ1*20,L:MUQ2*20', 'MDQ': 'L:MDQ1*20,L:MDQ2*20'}
STEP = {'MUQ': 0.1, 'MDQ': 0.1}
FOUND = {'L:MUQ1': 272.0, 'L:MUQ2': 246.0, 'L:MDQ1': 226.0, 'L:MDQ2': 172.0}
BOUNDS = {'L:MUQ1': [250, 300], 'L:MUQ2': [225, 275], 'L:MDQ1': [200, 250], 'L:MDQ2': [150, 180]}

settings, steps, oob = quiet(expand_mults, {'mult:MUQ': 2.4, 'L:ASOL': 400.0}, MULTS, STEP, FOUND, BOUNDS)
assert steps == {'MUQ': 2} and oob == {'MUQ': 0.0}, (steps, oob)
assert settings == {'L:ASOL': 400.0, 'L:MUQ1': 276.0, 'L:MUQ2': 250.0}, settings   # 20 * 0.1 * 2 = 4
settings, steps, _ = quiet(expand_mults, {'mult:MUQ': -2.6}, MULTS, STEP, FOUND, BOUNDS)
assert steps == {'MUQ': -3} and settings['L:MUQ1'] == 266.0
# clipping: MDQ2 wants 192 but its bound is 180 -> 12 of the 20 requested is lost
settings, steps, oob = quiet(expand_mults, {'mult:MDQ': 10}, MULTS, STEP, FOUND, BOUNDS)
assert settings['L:MDQ1'] == 246.0 and settings['L:MDQ2'] == 180.0, settings
assert abs(oob['MDQ'] - 0.6) < 1e-12, oob
# step 0 moves nothing and reports nothing lost
settings, steps, oob = quiet(expand_mults, {'mult:MDQ': 0.2}, MULTS, STEP, FOUND, BOUNDS)
assert settings['L:MDQ2'] == 172.0 and oob['MDQ'] == 0.0
for bad in ({'mult:MUQ': 1, 'L:MUQ1': 270.0}, {'mult:NOPE': 1}):
    try:
        quiet(expand_mults, bad, MULTS, STEP, FOUND, BOUNDS)
        raise AssertionError(f'expected BadgerEnvVarError for {bad}')
    except BadgerEnvVarError:
        pass
try:
    quiet(expand_mults, {'mult:MUQ': 1}, MULTS, STEP, {}, BOUNDS)
    raise AssertionError('expected BadgerEnvVarError without as-found values')
except BadgerEnvVarError:
    pass

# --- RIL Pacsys environment on the fake backend ------------------------------------------
env_mod = importlib.import_module('environments.01_Linac_RIL_tuning_Pacsys')
fb = FakeBackend()
for dev, val in FOUND.items():
    fb.set_reading(f'{dev}.SETTING', val)      # eventless: writes update it, @I reads see it
env = env_mod.Environment(interface=Interface())
env.interface._backend_override = fb
env.interface._timeout = 1.0
assert mult_members(env.mults) == ['L:MUQ1', 'L:MUQ2', 'L:MDQ1', 'L:MDQ2']

# a fresh run: mults read 0, devices read their settings, as-found captured once
vals = quiet(env.get_variables, ['mult:MUQ', 'L:MUQ1'])
assert vals == {'mult:MUQ': 0.0, 'L:MUQ1': 272.0}, vals
assert env._as_found == FOUND, env._as_found
n_reads = len(fb.reads)
quiet(env.get_variables, ['mult:MDQ'])
assert len(fb.reads) == n_reads, 'as-found must not be re-read'

# a step: both quads of the pair move by coefficient * step size * rounded steps
quiet(env.set_variables, {'mult:MUQ': 2.4})
assert ('L:MUQ1.SETTING', 274.0) in fb.writes and ('L:MUQ2.SETTING', 248.0) in fb.writes, fb.writes   # 20 * 0.05 * 2
assert quiet(env.get_variables, ['mult:MUQ']) == {'mult:MUQ': 2.0}
assert quiet(env.get_observables, ['MultOOB_MUQ']) == {'MultOOB_MUQ': 0.0}
assert env._as_found['L:MUQ1'] == 272.0, 'as-found is fixed for the run'

# the next step is from as-found, not from the last setting
quiet(env.set_variables, {'mult:MUQ': 1})
assert fb.writes[-2:] == [('L:MUQ1.SETTING', 273.0), ('L:MUQ2.SETTING', 247.0)], fb.writes[-2:]

# a clipped step shows up in the MultOOB observable
quiet(env.set_variables, {'mult:MDQ': 10})
assert ('L:MDQ2.SETTING', 180.0) in fb.writes and ('L:MDQ1.SETTING', 236.0) in fb.writes   # MDQ2 wanted 182
oob = quiet(env.get_observables, ['MultOOB_MDQ', 'MultOOB_MUQ'])
assert abs(oob['MultOOB_MDQ'] - 0.2) < 1e-12 and oob['MultOOB_MUQ'] == 0.0, oob          # 2 of 10 lost

# operators can change the step size (template param / GUI env params)
env.mult_step_size['MUQ'] = 0.5
quiet(env.set_variables, {'mult:MUQ': 1})
assert fb.writes[-2] == ('L:MUQ1.SETTING', 282.0), fb.writes[-2]          # 20 * 0.5 * 1

# a quad ticked together with its mult is a configuration error, nothing written
n_writes = len(fb.writes)
try:
    quiet(env.set_variables, {'mult:MUQ': 1, 'L:MUQ1': 270.0})
    raise AssertionError('expected BadgerEnvVarError')
except BadgerEnvVarError:
    assert len(fb.writes) == n_writes

print('MULTS TEST PASSED')
