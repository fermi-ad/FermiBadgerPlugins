"""Offscreen check of "Continue from run" (badger-1.6.0-continue-run.patch), in both
GUIs: the action bar's Continue button and the History menu's entry arm it; Go
then starts a new run seeded with the displayed run's points (no initial points),
with a fresh trust region and a note in its description; showing another run
disarms it. "Add its points" adds more runs, merged after a summary dialog.
Also the merge rules themselves: runs with other variables, or missing one of
the new run's constraints, are skipped; changed environment parameters or
formulas are reported; the age and range filters.

Uses a simulation template and fake points, and stops at run_monitor.start, so
nothing is evaluated and nothing reaches pacsys.

Run from the repo root:
    pixi run python tests/continue_run_gui_test.py
"""
SIM = "tuning_templates/simulation/Xfer400MeV_example_VirtualAccelerator_MADXSuite.yaml"
TUNEQX = "tuning_templates/simulation/TuneQx_SimpleVirtualAccelerator.yaml"  # TuRBO
N = 6


def stop_workers():
    """Badger pre-spawns a run worker; left alive, it holds the output pipe open."""
    import multiprocessing
    for child in multiprocessing.active_children():
        child.terminate()
        child.join()


def fake_points(vocs, t0=1.0e9):
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(0)
    points = pd.DataFrame(
        {n: rng.uniform(lo, hi, N) for n, (lo, hi) in zip(vocs.variable_names, vocs.bounds)}
    )
    for n in vocs.output_names:
        points[n] = rng.normal(size=N)
    points["timestamp"] = t0 + np.arange(N)
    return points


def check_helpers():
    import time
    from types import SimpleNamespace

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
        def __init__(self, variables, data=None, constraints=None, params=None, env="E"):
            vocs = VOCS(
                variables=variables,
                objectives={"f": "MINIMIZE"},
                constraints=constraints or {},
            )
            self.generator = ExpectedImprovementGenerator(
                vocs=vocs, turbo_controller="optimize"
            )
            self.vocs, self.data, self.description = vocs, data, None
            params = params or {"w": 1}
            self.environment = SimpleNamespace(name=env, model_dump=lambda: dict(params))
            self.formulas = self.constraint_formulas = self.observable_formulas = {}

    now = time.time()
    old = R({"x": [0, 1]}, pd.DataFrame(
        {"x": [0.2, 0.8, 3.0], "f": [1.0, 2.0, 3.0], "timestamp": [now - 7200, now - 60, now - 30]}
    ))
    older = R({"x": [0, 1]}, pd.DataFrame({"x": [0.5], "f": [0.0], "timestamp": [now - 9000]}))
    wider = R({"x": [-5, 5]})

    data, report = seed_data(wider, [("A", old), ("B", older)])
    assert len(data) == 4 and (data["live"] == 0).all()
    assert list(data.index) == [0, 1, 2, 3] and data["x"].iloc[0] == 0.5  # oldest first
    assert [e["points"] for e in report] == [3, 1] and not report[0]["notes"]

    # Filters: older than 1 h; outside the new ranges (narrowed to [0, 1]: x = 3 goes)
    data, _ = seed_data(wider, [("A", old), ("B", older)], max_age_hours=1)
    assert len(data) == 2, data
    data, report = seed_data(R({"x": [0, 1]}), [("A", old)], in_ranges=True)
    assert len(data) == 2 and report[0]["points"] == 2

    # Skipped: other variables; a constraint the earlier run did not measure
    _, report = seed_data(R({"y": [0, 1]}), [("A", old)])
    assert "other variables" in report[0]["skipped"]
    _, report = seed_data(R({"x": [0, 1]}, constraints={"c": ["LESS_THAN", 1]}), [("A", old)])
    assert "constraint(s) c" in report[0]["skipped"]

    # Reported: changed environment parameters (e.g. weights), another environment
    _, report = seed_data(R({"x": [0, 1]}, params={"w": 2}), [("A", old)])
    assert report[0]["notes"] == ["w: was 1, now 2"], report
    _, report = seed_data(R({"x": [0, 1]}, env="F"), [("A", old)])
    assert "environment E, not F" in report[0]["notes"][0]

    neldermead = R({"x": [0, 1]})
    neldermead.generator = SimpleNamespace(name="neldermead")
    try:
        seed_data(neldermead, [("A", old)])
        raise AssertionError("neldermead accepted")
    except BadgerRoutineError:
        pass

    wider.generator.add_data(seed_data(wider, [("A", old)])[0])
    wider.generator.turbo_controller.length = 0.05  # an earlier run shrank it
    wider.generator.turbo_controller.failure_tolerance = 7  # a setting: kept
    fresh_trust_region(wider)
    tc = wider.generator.turbo_controller
    assert tc.length == 0.25 and tc.failure_tolerance == 7, tc
    assert tc.vocs is wider.generator.vocs  # the new ranges

    note_source(wider, 2, ["A-2026.yaml"])
    assert wider.description == "Seeded with 2 points from A-2026.yaml."
    wider.description = "tuning"
    note_source(wider, 4, ["A", "B"])
    assert wider.description == "tuning\nSeeded with 4 points from A, B."


