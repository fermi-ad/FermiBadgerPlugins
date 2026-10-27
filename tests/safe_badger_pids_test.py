"""Checks of `safe-badger pids` (safe_badger.find_sessions): which process is the
Badger GUI, its launcher and its run workers, from `ps` output. Linux case from
the production host (2026-10-27), where the workers are forks with the GUI's very
command line; a macOS-style session (multiprocessing commands, a helper); and a
plain `badger -mini` with no safe-badger watching it.

Run from the repo root:
    pixi run python tests/safe_badger_pids_test.py
"""
import sys

sys.path.insert(0, ".")
from safe_badger import _seconds, find_sessions  # noqa: E402

B = "/home/lcape/FermiBadgerPlugins/.pixi/envs/default/bin"
ps = f"""
  10705  10600     05:00 tail -f logs/safe-badger.log
  30203  10601     02:10 pixi run safe-badger mini -t development/ZZ_PacsysTesting.yaml
  30254  30203     02:09 {B}/python safe_badger.py mini -t development/ZZ_PacsysTesting.yaml
  30255  30254     02:09 {B}/python3.12 {B}/badger -mini -cf /home/lcape/FermiBadgerPlugins/config.local.yaml -t development/ZZ_PacsysTesting.yaml
  30287  30255     00:40 {B}/python3.12 {B}/badger -mini -cf /home/lcape/FermiBadgerPlugins/config.local.yaml -t development/ZZ_PacsysTesting.yaml
  30279  30255     02:05 {B}/python3.12 {B}/badger -mini -cf /home/lcape/FermiBadgerPlugins/config.local.yaml -t development/ZZ_PacsysTesting.yaml
  40001   3999  01-02:03:04 {B}/python3.12 {B}/badger -g -cf config.local.yaml
  40010  40001  01-02:03:00 {B}/python3.12 {B}/badger -g -cf config.local.yaml
  50001  49999     10:00 /Users/x/.pixi/envs/default/bin/python safe_badger.py mini
  50002  50001     09:59 /Users/x/.pixi/envs/default/bin/python3.12 /Users/x/.pixi/envs/default/bin/badger -mini -cf c.yaml
  50003  50002     09:58 /Users/x/.pixi/envs/default/bin/python -c from multiprocessing.resource_tracker import main;main(7)
  50004  50002     09:57 /Users/x/.pixi/envs/default/bin/python -c from multiprocessing.spawn import spawn_main; spawn_main(tracker_fd=8)
""".splitlines()

assert _seconds("02:09") == 129 and _seconds("1:02:09") == 3729
assert _seconds("01-02:03:04") == ((24 + 2) * 60 + 3) * 60 + 4

sessions = {s["gui"]: s for s in find_sessions(ps)}
assert sorted(sessions) == [30255, 40001, 50002], sessions  # workers are not GUIs

linux = sessions[30255]
assert linux["launcher"] == 30254
assert linux["workers"] == [30279, 30287], linux  # oldest (the running one) first

plain = sessions[40001]
assert plain["launcher"] is None and plain["workers"] == [40010], plain

mac = sessions[50002]
assert mac["launcher"] == 50001 and mac["workers"] == [50003, 50004], mac

assert find_sessions(["  1  0  00:01 /sbin/launchd"]) == []

print("SAFE-BADGER PIDS TEST PASSED")
