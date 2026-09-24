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
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

FIELDS = (
    ("pressure", "Surface pressure", "mN/m"),
    ("area", "Area", "cm^2"),
    ("temperature", "Temperature", "degC"),
    ("barrier", "Barrier separation", "mm"),
)

MODES = (
    ("Pressure control", "spin_pressure", "mN/m", 2),
    ("Area control", "spin_area", "cm^2", 1),
)


class TroughPanelHandCoded(QWidget):
    """Live readouts, plus a setpoint whose meaning follows the control mode."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("TroughPanel")
        self.setWindowTitle("Trough")
        self.resize(460, 380)

        root = QVBoxLayout(self)
        root.setObjectName("root")

        self.title = QLabel("Langmuir Trough", self)
        self.title.setObjectName("title")
        root.addWidget(self.title)

        # ── readouts ─────────────────────────────────────────────────────────
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

        # ── control ──────────────────────────────────────────────────────────
        self.control_box = QGroupBox("Control", self)
        self.control_box.setObjectName("control_box")
        control_col = QVBoxLayout(self.control_box)
        control_col.setObjectName("control_col")

        mode_row = QHBoxLayout()
        mode_row.setObjectName("mode_row")
        self.lbl_mode = QLabel("Mode", self.control_box)
        self.lbl_mode.setObjectName("lbl_mode")
        mode_row.addWidget(self.lbl_mode)

        self.combo_mode = QComboBox(self.control_box)
        self.combo_mode.setObjectName("combo_mode")
        self.combo_mode.setToolTip("Which quantity the barrier servo holds constant")
        for label, _spin, _unit, _dp in MODES:
            self.combo_mode.addItem(label)
        mode_row.addWidget(self.combo_mode)
        mode_row.addItem(
            QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        )
        control_col.addLayout(mode_row)

        setpoint_row = QHBoxLayout()
        setpoint_row.setObjectName("setpoint_row")

        self.setpoint_stack = QStackedWidget(self.control_box)
        self.setpoint_stack.setObjectName("setpoint_stack")

        self.page_pressure = QWidget()
        self.page_pressure.setObjectName("page_pressure")
        pressure_row = QHBoxLayout(self.page_pressure)
        pressure_row.setObjectName("pressure_row")
        self.lbl_target_pressure = QLabel("Target pressure", self.page_pressure)
        self.lbl_target_pressure.setObjectName("lbl_target_pressure")
        pressure_row.addWidget(self.lbl_target_pressure)
        self.spin_pressure = QDoubleSpinBox(self.page_pressure)
        self.spin_pressure.setObjectName("spin_pressure")
        self.spin_pressure.setSuffix(" mN/m")
        self.spin_pressure.setDecimals(2)
        self.spin_pressure.setMaximum(72.0)
        pressure_row.addWidget(self.spin_pressure)
        self.setpoint_stack.addWidget(self.page_pressure)

        self.page_area = QWidget()
        self.page_area.setObjectName("page_area")
        area_row = QHBoxLayout(self.page_area)
        area_row.setObjectName("area_row")
        self.lbl_target_area = QLabel("Target area", self.page_area)
        self.lbl_target_area.setObjectName("lbl_target_area")
        area_row.addWidget(self.lbl_target_area)
        self.spin_area = QDoubleSpinBox(self.page_area)
        self.spin_area.setObjectName("spin_area")
        self.spin_area.setSuffix(" cm^2")
        self.spin_area.setDecimals(1)
        self.spin_area.setMaximum(1000.0)
        area_row.addWidget(self.spin_area)
        self.setpoint_stack.addWidget(self.page_area)

        self.setpoint_stack.setCurrentIndex(0)
        setpoint_row.addWidget(self.setpoint_stack)

        self.btn_apply = QPushButton("Apply", self.control_box)
        self.btn_apply.setObjectName("btn_apply")
        setpoint_row.addWidget(self.btn_apply)
        control_col.addLayout(setpoint_row)
        root.addWidget(self.control_box)

        # ── start / stop ─────────────────────────────────────────────────────
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

        self.combo_mode.currentIndexChanged.connect(self.setpoint_stack.setCurrentIndex)
        self.btn_apply.clicked.connect(self._on_apply)
        self.btn_start.clicked.connect(lambda: self.set_status("Running"))
        self.btn_stop.clicked.connect(lambda: self.set_status("Stopped"))

    # ── behaviour — identical to the .ui version ─────────────────────────────

    def update_readings(self, readings: dict[str, float]) -> None:
        for key, _caption, _unit in FIELDS:
            label = getattr(self, f"val_{key}")
            value = readings.get(key)
            label.setText("--" if value is None else f"{value:.2f}")

    def set_mode(self, index: int) -> None:
        self.combo_mode.setCurrentIndex(index)

    def set_status(self, text: str) -> None:
        self.status.setText(text)

    def _on_apply(self) -> None:
        _label, spin_name, unit, decimals = MODES[self.combo_mode.currentIndex()]
        value = getattr(self, spin_name).value()
        self.set_status(f"Target {value:.{decimals}f} {unit}")