def main():
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox

    import badger.gui.mini  # noqa: F401,E402  sets Badger's Qt high-DPI options, which must come before the QApplication
    app = QApplication.instance() or QApplication([])  # noqa: F841
    from badger.settings import init_settings

    init_settings("config.local.yaml")
    import badger.archive
    from badger.archive import load_run
    from badger.gui.components import continue_run
    from badger.gui.mini.windows.main_window import BadgerMiniWindow
    from badger.gui.windows.main_window import BadgerMainWindow

    check_helpers()

    def fail(_parent, title, text, *a, **k):
        raise AssertionError(f"{title}: {text}")

    # No dialog may appear unless a step below expects it (a single-run Continue
    # with nothing changed asks no question).
    QMessageBox.critical = QMessageBox.warning = staticmethod(fail)
    QMessageBox.question = QMessageBox.information = staticmethod(fail)
    QMessageBox.exec_ = lambda self: QMessageBox.Ok  # full GUI's "Data loaded" notice
    summaries = []

    def accept(self):
        summaries.append(self.total.text())
        return QDialog.Accepted

    continue_run.SeedSummaryDialog.exec_ = accept

    def check(window_cls):
        window = window_cls()
        page = window.home_page
        bar = page.run_action_bar
        btn = bar.btn_continue
        assert btn.isVisibleTo(window) and not btn.isEnabled()

        page.routine_editor.load_template_yaml(False, template_path=SIM)
        source = page.routine_editor._compose_routine()

        # An archived run read back must not look changed (no false warnings).
        source.data = fake_points(source.vocs)
        path = badger.archive.save_tmp_run(source)
        try:
            archived = load_run(path)
        finally:
            root = init_settings().read_value("BADGER_ARCHIVE_ROOT")
            os.remove(os.path.join(root, ".tmp", path))  # save_tmp_run's file
        notes = continue_run.differences(page.routine_editor._compose_routine(), archived)
        assert notes == [], notes

        def show(run):  # as go_run leaves a displayed run
            run.data = fake_points(run.vocs)
            page.current_routine = run
            if hasattr(page, "data_panel"):
                page.data_panel.load_data(run)
            bar.toggle_other(False)

        # Enabled once a run with points is shown; another run shown disarms it.
        show(source)
        assert btn.isEnabled()
        page.history_browser.sig_continue.emit()  # History menu entry
        assert btn.isChecked()
        if hasattr(page, "data_panel"):
            assert page.data_panel.use_data and not page.data_panel.init_points
        page.go_run(-1)  # (also empties the shown routine's data)
        assert not btn.isChecked()

        # One run: Go seeds from it.
        show(source)
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
        bar.run_start()  # (start is stubbed): one Go per Continue
        assert not btn.isChecked()
        bar.routine_finished()

        # Several runs: "Add its points" needs Continue armed; then the summary.
        show(source)
        other = page.routine_editor._compose_routine()
        other.data = fake_points(other.vocs, t0=0.9e9)  # older: merged first
        badger.archive.load_run = lambda name: other
        told = []
        QMessageBox.information = staticmethod(lambda *a, **k: told.append(a[2]))
        page.history_browser.sig_add_seed.emit("other-run.yaml")
        assert told and not page.seed_extra
        QMessageBox.information = staticmethod(fail)
        btn.setChecked(True)
        page.history_browser.sig_add_seed.emit("other-run.yaml")
        page.history_browser.sig_add_seed.emit("other-run.yaml")  # added once
        assert [n for n, _ in page.seed_extra] == ["other-run.yaml"]
        assert "1 more run(s)" in page.status_bar.toolTip(), page.status_bar.toolTip()
        page.start_run()
        assert summaries[-1] == f"Seed with {2 * N} of {2 * N} points.", summaries
        run = page.current_routine
        assert len(run.data) == 2 * N and run.data["timestamp"].iloc[0] == 0.9e9
        assert "other-run.yaml" in run.description, run.description
        btn.setChecked(False)
        assert page.seed_extra == []  # disarming forgets added runs

        # Plain Go right after showing a seeded TuRBO run: the new run gets no
        # stale trust-region centre (badger-1.6.0-turbo-state-reset.patch; one
        # left over made every new point fall outside the region), and no
        # copied "Seeded with" line.
        page.routine_editor.load_template_yaml(False, template_path=TUNEQX)
        shown = page.routine_editor._compose_routine()
        shown.generator.turbo_controller.center_x = {"kqd": -0.7927, "kqf": 0.8008}
        shown.description = "Regulate Qx.\nSeeded with 1 points from X.yaml."
        page.routine_editor.set_routine(shown, silent=True)
        page.start_run()
        run = page.current_routine
        assert started[-1]["init_points_flag"] and not started[-1]["run_data_flag"]
        assert run.generator.turbo_controller.center_x is None, run.generator.turbo_controller
        assert run.description == "Regulate Qx.", repr(run.description)
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
