"""Tests for the .ui convention demo.

Three things are worth proving, and the middle one is the whole argument:

1. Every .ui in the tree loads. This is the guard that makes the convention safe — a
   Designer/uic version mismatch or a hand-edited .ui shows up here, not as an empty
   panel at the beamline.
2. The .ui panel and the hand-coded panel produce the *same widget tree*. Without this,
   "the .ui version is shorter" would be worthless — it could just be doing less.
3. Behaviour is identical, so the comparison is about layout only.

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
    from_ui = TroughPanel()
    handcoded = TroughPanelHandCoded()
    qtbot.addWidget(from_ui)
    qtbot.addWidget(handcoded)

    assert widget_tree(from_ui) == widget_tree(handcoded)


def test_both_expose_the_same_named_children(qtbot):
    from_ui = TroughPanel()
    handcoded = TroughPanelHandCoded()
    qtbot.addWidget(from_ui)
    qtbot.addWidget(handcoded)

    expected = {
        "title", "readouts_box", "control_box", "status",
        "spin_setpoint", "btn_apply", "btn_start", "btn_stop", "lbl_setpoint",
    } | {f"{p}_{f}" for p in ("lbl", "val", "unit")
         for f in ("pressure", "area", "temperature", "barrier")}

    for name in expected:
        assert hasattr(from_ui, name), f".ui version missing {name}"
        assert hasattr(handcoded, name), f"hand-coded version missing {name}"


# ── 3. behaviour parity ──────────────────────────────────────────────────────

@pytest.mark.parametrize("cls", [TroughPanel, TroughPanelHandCoded])
def test_readings_render_identically(qtbot, cls):
    panel = cls()
    qtbot.addWidget(panel)

    panel.update_readings({"pressure": 22.413, "area": 145.2})
    assert panel.val_pressure.text() == "22.41"
    assert panel.val_area.text() == "145.20"
    assert panel.val_temperature.text() == "--", "absent reading must not show a stale value"


@pytest.mark.parametrize("cls", [TroughPanel, TroughPanelHandCoded])
def test_apply_reports_the_setpoint(qtbot, cls):
    panel = cls()
    qtbot.addWidget(panel)

    panel.spin_setpoint.setValue(30.0)
    panel.btn_apply.click()
    assert panel.status.text() == "Target 30.00 mN/m"


@pytest.mark.parametrize("cls", [TroughPanel, TroughPanelHandCoded])
def test_start_stop_change_status(qtbot, cls):
    panel = cls()
    qtbot.addWidget(panel)

    panel.btn_start.click()
    assert panel.status.text() == "Running"
    panel.btn_stop.click()
    assert panel.status.text() == "Stopped"
