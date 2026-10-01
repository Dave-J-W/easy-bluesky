"""Trough panel — layout in a .ui, behaviour here.

Two things to notice.

**The readout rows are discovered from the .ui, not listed here.** Any row a human adds in
Designer appears and updates with no Python change at all. That is the editability claim,
and `test_extended_ui_works_with_unmodified_python` proves it by loading a second, edited
.ui into this same unmodified class.

**The panel does no I/O.** It consumes a plain mapping of readings, which is the shape of
the `PVBatch` event in `docs/refactoring-plan.md`. The two proposals compose: once views
receive a facade instead of a worker, a view is layout plus a thin binding, and the layout
is the part that belongs in a .ui.

Switching control mode changes what the operator sees but not the widget tree — see
README.md, "What 'static' means".
"""

from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QWidget

from ui_loader import load_ui

#: (combo label, setpoint spinbox, unit, decimals) — index matches the stack page.
MODES = (
    ("Pressure control", "spin_pressure", "mN/m", 2),
    ("Area control", "spin_area", "cm^2", 1),
)

NO_READING = "--"


class TroughPanel(QWidget):
    """Live readouts, plus a setpoint whose meaning follows the control mode."""

    def __init__(self, parent: QWidget | None = None, ui_name: str = "trough_panel") -> None:
        super().__init__(parent)
        load_ui(ui_name, self)

        # Readouts come from the .ui. A row is a val_<field> label; its caption and unit
        # are lbl_<field> and unit_<field>. Nothing about the field set lives in Python.
        self._values: dict[str, QLabel] = {}
        for widget in self.findChildren(QLabel):
            name = widget.objectName()
            if name.startswith("val_"):
                self._values[name[len("val_"):]] = widget

        # The entire mode switch. Both pages already exist; this only selects one.
        self.combo_mode.currentIndexChanged.connect(self.setpoint_stack.setCurrentIndex)

        self.btn_apply.clicked.connect(self._on_apply)
        self.btn_start.clicked.connect(lambda: self.set_status("Running"))
        self.btn_stop.clicked.connect(lambda: self.set_status("Stopped"))

    # ── what the .ui declared ────────────────────────────────────────────────

    def fields(self) -> tuple[str, ...]:
        """Readout fields this panel displays, in .ui order."""
        return tuple(self._values)

    def unit_of(self, field: str) -> str | None:
        """The unit the .ui declares for a field, or None if the row is incomplete."""
        label = self.findChild(QLabel, f"unit_{field}")
        return label.text() if label is not None else None

    def incomplete_rows(self) -> tuple[str, ...]:
        """Fields whose row is missing its caption or unit label.

        A half-finished row is the realistic way a non-programmer's Designer edit goes
        wrong, so the panel can name it and a test can refuse it.
        """
        bad = []
        for field in self._values:
            caption = self.findChild(QLabel, f"lbl_{field}")
            unit = self.findChild(QLabel, f"unit_{field}")
            if caption is None or unit is None:
                bad.append(field)
        return tuple(bad)

    # ── behaviour ────────────────────────────────────────────────────────────

    def update_readings(self, readings: dict[str, float]) -> None:
        """Apply a reading mapping, e.g. {"pressure": 22.41}.

        Keys with no row in the .ui are ignored; a row with no reading shows '--' rather
        than a stale number.
        """
        for field, label in self._values.items():
            value = readings.get(field)
            label.setText(NO_READING if value is None else f"{value:.2f}")

    def set_mode(self, index: int) -> None:
        """Select pressure (0) or area (1) control."""
        self.combo_mode.setCurrentIndex(index)

    def set_status(self, text: str) -> None:
        self.status.setText(text)

    def _on_apply(self) -> None:
        _label, spin_name, unit, decimals = MODES[self.combo_mode.currentIndex()]
        value = getattr(self, spin_name).value()
        self.set_status(f"Target {value:.{decimals}f} {unit}")
