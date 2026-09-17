"""Offline self-check for BasicPacsysInterface -- no control network needed.

Uses pacsys.testing.FakeBackend (set via the interface's _backend_override
seam) to exercise the DRF-parsing helpers, get_values/get_settings/set_values,
and the settle-to-tolerance loop end to end.

Run directly: python test_basic_pacsys_interface.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from __init__ import Interface  # noqa: E402

from pacsys.testing import FakeBackend  # noqa: E402
from pacsys.errors import DeviceError  # noqa: E402


def make_interface(backend):
    intf = Interface()
    intf._backend_override = backend
    return intf


def test_extract_reading_devices():
    intf = make_interface(FakeBackend())
    assert intf.extract_reading_devices(['L:CDPHAS']) == ['L:CDPHAS']
    assert intf.extract_reading_devices(['L:CDPHAS,L:LDPADJ']) == ['L:CDPHAS']
    assert intf.extract_reading_devices(['L:CDPHAS,L:LDPADJ,tol2@5.0']) == ['L:CDPHAS']
    assert intf.extract_reading_devices(['L:CDPHAS-SETPOINT']) == ['L:CDPHAS']


def test_extract_setting_devices():
    intf = make_interface(FakeBackend())
    assert intf.extract_setting_devices(['L:CDPHAS']) == ['L:CDPHAS']
    assert intf.extract_setting_devices(['L:CDPHAS,L:LDPADJ']) == ['L:LDPADJ']
    assert intf.extract_setting_devices(['L:CDPHAS,L:LDPADJ,tol2@5.0']) == ['L:LDPADJ']


def test_get_values_plain_read_no_sample_events():
    # Environment.get_variables() calls get_values(names) with NO sample_events --
    # this is the shape that used to KeyError via read_once()'s shadowed default.
    fb = FakeBackend()
    fb.set_reading('M:OUTTMP', 72.5)
    intf = make_interface(fb)
    result = intf.get_values(['M:OUTTMP'])
    assert result == {'M:OUTTMP': 72.5}


def test_get_values_with_sample_events():
    fb = FakeBackend()
    fb.set_reading('M:OUTTMP@e,52,e,0', 10.0)
    intf = make_interface(fb)
    result = intf.get_values(['M:OUTTMP'], sample_events={'default': '@e,52,e,0'})
    assert result == {'M:OUTTMP': 10.0}


def test_get_values_bad_reading_raises():
    fb = FakeBackend()
    fb.set_error('M:BADDEV', -42, 'Device not found')
    intf = make_interface(fb)
    try:
        intf.get_values(['M:BADDEV'])
    except DeviceError:
        pass
    else:
        raise AssertionError('expected DeviceError for a bad reading')


def test_get_settings():
    fb = FakeBackend()
    fb.set_reading('L:LDPADJ.SETTING@I', 5.0)
    intf = make_interface(fb)
    result = intf.get_settings(['L:LDPADJ'])
    assert result == {'L:LDPADJ': 5.0}


def test_set_values_nosettings_is_noop():
    fb = FakeBackend()
    intf = make_interface(fb)
    intf.set_values({'M:OUTTMP': 5.0}, settings_role='nosettings')
    assert fb.writes == []


def test_set_values_writes_and_settles():
    fb = FakeBackend()
    # Settling loop reads back the reading device through get_values(); seed a
    # constant value so the buffer's spread is 0 and tolerance is met immediately.
    fb.set_reading('L:CDPHAS', 1.0)
    intf = make_interface(fb)
    intf.set_values({'L:CDPHAS,L:LDPADJ,tol2@5.0': 2.0}, settings_role='testing')
    assert fb.was_written('L:LDPADJ')


if __name__ == '__main__':
    tests = [v for k, v in list(globals().items()) if k.startswith('test_')]
    for t in tests:
        t()
        print(f'{t.__name__}: OK')
    print(f'{len(tests)} checks passed.')
