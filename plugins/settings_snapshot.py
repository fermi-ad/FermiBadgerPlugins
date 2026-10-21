"""Snapshot every device setting a Badger environment can change, and put them back.

A snapshot is a JSON file of raw `<device>.SETTING` values, read with pacsys the
first time a Badger session loads an environment that declares the device
(first-seen wins: later template loads only add devices). Restore writes the
same raw values back with pacsys. Badger's own environment code is not involved
on either side, so mult knobs, read/set pairs and periodic unwrapping can't skew
what gets restored, and Acsys environments are covered too (same devices).

Used two ways:
- by the -mini GUI (badger-1.6.0-mini-revert-settings.patch): capture after each
  template load, the Revert button, and the Keep/Revert question on close;
- as the launcher that restores automatically when Badger exits without that
  question being answered (crash, kill, Ctrl-C, closed terminal):

    python plugins/settings_snapshot.py run <badger command ...>
    python plugins/settings_snapshot.py restore <snapshot.json>
    python plugins/settings_snapshot.py diff <snapshot.json>

Only the standard library and pacsys are imported; never Badger.
"""
import json
import logging
import math
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SNAP_DIR = REPO / 'logs' / 'snapshots'
LAUNCHER_LOG = REPO / 'logs' / 'launcher.log'
TIMEOUT = 15.0
REL_TOL = 1e-3
ABS_TOL = 1e-6

# Same rule as BasicPacsysInterface.extract_setting_devices: in 'READ,SET[,tol...]'
# the setting device is the second field. Copied, not imported: Acsys environments
# never load that interface.
_PAIR = re.compile(r'^.:.+,.:.+')

log = logging.getLogger('settings_snapshot')


# --- what to snapshot ------------------------------------------------------------

def devices_for(variables, role) -> dict[str, str]:
    """{setting device: role} for every variable name an environment declares, or {}
    when it can't write anything (simulation environments, role 'nosettings')."""
    if not role or role == 'nosettings':
        return {}
    devices = {}
    for name in variables:
        if name.startswith('mult:') or '-SETPOINT' in name:
            continue  # virtual knob (its member devices are plain variables) / observable
        device = name.split(',')[1] if _PAIR.fullmatch(name) else name
        devices[device] = role
    return devices


# --- file handling ---------------------------------------------------------------

_default_path = None


def session_path() -> Path:
    """This process's snapshot file: the launcher's, or one of our own if Badger was
    started without the launcher (the Revert button still works then)."""
    global _default_path
    if os.environ.get('FERMIBADGER_SNAPSHOT'):
        return Path(os.environ['FERMIBADGER_SNAPSHOT'])
    if _default_path is None:
        _default_path = SNAP_DIR / f'{datetime.now():%Y%m%d-%H%M%S}-{os.getpid()}.json'
    return _default_path


def load(path) -> dict:
    return json.loads(Path(path).read_text())


def _save(path, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(data, indent=1))
    os.replace(tmp, path)  # atomic: a crash never leaves a half-written snapshot


def resolve(path, how: str) -> None:
    """Record the operator's (or launcher's) decision, so nothing restores again."""
    data = load(path)
    data['resolved'] = how
    data['updated'] = datetime.now().isoformat(timespec='seconds')
    _save(path, data)


def age(data) -> str:
    seconds = (datetime.now() - datetime.fromisoformat(data['created'])).total_seconds()
    hours, rem = divmod(int(seconds), 3600)
    return f'{hours} h {rem // 60} min' if hours else f'{rem // 60} min'


# --- pacsys ----------------------------------------------------------------------

def _read(devices, backend=None) -> dict[str, float]:
    import pacsys
    source = backend if backend is not None else pacsys
    drfs = [f'{d}.SETTING@I' for d in devices]
    readings = source.get_many(drfs, timeout=TIMEOUT)
    bad = [f'{r.drf}: {r.message or r.error_code}' for r in readings if not r.ok]
    if bad:
        raise RuntimeError('could not read settings: ' + '; '.join(bad))
    return {d: float(r.value) for d, r in zip(devices, readings)}


