"""Offscreen check of badger-1.6.0-docs-back-button.patch: the docs window's Back
button (in the toolbar above the page, so it stays on screen however far the page
scrolls) returns from a followed link to the page before, at the same scroll
position; opening the docs afresh (a ? or Open Docs button) starts a new history.

Uses our own pages (docs/guides/minimode.md, docs/algorithms/*.md), so it works
without Badger's guides having been fetched.

Run from the repo root:
    pixi run python tests/docs_back_test.py
"""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtCore import QUrl  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

import badger.gui.mini  # noqa: F401,E402  Badger's Qt options before the QApplication

app = QApplication.instance() or QApplication([])
from badger.settings import init_settings  # noqa: E402

init_settings("config.local.yaml")
from badger.gui.windows.docs_window import BadgerDocsWindow  # noqa: E402


def settle():
    for _ in range(10):
        app.processEvents()
        time.sleep(0.02)


w = BadgerDocsWindow(None, "minimode")
w.resize(640, 400)
w.show()
w.update_docs("minimode")  # as the action bar's ? does
settle()
back, bar = w.btn_back, w.markdown_viewer.verticalScrollBar()
assert "# The compact GUI" in w.docs and not back.isEnabled()
assert bar.maximum() > 0, "page too short to test scrolling"

bar.setValue(bar.maximum() // 2)
where = bar.value()
w.handle_link_click(QUrl("/expected_improvement"))  # a link in the page
settle()
assert w.docs_name == "expected_improvement" and back.isEnabled(), w.docs_name
assert back.isVisible() and back.y() < w.markdown_viewer.y()  # above the page

w.go_back()
settle()
assert w.docs_name == "minimode" and "# The compact GUI" in w.docs, w.docs_name
assert bar.value() == where, (bar.value(), where)  # same place in the page
assert not back.isEnabled()

w.handle_link_click(QUrl("https://example.org"))  # external: a note, and Back
settle()
assert "not yet implemented" in w.docs_name and back.isEnabled()
w.go_back()
settle()
assert w.docs_name == "minimode"

w.handle_link_click(QUrl("/expected_improvement"))
w.update_docs("minimode")  # opened afresh: a new history
assert not w.history and not back.isEnabled()

print("docs_back_test ok", flush=True)
os._exit(0)
