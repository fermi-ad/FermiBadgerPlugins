# safe-badger: how the snapshot, Revert and automatic restore are built

Operator summary: README, [safe-badger: revert and crash safety](../README.md#safe-badger-revert-and-crash-safety).
This page is the technical description: where the code is, what runs in which
process, the snapshot file format, and how each way of ending a session is
handled.

## Why it exists

Before this, nothing recorded the machine's settings when Badger started.
Badger's own **Reset environment** button covers only the *checked* variables,
only back to the start of the *latest* run, and only in memory. If Badger
crashed or was killed mid-run, the machine stayed wherever the optimizer had
put it. Worse, Badger's run worker is a separate process that is not a daemon,
so it could keep writing settings after the GUI was gone.

safe-badger adds three things:

1. A **snapshot**: every device the loaded template's environment can write,
   checked or not, with its live setting at the moment the template was loaded.
2. A **Revert** button and a **Keep / Revert / Cancel** question on close, in
   the `-mini` GUI.
3. A **launcher** that restores the snapshot automatically when Badger ends
   without the operator answering that question.

## Where the code is

| Piece | File | Role |
|---|---|---|
| Snapshot library | `plugins/settings_snapshot.py` | Which devices, read, save, diff, restore, table formatting. Imports only the standard library and pacsys, never Badger. |
| Launcher and CLI | `safe_badger.py` (repo root) | `mini`, `diff` and `restore` subcommands; process supervision; automatic restore; stale-snapshot handling; Kerberos check. |
| GUI hooks | `patches/badger-1.6.0-mini-revert-settings.patch` | Patches three Badger files (below). Applied by `pixi_setup.sh` / `setup.sh`. |
| pixi task | `pixi.toml`: `safe-badger = "python safe_badger.py"` | `pixi run safe-badger <subcommand> [args]` |
| Tests | `tests/settings_snapshot_test.py`, `tests/settings_snapshot_gui_test.py` | Offline, against `pacsys.testing.FakeBackend`. |
| Output | `logs/snapshots/*.json`, `logs/safe-badger.log` | `logs/` is gitignored. |

`settings_snapshot.py` lives in `plugins/` because that directory is
Badger's `BADGER_PLUGIN_ROOT`, which Badger puts on `sys.path` when it starts
(`badger/factory.py`). The patched GUI can therefore `import settings_snapshot`
without any path set-up. `safe_badger.py` adds `plugins/` to its own path.

The patch touches:

- `badger/gui/components/action_bar.py`: a `btn_revert` button, hidden by
  default so the full GUI (`-g`) is unchanged; disabled by `lock()` while a run
  is active and re-enabled by `unlock()` / `routine_finished()` only if
  `revert_ready` is set.
- `badger/gui/mini/pages/home_page.py`: shows the button, and adds
  `snapshot_settings`, `revert_settings`, `settle_settings` and helpers.
- `badger/gui/mini/windows/main_window.py`: `closeEvent` calls
  `settle_settings()` before closing; if that returns False the window stays
  open.

## Processes

```
terminal / operator shortcut
└─ pixi run safe-badger mini -t 01_Linac_RIL_tuning.yaml
   └─ python safe_badger.py mini ...                 the launcher
      │   catches SIGINT, SIGTERM, SIGHUP
      │   env: FERMIBADGER_SNAPSHOT=logs/snapshots/<time>-<pid>.json
      │        FERMIBADGER_LAUNCHER_PID=<its pid>
      └─ badger -mini -cf config.local.yaml -t ...   new session = new process group
         └─ multiprocessing run worker(s)            same process group as Badger
```

The launcher starts Badger with `subprocess.Popen(..., start_new_session=True)`.
That makes Badger the leader of a new session and process group. Every process
Badger starts, including the multiprocessing worker that executes runs and
writes settings, inherits that group. One `os.killpg()` call can therefore
stop all of them, even a worker whose parent GUI has already died.

A new session also means that terminal signals (Ctrl-C, closing the window)
reach only the launcher, not Badger. The launcher decides what happens: it
always stops Badger first, then restores.

## The snapshot file

One file per Badger session, at the path in `FERMIBADGER_SNAPSHOT`. Without
the launcher (plain `badger -mini`), `settings_snapshot.session_path()` makes
its own path under `logs/snapshots/`, so the Revert button and close question
still work. Only the automatic restore is missing then.

```json
{
 "version": 1,
 "launcher_pid": 41234,
 "gui_pid": 41240,
 "created": "2026-10-21T13:05:00",
 "updated": "2026-10-21T13:07:12",
 "templates": ["01_Linac_RIL_tuning.yaml"],
 "resolved": null,
 "devices": {
  "L:MUQ1": {"value": 275.0, "role": "ril_tuning",
             "template": "01_Linac_RIL_tuning.yaml", "t": "2026-10-21T13:05:00"}
 }
}
```

- The file is only created once a template has at least one writable device.
- **First-seen wins.** A later template load adds devices that aren't in the
  file yet, and never overwrites one that is. A device that the optimizer has
  already moved is therefore still restored to its value from the start of the
  session.
- The **settings role is stored per device**. Two templates can use different
  DPM roles, and each device is written back under the role its own template
  used.
- `resolved` records how the session ended:
  - `null`: undecided, so the launcher will restore.
  - `keep`: the operator chose Keep, or nothing differed at close.
  - `reverted`: the operator chose Revert at close.
  - `restored-by-launcher`: the launcher restored it automatically.
  - `restored-manually`: someone ran `safe-badger restore`.
- Every write goes to `<file>.tmp` and then `os.replace()`s it. That rename is
  atomic, so a crash never leaves a half-written snapshot.

## Which devices are snapshotted

`settings_snapshot.devices_for(variables, role)` walks the environment
class's `variables` dict:

- `mult:*` knobs are skipped. They are virtual; their member quads are plain
  variables in the same environment and are snapshotted directly.
- Names containing `-SETPOINT` are skipped. They are observables.
- A read/set pair (`READ,SET[,tolN@T]`, e.g. `L:CDPHAS,L:LDPADJ,tol2@0.1`)
  records its second field, the setting device. This rule is copied from
  `BasicPacsysInterface.extract_setting_devices`, not imported, because Acsys
  environments never load that interface.
- If the role is missing or `nosettings`, nothing is recorded. This covers the
  simulation environments, and EnergyStabilization unless its template sets a
  role.

The GUI takes the environment **class** (`routine_editor.env`) and the
template's environment parameters (for `settings_role`, falling back to the
class default). It does not instantiate the environment, because simulation
environments load a whole lattice when instantiated.

