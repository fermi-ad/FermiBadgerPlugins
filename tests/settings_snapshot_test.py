"""Offline checks of plugins/settings_snapshot.py, no control network needed.

Covers: which devices an environment snapshots (mults, -SETPOINT observables and
'nosettings' dropped, read/set pairs give the setting device); first-seen merge;
diff; restore writes only what moved, grouped by role, retries, reports failures;
the launcher ends Badger's whole process group and restores unless resolved.

Run from the repo root:
    pixi run python tests/settings_snapshot_test.py
"""
import importlib.util
import json
import os
import signal
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, 'plugins')

from pacsys.testing import FakeBackend
import settings_snapshot as ss


def env_class(folder):
    spec = importlib.util.spec_from_file_location(
        folder, f'plugins/environments/{folder}/__init__.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Environment


tmp = Path(tempfile.mkdtemp())

# --- devices_for -----------------------------------------------------------------
ril = env_class('01_Linac_RIL_tuning_Pacsys')
devices = ss.devices_for(ril.variables, 'ril_tuning')
assert 'L:MUQ1' in devices and devices['L:MUQ1'] == 'ril_tuning'
assert not any(d.startswith('mult:') for d in devices), devices
assert len(devices) == len(ril.variables) - 2

es = env_class('01_Linac_EnergyStabilization_Pacsys')
assert ss.devices_for(es.variables, 'nosettings') == {}
assert ss.devices_for(es.variables, 'linac_rf') == {
    'L:V5QSET': 'linac_rf', 'L:LDPADJ': 'linac_rf', 'L:L7PADJ': 'linac_rf'}
assert ss.devices_for({'L:X': [0, 1], 'B:Y-SETPOINT': [0, 1]}, 'r') == {'L:X': 'r'}
assert ss.devices_for({'x1': [0, 1]}, None) == {}  # simulation env: no role

# --- capture: first-seen merge -----------------------------------------------------
fb = FakeBackend()
for d, v in {'L:A': 1.0, 'L:B': 2.0, 'L:C': 359.5}.items():
    fb.set_reading(f'{d}.SETTING', v)
path = tmp / 'snap.json'
assert ss.capture({'L:A': [0, 9], 'L:B': [0, 9]}, 'r1', path, 'one.yaml', backend=fb) == 2
fb.set_reading('L:A.SETTING', 5.0)  # moved between template loads
assert ss.capture({'L:A': [0, 9], 'L:C': [0, 720]}, 'r2', path, 'two.yaml', backend=fb) == 3
data = ss.load(path)
assert data['devices']['L:A'] == {**data['devices']['L:A'], 'value': 1.0, 'role': 'r1',
                                   'template': 'one.yaml'}, data['devices']['L:A']
assert data['devices']['L:C']['role'] == 'r2'
assert data['templates'] == ['one.yaml', 'two.yaml'] and data['resolved'] is None
assert not list(tmp.glob('*.tmp'))
assert ss.capture({'x': [0, 1]}, 'nosettings', tmp / 'none.json', backend=fb) == 0
assert not (tmp / 'none.json').exists()

# --- diff: raw values, periodic not unwrapped ---------------------------------------
fb.set_reading('L:C.SETTING', -0.5)  # same phase as 359.5, but a different raw setting
assert ss.diff(path, backend=fb) == [('L:A', 1.0, 5.0), ('L:C', 359.5, -0.5)]
fb.set_reading('L:B.SETTING', 2.0 * (1 + 1e-4))  # inside tolerance
assert [d for d, _, _ in ss.diff(path, backend=fb)] == ['L:A', 'L:C']

# --- restore: only what moved, grouped by role --------------------------------------
roles = []


def writer_for(role):
    roles.append(role)
    return fb


assert ss.restore(path, backend=fb, open_writer=writer_for, pause=0) == []
assert sorted(roles) == ['r1', 'r2']
assert sorted(drf for drf, _ in fb.writes) == ['L:A.SETTING', 'L:C.SETTING'], fb.writes
assert ss.diff(path, backend=fb) == []

# --- restore: retry, then report what still differs ---------------------------------
fb2 = FakeBackend()
fb2.set_reading('L:A.SETTING', 1.0)
fb2.set_reading('L:B.SETTING', 2.0)
path2 = tmp / 'snap2.json'
ss.capture({'L:A': [0, 9], 'L:B': [0, 9]}, 'r1', path2, backend=fb2)
fb2.set_reading('L:A.SETTING', 3.0)
fb2.set_reading('L:B.SETTING', 4.0)
fb2.set_write_result('L:B.SETTING', success=False, message='no')
assert ss.restore(path2, backend=fb2, pause=0) == ['L:B']
assert len([w for w in fb2.writes if w[0] == 'L:B.SETTING']) == 3  # tried every pass
assert ss.diff(path2, backend=fb2) == [('L:B', 2.0, 4.0)]

# --- launcher: ends the whole process group, restores unless resolved ---------------
CHILD = ('import subprocess, sys, time; '
         'p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"]); '
         'open(sys.argv[1], "w").write(str(p.pid)); time.sleep(60)')


def launch(kill, resolved=None):
    snap = tmp / f'launch-{kill}-{resolved}.json'
    snap.write_text(json.dumps({'created': '2026-01-01T00:00:00', 'resolved': resolved,
                                'devices': {'L:A': {'value': 1.0, 'role': 'r'}}}))
    pidfile = tmp / f'grandchild-{kill}-{resolved}'
    called = []

    def fake_restore(p):
        called.append(p)
        return []

    def killer():
        while not pidfile.exists() or not pidfile.read_text():
            time.sleep(0.05)
        if kill == 'child':
            # Badger itself dies hard; its grandchild (run subprocess) lives on.
            os.kill(child_pid[0], signal.SIGKILL)
        else:
            os.kill(os.getpid(), signal.SIGTERM)  # the launcher is told to stop

    child_pid = []
    real_popen = ss.subprocess.Popen

    def popen(*a, **kw):
        p = real_popen(*a, **kw)
        child_pid.append(p.pid)
        return p

    ss.subprocess.Popen = popen
    threading.Thread(target=killer, daemon=True).start()
    try:
        ss.supervise([sys.executable, '-c', CHILD, str(pidfile)], snap, restore_fn=fake_restore)
    finally:
        ss.subprocess.Popen = real_popen
    grandchild = int(pidfile.read_text())
    for _ in range(50):  # orphaned, so init reaps it; give that a moment
        if not ss._alive(grandchild):
            break
        time.sleep(0.1)
    assert not ss._alive(grandchild), 'run subprocess survived'
    return called, ss.load(snap)


called, data = launch('child')
assert called and data['resolved'] == 'restored-by-launcher'
called, data = launch('launcher')
assert called and data['resolved'] == 'restored-by-launcher'
called, data = launch('child', resolved='keep')
assert not called and data['resolved'] == 'keep'
signal.signal(signal.SIGTERM, signal.SIG_DFL)

print('settings_snapshot_test ok')
