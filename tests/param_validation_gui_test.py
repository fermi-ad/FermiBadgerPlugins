"""Offscreen check of dict-valued parameter validation as you type
(badger-1.6.0-param-validation.patch), in the -mini and the full GUI, using a
simulation template (nothing reaches ACNET).

Run from the repo root:
    pixi run python tests/param_validation_gui_test.py
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

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication, QMessageBox

    app = QApplication.instance() or QApplication([])
    from badger.settings import init_settings

    init_settings("config.local.yaml")
    from badger.gui.components.pydantic_editor import check_dict_text, parameter_problems
    from badger.gui.mini.windows.main_window import BadgerMiniWindow
    from badger.gui.windows.main_window import BadgerMainWindow

    # The kinds of value a field accepts come from the template's own value.
    numbers = {"L:A": 1.0}
    assert check_dict_text("{L:A: 2, L:B: -0.5}", numbers) is None
    assert "has no value" in check_dict_text("{L:A 2}", numbers)
    assert "expected a number" in check_dict_text("{L:A: abc}", numbers)
    assert "braces" in check_dict_text("{L:A: 2", numbers)
    assert "braces" in check_dict_text("L:A, 2", numbers) or "Must be" in check_dict_text("L:A, 2", numbers)
    hold = {"defaults": None, "B:400DFT": "hold"}  # EnergyStabilization setpoints
    assert check_dict_text("{defaults: None, B:400DFT: hold, B:400DF2: 1.5}", hold) is None
    assert check_dict_text("{}", numbers) is None

    def check(window_cls, editor_of):
        window = window_cls()
        page = window.home_page
        page.routine_editor.load_template_yaml(False, template_path=SIM)
        for _ in range(20):
            app.processEvents()
        editor = editor_of(page.routine_editor)
        item = editor.findItems("setpoints", __import__("PyQt5").QtCore.Qt.MatchFlag.MatchExactly, 0)[0]
        line = editor.itemWidget(item, editor.value_col)
        assert line.text() == "{bpvq17.y: 0.0}", line.text()
        assert parameter_problems(page.routine_editor) == []

        line.setText("{bpvq17.y 0.0}")  # typed: validate() runs on the change
        assert line.property("error") is True
        assert "has no value" in item.toolTip(0), item.toolTip(0)

        warned, started = [], []
        QMessageBox.warning = staticmethod(lambda *a, **k: warned.append(a[2]))
        page.run_monitor.start = lambda **k: started.append(k)
        page.start_run()
        assert warned and "setpoints: 'bpvq17.y 0.0' has no value" in warned[0], warned
        assert not started  # Go refused

        line.setText("{bpvq17.y: 0.25}")  # fixed: the mark goes away
        assert not line.property("error"), line.property("error")
        assert parameter_problems(page.routine_editor) == []
        return window

    windows = [  # noqa: F841 keep alive
        check(BadgerMiniWindow, lambda r: r.env_box.edit_env_params),
        check(BadgerMainWindow, lambda r: r.env_box.edit),
    ]
    stop_workers()
    print("param_validation_gui_test ok", flush=True)
    os._exit(0)  # skip Qt/subprocess teardown noise


if __name__ == "__main__":  # Badger spawns workers that re-import this file
    try:
        main()
    finally:  # a failed assert must not leave a run worker holding the pipe
        stop_workers()
