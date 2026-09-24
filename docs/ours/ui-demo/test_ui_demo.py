"""Tests for the .ui convention demo.

Four things are worth proving:

1. Every .ui in the tree loads. This is the guard that makes the convention safe — a
   Designer/uic version mismatch or a hand-edited .ui shows up here, not as an empty
   panel at the beamline.
2. The .ui panel and the hand-coded panel produce the *same widget tree*. Without this,
   "the .ui version is shorter" would be worthless — it could just be doing less.
3. Behaviour is identical, so the comparison is about layout only.
4. **Switching control mode does not change the widget tree.** This is the load-bearing
   test for the claim in README.md that a mode dropdown is still a *static* panel: the
   visible page changes, the structure does not.

Runs headless: no hardware, no EPICS, no queue server.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QWidget

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from trough_panel import TroughPanel  # noqa: E402
from trough_panel_handcoded import TroughPanelHandCoded  # noqa: E402
from ui_loader import iter_ui_files, load_ui  # noqa: E402

REPO_ROOT = HERE.parents[2]
BOTH = [TroughPanel, TroughPanelHandCoded]

PRESSURE, AREA = 0, 1


def widget_tree(root: QWidget) -> list[tuple[str, str, str]]:
    """(objectName, className, parentObjectName) for every descendant widget.

    Sorted, so the comparison does not depend on construction order — which legitimately
    differs between uic and hand-written code.
    """
    out = []
    for w in root.findChildren(QWidget):
        parent = w.parentWidget()
        out.append((w.objectName(), w.metaObject().className(),
                    parent.objectName() if parent else ""))
    return sorted(out)


# ── 1. the guard ─────────────────────────────────────────────────────────────

def test_every_ui_file_in_the_repo_loads(qtbot):
    """New panels are covered automatically — nothing to remember to register."""
    ui_files = iter_ui_files(REPO_ROOT)
    assert ui_files, "no .ui files found; this test would pass vacuously"
    for path in ui_files:
        host = QWidget()
        qtbot.addWidget(host)
        load_ui(path.stem, host, base_dir=path.parent)


def test_missing_ui_raises_a_useful_error(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    with pytest.raises(FileNotFoundError, match="no .ui file at"):
        load_ui("does_not_exist", host)


# ── 2. the argument ──────────────────────────────────────────────────────────

def test_ui_and_handcoded_build_the_same_widget_tree(qtbot):
    from_ui, handcoded = TroughPanel(), TroughPanelHandCoded()
    qtbot.addWidget(from_ui)
    qtbot.addWidget(handcoded)

    assert widget_tree(from_ui) == widget_tree(handcoded)


def test_both_expose_the_same_named_children(qtbot):
    from_ui, handcoded = TroughPanel(), TroughPanelHandCoded()
    qtbot.addWidget(from_ui)
    qtbot.addWidget(handcoded)

    expected = {
        "title", "readouts_box", "control_box", "status",
        "btn_apply", "btn_start", "btn_stop",
        "lbl_mode", "combo_mode", "setpoint_stack", "page_pressure", "page_area",
        "lbl_target_pressure", "spin_pressure", "lbl_target_area", "spin_area",
    } | {f"{p}_{f}" for p in ("lbl", "val", "unit")
         for f in ("pressure", "area", "temperature", "barrier")}

    for name in expected:
        assert hasattr(from_ui, name), f".ui version missing {name}"
        assert hasattr(handcoded, name), f"hand-coded version missing {name}"


# ── 3. behaviour parity ──────────────────────────────────────────────────────

@pytest.mark.parametrize("cls", BOTH)
def test_readings_render_identically(qtbot, cls):
    panel = cls()
    qtbot.addWidget(panel)

    panel.update_readings({"pressure": 22.413, "area": 145.2})
    assert panel.val_pressure.text() == "22.41"
    assert panel.val_area.text() == "145.20"
    assert panel.val_temperature.text() == "--", "absent reading must not show a stale value"


@pytest.mark.parametrize("cls", BOTH)
def test_start_stop_change_status(qtbot, cls):
    panel = cls()
    qtbot.addWidget(panel)

    panel.btn_start.click()
    assert panel.status.text() == "Running"
    panel.btn_stop.click()
    assert panel.status.text() == "Stopped"


# ── 4. the mode dropdown: state changes, structure does not ──────────────────

@pytest.mark.parametrize("cls", BOTH)
def test_mode_switch_does_not_change_the_widget_tree(qtbot, cls):
    """The load-bearing test for 'a mode dropdown is still a static panel'.

    Every widget for both modes exists from construction. Switching mode selects a
    QStackedWidget page; it creates and destroys nothing.
    """
    panel = cls()
    qtbot.addWidget(panel)

    before = widget_tree(panel)
    panel.set_mode(AREA)
    after_area = widget_tree(panel)
    panel.set_mode(PRESSURE)
    after_back = widget_tree(panel)

    assert before == after_area == after_back


@pytest.mark.parametrize("cls", BOTH)
def test_mode_selects_the_matching_page(qtbot, cls):
    panel = cls()
    qtbot.addWidget(panel)

    assert panel.setpoint_stack.currentIndex() == PRESSURE
    assert panel.setpoint_stack.currentWidget() is panel.page_pressure

    panel.set_mode(AREA)
    assert panel.setpoint_stack.currentIndex() == AREA
    assert panel.setpoint_stack.currentWidget() is panel.page_area


@pytest.mark.parametrize("cls", BOTH)
def test_apply_reports_the_setpoint_of_the_active_mode(qtbot, cls):
    """Units follow the mode — an area target must never be reported in mN/m."""
    panel = cls()
    qtbot.addWidget(panel)

    panel.spin_pressure.setValue(30.0)
    panel.spin_area.setValue(145.0)

    panel.set_mode(PRESSURE)
    panel.btn_apply.click()
    assert panel.status.text() == "Target 30.00 mN/m"

    panel.set_mode(AREA)
    panel.btn_apply.click()
    assert panel.status.text() == "Target 145.0 cm^2"


@pytest.mark.parametrize("cls", BOTH)
def test_mode_labels_match_between_combo_and_pages(qtbot, cls):
    panel = cls()
    qtbot.addWidget(panel)

    assert [panel.combo_mode.itemText(i) for i in range(panel.combo_mode.count())] == [
        "Pressure control",
        "Area control",
    ]
    assert panel.combo_mode.count() == panel.setpoint_stack.count()
