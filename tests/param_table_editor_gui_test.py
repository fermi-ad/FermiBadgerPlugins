"""Offscreen check of the Edit... table for {name: value} parameters
(badger-1.6.0-param-table-editor.patch), in the -mini and the full GUI, using a
simulation template (nothing reaches ACNET).

Run from the repo root:
    pixi run python tests/param_table_editor_gui_test.py
"""
SIM = "tuning_templates/simulation/Xfer400MeV_example_VirtualAccelerator_MADXSuite.yaml"


def stop_workers():
    """Badger pre-spawns a run worker; left alive, it holds the output pipe open."""
    import multiprocessing
    for child in multiprocessing.active_children():
        child.terminate()
        child.join()


def main():
    import importlib.util
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import yaml
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox, QWidget

    app = QApplication.instance() or QApplication([])
    from badger.settings import init_settings

    init_settings("config.local.yaml")
    from badger.gui.components import pydantic_editor as pe
    from badger.gui.mini.windows.main_window import BadgerMiniWindow
    from badger.gui.windows.main_window import BadgerMainWindow

    # Values with commas (supply_groups, mults) survive the round trip.
    groups = {"SourceATrims": "L:ATRMHU,L:ATRMVU", "MUQ": "L:MUQ1*20.0,L:MUQ2*20.0"}
    assert yaml.safe_load(pe._mapping_to_text(groups)) == groups
    assert pe._parse_cell("1.2") == 1.2 and pe._parse_cell("hold") == "hold"
    assert pe._parse_cell("") is None

    # Key completion: the environment's variables, observables, and the
    # readings behind -SETPOINT observables.
    spec = importlib.util.spec_from_file_location(
        "ril", "plugins/environments/01_Linac_RIL_tuning_Pacsys/__init__.py")
    ril = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ril)
    holder = QWidget()
    holder.env = ril.Environment
    child = QWidget(holder)
    names = pe._environment_names(child)
    assert {"L:MUQ1", "L:TUNRAD", "L:D73BPV-SETPOINT", "L:D73BPV"} <= set(names), names[:10]

    def scripted(steps):
        """Run the dialog without showing it: apply `steps` to it, then OK."""
        def exec_(dialog):
            steps(dialog)
            dialog.accept()
            return QDialog.Accepted if dialog.result_mapping is not None else QDialog.Rejected
        pe.MappingTableDialog.exec_ = exec_

    def rows(dialog):
        t = dialog.table
        return [(t.item(r, 0).text(), t.item(r, 1).text()) for r in range(t.rowCount())]

    def check(window_cls, editor_of):
        window = window_cls()
        page = window.home_page
        page.routine_editor.load_template_yaml(False, template_path=SIM)
        for _ in range(20):
            app.processEvents()
        editor = editor_of(page.routine_editor)
        item = editor.findItems("setpoints", Qt.MatchFlag.MatchExactly, 0)[0]
        line = editor.itemWidget(item, editor.value_col)
        assert line.edit_button.text() == "Edit..."

        # Edit a value and add a row: no braces typed, order kept.
        seen = []

        def edit(d):
            seen.append(rows(d))
            d.table.item(0, 1).setText("0.25")
            d.add_row("bpvq18.x", "1.5")
        scripted(edit)
        line.edit_button.click()
        assert seen == [[("bpvq17.y", "0.0")]], seen
        assert line.text() == "{bpvq17.y: 0.25, bpvq18.x: 1.5}", line.text()
        assert pe.parameter_problems(page.routine_editor) == []

        # A bad value: OK refuses, the text is unchanged.
        warned = []
        QMessageBox.warning = staticmethod(lambda *a, **k: warned.append(a[2]))
        scripted(lambda d: d.table.item(1, 1).setText("abc"))
        line.edit_button.click()
        assert warned and "expected a number" in warned[0], warned
        assert line.text() == "{bpvq17.y: 0.25, bpvq18.x: 1.5}"

        # Broken text: the table starts from the template's values, OK replaces it.
        line.setText("{bpvq17.y: 0.25")
        notes = []
        scripted(lambda d: notes.append(rows(d)))
        line.edit_button.click()
        assert notes == [[("bpvq17.y", "0.0")]], notes
        assert line.text() == "{bpvq17.y: 0.0}" and not line.property("error")
        return window

    windows = [  # noqa: F841 keep alive
        check(BadgerMiniWindow, lambda r: r.env_box.edit_env_params),
        check(BadgerMainWindow, lambda r: r.env_box.edit),
    ]
    stop_workers()
    print("param_table_editor_gui_test ok", flush=True)
    os._exit(0)  # skip Qt/subprocess teardown noise


if __name__ == "__main__":  # Badger spawns workers that re-import this file
    try:
        main()
    finally:  # a failed assert must not leave a run worker holding the pipe
        stop_workers()
