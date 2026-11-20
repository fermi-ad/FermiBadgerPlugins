"""Offline check of 03_Booster_Pacsys, on pacsys's FakeBackend with 0.1%
noise on its readings (tests/noisy_fake.py; settings stay exact): nothing reaches ACNET.
When you change or delete a feature in the environment, change or delete its lines here;
a failure names the line.

Run from the repo root:
    pixi run python tests/03_Booster_Pacsys_test.py
"""
import contextlib
import importlib
import io
import sys

sys.path.insert(0, 'plugins')
from noisy_fake import NoisyFakeBackend  # noqa: E402  readings carry 0.1% noise
from interfaces.BasicPacsysInterface import Interface  # noqa: E402

NAME = '03_Booster_Pacsys'
MOD = importlib.import_module(f'environments.{NAME}')
E = MOD.Environment


def quiet(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


env = E(interface=Interface())
assert env.settings_role == 'nosettings'

# --- the device table (devices.csv): every variable has a range; the earlier injection
# draft's devices are all here; L:C7PHAS is periodic; B:VIMIN writes are off
assert len(E.variables) > 400 and all(lo < hi for lo, hi in E.variables.values())
for dev in ('L:C7PHAS', 'B:VIMIN', 'B:VIMAX', 'B:MH1', 'B:MH2', 'B:MV1', 'B:MV2'):
    assert dev in E.variables, dev
for dev in ('B:BOOEFF', 'G:LINEFF', 'WorstLossNorm', *MOD._WORST_LOSS_DEVICES):
    assert dev in E.observables, dev
assert not set(E.variables) & set(E.observables)
assert env.periodic_devices.get('L:C7PHAS') == 360.0
assert env.allow_auto_written == []
assert {'B:VIMIN', 'L:C7PHAS'} <= MOD._AUTO_WRITTEN and 'B:MH1' not in MOD._AUTO_WRITTEN
fb = env.interface._backend_override = NoisyFakeBackend()
env.interface._timeout = 5.0
object.__setattr__(env, 'settings_role', 'testing')  # a writing role, for the fake only

# --- get_variables: plain settings
settings = {'L:C7PHAS': 161.5, 'B:VIMIN': 103.0, 'B:VIMAX': 967.0,
            'B:MH1': 351.0, 'B:MH2': 695.0, 'B:MV1': 375.0, 'B:MV2': 365.0}
for dev, val in settings.items():
    fb.set_reading(f'{dev}.SETTING', val)
got = quiet(env.get_variables, list(settings))
assert got == settings, got  # settings: exact

# --- set_variables: a setting another loop also writes (B:VIMIN, L:C7PHAS) is refused
# unless allow_auto_written names it, and nothing of that request is written
try:
    quiet(env.set_variables, {'B:VIMIN': 104.0, 'L:C7PHAS': 161.0, 'B:MH1': 352.0})
    raise AssertionError('auto-written settings were not refused')
except RuntimeError as error:
    assert 'B:VIMIN' in str(error) and 'L:C7PHAS' in str(error), error
assert not fb.writes, fb.writes
quiet(env.set_variables, {'B:MH1': 352.0})
w = fb.get_written_value
assert w('B:MH1.SETTING') == 352.0
object.__setattr__(env, 'allow_auto_written', ['B:VIMIN'])  # the hardware owner's sign-off
quiet(env.set_variables, {'B:VIMIN': 104.0})
assert w('B:VIMIN.SETTING') == 104.0

# --- get_observables: readings plus the computed WorstLossNorm (max over the
# calibrated devices of (reading - baseline) / scale); only requested names return.
# WorstLossNorm pulls every device in _WORST_LOSS_DEVICES, so all 49 need a reading.
for dev in MOD._WORST_LOSS_DEVICES:
    baseline, _ = MOD._WORST_LOSS_BASELINE_SCALE.get(dev, (0.01, 0.0))
    fb.set_reading(dev, baseline)  # at its own baseline: contributes ~0 to the max
fb.set_reading('B:BOOEFF', 93.0)
fb.set_reading('G:LINEFF', 0.9)
fb.set_reading('B:BLMS12', 0.509)  # baseline 0.009, scale 0.001 -> norm = 500: the spike
fb.set_reading('B:BLML05', 0.02)  # uncalibrated (n < 20): read, but excluded from the max

names = ['B:BOOEFF', 'G:LINEFF', 'B:BLMS01', 'B:BLMS12', 'B:BLML05', 'WorstLossNorm']
asked = list(names)
out = quiet(env.get_observables, asked)
assert asked == names and sorted(out) == sorted(names), out  # list untouched; nothing extra
assert abs(out['B:BOOEFF'] - 93.0) < 93.0 * 0.01, out
assert abs(out['WorstLossNorm'] - 500.0) < 5.0, out  # B:BLMS12's spike dominates the max
print(f'{NAME} TEST PASSED')
