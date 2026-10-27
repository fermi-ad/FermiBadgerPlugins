"""Offscreen check of badger-1.6.0-outside-limits.patch, in both GUIs: a variable
whose current value is outside its hard limits (like the RIL source solenoids at
50 A, limits 300-500 A, during the 2026-10-26 shutdown prep) is unticked with a
warning when the template loads, instead of a zero-width range crashing the load;
the other variables load as usual; re-ticked, Go refuses and unticks it again;
back within its limits, Go starts.

ZZ_PacsysTesting template (limits -100 to 100) with Z:CUBE_X at 150; pacsys reads
come from a FakeBackend, and run_monitor.start is stubbed: nothing reaches ACNET.

Run from the repo root:
    pixi run python tests/outside_limits_gui_test.py
"""
TEMPLATE = "tuning_templates/development/ZZ_PacsysTesting.yaml"
START = {"G:AMANDA": 1.0, "Z:CUBE_X": 150.0, "Z:CUBE_Y": 3.0, "Z:CUBE_Z": 4.0}


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

    def set_device(d, v):
        for drf in (d, f"{d}.READING", f"{d}.SETTING"):
            fb.set_reading(drf, v)

    for d, v in START.items():
        set_device(d, v)
    pacsys.get_many = fb.get_many

    warned = []

    def fail(_parent, title, text, *a, **k):
        raise AssertionError(f"{title}: {text}")

    QMessageBox.critical = staticmethod(fail)
    QMessageBox.warning = staticmethod(lambda _p, title, text, *a, **k: warned.append((title, text)))

    def check(window_cls):
        set_device("Z:CUBE_X", 150.0)
        window = window_cls()
        page = window.home_page
        editor = page.routine_editor
        table = editor.env_box.var_table
        warned.clear()

        # Load: Z:CUBE_X unticked with a warning, no crash; the rest load as usual.
        editor.load_template_yaml(False, template_path=TEMPLATE)
        assert len(warned) == 1, warned
        title, text = warned[0]
        assert title == "Variables outside their limits", title
        assert "Z:CUBE_X: reads 150, limits -100 to 100" in text, text
        assert "Go was cancelled" not in text
        assert not table.is_checked("Z:CUBE_X")
        assert all(table.is_checked(d) for d in ("G:AMANDA", "Z:CUBE_Y", "Z:CUBE_Z"))
        vocs, _ = editor.env_box.compose_vocs()
        assert sorted(vocs.variable_names) == ["G:AMANDA", "Z:CUBE_Y", "Z:CUBE_Z"]
        assert all(hi > lo for lo, hi in vocs.bounds), vocs.bounds

        # Re-ticked by hand: Go refuses and unticks it again.
        started = []
        page.run_monitor.start = lambda **k: started.append(k)
        table.set_selected(list(START))
        warned.clear()
        page.start_run()
        assert not started, "Go started with a variable outside its limits"
        assert len(warned) == 1 and "Go was cancelled" in warned[0][1], warned
        assert not table.is_checked("Z:CUBE_X")

        # Back within its limits: Go starts.
        set_device("Z:CUBE_X", 2.0)
        table.set_selected(list(START))
        warned.clear()
        page.start_run()
        assert started and not warned, (started, warned)
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
    print("outside_limits_gui_test ok", flush=True)
    os._exit(0)  # skip Qt/subprocess teardown noise


if __name__ == "__main__":  # Badger spawns workers that re-import this file
    main()
