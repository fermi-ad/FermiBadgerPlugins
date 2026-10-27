"""Offscreen check of badger-1.6.0-quiet-template-load.patch, in both GUIs: loading
a template with a safety TuRBO controller (a RIL template) logs no ERROR. Before,
filling the objectives table sent a partial VOCS (objectives, no constraints yet)
to the generator editor, whose validation then failed ("safety turbo controller
can only be used with constraints") and was logged twice on every such load. The
editor must still end up with the whole VOCS: the composed routine has the
safety controller and all the template's constraints.

development/01_Linac_RIL_tuning_Pacsys.yaml with every device read mid-range from
a pacsys FakeBackend: nothing reaches ACNET.

Run from the repo root:
    pixi run python tests/quiet_template_load_gui_test.py
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
    import logging
    import os
    import sys
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

    errors = []

    class Errors(logging.Handler):
        def emit(self, record):
            if record.levelno >= logging.ERROR:
                errors.append(record.getMessage())

    logging.getLogger().addHandler(Errors())

    import yaml

    wanted = sorted(yaml.safe_load(open(TEMPLATE))["vocs"]["constraints"])

    def check(window_cls):
        window = window_cls()
        editor = window.home_page.routine_editor
        errors.clear()
        editor.load_template_yaml(False, template_path=TEMPLATE)
        assert not errors, errors
        routine = editor._compose_routine()
        tc = routine.generator.turbo_controller
        assert type(tc).__name__ == "SafetyTurboController", tc
        assert sorted(routine.vocs.constraint_names) == wanted, routine.vocs.constraint_names
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
    print("quiet_template_load_gui_test ok", flush=True)
    os._exit(0)  # skip Qt/subprocess teardown noise


if __name__ == "__main__":  # Badger spawns workers that re-import this file
    main()
