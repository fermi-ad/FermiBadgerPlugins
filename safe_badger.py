"""safe-badger: run Badger so that an interrupted session can't leave the machine
wherever the optimizer put it.

    pixi run safe-badger mini [badger args ...]   e.g.  mini -t 01_Linac_RIL_tuning.yaml
    pixi run safe-badger g [badger args ...]      the full GUI, same protection
    pixi run safe-badger diff <snapshot.json>      what differs from the snapshot now
    pixi run safe-badger restore <snapshot.json>   write the snapshot back
    pixi run safe-badger pids                      which process is which (for kill tests)

`mini` / `g` start `badger -mini|-g -cf config.local.yaml <args>` as a child in
its own process session, with FERMIBADGER_SNAPSHOT naming a new file under
logs/snapshots/. The patched GUI fills that file each time it loads a template
and when a run starts, and records the operator's Keep/Revert answer in it on
close. When
Badger exits for any reason, or safe-badger itself gets SIGINT/SIGTERM/SIGHUP,
safe-badger ends Badger's whole process group and, if the file holds no answer,
restores every device in it, provided the session's first template load was
less than MAX_AUTO_RESTORE_HOURS (settings_snapshot.py) ago; an older snapshot
is renamed *.expired and left for a manual restore. Everything is logged to
logs/safe-badger.log.

The snapshot, diff and restore logic is plugins/settings_snapshot.py. The full
description is docs/safe-badger.md.
"""
import logging
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / 'plugins'))
import settings_snapshot as snapshot  # noqa: E402

LOG_FILE = REPO / 'logs' / 'safe-badger.log'
GUIS = {'mini': '-mini', 'g': '-g'}  # safe-badger subcommand: badger flag

log = logging.getLogger('safe_badger')


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
    """Unresolved snapshots whose processes are gone come from a safe-badger that
    was itself killed. Never restore those automatically (the machine may have
    moved on since); rename them and say how to restore by hand."""
    for path in sorted(snapshot.SNAP_DIR.glob('*.json')):
        try:
            data = snapshot.load(path)
        except (OSError, ValueError):
            continue
        if data.get('resolved') or not data.get('devices'):
            continue
        if _alive(data.get('launcher_pid')) or _alive(data.get('gui_pid')):
            continue
        stale = path.with_suffix('.stale')
        path.rename(stale)
        log.warning('Unresolved snapshot from an earlier session (%s old, %d devices) '
                    'was NOT restored. To restore it: pixi run safe-badger restore %s',
                    snapshot.age(data), len(data['devices']), stale)


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
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    logging.raiseExceptions = False  # stderr may be gone (closed terminal); keep going
    fmt = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    for handler in (logging.FileHandler(LOG_FILE), logging.StreamHandler()):
        handler.setFormatter(fmt)
        for logger in (log, snapshot.log):  # restore()'s per-device write failures too
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)


def supervise(cmd, path, restore_fn=snapshot.restore) -> int:
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
        log.warning('safe-badger got signal %s; stopping Badger.',
                    signal.Signals(stop[0]).name)
    _end_group(child.pid)
    child.wait()

    path = Path(path)
    if not path.exists():
        log.info('Badger exited (%s); no device settings were captured.', child.returncode)
    else:
        data = snapshot.load(path)
        if data.get('resolved'):
            log.info('Badger exited (%s); operator chose "%s".', child.returncode,
                     data['resolved'])
        else:
            log.warning('Badger exited (%s) without a Keep/Revert decision.', child.returncode)
            if snapshot.age_seconds(data) > snapshot.MAX_AUTO_RESTORE_HOURS * 3600:
                expired = path.with_suffix('.expired')
                path.rename(expired)
                log.error('Snapshot is %s old, over the %d h limit for automatic restore: '
                          'NOT restored. To restore it anyway: '
                          'pixi run safe-badger restore %s', snapshot.age(data),
                          snapshot.MAX_AUTO_RESTORE_HOURS, expired)
                return _exit_code(child)
            log.warning('Restoring %d devices to their values from %s ago.',
                        len(data['devices']), snapshot.age(data))
            try:
                failed = restore_fn(path)
            except Exception as e:
                failed = [f'(restore aborted: {e})']
            if failed:
                log.error('RESTORE INCOMPLETE, still differing: %s. Retry by hand: '
                          'pixi run safe-badger restore %s', ', '.join(failed), path)
            else:
                snapshot.resolve(path, 'restored-by-launcher')
                log.info('Restore complete.')
    return _exit_code(child)


