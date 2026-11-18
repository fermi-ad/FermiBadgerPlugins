"""Offscreen check of badger-1.6.0-constraint-risk-tolerance.patch, in both GUIs: the
constraint table's "Critical" column is now "Stopping", and a new "Risk Tolerance" column
(percent, 0.01 to 100, default 100 = no limit) feeds the generator's
constraint_risk_tolerance (xopt-3.2.2-constraint-risk-tolerance.patch).

- A template loads with every constraint at 100 %.
- 5 % typed for one constraint reaches the composed routine's generator as 0.05; a 0
  typed in becomes 0.01 % on screen.
- A template that carries constraint_risk_tolerance shows it in the column, and the
  routine composed from it carries it on (so Save as and run archives keep it); a past
  run reopened (refresh_ui, as History does) shows its tolerances again.

development/01_Linac_RIL_tuning_Pacsys.yaml with every device read mid-range from a
pacsys FakeBackend: nothing reaches ACNET.

Run from the repo root:
    pixi run python tests/constraint_risk_tolerance_gui_test.py
"""
TEMPLATE = "tuning_templates/development/01_Linac_RIL_tuning_Pacsys.yaml"


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
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QApplication, QMessageBox

    import badger.gui.mini  # noqa: F401  Badger's Qt options before the QApplication
    app = QApplication.instance() or QApplication([])  # noqa: F841
    from badger.settings import init_settings

    init_settings("config.local.yaml")
    from badger.gui.mini.windows.main_window import BadgerMiniWindow
    from badger.gui.windows.main_window import BadgerMainWindow

    sys.path.insert(0, "plugins")
    env = importlib.import_module("environments.01_Linac_RIL_tuning_Pacsys").Environment
    fb = FakeBackend()
    for d, (lo, hi) in env.variables.items():
        for drf in (d, f"{d}.READING", f"{d}.SETTING"):
            fb.set_reading(drf, (lo + hi) / 2)
    pacsys.get_many = fb.get_many

    def fail(_parent, title, text, *a, **k):
        raise AssertionError(f"{title}: {text}")

    QMessageBox.critical = QMessageBox.warning = staticmethod(fail)

    # The same template, carrying risk tolerances in its generator section.
    with_risk = yaml.safe_load(open(TEMPLATE))
    with_risk["generator"]["constraint_risk_tolerance"] = {"L:D34LM": 0.02, "L:TK1RAD": 0.1}
    risk_path = Path(tempfile.mkdtemp()) / "with_risk.yaml"
    risk_path.write_text(yaml.safe_dump(with_risk))

    def row_of(table, name):
        for i in range(table.rowCount()):
            item = table.item(i, 1)
            if item is not None and item.text() == name:
                return i
        raise AssertionError(f"{name} not in the constraint table")

    def check(window_cls):
        window = window_cls()
        editor = window.home_page.routine_editor
        table = editor.env_box.con_table
        editor.load_template_yaml(False, template_path=TEMPLATE)

        headers = [table.horizontalHeaderItem(c).text() for c in range(table.columnCount())]
        assert headers[4:] == ["Stopping", "Risk Tolerance"], headers
        assert all(next(iter(item.values()))[3] == 100.0 for item in table.data), table.data
        assert editor._compose_routine().generator.constraint_risk_tolerance is None

        # 5 % on one constraint reaches the generator
        spin = table.cellWidget(row_of(table, "L:TUNRAD"), 5)
        spin.setValue(5.0)
        assert editor._compose_routine().generator.constraint_risk_tolerance == {"L:TUNRAD": 0.05}

        # a 0 typed in becomes the most cautious value, 0.01 %, where it shows
        spin.selectAll()
        QTest.keyClicks(spin, "0")
        QTest.keyClick(spin, Qt.Key_Return)
        assert abs(spin.value() - 0.01) < 1e-9, spin.value()
        assert "0.01" in spin.text(), spin.text()
        assert editor._compose_routine().generator.constraint_risk_tolerance == {"L:TUNRAD": 0.0001}

        # a template's own tolerances fill the column and carry on into the routine
        editor.load_template_yaml(False, template_path=str(risk_path))
        assert abs(table.cellWidget(row_of(table, "L:D34LM"), 5).value() - 2.0) < 1e-9
        assert abs(table.cellWidget(row_of(table, "L:TK1RAD"), 5).value() - 10.0) < 1e-9
        routine = editor._compose_routine()
        assert routine.generator.constraint_risk_tolerance == {"L:D34LM": 0.02, "L:TK1RAD": 0.1}
        assert routine.generator.model_dump()["constraint_risk_tolerance"] == \
            {"L:D34LM": 0.02, "L:TK1RAD": 0.1}

        # a past run (History) shows its tolerances: reload the routine after clearing
        editor.load_template_yaml(False, template_path=TEMPLATE)
        assert table.cellWidget(row_of(table, "L:D34LM"), 5).value() == 100.0
        editor.refresh_ui(routine, silent=True)
        assert abs(table.cellWidget(row_of(table, "L:D34LM"), 5).value() - 2.0) < 1e-9
        assert abs(table.cellWidget(row_of(table, "L:TK1RAD"), 5).value() - 10.0) < 1e-9
        assert not fb.writes
        return window

    try:
        windows = [check(BadgerMiniWindow), check(BadgerMainWindow)]  # noqa: F841 keep alive
    except BaseException:
        import traceback

        traceback.print_exc()
        stop_workers()
        os._exit(1)
    stop_workers()
    print("constraint_risk_tolerance_gui_test ok", flush=True)
    os._exit(0)


if __name__ == "__main__":  # Badger spawns workers that re-import this file
    main()
