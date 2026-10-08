"""Offline checks of BasicPacsysInterface on pacsys 0.3.0, no control network needed.

Covers: a failed setting raises; a bare device's stored SETTING is read back and a
mismatch only warns; a read/set pair's readback is its READING device, never compared
to the value sent; the settle loop times out; averaged reads via read_fresh; array
observables via the "|<reduce>" suffix.

Run from the repo root:
    conda run -n FermiBadger_env python tests/pacsys_interface_test.py
"""
import contextlib
import dataclasses
import io
import sys
import threading
import time

import numpy as np

sys.path.insert(0, 'plugins')

from pacsys.testing import FakeBackend
from pacsys.types import ValueType
from interfaces.BasicPacsysInterface import Interface, REDUCTIONS


def make():
    fb = FakeBackend()
    intf = Interface()
    intf._backend_override = fb
    intf._timeout = 1.0
    return fb, intf


def captured(fn, *a, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        out = fn(*a, **kw)
    return out, buf.getvalue()


# --- readback mapping ---------------------------------------------------------------
intf = Interface()
assert intf.readback_drf('L:ATRMHU') == 'L:ATRMHU.SETTING@I'
assert intf.readback_drf('L:CDPHAS,L:LDPADJ') == 'L:CDPHAS'
assert intf.readback_drf('L:C7PHAS,L:L7PADJ,tol2@0.1') == 'L:C7PHAS'
assert intf.readback_drf('L:D73BPV-SETPOINT') is None

# --- failed setting raises and names the device --------------------------------------
fb, intf = make()
fb.set_reading('L:ATRMHU', 0.0)
fb.set_write_result('L:ATRMHU.SETTING', success=False, error_code=-7, message='no settings privilege')
try:
    intf.set_values({'L:ATRMHU': 1.0}, settings_role='ril_tuning')
    raise AssertionError('expected RuntimeError')
except RuntimeError as e:
    assert 'L:ATRMHU' in str(e) and 'no settings privilege' in str(e), e

# --- bare device: stored setting read back, mismatch warns but continues -------------
fb, intf = make()
fb.set_reading('L:ATRMHU', 0.0)
_, text = captured(intf.set_values, {'L:ATRMHU': 1.5}, settings_role='ril_tuning')
assert fb.read('L:ATRMHU.SETTING@I') == 1.5 and fb.writes[-1] == ('L:ATRMHU.SETTING', 1.5)
assert 'differs' not in text, text
# pretend the front end clipped it: the stored setting reads back as 1.0
orig_get_many = fb.get_many
def clipped(drfs, timeout=None):
    return [dataclasses.replace(r, value=1.0) if r.drf.startswith('L:ATRMHU.SETTING') else r
            for r in orig_get_many(drfs, timeout=timeout)]
fb.get_many = clipped
_, text = captured(intf.set_values, {'L:ATRMHU': 1.5}, settings_role='ril_tuning')
assert 'L:ATRMHU stored setting 1.0 differs from the 1.5 sent' in text, text

# --- read/set pair: write lands on the setting device, readback is the READING device --
fb, intf = make()
fb.set_reading('L:CDPHAS', 123.0)                    # measured phase, nothing like the adjust value
fb.set_reading('L:LDPADJ', 0.0)
fb.reads.clear()
_, text = captured(intf.set_values, {'L:CDPHAS,L:LDPADJ,tol2@0.1': -3.0}, settings_role='ril_tuning')
assert fb.reads and all(r.startswith('L:CDPHAS') for r in fb.reads), fb.reads  # only the READING device was read back
assert fb.writes[-1] == ('L:LDPADJ.SETTING', -3.0) and fb.read('L:LDPADJ.SETTING@I') == -3.0
assert 'differs' not in text, text                       # 123 vs -3 is not a mismatch: different quantities
# a pair without a tol spec is only warned about, once
_, text = captured(intf.set_values, {'L:CDPHAS,L:LDPADJ': -2.0}, settings_role='ril_tuning')
assert 'no tolN@T spec' in text, text
_, text = captured(intf.set_values, {'L:CDPHAS,L:LDPADJ': -1.0}, settings_role='ril_tuning')
assert 'no tolN@T spec' not in text, text

# --- settle loop times out instead of spinning forever -------------------------------
fb, intf = make()
fb.set_reading('L:LDPADJ', 0.0)
state = {'v': 0.0}
# a reading that never settles: alternate 0 and 10 on every read
orig_get_many = fb.get_many
def jumpy(drfs, timeout=None):
    state['v'] = 10.0 - state['v']
    fb.set_reading('L:CDPHAS', state['v'])
    return orig_get_many(drfs, timeout=timeout)
fb.get_many = jumpy
intf._timeout = 0.5
try:
    captured(intf.set_values, {'L:CDPHAS,L:LDPADJ,tol2@0.1': 1.0}, settings_role='ril_tuning')
    raise AssertionError('expected settle timeout')
except RuntimeError as e:
    assert 'did not settle' in str(e) and 'L:CDPHAS' in str(e), e

# --- averaged observable: mean of N fresh events --------------------------------------
fb, intf = make()
intf._timeout = 3.0
fb.set_reading('L:TUNRAD', 1.0)
def pump():
    for v in (1.0, 2.0, 6.0):
        time.sleep(0.05)
        fb.emit_reading('L:TUNRAD@e,52,e,0', v)
threading.Thread(target=pump, daemon=True).start()
out = intf.get_values(['L:TUNRAD'], sample_events={'default': '@e,52,e,0'}, average_events={'L:TUNRAD': 3})
assert out == {'L:TUNRAD': 3.0}, out
# N > 1 with an immediate event cannot stream
try:
    intf.get_values(['L:TUNRAD'], average_events={'default': 2})
    raise AssertionError('expected ValueError for @i averaging')
except ValueError as e:
    assert '@i' in str(e), e
# N == 1 is the plain path, unchanged
fb.set_reading('L:TUNRAD', 4.5)
assert intf.get_values(['L:TUNRAD'], average_events={'default': 1}) == {'L:TUNRAD': 4.5}

# --- array observable: "<DRF>|<reduce>" ------------------------------------------------
fb, intf = make()
fb.set_reading('B:BPMARR', np.array([3.0, -4.0, 0.0, 0.0]), value_type=ValueType.SCALAR_ARRAY)
out = intf.get_values(['B:BPMARR|rms', 'B:BPMARR|absmax', 'B:BPMARR|sum'])
assert abs(out['B:BPMARR|rms'] - 2.5) < 1e-9, out
assert out['B:BPMARR|absmax'] == 4.0 and out['B:BPMARR|sum'] == -1.0, out
assert set(REDUCTIONS) == {'mean', 'rms', 'std', 'min', 'max', 'sum', 'absmax'}
try:
    intf.get_values(['B:BPMARR|bogus'])
    raise AssertionError('expected ValueError for unknown reduction')
except ValueError as e:
    assert 'bogus' in str(e), e
# reduction on a scalar is a mistake, not a silent pass-through
fb.set_reading('L:TUNRAD', 1.0)
try:
    intf.get_values(['L:TUNRAD|rms'])
    raise AssertionError('expected ValueError for scalar reduction')
except ValueError as e:
    assert 'needs an array' in str(e), e

print('PACSYS INTERFACE TEST PASSED')
