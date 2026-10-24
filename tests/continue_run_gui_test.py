"""Offscreen check of "Continue from run" (badger-1.6.0-continue-run.patch), in both
GUIs: the action bar's Continue button and the History menu's entry arm it; Go
then starts a new run seeded with the displayed run's points (no initial points),
with a fresh trust region and a note in its description; showing another run
disarms it. Uses a simulation template and fake points, and stops at
run_monitor.start, so nothing is evaluated and nothing reaches pacsys.

Run from the repo root:
    pixi run python tests/continue_run_gui_test.py
"""
SIM = "tuning_templates/simulation/Xfer400MeV_example_VirtualAccelerator_MADXSuite.yaml"
N = 6


def stop_workers():
    """Badger pre-spawns a run worker; left alive, it holds the output pipe open."""
    import multiprocessing
    for child in multiprocessing.active_children():
        child.terminate()
        child.join()


def fake_points(vocs):
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(0)
    points = pd.DataFrame(
        {n: rng.uniform(lo, hi, N) for n, (lo, hi) in zip(vocs.variable_names, vocs.bounds)}
    )
    for n in vocs.output_names:
        points[n] = rng.normal(size=N)
    return points


def check_helpers():
    import pandas as pd
    from xopt import VOCS
    from xopt.generators.bayesian import ExpectedImprovementGenerator

    from badger.errors import BadgerRoutineError
    from badger.gui.components.continue_run import (
        fresh_trust_region,
        note_source,
        seed_data,
    )

    class R:  # stands in for a Routine: only what the helpers read
        def __init__(self, variables, data=None, description=None):
            vocs = VOCS(variables=variables, objectives={"f": "MINIMIZE"})
            self.generator = ExpectedImprovementGenerator(
                vocs=vocs, turbo_controller="optimize"
            )
            self.vocs, self.data, self.description = vocs, data, description

    old = R({"x": [0, 1]}, pd.DataFrame({"x": [0.2, 0.8], "f": [1.0, 2.0]}))
    wider = R({"x": [-5, 5]})
    data = seed_data(wider, old)
    assert len(data) == 2 and (data["live"] == 0).all()

    try:
        seed_data(R({"y": [0, 1]}), old)
        raise AssertionError("different variables accepted")
    except BadgerRoutineError as e:
        assert "same variables" in str(e)

    wider.generator.add_data(data)
    wider.generator.turbo_controller.length = 0.05  # an earlier run shrank it
    wider.generator.turbo_controller.failure_tolerance = 7  # a setting: kept
    fresh_trust_region(wider)
    tc = wider.generator.turbo_controller
    assert tc.length == 0.25 and tc.failure_tolerance == 7, tc
    assert tc.vocs is wider.generator.vocs  # the new ranges

    note_source(wider, 2, "A-2026.yaml")
    assert wider.description == "Seeded with 2 points from A-2026.yaml."
    wider.description = "tuning"
    note_source(wider, 2)
    assert wider.description == "tuning\nSeeded with 2 points from earlier runs."


def main():
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication, QMessageBox

    import badger.gui.mini  # noqa: F401,E402  sets Badger's Qt high-DPI options, which must come before the QApplication
    app = QApplication.instance() or QApplication([])  # noqa: F841
    from badger.settings import init_settings

    init_settings("config.local.yaml")
    from badger.gui.mini.windows.main_window import BadgerMiniWindow
    from badger.gui.windows.main_window import BadgerMainWindow

    check_helpers()

    def fail(_parent, title, text, *a, **k):
        raise AssertionError(f"{title}: {text}")

    QMessageBox.critical = QMessageBox.warning = staticmethod(fail)
    QMessageBox.exec_ = lambda self: QMessageBox.Ok  # full GUI's "Data loaded" notice

    def check(window_cls):
        window = window_cls()
        page = window.home_page
        bar = page.run_action_bar
        btn = bar.btn_continue
        assert btn.isVisibleTo(window) and not btn.isEnabled()

        page.routine_editor.load_template_yaml(False, template_path=SIM)
        source = page.routine_editor._compose_routine()
        source.data = fake_points(source.vocs)
        page.current_routine = source  # as go_run leaves it for a displayed run
        if hasattr(page, "data_panel"):
            page.data_panel.load_data(source)

        # Enabled once a run with points is shown; another run shown disarms it.
        bar.toggle_other(False)
        assert btn.isEnabled()
        page.history_browser.sig_continue.emit()  # History menu entry
        assert btn.isChecked()
        if hasattr(page, "data_panel"):
            assert page.data_panel.use_data and not page.data_panel.init_points
        page.go_run(-1)  # (also empties the shown routine's data)
        assert not btn.isChecked()
        source.data = fake_points(source.vocs)
        page.current_routine = source
        if hasattr(page, "data_panel"):
            page.data_panel.load_data(source)
        bar.toggle_other(False)
        btn.setChecked(True)

        started = []
        page.run_monitor.start = lambda **k: started.append(k)
        page.start_run()
        assert started, "Go did not start"
        assert started[-1]["run_data_flag"] and not started[-1]["init_points_flag"]
        run = page.current_routine
        assert run is not source and len(run.data) == N, run.data
        assert (run.data["live"] == 0).all()
        assert f"Seeded with {N} points" in (run.description or ""), run.description
        return window

    try:
        windows = [check(BadgerMiniWindow), check(BadgerMainWindow)]  # noqa: F841 keep alive
    except BaseException:
        import traceback

        traceback.print_exc()
        stop_workers()  # else the run worker keeps the test alive
        os._exit(1)
    stop_workers()
    print("continue_run_gui_test ok", flush=True)
    os._exit(0)  # skip Qt/subprocess teardown noise


if __name__ == "__main__":  # Badger spawns workers that re-import this file
    main()
