"""Offscreen check of the -mini "Save as..." button (badger-1.6.0-mini-simpler-ui.patch):
saves default to <template dir>/saved/, the dropdown names them "saved/<name>" and
loads them back, and saving over anything else in the template directory is
refused. Uses a simulation template, so nothing reaches pacsys.

Run from the repo root:
    pixi run python tests/save_template_gui_test.py
"""
SIM = "tuning_templates/simulation/Xfer400MeV_example_VirtualAccelerator_MADXSuite.yaml"


def stop_workers():
    """Badger pre-spawns a run worker; left alive, it holds the output pipe open."""
    import multiprocessing
    for child in multiprocessing.active_children():
        child.terminate()
        child.join()


def main():
    import os
    import re
    import tempfile
    from pathlib import Path

    import yaml

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication, QFileDialog, QMessageBox

    app = QApplication.instance() or QApplication([])  # noqa: F841
    from badger.settings import init_settings

    init_settings("config.local.yaml")
    from badger.gui.mini.windows.main_window import BadgerMiniWindow

    window = BadgerMiniWindow()
    page = window.home_page.routine_editor
    templates = Path(tempfile.mkdtemp())
    page.template_dir = str(templates)  # keep the test out of the repo's tuning_templates/
    combo = page.env_box.template_cb

    page.load_template_yaml(False, template_path=SIM)
    stem = Path(SIM).stem
    assert combo.currentText() == stem, combo.currentText()

    # Default location and name: <template dir>/saved/<template>_<YYYYmmdd_HHMM>.yaml
    suggested = []

    def save_to(path):
        def dialog(_parent, _title, default, _filter, **_):
            suggested.append(default)
            return (str(path) if path else default), ""
        QFileDialog.getSaveFileName = staticmethod(dialog)

    warned = []
    QMessageBox.warning = staticmethod(lambda *a, **k: warned.append(a[2]))
    QMessageBox.critical = staticmethod(lambda *a, **k: (_ for _ in ()).throw(AssertionError(a[2])))

    save_to(None)
    page.env_box.save_template_button.click()
    default = Path(suggested[-1])
    assert default.parent == templates / "saved", default
    assert re.fullmatch(re.escape(stem) + r"_\d{8}_\d{4}\.yaml", default.name), default.name
    assert default.exists() and not warned
    saved = yaml.safe_load(default.read_text())
    assert saved["environment"]["name"] == "99_Sim_VirtualAccelerator_MADXSuite", saved["environment"]
    assert "vocs" in saved
    assert combo.currentText() == f"saved/{default.stem}", combo.currentText()

    # The dropdown's "saved/<name>" loads it back, from the template directory.
    page.load_template_yaml(False, template_path=f"saved/{default.name}")
    assert combo.currentText() == f"saved/{default.stem}", combo.currentText()

    # Saving over a template outside saved/ inside the template directory: refused.
    ops = templates / "01_Ops.yaml"
    ops.write_text("untouched")
    save_to(ops)
    page.env_box.save_template_button.click()
    assert warned and "managed in git" in warned[-1] and ops.read_text() == "untouched"

    # Anywhere outside the template directory is the operator's choice.
    elsewhere = Path(tempfile.mkdtemp()) / "mine.yaml"
    save_to(elsewhere)
    page.env_box.save_template_button.click()
    assert elsewhere.exists() and combo.currentText() == "mine"

    stop_workers()
    print("save_template_gui_test ok", flush=True)
    os._exit(0)  # skip Qt/subprocess teardown noise


if __name__ == "__main__":  # Badger spawns workers that re-import this file
    try:
        main()
    finally:  # a failed assert must not leave a run worker holding the pipe
        stop_workers()
