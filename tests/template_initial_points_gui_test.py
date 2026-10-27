"""Offscreen check of badger-1.6.0-template-initial-points.patch, in both GUIs: a
template's own `initial_points` fill the Initial Points table, replacing what its
actions (or Badger's default actions) put there, and are the run's initial points.
development/ZZ_PacsysTesting.yaml has exactly one, (-4, 4, -4, -2), near the
TwoWells decoy.

pacsys reads come from a FakeBackend: nothing reaches ACNET.

Run from the repo root:
    pixi run python tests/template_initial_points_gui_test.py
"""
TEMPLATE = "tuning_templates/development/ZZ_PacsysTesting.yaml"
START = {"G:AMANDA": 50.0, "Z:CUBE_X": 2.0, "Z:CUBE_Y": 3.0, "Z:CUBE_Z": 4.0}  # G:AMANDA outside -10..10
WANTED = {"G:AMANDA": -4.0, "Z:CUBE_X": 4.0, "Z:CUBE_Y": -4.0, "Z:CUBE_Z": -2.0}


def stop_workers():
    """Badger pre-spawns a run worker; left alive, it holds the output pipe open."""
    import multiprocessing
    for child in multiprocessing.active_children():
        child.terminate()
        child.join()


def main():
    import os
    import tempfile
    from pathlib import Path

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ["FERMIBADGER_SNAPSHOT"] = str(Path(tempfile.mkdtemp()) / "snap.json")
    os.environ.pop("FERMIBADGER_LAUNCHER_PID", None)

    import pacsys
    from pacsys.testing import FakeBackend
    from PyQt5.QtWidgets import QApplication, QMessageBox

    import badger.gui.mini  # noqa: F401,E402  sets Badger's Qt high-DPI options, which must come before the QApplication
    app = QApplication.instance() or QApplication([])  # noqa: F841
    from badger.settings import init_settings

    init_settings("config.local.yaml")
    from badger.gui.mini.windows.main_window import BadgerMiniWindow
    from badger.gui.windows.main_window import BadgerMainWindow

    fb = FakeBackend()
    for d, v in START.items():
        for drf in (d, f"{d}.READING", f"{d}.SETTING"):
            fb.set_reading(drf, v)
    pacsys.get_many = fb.get_many

    def fail(_parent, title, text, *a, **k):
        raise AssertionError(f"{title}: {text}")

    QMessageBox.critical = QMessageBox.warning = staticmethod(fail)

    def check(window_cls):
        window = window_cls()
        editor = window.home_page.routine_editor
        editor.load_template_yaml(False, template_path=TEMPLATE)
        routine = editor._compose_routine()
        points = routine.initial_points
        assert len(points) == 1, points  # not the current values, nor random ones
        assert {n: float(points[n].iloc[0]) for n in WANTED} == WANTED, points
        assert not fb.writes
        return window

    try:
        windows = [check(BadgerMiniWindow), check(BadgerMainWindow)]  # noqa: F841 keep alive
    except BaseException:
        import traceback

        traceback.print_exc()
        stop_workers()  # else the run worker keeps the test alive
        os._exit(1)
    stop_workers()
    print("template_initial_points_gui_test ok", flush=True)
    os._exit(0)  # skip Qt/subprocess teardown noise


if __name__ == "__main__":  # Badger spawns workers that re-import this file
    main()
