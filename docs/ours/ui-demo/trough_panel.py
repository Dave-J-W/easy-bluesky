"""Trough panel — layout in trough_panel.ui, behaviour here.

Compare with trough_panel_handcoded.py, which builds the identical widget tree in Python.
test_ui_demo.py asserts the two are equivalent, so the difference between them is purely
where the layout lives, not what the panel is.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QWidget

from ui_loader import load_ui

FIELDS = ("pressure", "area", "temperature", "barrier")


class TroughPanel(QWidget):
    """Live readouts plus a pressure setpoint."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        load_ui("trough_panel", self)

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

    def set_status(self, text: str) -> None:
        self.status.setText(text)

    def _on_apply(self) -> None:
        self.set_status(f"Target {self.spin_setpoint.value():.2f} mN/m")
