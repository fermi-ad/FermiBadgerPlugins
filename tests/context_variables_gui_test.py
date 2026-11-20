"""Offscreen check of badger-1.6.0-context-variables.patch in both GUIs: the variable
table's Context column (checked = an Xopt ContextualVariable: never moved, read and
modeled).

development/03_Booster_InjectionTuning_Pacsys.yaml, every device read from a pacsys
FakeBackend (nothing reaches ACNET). In each GUI:
- the column is there (header "Context", with a tooltip), unchecked by default;
- checking it for B:MV1 composes a routine whose VOCS has B:MV1 as a ContextualVariable,
  its domain the row's range; the initial-points table drops B:MV1;
- the template written from the GUI marks it, and loading that template checks it again;
- a past run reopened (refresh_ui, as History does) shows it checked.

Run from the repo root:
    pixi run python tests/context_variables_gui_test.py
"""
TEMPLATE = "tuning_templates/development/03_Booster_InjectionTuning_Pacsys.yaml"


def stop_workers():
    """Badger pre-spawns a run worker; left alive, it holds the output pipe open."""
    import multiprocessing
    for child in multiprocessing.active_children():
        child.terminate()
        child.join()


def main():
    import importlib
    import os
    import sys
    import tempfile
    from pathlib import Path

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ["FERMIBADGER_SNAPSHOT"] = str(Path(tempfile.mkdtemp()) / "snap.json")
    os.environ.pop("FERMIBADGER_LAUNCHER_PID", None)

    import pacsys
    import yaml
    from pacsys.testing import FakeBackend
    from PyQt5.QtWidgets import QApplication, QCheckBox, QMessageBox

    import badger.gui.mini  # noqa: F401  Badger's Qt options before the QApplication
    app = QApplication.instance() or QApplication([])  # noqa: F841
    from badger.settings import init_settings

    init_settings("config.local.yaml")
    from badger.gui.mini.windows.main_window import BadgerMiniWindow
    from badger.gui.windows.main_window import BadgerMainWindow
    from xopt.vocs import ContextualVariable

    sys.path.insert(0, "plugins")
    env = importlib.import_module("environments.03_Booster_Pacsys").Environment
    fb = FakeBackend()
    for d, (lo, hi) in env.variables.items():  # the mini GUI reads every variable's value
        for drf in (d, f"{d}.READING", f"{d}.SETTING"):
            fb.set_reading(drf, (lo + hi) / 2)
    for d in env.observables:
        if ":" in d:
            fb.set_reading(d, 0.01)
    pacsys.get_many = fb.get_many

    def fail(_parent, title, text, *a, **k):
        raise AssertionError(f"{title}: {text}")

    QMessageBox.critical = QMessageBox.warning = staticmethod(fail)

    def row_of(table, name):
        for i in range(table.rowCount()):
            item = table.item(i, 1)
            if item is not None and item.text() == name:
                return i
        raise AssertionError(f"{name} not in the variable table")

    def context_box(table, name):
        col = table.columnCount() - 1
        box = table.cellWidget(row_of(table, name), col).findChild(QCheckBox)
        assert box is not None, "no Context checkbox"
        return box

    def check(window_cls):
        window = window_cls()
        editor = window.home_page.routine_editor
        table = editor.env_box.var_table
        editor.load_template_yaml(False, template_path=TEMPLATE)

        col = table.columnCount() - 1
        header = table.horizontalHeaderItem(col)
        assert header.text() == "Context" and "never moved" in header.toolTip(), header.text()
        assert not context_box(table, "B:MV1").isChecked()
        routine = editor._compose_routine()
        assert not isinstance(routine.vocs.variables["B:MV1"], ContextualVariable)
        assert "B:MV1" in editor.get_init_table_header()

        # check it: the composed VOCS makes it contextual, over the row's range
        context_box(table, "B:MV1").setChecked(True)
        routine = editor._compose_routine()
        var = routine.vocs.variables["B:MV1"]
        assert isinstance(var, ContextualVariable), type(var)
        lo, hi = table.bounds["B:MV1"]
        assert list(var.domain) == [lo, hi], (var.domain, lo, hi)
        assert not isinstance(routine.vocs.variables["B:MH1"], ContextualVariable)
        assert "B:MV1" not in editor.get_init_table_header(), editor.get_init_table_header()

        # the template written from the GUI marks it; loading that template checks it again
        saved = editor.generate_template_dict_from_gui()
        entry = saved["vocs"]["variables"]["B:MV1"]
        assert isinstance(entry, dict) and entry.get("type") == "ContextualVariable", entry
        path = Path(tempfile.mkdtemp()) / "ctx.yaml"
        path.write_text(yaml.safe_dump(saved))
        editor.load_template_yaml(False, template_path=TEMPLATE)
        assert not context_box(table, "B:MV1").isChecked()
        editor.load_template_yaml(False, template_path=str(path))
        assert context_box(table, "B:MV1").isChecked()
        assert isinstance(editor._compose_routine().vocs.variables["B:MV1"], ContextualVariable)

        # a past run reopened shows it
        editor.load_template_yaml(False, template_path=TEMPLATE)
        editor.refresh_ui(routine, silent=True)
        assert context_box(table, "B:MV1").isChecked()
        assert not fb.writes, fb.writes
        return window

    try:
        windows = [check(BadgerMiniWindow), check(BadgerMainWindow)]  # noqa: F841 keep alive
    except BaseException:
        import traceback

        traceback.print_exc()
        stop_workers()
        os._exit(1)
    stop_workers()
    print("context_variables_gui_test ok", flush=True)
    os._exit(0)


if __name__ == "__main__":  # Badger spawns workers that re-import this file
    main()
