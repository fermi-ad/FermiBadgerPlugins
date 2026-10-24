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

    import badger.gui.mini  # noqa: F401,E402  sets Badger's Qt high-DPI options, which must come before the QApplication
    app = QApplication.instance() or QApplication([])
    from badger.settings import init_settings

    init_settings("config.local.yaml")
    from badger.gui.components import pydantic_editor as pe
    from badger.gui.mini.windows.main_window import BadgerMiniWindow
    from badger.gui.windows.main_window import BadgerMainWindow

    # Values with commas (e.g. sample_events' '@e,52,e,0') survive the round trip.
    groups = {"default": "@e,52,e,0", "B:BOOEFF": "@e,1f,e,0"}
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

    # Mults and bulk supplies: one parameter each, edited in one dialog with
    # members from pulldowns of the environment's settable devices. RIL's defaults.
    params = {f: ril.Environment.model_fields[f].default for f in ("mults", "supplies", "debug")}
    page = QWidget()
    page.env = ril.Environment
    editor = pe.BadgerPydanticEditor(page)
    editor.set_params_from_dict(params)

    def line_of(field):
        item = editor.findItems(field, Qt.MatchFlag.MatchExactly, 0)[0]
        return editor.itemWidget(item, editor.value_col)

    def group_steps(steps):
        def exec_(dialog):
            steps(dialog)
            dialog.accept()
            return QDialog.Accepted if dialog.result is not None else QDialog.Rejected
        pe.DeviceGroupsDialog.exec_ = exec_

    def members(dialog, group):
        _, table = dialog.sections[group]
        return [table.cellWidget(r, 0).currentText() for r in range(table.rowCount())]

    def mults_edit(d):
        assert set(d.sections) == {"MUQ", "MDQ"}, list(d.sections)
        assert members(d, "MUQ") == ["L:MUQ1", "L:MUQ2"], members(d, "MUQ")
        combo = d.sections["MUQ"][1].cellWidget(0, 0)
        items = [combo.itemText(i) for i in range(combo.count())]
        assert "L:MUQ1" in items and not any(i.startswith("mult:") for i in items)
        assert not combo.isEditable()  # a pulldown: the environment's devices only
        assert d.sections["MUQ"][1].item(0, 2).text() == "1"  # 20 x 0.05 per step
        d.sections["MUQ"][0].setValue(0.1)
        d.sections["MUQ"][1].cellWidget(0, 1).setValue(10.0)
        d.add_member("MUQ", "L:MDQ1", 5.0)
    group_steps(mults_edit)
    line_of("mults").edit_button.click()
    mults = yaml.safe_load(line_of("mults").text())
    assert mults["MUQ"] == {"step": 0.1, "members": {"L:MUQ1": 10.0, "L:MUQ2": 20.0, "L:MDQ1": 5.0}}, mults
    assert mults["MDQ"] == {"step": 0.05, "members": {"L:MDQ1": 20.0, "L:MDQ2": 20.0}}, mults
    ril.Environment(mults=mults)  # what the environment validates at Go

    warned = []
    QMessageBox.warning = staticmethod(lambda *a, **k: warned.append(a[2]))
    group_steps(lambda d: d.add_member("MDQ", "L:MDQ1", 1.0))  # already a member
    line_of("mults").edit_button.click()
    assert warned and "L:MDQ1 is listed twice" in warned[-1], warned

    def supplies_edit(d):
        _, table = d.sections["SourceATrims"]
        assert table.columnCount() == 1  # members only, no scale
        assert members(d, "SourceATrims") == ["L:ATRMHU", "L:ATRMVU", "L:ATRMHD", "L:ATRMVD"]
        d.sections["SourceATrims"][0].setValue(6.5)
        table.removeRow(3)
    group_steps(supplies_edit)
    line_of("supplies").edit_button.click()
    supplies = yaml.safe_load(line_of("supplies").text())
    assert supplies["SourceATrims"] == {"limit": 6.5, "devices": ["L:ATRMHU", "L:ATRMVU", "L:ATRMHD"]}
    ril.Environment(supplies=supplies)
    assert pe.parameter_problems(page) == []

    # Flattening a mult by hand is caught as you type.
    line_of("mults").setText("{MUQ: 0.05}")
    assert "expected a {...} group" in pe.parameter_problems(page)[0], pe.parameter_problems(page)

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
