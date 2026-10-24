"""Offscreen check of the Revert button, the snapshot at template load and at Go,
and the Keep/Revert question on close (badger-1.6.0-revert-settings.patch), in
both the -mini and the full GUI, with pacsys replaced by FakeBackend.

Run from the repo root:
    pixi run python tests/settings_snapshot_gui_test.py
"""
SIM = "tuning_templates/simulation/Xfer400MeV_example_VirtualAccelerator_MADXSuite.yaml"
ZZ = "tuning_templates/development/ZZ_PacsysTesting.yaml"
START = {"G:AMANDA": 1.0, "Z:CUBE_X": 2.0, "Z:CUBE_Y": 3.0, "Z:CUBE_Z": 4.0}


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

    import pacsys
    from pacsys.testing import FakeBackend
    from PyQt5.QtWidgets import QApplication, QMessageBox

    import badger.gui.mini  # noqa: F401,E402  sets Badger's Qt high-DPI options, which must come before the QApplication
    app = QApplication.instance() or QApplication([])  # noqa: F841
    from badger.settings import init_settings

    init_settings("config.local.yaml")
    from badger.gui.mini.windows.main_window import BadgerMiniWindow
    from badger.gui.windows.main_window import BadgerMainWindow
    import settings_snapshot  # plugin root is on the path once badger.factory loads

    settings_snapshot.time.sleep = lambda s: None
    shown = []

    def answer(text):
        """Make every QMessageBox pick the button labelled `text` (no dialogs offscreen)."""
        def pick(self):
            shown.append(self.text())
            [b for b in self.buttons() if b.text().replace("&", "") == text][0].click()
        QMessageBox.exec_ = pick
        QMessageBox.information = staticmethod(lambda *a, **k: None)

    def fail(_parent, title, text, *a, **k):
        raise AssertionError(f"{title}: {text}")

    def check(window_cls):
        snap_file = Path(tempfile.mkdtemp()) / "snap.json"
        os.environ["FERMIBADGER_SNAPSHOT"] = str(snap_file)
        os.environ.pop("FERMIBADGER_LAUNCHER_PID", None)
        fb = FakeBackend()
        for d, v in START.items():
            for drf in (f"{d}.SETTING", f"{d}.READING", d):
                fb.set_reading(drf, v)
        pacsys.get_many = fb.get_many
        writer_roles = []

        class Writer:  # restore() closes each role's session; keep the shared fake open
            write_many = staticmethod(fb.write_many)
            close = staticmethod(lambda: None)

        settings_snapshot._open_writer = lambda role: writer_roles.append(role) or Writer
        QMessageBox.critical = QMessageBox.warning = staticmethod(fail)

        window = window_cls()
        page = window.home_page
        bar = page.run_action_bar
        assert bar.btn_revert.isVisibleTo(window) and not bar.btn_revert.isEnabled()

        # Simulation template: nothing writable, no snapshot, button stays disabled.
        page.routine_editor.load_template_yaml(False, template_path=SIM)
        assert not snap_file.exists() and not bar.btn_revert.isEnabled()

        page.routine_editor.load_template_yaml(False, template_path=ZZ)
        data = settings_snapshot.load(snap_file)
        assert sorted(data["devices"]) == sorted(START), data
        assert {d["role"] for d in data["devices"].values()} == {"testing"}
        assert bar.btn_revert.isEnabled()
        status = page.status_bar  # the label elides; its tooltip has the full text
        assert "NO automatic restore" in status.toolTip(), status.toolTip()
        os.environ["FERMIBADGER_LAUNCHER_PID"] = str(os.getpid())
        page.routine_editor.load_template_yaml(False, template_path=ZZ)
        until = settings_snapshot.auto_restore_until(settings_snapshot.load(snap_file))
        assert f"automatic restore if interrupted until {until:%H:%M}" in status.toolTip()

        # Go: snapshots the environment as it is now (here: as if chosen without a
        # template); a failed snapshot asks, and No cancels the run.
        snap_file.unlink()
        assert page.snapshot_at_go() is True
        assert sorted(settings_snapshot.load(snap_file)["devices"]) == sorted(START)
        snap_file.unlink()
        pacsys.get_many = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no ACNET"))
        asked = []
        QMessageBox.warning = staticmethod(lambda *a, **k: asked.append(a[2]) or QMessageBox.No)
        started = []
        page.run_monitor.start = lambda **k: started.append(k)
        page.start_run()
        assert asked and "no ACNET" in asked[0] and not started  # run cancelled
        QMessageBox.warning = staticmethod(fail)
        pacsys.get_many = fb.get_many
        assert page.snapshot_at_go() is True

        # Revert button: confirm, write back only what moved.
        fb.set_reading("Z:CUBE_X.SETTING", 9.0)
        answer("Yes")
        page.revert_settings()
        assert fb.get_written_value("Z:CUBE_X.SETTING") == 2.0 and len(fb.writes) == 1
        assert writer_roles == ["testing"]
        assert "<pre style=" in shown[-1] and "Device" in shown[-1], shown[-1]  # fixed-width
        assert settings_snapshot.load(snap_file)["resolved"] is None  # session goes on

        # Close with changes: Cancel stays open, Keep records the decision.
        fb.set_reading("Z:CUBE_Y.SETTING", 7.0)
        answer("Cancel")
        assert page.settle_settings() is False
        assert settings_snapshot.load(snap_file)["resolved"] is None
        answer("Keep")
        assert page.settle_settings() is True
        assert settings_snapshot.load(snap_file)["resolved"] == "keep"

        # Close → Revert writes back and records it.
        settings_snapshot.resolve(snap_file, None)
        answer("Revert")
        assert page.settle_settings() is True
        assert fb.get_written_value("Z:CUBE_Y.SETTING") == 3.0
        assert settings_snapshot.load(snap_file)["resolved"] == "reverted"

        # Close with nothing changed: no question, recorded as keep.
        settings_snapshot.resolve(snap_file, None)
        QMessageBox.exec_ = lambda self: (_ for _ in ()).throw(AssertionError("asked"))
        assert page.settle_settings() is True
        assert settings_snapshot.load(snap_file)["resolved"] == "keep"
        return window

    windows = [check(BadgerMiniWindow), check(BadgerMainWindow)]  # noqa: F841 keep alive
    stop_workers()
    print("settings_snapshot_gui_test ok", flush=True)
    os._exit(0)  # skip Qt/subprocess teardown noise


if __name__ == "__main__":  # Badger spawns workers that re-import this file
    try:
        main()
    finally:  # a failed assert must not leave a run worker holding the pipe
        stop_workers()