_BADGER_GUI = re.compile(r"bin/badger (-mini|-g)\b")


def _seconds(etime: str) -> int:
    """ps etime, [[dd-]hh:]mm:ss, in seconds."""
    days, _, rest = etime.rpartition("-")
    parts = [int(x) for x in rest.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, sec = parts
    return (int(days or 0) * 24 + h) * 3600 + m * 60 + sec


def find_sessions(ps_lines):
    """From `ps -eo pid=,ppid=,etime=,command=` lines: one dict per Badger GUI,
    {gui, launcher (or None), workers (oldest first), command}. A GUI is a
    `badger -mini|-g` process whose parent is not one: on Linux the run workers
    are forks with the very same command line, on macOS `multiprocessing` ones."""
    rows = {}
    for line in ps_lines:
        f = line.split(None, 3)
        if len(f) == 4 and f[0].isdigit():
            rows[int(f[0])] = (int(f[1]), _seconds(f[2]), f[3])
    badgers = {p for p, (_, _, cmd) in rows.items() if _BADGER_GUI.search(cmd)}
    sessions = []
    for pid in sorted(badgers):
        ppid, _, cmd = rows[pid]
        if ppid in badgers:
            continue  # a forked worker
        workers = sorted((p for p, (pp, _, _) in rows.items() if pp == pid),
                         key=lambda p: -rows[p][1])
        parent = rows.get(ppid, (0, 0, ""))[2]
        sessions.append({"gui": pid, "command": cmd, "workers": workers,
                         "launcher": ppid if "safe_badger.py" in parent else None})
    return sessions


def show_pids() -> int:
    ps = subprocess.run(["ps", "-eo", "pid=,ppid=,etime=,command="],
                        capture_output=True, text=True).stdout.splitlines()
    sessions = find_sessions(ps)
    if not sessions:
        print("No Badger is running.")
        return 0
    for s in sessions:
        cmd = s["command"]
        print(f"Badger GUI   {s['gui']}    {cmd[cmd.find('badger '):][:100]}")
        if s["launcher"]:
            print(f"  launcher   {s['launcher']}    safe-badger, watching it")
        else:
            print("  launcher   NONE: no safe-badger watching this Badger (no automatic restore)")
        if s["workers"]:
            print(f"  workers    {' '.join(map(str, s['workers']))}    oldest first: during a run the"
                  " oldest runs it, the newest is the spare (macOS also lists a helper)")
        print("  tests:")
        print(f"    kill -9 {s['gui']}      the GUI dies: safe-badger ends its group and restores")
        if s["launcher"]:
            print(f"    kill -HUP {s['launcher']}   the launcher is told to stop: it ends Badger and restores")
            print(f"    (never kill -9 {s['launcher']}: a SIGKILLed launcher can do nothing; Badger runs on)")
        print()
    return 0


def _exit_code(child) -> int:
    rc = child.returncode
    return rc if rc >= 0 else 128 - rc


def main(argv) -> int:
    if argv == ['pids']:
        return show_pids()
    if not argv or argv[0] not in (*GUIS, 'restore', 'diff') \
            or (argv[0] not in GUIS and len(argv) != 2):
        print(__doc__)
        return 2
    _setup_logging()
    if argv[0] in GUIS:
        _check_kerberos()
        snapshot.SNAP_DIR.mkdir(parents=True, exist_ok=True)
        _flag_stale()
        path = snapshot.SNAP_DIR / f'{datetime.now():%Y%m%d-%H%M%S}-{os.getpid()}.json'
        log.info('Starting Badger; snapshot file %s', path)
        log.info('If Badger is interrupted within %d h of loading the first template, '
                 'every device it changed is restored automatically. After that, use '
                 'Revert, or answer Keep/Revert when closing.',
                 snapshot.MAX_AUTO_RESTORE_HOURS)
        badger = ['badger', GUIS[argv[0]], '-cf', str(REPO / 'config.local.yaml')]
        return supervise(badger + argv[1:], path)

    path = Path(argv[1])
    data = snapshot.load(path)
    changes = snapshot.diff(path)
    if changes:
        print(snapshot.format_changes(changes))
    print(f'{len(changes)} of {len(data["devices"])} devices differ '
          f'(snapshot taken {snapshot.age(data)} ago).')
    if argv[0] == 'diff' or not changes:
        return 0
    failed = snapshot.restore(path)
    if failed:
        log.error('Still differing after restore: %s', ', '.join(failed))
        return 1
    snapshot.resolve(path, 'restored-manually')
    log.info('Restored %d devices from %s.', len(changes), path)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