def _open_writer(role):
    import pacsys
    from pacsys import KerberosAuth
    return pacsys.dpm(auth=KerberosAuth(), role=role, timeout=TIMEOUT)


# --- capture / diff / restore ----------------------------------------------------

def capture(variables, role, path=None, template=None, backend=None) -> int:
    """Add the devices behind `variables` not already in the snapshot, with their live
    settings. Returns how many devices the snapshot now holds (0: nothing written)."""
    path = Path(path) if path else session_path()
    devices = devices_for(variables, role)
    now = datetime.now().isoformat(timespec='seconds')
    data = load(path) if path.exists() else {
        'version': 1,
        'launcher_pid': int(os.environ.get('FERMIBADGER_LAUNCHER_PID', 0)) or None,
        'gui_pid': os.getpid(),
        'created': now,
        'templates': [],
        'resolved': None,
        'devices': {},
    }
    new = [d for d in devices if d not in data['devices']]
    if new:
        for device, value in _read(new, backend).items():
            data['devices'][device] = {'value': value, 'role': devices[device],
                                       'template': template, 't': now}
    if not data['devices']:
        return 0
    if template and template not in data['templates']:
        data['templates'].append(template)
    data['updated'] = now
    _save(path, data)
    return len(data['devices'])


def diff(path, backend=None) -> list[tuple[str, float, float]]:
    """[(device, snapshot value, live value)] for every device that has moved."""
    snapshot = load(path)['devices']
    if not snapshot:
        return []
    live = _read(list(snapshot), backend)
    return [(d, s['value'], live[d]) for d, s in snapshot.items()
            if not math.isclose(live[d], s['value'], rel_tol=REL_TOL, abs_tol=ABS_TOL)]


def restore(path, backend=None, open_writer=None, retries=3, pause=2.0) -> list[str]:
    """Write back every device that differs from the snapshot, one pacsys session per
    settings role, re-reading and retrying. Returns the devices that still differ."""
    if open_writer is None:
        open_writer = (lambda role: backend) if backend is not None else _open_writer
    devices = load(path)['devices']
    for attempt in range(retries):
        todo = diff(path, backend)
        if not todo:
            return []
        by_role = {}
        for device, value, _ in todo:
            by_role.setdefault(devices[device]['role'], []).append((device, value))
        for role, items in by_role.items():
            writer = open_writer(role)
            try:
                results = writer.write_many([(f'{d}.SETTING', v) for d, v in items],
                                            timeout=TIMEOUT)
                for (device, _), result in zip(items, results):
                    if not result.ok:
                        log.warning('write %s failed: %s %s', device, result.error_code,
                                    result.message)
            except Exception as e:  # a session that won't open: retry, report at the end
                log.warning('writing role %s failed: %s', role, e)
            finally:
                if writer is not backend:
                    writer.close()
        if attempt < retries - 1:
            time.sleep(pause)
    return [d for d, _, _ in diff(path, backend)]


# --- launcher --------------------------------------------------------------------

def _alive(pid) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _check_kerberos() -> None:
    # Ask pacsys, not klist: pixi's MIT klist can't see the macOS ticket cache.
    try:
        from pacsys import KerberosAuth
        KerberosAuth()  # validates the ticket on construction
    except Exception as e:
        log.warning('NO VALID KERBEROS TICKET (%s): automatic restore of machine '
                    'settings WILL FAIL if Badger is interrupted. Run kinit first.', e)


def _flag_stale() -> None:
    """Unresolved snapshots whose processes are gone come from a launcher that was
    itself killed. Never restore those automatically (the machine may have moved on
    since); rename them and say how to restore by hand."""
    for path in sorted(SNAP_DIR.glob('*.json')):
        try:
            data = load(path)
        except (OSError, ValueError):
            continue
        if data.get('resolved') or not data.get('devices'):
            continue
        if _alive(data.get('launcher_pid')) or _alive(data.get('gui_pid')):
            continue
        stale = path.with_suffix('.stale')
        path.rename(stale)
        log.warning('Unresolved snapshot from an earlier session (%s old, %d devices) '
                    'was NOT restored. To restore it: pixi run restore %s',
                    age(data), len(data['devices']), stale)


