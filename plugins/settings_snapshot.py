"""Snapshot every device setting a Badger environment can change, and put them back.

A snapshot is a JSON file of raw `<device>.SETTING` values, read with pacsys the
first time a Badger session loads an environment that declares the device
(first-seen wins: later template loads only add devices). Restore writes the
same raw values back with pacsys. Badger's own environment code is not involved
on either side, so mult knobs, read/set pairs and periodic unwrapping can't skew
what gets restored, and Acsys environments are covered too (same devices).

Imported by:
- the -mini GUI (badger-1.6.0-mini-revert-settings.patch): capture after each
  template load, the Revert button, the Keep/Revert question on close;
- safe_badger.py (repo root), the launcher that restores automatically when
  Badger exits without that question answered, and the restore/diff commands.

Only the standard library and pacsys are imported; never Badger.
"""
import json
import logging
import math
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SNAP_DIR = REPO / 'logs' / 'snapshots'
TIMEOUT = 15.0
REL_TOL = 1e-3
# safe-badger restores automatically only within this long of the session's first
# template load. Sessions normally last under 30 min; past this, someone may have
# retuned by hand since, so the snapshot is kept for a manual restore instead.
MAX_AUTO_RESTORE_HOURS = 2
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


def format_changes(changes) -> str:
    """[(device, startup, now)] as an aligned table, for a fixed-width font."""
    width = max([len('Device')] + [len(d) for d, _, _ in changes])
    rows = [f'{"Device":<{width}}  {"Now":>14}  {"Startup":>14}']
    rows += [f'{d:<{width}}  {now:>14.6g}  {startup:>14.6g}' for d, startup, now in changes]
    return '\n'.join(rows)


def age_seconds(data) -> float:
    return (datetime.now() - datetime.fromisoformat(data['created'])).total_seconds()


def auto_restore_until(data) -> datetime:
    return datetime.fromisoformat(data['created']) + timedelta(hours=MAX_AUTO_RESTORE_HOURS)


def age(data) -> str:
    seconds = age_seconds(data)
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
