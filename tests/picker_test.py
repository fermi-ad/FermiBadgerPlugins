"""Offscreen check for the pick-to-add dropdown patched into Badger's env boxes.

Run:  conda run -n FermiBadger_env python -m pytest tests/picker_test.py
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from badger.gui.components.obj_table import ObjectiveTable  # noqa: E402
from badger.gui.components.picker import Picker  # noqa: E402
from badger.gui.components.env_cbox import BadgerEnvBox  # noqa: E402

app = QApplication.instance() or QApplication([])


def test_picker_lists_all_in_source_order_marks_checked_and_emits_pick():
    selected = {"b"}
    names = ["c", "a", "b"]  # deliberately not alphabetical
    picker = Picker(lambda: [(n, n in selected) for n in names], "Add...")
    got = []
    picker.picked.connect(got.append)

    picker.refresh()
    assert [picker.itemText(i) for i in range(picker.count())] == ["c", "a", "b"]
    assert picker.itemIcon(2).isNull() is False  # "b" is checked: has the check icon
    assert picker.itemIcon(0).isNull()

    picker._pick("a")
    assert got == ["a"]
    assert picker.currentText() == ""

    picker._pick("zzz")  # not a known name: ignored
    assert got == ["a"]

    picker.clear()  # routine pages call this; must not drop the item list logic
    picker.refresh()
    assert picker.count() == 3


def test_pick_item_marks_editable_table_row_selected():
    table = ObjectiveTable()
    table.update_items(
        [{"q": ["MINIMIZE"]}, {"p": ["MINIMIZE"]}], {"q": False, "p": True}, {}
    )
    assert BadgerEnvBox.list_items(table) == [("q", False), ("p", True)]
    # selected-only, one selected: one visible row plus the hidden placeholder row
    table.show_selected_only = True
    table.update_items()
    assert table.rowCount() == 2 and table.isRowHidden(1) and not table.isRowHidden(0)
    table.update_items(status={"q": False, "p": False})
    assert table.rowCount() == 1 and table.isRowHidden(0)  # nothing selected: zero visible rows
    table.update_items(status={"q": False, "p": True})
    BadgerEnvBox.pick_item(table, "q")
    assert table.status["q"] is True
    assert BadgerEnvBox.list_items(table) == [("q", True), ("p", True)]
    BadgerEnvBox.pick_item(table, "q")  # already checked: no-op
    assert table.status["q"] is True


def test_popup_opens_on_click_and_closes_after_pick():
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QLineEdit, QVBoxLayout, QWidget

    w = QWidget()
    lay = QVBoxLayout(w)
    picker = Picker(lambda: [("a1", False), ("b2", True)], "Add")
    other = QLineEdit()
    lay.addWidget(picker)
    lay.addWidget(other)
    w.show()
    QTest.qWaitForWindowExposed(w)
    popup = picker.completer().popup()

    QTest.mouseClick(picker.lineEdit(), Qt.LeftButton)
    QTest.qWait(50)
    assert popup.isVisible()

    picker._pick("a1")
    QTest.qWait(50)
    assert not popup.isVisible()  # regression: popup used to reopen itself forever

    QTest.mouseClick(other, Qt.LeftButton)
    QTest.qWait(50)
    assert not popup.isVisible()
    w.close()


if __name__ == "__main__":
    test_picker_lists_all_in_source_order_marks_checked_and_emits_pick()
    test_pick_item_marks_editable_table_row_selected()
    test_popup_opens_on_click_and_closes_after_pick()
    print("picker_test: ok")
