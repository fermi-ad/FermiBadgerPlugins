"""End-to-end check of badger-1.6.0-worker-stops-without-gui.patch: when the Badger
GUI dies mid-run (kill -9), its run workers stop within a few seconds, and the
run sets no further points: the run's archive file stops growing. Before, the
workers outlived the GUI (a spare waiting forever; with plain `badger -mini`,
nothing else ended a running one).

A child process opens -mini offscreen, loads the TuneQx simulation template,
presses Go and, a few seconds into the run, SIGKILLs itself. Offline: the
simulation needs no control network. The run goes to the usual archive (Badger's
run worker reads the per-user settings, so it cannot be redirected); the test
deletes the files it created there.

Run from the repo root:
    pixi run python tests/worker_stops_without_gui_test.py
"""
import os
import sys

TEMPLATE = "tuning_templates/simulation/TuneQx_SimpleVirtualAccelerator.yaml"
RUN_SECONDS = 12


def gui(config):
    """The child: start a run, report the workers' PIDs, then die like kill -9."""
    import multiprocessing
    import signal

    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ.pop("FERMIBADGER_SNAPSHOT", None)
    from badger.settings import init_settings

    init_settings(config)
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QApplication

    import badger.gui.mini  # noqa: F401  Badger's Qt options before the QApplication
    app = QApplication.instance() or QApplication([])
    from badger.gui.mini.windows.main_window import BadgerMiniWindow

    window = BadgerMiniWindow()
    page = window.home_page
    page.routine_editor.load_template_yaml(False, template_path=TEMPLATE)
    page.run_monitor.on_error = lambda e: print("RUNERROR", repr(e), flush=True)  # no modal box

    def die():
        pids = [p.pid for p in multiprocessing.active_children()]
        print("WORKERS", " ".join(map(str, pids)), flush=True)
        os.kill(os.getpid(), signal.SIGKILL)

    # Go once Badger's pre-started run worker is ready (Go before then fails),
    # however long a loaded machine takes; then die RUN_SECONDS later.
    waited = []

    def go_when_ready():
        if page.process_manager.processes_queue or len(waited) > 120:
            page.start_run()
            QTimer.singleShot(RUN_SECONDS * 1000, die)
        else:
            waited.append(1)
            QTimer.singleShot(500, go_when_ready)

    QTimer.singleShot(500, go_when_ready)
    app.exec_()
    _ = window


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # a zombie (dead, not yet reaped) counts as gone
    stat = os.popen(f"ps -o stat= -p {pid}").read().strip()
    return bool(stat) and not stat.startswith("Z")


def main():
    import glob
    import subprocess
    import tempfile
    import time
    from pathlib import Path

    import yaml

    tmp = Path(tempfile.mkdtemp())
    config = "config.local.yaml"
    root = Path(yaml.safe_load(open(config))["BADGER_ARCHIVE_ROOT"]["value"])

    def archive_files():
        return set(glob.glob(str(root / "**" / "*.yaml"), recursive=True)) | set(
            glob.glob(str(root / ".tmp" / "*.yaml"))
        )

    before = archive_files()
    try:
        check(tmp, config, archive_files, before)
    finally:  # leave the archive as it was
        for f in archive_files() - before:
            os.remove(f)
            day = os.path.dirname(f)
            if not day.endswith(".tmp") and not os.listdir(day):
                os.rmdir(day)  # the day's folder, if this run made it


def check(tmp, config, archive_files, before):
    import subprocess
    import time

    import yaml

    # Output to a file, not a pipe: a surviving worker would hold a pipe open.
    out = tmp / "gui.log"
    with open(out, "w") as f:
        child = subprocess.Popen(
            [sys.executable, __file__, "--gui", config],
            stdout=f, stderr=subprocess.STDOUT,
        )
        child.wait(timeout=180)
    text = out.read_text()
    assert child.returncode == -9, (child.returncode, text[-2000:])
    lines = [ln for ln in text.splitlines() if ln.startswith("WORKERS")]
    assert lines, text[-2000:]
    assert "RUNERROR" not in text, text[text.index("RUNERROR"):][:1000]
    workers = [int(p) for p in lines[0].split()[1:]]
    assert len(workers) >= 2, f"expected the running worker and the spare: {workers}"

    deadline = time.time() + 6
    while time.time() < deadline and any(alive(p) for p in workers):
        time.sleep(0.2)
    left = [p for p in workers if alive(p)]
    for p in left:  # don't leave them running if the check fails
        os.kill(p, 9)
    assert not left, f"workers still running after the GUI died: {left}"

    runs = [f for f in archive_files() - before if "/.tmp/" not in f]
    assert runs, "the run did not start"
    size = os.path.getsize(runs[0])
    time.sleep(3)
    assert os.path.getsize(runs[0]) == size, "the run kept going"
    points = len(yaml.safe_load(open(runs[0]))["data"]["kqd"])
    assert points >= 2, points
    print(f"run stopped at {points} points; {len(workers)} worker(s) gone")
    print("worker_stops_without_gui_test ok", flush=True)


if __name__ == "__main__":
    if sys.argv[1:2] == ["--gui"]:
        gui(sys.argv[2])
    else:
        main()
