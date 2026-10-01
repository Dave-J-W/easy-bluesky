"""Tests for the .ui convention demo.

Five things are worth proving:

1. Every .ui in the tree loads. The guard that makes the convention safe — a
   Designer/uic version mismatch or a hand-edited .ui shows up here, not as an empty
   panel at the beamline.
2. The .ui panel and the hand-coded panel produce the *same widget tree*. Without this,
   "the .ui version is shorter" would be worthless — it could just be doing less.
3. Behaviour is identical, so the comparison is about layout only.
4. Switching control mode does not change the widget tree — the load-bearing test for
   "a mode dropdown is still a *static* panel".
5. **An edited .ui works against unmodified Python**, and a half-finished edit is caught.
   This is the editability claim, made executable.

Runs headless: no hardware, no EPICS, no queue server.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QLabel, QWidget

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from trough_panel import TroughPanel  # noqa: E402
from trough_panel_handcoded import TroughPanelHandCoded  # noqa: E402
from ui_loader import iter_ui_files, load_ui  # noqa: E402

REPO_ROOT = HERE.parents[2]
BOTH = [TroughPanel, TroughPanelHandCoded]

PRESSURE, AREA = 0, 1

BASE_FIELDS = ("pressure", "area", "temperature", "barrier")
EXTENDED_FIELDS = BASE_FIELDS + ("ph",)


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
    } | {f"{p}_{f}" for p in ("lbl", "val", "unit") for f in BASE_FIELDS}

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
    """Every widget for both modes exists from construction. Switching mode selects a
    QStackedWidget page; it creates and destroys nothing."""
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

    assert panel.setpoint_stack.currentWidget() is panel.page_pressure
    panel.set_mode(AREA)
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


# ── 5. the editability claim, made executable ────────────────────────────────

def test_readout_fields_come_from_the_ui(qtbot):
    panel = TroughPanel()
    qtbot.addWidget(panel)
    assert panel.fields() == BASE_FIELDS


def test_extended_ui_works_with_unmodified_python(qtbot):
    """The whole proposal in one test.

    trough_panel_extended.ui is trough_panel.ui after three Designer edits: a fifth
    readout row added, one row relabelled, and the Control group moved above Readouts.
    No Python changed. The same TroughPanel class loads it and the new row works.
    """
    panel = TroughPanel(ui_name="trough_panel_extended")
    qtbot.addWidget(panel)

    assert panel.fields() == EXTENDED_FIELDS, "the added row should appear with no code change"
    assert panel.unit_of("ph") == "pH"
    assert panel.lbl_area.text() == "Trough area", "the relabel should take effect"

    panel.update_readings({"ph": 7.42, "pressure": 22.41})
    assert panel.val_ph.text() == "7.42"
    assert panel.val_pressure.text() == "22.41"
    assert panel.val_temperature.text() == "--"


def test_the_field_set_is_not_named_in_python():
    """Guards the claim directly: readout-only field names must not appear in the source.

    'pressure' and 'area' are excluded because they legitimately appear in MODES for the
    setpoint pages — that is a control concern, not a readout one.
    """
    source = (HERE / "trough_panel.py").read_text(encoding="utf-8")
    for field in ("temperature", "barrier", "ph"):
        assert field not in source, (
            f"{field!r} appears in trough_panel.py; the readout set must live in the .ui"
        )


@pytest.mark.parametrize("ui_name", ["trough_panel", "trough_panel_extended"])
def test_shipped_ui_files_have_complete_rows(qtbot, ui_name):
    panel = TroughPanel(ui_name=ui_name)
    qtbot.addWidget(panel)
    assert panel.incomplete_rows() == ()


def test_a_half_finished_designer_edit_is_caught(qtbot):
    """The realistic way a non-programmer's edit goes wrong: a value box added without
    its caption or unit. The panel names it, so a test can refuse it."""
    panel = TroughPanel()
    qtbot.addWidget(panel)

    orphan = QLabel("--", panel.readouts_box)
    orphan.setObjectName("val_conductivity")
    reloaded = TroughPanel()
    qtbot.addWidget(reloaded)

    # Simulate the same mistake inside the discovery map, as loading a broken .ui would.
    reloaded._values["conductivity"] = orphan
    assert reloaded.incomplete_rows() == ("conductivity",)
    assert reloaded.unit_of("conductivity") is None
