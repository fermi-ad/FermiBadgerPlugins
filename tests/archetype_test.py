"""Offline check of every feature in ZZ_Archetype_Pacsys, the pattern new environments
are copied from (`pixi run new-env`), on pacsys's FakeBackend with 0.1% noise on its
readings (tests/noisy_fake.py; settings stay exact): nothing reaches ACNET.

Run from the repo root:
    pixi run python tests/archetype_test.py
"""
import contextlib
import importlib
import io
import sys

import numpy as np

sys.path.insert(0, 'plugins')
from noisy_fake import NoisyFakeBackend  # noqa: E402  readings carry 0.1% noise
from pacsys.types import ValueType  # noqa: E402
from pydantic import ValidationError  # noqa: E402
from interfaces.BasicPacsysInterface import Interface  # noqa: E402

E = importlib.import_module('environments.ZZ_Archetype_Pacsys').Environment
PAIR = 'L:CDPHAS,L:LDPADJ,tol2@0.1'


def quiet(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


# --- never writes: any role but nosettings is refused, at construction and in the GUI
for make in (lambda: E(interface=Interface(), settings_role='ril_tuning'),
             lambda: setattr(E(interface=Interface()), 'settings_role', 'ril_tuning')):
    try:
        make()
        raise AssertionError('the archetype accepted a writing role')
    except ValidationError:
        pass

env = E(interface=Interface())
assert env.settings_role == 'nosettings'
fb = env.interface._backend_override = NoisyFakeBackend()
env.interface._timeout = 5.0
object.__setattr__(env, 'settings_role', 'testing')  # bypass the guard, to test the write path

settings = {'L:ATRMHU': 1.0, 'L:ATRMVU': 1.0, 'L:ATRMHD': 1.0, 'L:ATRMVD': -1.0,
            'L:MUQ1H': 0.5, 'L:MUQ1V': 0.5, 'L:MDQ1H': -0.5, 'L:MDQ1V': 0.5,
            'L:MUQ1': 272.0, 'L:MUQ2': 250.0, 'L:RFQPAH': -155.0}  # RFQPAH: 205 on another branch
for dev, val in settings.items():
    fb.set_reading(f'{dev}.SETTING', val)
fb.set_reading('L:CDPHAS', 2.0)  # a pair's value is its reading; 362 is the same phase

# --- get_variables: plain settings, a mult (0 steps at the start), a pair's reading;
# periodic values on the branch nearest the middle of their hard limits
got = quiet(env.get_variables, ['L:ATRMHU', 'mult:MUQ', 'L:RFQPAH', PAIR])
assert {k: got[k] for k in ('L:ATRMHU', 'mult:MUQ', 'L:RFQPAH')} == \
    {'L:ATRMHU': 1.0, 'mult:MUQ': 0.0, 'L:RFQPAH': 205.0}, got  # settings: exact
assert abs(got[PAIR] - 362.0) < 0.05, got  # a reading: 2.0 +- 0.1%, on the 360 branch
assert env._as_found == {'L:MUQ1': 272.0, 'L:MUQ2': 250.0}, env._as_found

# --- set_variables: a mult step moves both quads; the bulk supply clips the largest
# trim; the pair writes its setting device and waits for the reading to settle
quiet(env.set_variables, {'mult:MUQ': 2, 'L:ATRMHU': 4.0, 'L:ATRMVU': 4.0, PAIR: 362.0})
w = fb.get_written_value
assert w('L:MUQ1.SETTING') == 274.0 and w('L:MUQ2.SETTING') == 252.0  # 20 * 0.05 * 2 = 2 A
# positive budget 8 A: 4 + 4 + 1 (ATRMHD) = 9, so the largest being set loses 1 A
assert sorted([w('L:ATRMHU.SETTING'), w('L:ATRMVU.SETTING')]) == [3.0, 4.0]
assert w('L:LDPADJ.SETTING') is not None and w(f'{PAIR}.SETTING') is None

# --- get_observables: readings, a -SETPOINT ('hold' and a number), a reduced array,
# the computed ones, and the ones from settings; only the requested names come back
ev = env.sample_events
fb.set_reading('G:LINEFF' + ev['default'], 0.9)
fb.set_reading('L:D7TOR' + ev['default'], 30.0)  # average_events 3: mean of 3 noisy events
fb.set_reading('B:400DFT' + ev['default'], 10.0)  # 'hold': the first reading is the target
for d, v in {'L:D73BPV': -0.53 + 0.1, 'L:D74BPV': -1.7 - 0.2}.items():
    fb.set_reading(d + ev['default'], v)
for d in env.w_sumsq:
    fb.set_reading(d + ev['default'], 1.0)
gate = np.r_[np.zeros(3), np.ones(500)]
signal = np.r_[np.zeros(3), np.tile([1.0, 3.0], 250)]
fb.set_reading('Z:INSPLL_1_SRS[:]' + ev['Z:INSPLL_1_SRS[:]'], gate, value_type=ValueType.SCALAR_ARRAY)
fb.set_reading('Z:ITGSIG_1_SRS[:]' + ev['Z:ITGSIG_1_SRS[:]'], signal, value_type=ValueType.SCALAR_ARRAY)

names = ['G:LINEFF', 'L:D7TOR', 'B:400DFT-SETPOINT', 'Z:ITGSIG_1_SRS[:]|std', 'W_SumLosses',
         'VTrajError_SumSqBPM_calc', 'SpillDutyFactor_calc', 'BulkPS_SourceATrims_Pos',
         'BulkPS_MEBTQ1trims', 'MultOOB_MUQ']
asked = list(names)
out = quiet(env.get_observables, asked)
assert asked == names and sorted(out) == sorted(names), out  # list untouched; nothing extra
assert np.isclose(out['G:LINEFF'], 0.9, rtol=0.01), out
assert np.isclose(out['L:D7TOR'], 30.0, rtol=0.01) and out['L:D7TOR'] != 30.0, out
assert out['B:400DFT-SETPOINT'] < (10.0 * 0.01) ** 2, out  # held at its first reading, +- noise
assert np.isclose(out['VTrajError_SumSqBPM_calc'], 0.1 ** 2 + 0.2 ** 2, rtol=0.1), out
assert np.isclose(out['Z:ITGSIG_1_SRS[:]|std'], np.std(signal), rtol=0.01), out
assert np.isclose(out['W_SumLosses'], len(env.w_sumsq) * 4.0, rtol=0.01), out  # (1 * (1 + 1))^2 each
spill = signal[2:3 + env.spill_length]
assert np.isclose(out['SpillDutyFactor_calc'], 1 / (1 + np.var(spill)), rtol=0.01), out
assert out['BulkPS_MEBTQ1trims'] == 2.0, out  # sum of |I|: 0.5 * 4
assert out['MultOOB_MUQ'] == 0.0, out
print('ARCHETYPE TEST PASSED')