## Reading and writing

Snapshot, diff and restore deal in raw device settings via pacsys. Badger's
`env.get_variables()` / `set_variables()` are never used, so nothing in an
environment's own logic can change what gets restored: mult expansion, pair
settle loops, periodic-phase unwrapping or supply-limit clipping.

- **Read:** one `pacsys.get_many(["<dev>.SETTING@I", ...], timeout=15)`. Any
  failed reading raises, and the whole capture or diff fails rather than
  recording a partial picture.
- **Compare:** `math.isclose(live, snapshot, rel_tol=1e-3, abs_tol=1e-6)`.
  Values are raw, so a phase at 359.5 and one at -0.5 count as different
  settings.
- **Write:** only the devices that differ, grouped by role. Each role opens one
  `pacsys.dpm(auth=KerberosAuth(), role=<role>)` session and calls
  `write_many([("<dev>.SETTING", value), ...])`. Per-device write failures are
  logged.
- **Verify:** after writing, it diffs again. It makes up to 3 passes, 2 s
  apart, and returns the devices that still differ. An empty list means success.
- **Kerberos:** `safe-badger mini` checks at start by constructing
  `pacsys.KerberosAuth()`, which validates the ticket. It deliberately doesn't
  run `klist`: the `klist` inside the pixi environment (MIT krb5) can't see the
  macOS ticket cache, and reports "no ticket" when pacsys has one.

## GUI behaviour

- **Capture:** `routine_editor.sig_load_template` is emitted after every
  successful template load (`-t` at start-up, the template dropdown, and
  loading from a file). It is connected to `home_page.snapshot_settings`. If
  the capture fails, a warning dialog says the safety net doesn't cover this
  template's devices.
- **Revert button:** enabled once the snapshot holds devices, and disabled
  while a run is active.
  1. It reads the live settings and shows the devices that moved, as a
     fixed-width table (`Device  Now  Startup`) with the snapshot's age.
  2. On Yes, it restores under a wait cursor, refreshes the variable table, and
     reports any device that still differs, with the manual command.
  3. It does not set `resolved`: the session goes on, and later changes are
     still covered.
- **Close** (`settle_settings`):
  - No snapshot: the window closes.
  - Nothing differs: it records `keep` and closes.
  - Otherwise it shows the same table with **Keep / Revert / Cancel**:
    - Keep records `keep`.
    - Revert restores, then records `reverted`. If the restore fails, the
      window stays open.
    - Cancel keeps the window open.
  - If the live settings can't be read, it asks whether to close anyway; an
    undecided snapshot is then left for the launcher.
  - Closing during a run first asks to stop the run (Badger's existing
    dialog). Badger then re-enters `closeEvent` once the run has stopped, and
    the same question appears.