def _end_group(pgid, grace=5.0) -> None:
    """TERM then KILL Badger's whole process group: the GUI and any run subprocess
    it left behind, so nothing writes while (or after) we restore."""
    # EPERM here means only zombies are left (macOS): nothing that can still write.
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
        except (ProcessLookupError, PermissionError):
            return
        deadline = time.monotonic() + grace
        while time.monotonic() < deadline:
            try:
                os.killpg(pgid, 0)
            except (ProcessLookupError, PermissionError):
                return
            time.sleep(0.1)


def _setup_logging() -> None:
    LAUNCHER_LOG.parent.mkdir(parents=True, exist_ok=True)
    logging.raiseExceptions = False  # stderr may be gone (closed terminal); keep going
    fmt = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    handlers = [logging.FileHandler(LAUNCHER_LOG), logging.StreamHandler()]
    for h in handlers:
        h.setFormatter(fmt)
        log.addHandler(h)
    log.setLevel(logging.INFO)


def supervise(cmd, path, restore_fn=restore) -> int:
    """Run `cmd` in its own process group with FERMIBADGER_SNAPSHOT=path; when it
    exits (or we are signalled), end the group and restore unless the operator
    already decided. Returns the child's exit code."""
    stop = []

    def on_signal(signum, _frame):
        stop.append(signum)

    for s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(s, on_signal)

    env = dict(os.environ, FERMIBADGER_SNAPSHOT=str(path),
               FERMIBADGER_LAUNCHER_PID=str(os.getpid()))
    child = subprocess.Popen(cmd, start_new_session=True, env=env)
    while child.poll() is None and not stop:
        time.sleep(0.2)
    if stop:
        log.warning('Launcher got signal %s; stopping Badger.', signal.Signals(stop[0]).name)
    _end_group(child.pid)
    child.wait()

    path = Path(path)
    if not path.exists():
        log.info('Badger exited (%s); no device settings were captured.', child.returncode)
    else:
        data = load(path)
        if data.get('resolved'):
            log.info('Badger exited (%s); operator chose "%s".', child.returncode,
                     data['resolved'])
        else:
            log.warning('Badger exited (%s) without a Keep/Revert decision: restoring '
                        '%d devices to their values from %s ago.', child.returncode,
                        len(data['devices']), age(data))
            try:
                failed = restore_fn(path)
            except Exception as e:
                failed = [f'(restore aborted: {e})']
            if failed:
                log.error('RESTORE INCOMPLETE, still differing: %s. Retry by hand: '
                          'pixi run restore %s', ', '.join(failed), path)
            else:
                resolve(path, 'restored-by-launcher')
                log.info('Restore complete.')
    rc = child.returncode
    return rc if rc >= 0 else 128 - rc


def main(argv) -> int:
    if len(argv) < 2 or argv[0] not in ('run', 'restore', 'diff'):
        print(__doc__)
        return 2
    _setup_logging()
    if argv[0] == 'run':
        _check_kerberos()
        SNAP_DIR.mkdir(parents=True, exist_ok=True)
        _flag_stale()
        path = SNAP_DIR / f'{datetime.now():%Y%m%d-%H%M%S}-{os.getpid()}.json'
        return supervise(argv[1:], path)
    path = Path(argv[1])
    data = load(path)
    changes = diff(path)
    for device, snap, live in changes:
        print(f'{device:20s} now {live:<14.6g} snapshot {snap:.6g}')
    print(f'{len(changes)} of {len(data["devices"])} devices differ '
          f'(snapshot taken {age(data)} ago).')
    if argv[0] == 'diff' or not changes:
        return 0
    failed = restore(path)
    if failed:
        log.error('Still differing after restore: %s', ', '.join(failed))
        return 1
    resolve(path, 'restored-manually')
    log.info('Restored %d devices from %s.', len(changes), path)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
