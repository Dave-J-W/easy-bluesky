"""The same panel, built the way the codebase builds panels today.

Written in good faith, not as a straw man: object names are set because they are what
makes widgets addressable for styling and tests, and the structure matches
trough_panel.ui exactly. test_ui_demo.py proves the equivalence.

The point of this file is not that it is bad code. It is that every line of it is a
layout decision expressed as a program, so changing the layout means editing a program
and restarting the app.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

FIELDS = (
    ("pressure", "Surface pressure", "mN/m"),
    ("area", "Area", "cm^2"),
    ("temperature", "Temperature", "degC"),
    ("barrier", "Barrier separation", "mm"),
)


class TroughPanelHandCoded(QWidget):
    """Live readouts plus a pressure setpoint."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("TroughPanel")
        self.setWindowTitle("Trough")
        self.resize(420, 320)

        root = QVBoxLayout(self)
        root.setObjectName("root")

        self.title = QLabel("Langmuir Trough", self)
        self.title.setObjectName("title")
        root.addWidget(self.title)

        self.readouts_box = QGroupBox("Readouts", self)
        self.readouts_box.setObjectName("readouts_box")
        readouts_grid = QGridLayout(self.readouts_box)
        readouts_grid.setObjectName("readouts_grid")
        for row, (key, caption, unit) in enumerate(FIELDS):
            lbl = QLabel(caption, self.readouts_box)
            lbl.setObjectName(f"lbl_{key}")
            readouts_grid.addWidget(lbl, row, 0)

            val = QLabel("--", self.readouts_box)
            val.setObjectName(f"val_{key}")
            readouts_grid.addWidget(val, row, 1)

            unit_lbl = QLabel(unit, self.readouts_box)
            unit_lbl.setObjectName(f"unit_{key}")
            readouts_grid.addWidget(unit_lbl, row, 2)

            setattr(self, f"lbl_{key}", lbl)
            setattr(self, f"val_{key}", val)
            setattr(self, f"unit_{key}", unit_lbl)
        root.addWidget(self.readouts_box)

        self.control_box = QGroupBox("Control", self)
        self.control_box.setObjectName("control_box")
        control_row = QHBoxLayout(self.control_box)
        control_row.setObjectName("control_row")

        self.lbl_setpoint = QLabel("Target pressure", self.control_box)
        self.lbl_setpoint.setObjectName("lbl_setpoint")
        control_row.addWidget(self.lbl_setpoint)

        self.spin_setpoint = QDoubleSpinBox(self.control_box)
        self.spin_setpoint.setObjectName("spin_setpoint")
        self.spin_setpoint.setSuffix(" mN/m")
        self.spin_setpoint.setDecimals(2)
        self.spin_setpoint.setMaximum(72.0)
        control_row.addWidget(self.spin_setpoint)

        self.btn_apply = QPushButton("Apply", self.control_box)
        self.btn_apply.setObjectName("btn_apply")
        control_row.addWidget(self.btn_apply)
        root.addWidget(self.control_box)

        button_row = QHBoxLayout()
        button_row.setObjectName("button_row")
        self.btn_start = QPushButton("Start", self)
        self.btn_start.setObjectName("btn_start")
        button_row.addWidget(self.btn_start)

        self.btn_stop = QPushButton("Stop", self)
        self.btn_stop.setObjectName("btn_stop")
        button_row.addWidget(self.btn_stop)

        button_row.addItem(
            QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        )
        root.addLayout(button_row)

        self.status = QLabel("Disconnected", self)
        self.status.setObjectName("status")
        root.addWidget(self.status)

        self.btn_apply.clicked.connect(self._on_apply)
        self.btn_start.clicked.connect(lambda: self.set_status("Running"))
        self.btn_stop.clicked.connect(lambda: self.set_status("Stopped"))

    # ── behaviour — identical to the .ui version ─────────────────────────────

    def update_readings(self, readings: dict[str, float]) -> None:
        for key, _caption, _unit in FIELDS:
            label = getattr(self, f"val_{key}")
            value = readings.get(key)
            label.setText("--" if value is None else f"{value:.2f}")

    def set_status(self, text: str) -> None:
        self.status.setText(text)

    def _on_apply(self) -> None:
        self.set_status(f"Target {self.spin_setpoint.value():.2f} mN/m")
