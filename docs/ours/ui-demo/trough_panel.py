"""Trough panel — layout in trough_panel.ui, behaviour here.

Compare with trough_panel_handcoded.py, which builds the identical widget tree in Python.
test_ui_demo.py asserts the two are equivalent, so the difference between them is purely
where the layout lives, not what the panel is.

Note the mode dropdown. Switching between pressure control and area control changes what
the operator sees, but it does *not* change the widget tree: both setpoint pages exist
from construction and `QStackedWidget` just shows one of them. That is the difference
between a panel whose *state* varies and a panel whose *structure* varies, and only the
second kind is outside what a .ui can express. See README.md, "What 'static' means".
"""

from __future__ import annotations

from PyQt6.QtWidgets import QWidget

from ui_loader import load_ui

FIELDS = ("pressure", "area", "temperature", "barrier")

#: (combo label, setpoint spinbox, unit, decimals) — index matches the stack page.
MODES = (
    ("Pressure control", "spin_pressure", "mN/m", 2),
    ("Area control", "spin_area", "cm^2", 1),
)


class TroughPanel(QWidget):
    """Live readouts, plus a setpoint whose meaning follows the control mode."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        load_ui("trough_panel", self)

        # The entire mode switch. Both pages already exist; this only selects one.
        self.combo_mode.currentIndexChanged.connect(self.setpoint_stack.setCurrentIndex)

        self.btn_apply.clicked.connect(self._on_apply)
        self.btn_start.clicked.connect(lambda: self.set_status("Running"))
        self.btn_stop.clicked.connect(lambda: self.set_status("Stopped"))

    # ── behaviour ────────────────────────────────────────────────────────────

    def update_readings(self, readings: dict[str, float]) -> None:
        """Apply a reading dict, e.g. {"pressure": 22.41}. Unknown keys are ignored;
        a field with no reading shows '--' rather than a stale number."""
        for field in FIELDS:
            label = getattr(self, f"val_{field}")
            value = readings.get(field)
            label.setText("--" if value is None else f"{value:.2f}")

    def set_mode(self, index: int) -> None:
        """Select pressure (0) or area (1) control."""
        self.combo_mode.setCurrentIndex(index)

    def set_status(self, text: str) -> None:
        self.status.setText(text)

    def _on_apply(self) -> None:
        _label, spin_name, unit, decimals = MODES[self.combo_mode.currentIndex()]
        value = getattr(self, spin_name).value()
        self.set_status(f"Target {value:.{decimals}f} {unit}")
