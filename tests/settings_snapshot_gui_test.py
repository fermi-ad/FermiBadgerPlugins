"""Offscreen check of the -mini Revert button and the Keep/Revert question on close
(badger-1.6.0-mini-revert-settings.patch), with pacsys replaced by FakeBackend.

Run from the repo root:
    pixi run python tests/settings_snapshot_gui_test.py
"""
def main():
    import os
    import sys
    import tempfile
    from pathlib import Path

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    snap_file = Path(tempfile.mkdtemp()) / "snap.json"
    os.environ["FERMIBADGER_SNAPSHOT"] = str(snap_file)

    import pacsys  # noqa: E402
    from pacsys.testing import FakeBackend  # noqa: E402
    from PyQt5.QtWidgets import QApplication, QMessageBox  # noqa: E402

    fb = FakeBackend()
    for d, v in {"G:AMANDA": 1.0, "Z:CUBE_X": 2.0, "Z:CUBE_Y": 3.0, "Z:CUBE_Z": 4.0}.items():
        fb.set_reading(f"{d}.SETTING", v)
        fb.set_reading(f"{d}.READING", v)
        fb.set_reading(d, v)
    pacsys.get_many = fb.get_many

    app = QApplication.instance() or QApplication([])
    from badger.settings import init_settings  # noqa: E402

    init_settings("config.local.yaml")
    from badger.gui.mini.windows.main_window import BadgerMiniWindow  # noqa: E402
    import settings_snapshot  # noqa: E402  (plugin root is on the path once badger.factory loads)

    writer_roles = []
    shown = []


    class Writer:  # restore() closes each role's session; keep the shared fake open
        write_many = staticmethod(fb.write_many)
        close = staticmethod(lambda: None)


    settings_snapshot._open_writer = lambda role: writer_roles.append(role) or Writer
    settings_snapshot.time.sleep = lambda s: None


    def answer(text):
        """Make every QMessageBox pick the button labelled `text` (no dialogs offscreen)."""
        def pick(self):
            shown.append(self.text())
            [b for b in self.buttons() if b.text().replace("&", "") == text][0].click()
        QMessageBox.exec_ = pick
        QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
        QMessageBox.information = staticmethod(lambda *a, **k: None)


    def fail(_parent, title, text, *a, **k):
        raise AssertionError(f"{title}: {text}")


    QMessageBox.critical = QMessageBox.warning = staticmethod(fail)


    window = BadgerMiniWindow()
    bar = window.home_page.run_action_bar
    assert bar.btn_revert.isVisibleTo(window) and not bar.btn_revert.isEnabled()

    # Simulation template: nothing writable, no snapshot, button stays disabled.
    window.home_page.routine_editor.load_template_yaml(
        template_path="tuning_templates/simulation/Xfer400MeV_example_VirtualAccelerator_MADXSuite.yaml")
    assert not snap_file.exists() and not bar.btn_revert.isEnabled()

    window.home_page.routine_editor.load_template_yaml(
        template_path="tuning_templates/development/ZZ_PacsysTesting.yaml")
    data = settings_snapshot.load(snap_file)
    assert sorted(data["devices"]) == ["G:AMANDA", "Z:CUBE_X", "Z:CUBE_Y", "Z:CUBE_Z"], data
    assert {d["role"] for d in data["devices"].values()} == {"testing"}
    assert bar.btn_revert.isEnabled()
    status = window.home_page.status_bar  # the label elides; its tooltip has the full text
    assert "NO automatic restore" in status.toolTip(), status.toolTip()  # no safe-badger here
    os.environ["FERMIBADGER_LAUNCHER_PID"] = str(os.getpid())
    window.home_page.routine_editor.load_template_yaml(
        template_path="tuning_templates/development/ZZ_PacsysTesting.yaml")
    until = settings_snapshot.auto_restore_until(settings_snapshot.load(snap_file))
    assert f"automatic restore if interrupted until {until:%H:%M}" in status.toolTip()
    window.resize(1250, 790)
    window.show()
    for _ in range(50):
        QApplication.processEvents()
    window.grab().save(os.environ.get("SHOT_DIR", tempfile.gettempdir()) + "/status_bar.png")

    # Revert button: confirm, write back only what moved.
    fb.set_reading("Z:CUBE_X.SETTING", 9.0)
    answer("Yes")
    window.home_page.revert_settings()
    assert fb.get_written_value("Z:CUBE_X.SETTING") == 2.0 and len(fb.writes) == 1
    assert writer_roles == ["testing"]
    assert "<pre style=" in shown[-1] and "Device" in shown[-1], shown[-1]  # fixed-width table
    assert settings_snapshot.load(snap_file)["resolved"] is None  # session goes on

    # Close with changes: Cancel stays open, Keep records the decision.
    fb.set_reading("Z:CUBE_Y.SETTING", 7.0)
    answer("Cancel")
    assert window.home_page.settle_settings() is False
    assert settings_snapshot.load(snap_file)["resolved"] is None
    answer("Keep")
    assert window.home_page.settle_settings() is True
    assert settings_snapshot.load(snap_file)["resolved"] == "keep"

    # Close → Revert writes back and records it.
    settings_snapshot.resolve(snap_file, None)
    answer("Revert")
    assert window.home_page.settle_settings() is True
    assert fb.get_written_value("Z:CUBE_Y.SETTING") == 3.0
    assert settings_snapshot.load(snap_file)["resolved"] == "reverted"

    # Close with nothing changed: no question, recorded as keep.
    settings_snapshot.resolve(snap_file, None)
    QMessageBox.exec_ = lambda self: (_ for _ in ()).throw(AssertionError("asked"))
    assert window.home_page.settle_settings() is True
    assert settings_snapshot.load(snap_file)["resolved"] == "keep"

    import multiprocessing  # Badger's pre-spawned run worker; it isn't queued yet
    for child in multiprocessing.active_children():
        child.terminate()
        child.join()
    print("settings_snapshot_gui_test ok", flush=True)
    os._exit(0)  # skip Qt/subprocess teardown noise


if __name__ == "__main__":  # Badger spawns workers that re-import this file
    try:
        main()
    finally:  # a failed assert must not leave Badger's run worker holding the pipe
        import multiprocessing
        for child in multiprocessing.active_children():
            child.terminate()