## The launcher, step by step (`safe_badger.py`)

**Start (`main`, subcommand `mini`):**

1. Logging goes to `logs/safe-badger.log` and to stderr. It covers the launcher
   and `settings_snapshot`'s per-device write failures.
   `logging.raiseExceptions = False` keeps it going if stderr disappears (a
   closed terminal).
2. Kerberos check: a loud warning if there is no valid ticket. It does not stop.
3. Stale snapshots: any `logs/snapshots/*.json` that is unresolved, has
   devices, and whose `launcher_pid` and `gui_pid` are both dead was left by a
   launcher that was itself killed, or by a host that went down. These are
   **never restored automatically**, since the machine may have been retuned
   since. Each is renamed `*.stale` and the restore command is logged.
4. Badger starts: `badger -mini -cf <repo>/config.local.yaml <your args>` in a
   new session, with the two environment variables.

**Run (`supervise`):**

- The launcher polls the child every 0.2 s. Its SIGINT/SIGTERM/SIGHUP handler
  only records the signal; the loop sees it and moves on to shutdown.

**End, every time:**

1. **Stop the whole group** (`_end_group`): SIGTERM, wait up to 5 s, then
   SIGKILL, wait up to 5 s. This happens even if Badger already exited, to
   catch an orphaned run worker. On macOS, `killpg` on a group that holds only
   zombies returns EPERM; that is treated as "gone".
2. **Read the snapshot:**
   - No file: nothing was captured, nothing to do.
   - `resolved` set: the operator decided; log it.
   - `resolved` null: restore. On success it records `restored-by-launcher`.
     On failure it logs `RESTORE INCOMPLETE` and the exact
     `pixi run safe-badger restore <file>` command.
3. The exit code is Badger's, or 128 + the signal number if Badger was killed
   by a signal.

**`diff <file>` / `restore <file>`:** these print the fixed-width table and a
count of differing devices. `restore` then writes the snapshot back, verifies,
and records `restored-manually`; it exits 1 if anything still differs. They
work on `*.stale` files too.

## How each ending is handled

| How the session ends | What happens |
|---|---|
| Close, nothing changed | `keep` recorded, no question |
| Close → Keep | `keep` recorded; launcher does nothing |
| Close → Revert | restored in the GUI, `reverted` recorded |
| Close → Cancel | window stays open |
| Badger crashes, or `kill -9` on Badger | launcher stops the group (and the worker), then restores |
| Ctrl-C in the launcher's terminal | launcher stops Badger, then restores (the question is never shown) |
| Terminal window closed (SIGHUP) | same as Ctrl-C; output goes only to `logs/safe-badger.log` |
| `kill` (SIGTERM) on the launcher | same as Ctrl-C |
| `kill -9` on the launcher, host down | nothing at the time; the next `safe-badger mini` renames the snapshot `*.stale` and logs the restore command |
| No Kerberos ticket | warning at start; a restore fails and logs the manual command |
| Plain `badger -mini` (no launcher) | Revert and the close question work; no automatic restore |
| `badger -g` | unchanged; no snapshot |

## Limits

- **Snapshot age:** an automatic restore after a long session also reverts
  hours of possibly intended changes. Today the age is shown in dialogs and
  logs, but nothing enforces a limit (TODO.md).
- **Supply limits:** group sums are not rechecked on restore. It writes back a
  state that was live at the start of the session.
- **Environment switched without a template:** not snapshotted. Capture runs
  only on template load.

## Testing

- **`tests/settings_snapshot_test.py`** covers:
  - which devices are chosen (real RIL and EnergyStabilization classes);
  - the first-seen merge;
  - diff on raw periodic values;
  - restore writing only what moved, grouped by role;
  - retries and failure reporting;
  - the table format;
  - the launcher against a dummy child that starts a grandchild: SIGKILL to
    the child, SIGTERM to the launcher, and a resolved snapshot. In each case
    the grandchild must be gone and the restore called (or, for the resolved
    snapshot, not called).
- **`tests/settings_snapshot_gui_test.py`** runs the real `-mini` window
  offscreen with pacsys's `get_many` replaced by FakeBackend:
  - a simulation template leaves the button disabled;
  - `ZZ_PacsysTesting` is captured with role `testing`;
  - Revert writes only the moved device, and its table is in a `<pre>` block;
  - Cancel, Keep and Revert on close each behave as described above.

Never run `safe-badger mini` / `restore` from a development machine that has
VPN and a Kerberos ticket unless you mean it. Those really write to ACNET.
