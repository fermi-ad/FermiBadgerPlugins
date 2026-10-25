"""Offscreen check of badger-1.6.0-turbo-state-reset.patch, in both GUIs: a run
composed right after showing a TuRBO run gets no stale trust-region centre.
Upstream blanks it only for the short controller names, but a run's saved
controller is named OptimizeTurboController; the centre left over made every
new point fall outside the region (FeasibilityError on the first BO step,
seen 2026-10-25). Uses a simulation template; nothing is run.

Run from the repo root:
    pixi run python tests/turbo_state_reset_gui_test.py
"""
TUNEQX = "tuning_templates/simulation/TuneQx_SimpleVirtualAccelerator.yaml"  # TuRBO


def stop_workers():
    """Badger pre-spawns a run worker; left alive, it holds the output pipe open."""
    import multiprocessing
    for child in multiprocessing.active_children():
        child.terminate()
        child.join()


def main():
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication

    import badger.gui.mini  # noqa: F401,E402  sets Badger's Qt high-DPI options, which must come before the QApplication
    app = QApplication.instance() or QApplication([])  # noqa: F841
    from badger.settings import init_settings

    init_settings("config.local.yaml")
    from badger.gui.mini.windows.main_window import BadgerMiniWindow
    from badger.gui.windows.main_window import BadgerMainWindow

    def check(window_cls):
        window = window_cls()
        editor = window.home_page.routine_editor
        editor.load_template_yaml(False, template_path=TUNEQX)
        shown = editor._compose_routine()
        tc = shown.generator.turbo_controller
        assert type(tc).__name__ == "OptimizeTurboController", tc
        tc.center_x = {"kqd": -0.7927, "kqf": 0.8008}  # as a finished run leaves it
        tc.best_value = 0.1
        editor.set_routine(shown, silent=True)  # as go_run shows a run
        tc = editor._compose_routine().generator.turbo_controller
        assert tc.center_x is None and tc.best_value is None, tc
        return window

    try:
        windows = [check(BadgerMiniWindow), check(BadgerMainWindow)]  # noqa: F841 keep alive
    except BaseException:
        import traceback

        traceback.print_exc()
        stop_workers()  # else the run worker keeps the test alive
        os._exit(1)
    stop_workers()
    print("turbo_state_reset_gui_test ok", flush=True)
    os._exit(0)  # skip Qt/subprocess teardown noise


if __name__ == "__main__":  # Badger spawns workers that re-import this file
    main()
