"""Offline check of badger-1.6.0-change-tables.patch: the run monitor's before/after
confirmations (Apply Solution, Reset, Load Checkpoint) show a table of each variable's
value now, the value the action would set, and the change in percent of now
(settings_snapshot.format_changes, the same table as the Revert dialog). Variables in the
VOCS's order whatever order the environment returns them in; context variables (never
written) left out; a value now of 0 shows a dash.

Run from the repo root:
    pixi run python tests/change_tables_test.py
"""
import sys
from types import SimpleNamespace

sys.path.insert(0, "plugins")
from PyQt5.QtWidgets import QMessageBox  # noqa: E402
from xopt.vocs import VOCS, ContextualVariable  # noqa: E402

import badger.gui.components.settings_guard as guard  # noqa: E402
from badger.gui.components.run_monitor import BadgerOptMonitor  # noqa: E402

shown = []


def capture(parent, title, intro, table):
    shown.append((title, intro, table))
    return SimpleNamespace(exec_=lambda: QMessageBox.No)


guard.table_question = capture


class Env:
    name = "fake"

    def get_variables(self, names):  # deliberately not in the requested order
        now = {"B": 0.0, "C": 3.0, "A": 2.0}
        return {n: now[n] for n in reversed(names)}


vocs = VOCS(variables={"A": [0, 10], "B": [-1, 1], "C": ContextualVariable(domain=[0, 5])},
            objectives={"f": "MINIMIZE"})
monitor = SimpleNamespace(vocs=vocs, routine=SimpleNamespace(vocs=vocs, environment=Env()))
answer = BadgerOptMonitor._confirm_changes(monitor, "Reset Environment", "Reset?",
                                           {"A": 1.0, "B": 0.5, "C": 4.0}, "Run start")
assert answer is False  # No
title, intro, table = shown[-1]
assert table.splitlines() == [
    "Variable             Now       Run start       Change",
    "A                      2               1        -50 %",
    "B                      0             0.5            -",
], table
print(table)
print("CHANGE TABLES TEST PASSED")
