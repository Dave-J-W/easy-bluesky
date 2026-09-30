"""mca_viewer.py — IOC-native MCA viewer using EPICS ROI PVs directly."""

import json
import re
from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDoubleSpinBox, QGroupBox, QHBoxLayout,
    QHeaderView, QInputDialog, QLabel, QLineEdit, QMainWindow, QPushButton,
    QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

try:
    from scipy.optimize import curve_fit as _curve_fit
    from scipy.signal import find_peaks as _find_peaks
    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False

_FE55_KA_EV = 5895.0   # Mn Kα (eV)
_FE55_KB_EV = 6490.4   # Mn Kβ1 (eV)

try:
    import pyqtgraph as pg
    _HAS_PG = True
except ImportError:
    _HAS_PG = False

_MCA_SETTINGS_PATH = Path.home() / ".easy_bluesky" / "mca_viewer_settings.json"

_N_ROIS = 16   # fallback when pv_map carries no ROI signals

# Semi-transparent RGBA colors for ROI bands
_ROI_COLORS = [
    (255, 100, 100, 60),
    (100, 200, 100, 60),
    (100, 150, 255, 60),
    (255, 200,  50, 60),
    (200, 100, 255, 60),
    ( 50, 220, 220, 60),
    (255, 150,  50, 60),
    (150, 255, 150, 60),
    (255,  80, 200, 60),
    ( 80, 200, 255, 60),
    (255, 255, 100, 60),
    (200, 200, 200, 60),
    (255, 130, 130, 60),
    (130, 255, 130, 60),
    (130, 130, 255, 60),
    (255, 200, 130, 60),
]


def _load_settings() -> dict:
    try:
        if _MCA_SETTINGS_PATH.exists():
            return json.loads(_MCA_SETTINGS_PATH.read_text())
    except Exception:
        pass
    return {}


def _save_settings(settings: dict):
    try:
        _MCA_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        _MCA_SETTINGS_PATH.write_text(json.dumps(settings, indent=2))
    except Exception:
        pass


def extract_mca_prefix(pv_map: dict) -> str | None:
    """Return the MCA record base prefix by matching any ROI count PV."""
    pat = re.compile(r'^(.+)\.R\d+$')
    for pv in pv_map.values():
        if not pv:
            continue
        m = pat.match(pv)
        if m:
            return m.group(1)
    return None


def detect_n_rois(pv_map: dict) -> int:
    """Count ROI slots from the ophyd pv_map (PVs ending in .R{N}).

    Returns max(N)+1 so the viewer only subscribes to the ROIs the device
    actually exposes.  Falls back to _N_ROIS if no ROI PVs are found.
    """
    roi_pat = re.compile(r'\.R(\d+)$')
    indices = set()
    for pv in pv_map.values():
        if not pv:
            continue
        m = roi_pat.search(pv)
        if m:
            indices.add(int(m.group(1)))
    return max(indices) + 1 if indices else _N_ROIS


class MCAViewerWindow(QMainWindow):
    """Floating live MCA viewer driven by IOC ROI PVs — no PyMCA required."""

    _spectrum_received = pyqtSignal(object)           # np.ndarray
    _roi_cb_received   = pyqtSignal(int, object)      # idx, partial dict
    _status_received   = pyqtSignal(float, float, bool)  # ertm, eltm, acqg
    _cal_received      = pyqtSignal(float, float)     # calo (eV), cals (eV/ch)

    def __init__(self, device_name: str, mca_prefix: str = "",
                 pv_map: dict | None = None, parent=None):
        super().__init__(parent)
        self._device_name = device_name
        self._prefix      = mca_prefix.strip()
        self._pv_map      = pv_map or {}
        self._alive       = True
        self._live        = True
        self._n_rois      = detect_n_rois(self._pv_map)

        # CA PV handles — strong references to prevent GC
        self._pvs: list = []

        # Per-ROI reverse lookup: pvname → (idx, field)
        self._roi_pv_idx: dict = {}   # pvname → (idx, 'lo'|'hi'|'nm'|'counts')

        # ROI state — one slot per ROI exposed by the ophyd device
        self._rois: list[dict] = [
            {'lo': 0, 'hi': 0, 'name': '', 'counts': 0.0}
            for _ in range(self._n_rois)
        ]

        # pyqtgraph ROI region items — idx → LinearRegionItem
        self._regions: dict = {}

        # Energy calibration (eV): E = _calo + _cals * channel
        self._calo: float = 0.0
        self._cals: float = 0.0   # 0 = uncalibrated

        self._last_counts: np.ndarray | None = None
        self._updating_roi = False   # suppress write-back during programmatic updates
        self._pending_cal_gain:   float = 0.0
        self._pending_cal_offset: float = 0.0

        # Cached status/cal values — updated directly from CA callbacks
        self._ertm: float = 0.0
        self._eltm: float = 0.0
        self._acqg: bool  = False
        self._calo_ioc: float = 0.0
        self._cals_ioc: float = 0.0

        self._spectrum_received.connect(self._on_new_spectrum)
        self._roi_cb_received.connect(self._on_roi_update)
        self._status_received.connect(self._on_status_update)
        self._cal_received.connect(self._on_cal_update)

        self._build_ui()
        self._restore_settings()

        if self._prefix:
            QTimer.singleShot(200, lambda: self._connect_mca(self._prefix))

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.setWindowTitle(f"MCA Viewer — {self._device_name}")
        self.resize(1300, 750)

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(6)

        root.addWidget(self._build_ctrl())

        right_split = QSplitter(Qt.Orientation.Vertical)

        if _HAS_PG:
            self._plot_widget = pg.PlotWidget()
            self._plot_widget.setBackground('#1e1e1e')
            self._plot_widget.showGrid(x=True, y=True, alpha=0.2)
            self._plot_widget.setLabel('left', 'Counts')
            self._plot_widget.setLabel('bottom', 'Channel')
            self._curve = pg.PlotCurveItem(pen=pg.mkPen('w', width=1))
            self._plot_widget.addItem(self._curve)

            # Cursor line
            self._cursor_line = pg.InfiniteLine(pos=0, angle=90, movable=False,
                                                pen=pg.mkPen('#888888', width=1, style=Qt.PenStyle.DashLine))
            self._plot_widget.addItem(self._cursor_line)
            self._plot_widget.scene().sigMouseMoved.connect(self._on_mouse_moved)

            right_split.addWidget(self._plot_widget)
        else:
            no_pg = QLabel("<b>pyqtgraph not installed.</b><br>pip install pyqtgraph")
            no_pg.setAlignment(Qt.AlignmentFlag.AlignCenter)
            right_split.addWidget(no_pg)

        right_split.addWidget(self._build_roi_table())
        right_split.setStretchFactor(0, 2)
        right_split.setStretchFactor(1, 1)

        root.addWidget(right_split, stretch=1)

        self._status_lbl = QLabel("○ Not connected")
        self.statusBar().addWidget(self._status_lbl, 1)
        self._cursor_lbl = QLabel("")
        self.statusBar().addPermanentWidget(self._cursor_lbl)

    def _build_ctrl(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(230)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(2, 4, 4, 4)
        lay.setSpacing(8)

        # MCA Prefix
        gp = QGroupBox("MCA Prefix")
        gpl = QVBoxLayout(gp)
        gpl.setSpacing(4)
        self._prefix_edit = QLineEdit(self._prefix)
        self._prefix_edit.setPlaceholderText("e.g. IOC:mca1")
        self._prefix_edit.returnPressed.connect(self._on_connect_clicked)
        gpl.addWidget(self._prefix_edit)
        btn_conn = QPushButton("Connect")
        btn_conn.clicked.connect(self._on_connect_clicked)
        gpl.addWidget(btn_conn)
        lay.addWidget(gp)

        # Acquire
        ga = QGroupBox("Acquire")
        gal = QVBoxLayout(ga)
        gal.setSpacing(5)
        row = QHBoxLayout()
        self._btn_erase = _btn("⏮  Erase+Start", "#1a3a1a", "#6ddc6d")
        self._btn_stop  = _btn("■  Stop",          "#3a1a1a", "#dc6d6d")
        self._btn_erase.clicked.connect(self._on_erase_start)
        self._btn_stop.clicked.connect(self._on_stop)
        row.addWidget(self._btn_erase)
        row.addWidget(self._btn_stop)
        gal.addLayout(row)
        self._btn_start = _btn("▶  Start", "#1a2a3a", "#6db0dc")
        self._btn_start.clicked.connect(self._on_start)
        gal.addWidget(self._btn_start)
        r2 = QHBoxLayout()
        r2.addWidget(QLabel("Preset:"))
        self._spin_preset = QDoubleSpinBox()
        self._spin_preset.setRange(0.0, 86400.0)
        self._spin_preset.setDecimals(2)
        self._spin_preset.setSuffix(" s")
        self._spin_preset.setValue(10.0)
        self._spin_preset.wheelEvent = lambda e: e.ignore()
        self._spin_preset.editingFinished.connect(
            lambda: self._ca_put('.PRTM', self._spin_preset.value()))
        r2.addWidget(self._spin_preset)
        gal.addLayout(r2)
        lay.addWidget(ga)

        # Display
        gd = QGroupBox("Display")
        gdl = QVBoxLayout(gd)
        self._chk_live = QCheckBox("Live update")
        self._chk_live.setChecked(True)
        self._chk_live.toggled.connect(self._on_live_toggled)
        gdl.addWidget(self._chk_live)
        btn_read = QPushButton("Read Now")
        btn_read.clicked.connect(self._on_read_now)
        gdl.addWidget(btn_read)
        self._chk_logy = QCheckBox("Log Y")
        self._chk_logy.toggled.connect(self._on_logy_toggled)
        gdl.addWidget(self._chk_logy)
        self._chk_kev = QCheckBox("Show keV")
        self._chk_kev.setEnabled(False)
        self._chk_kev.toggled.connect(self._on_kev_toggled)
        gdl.addWidget(self._chk_kev)
        lay.addWidget(gd)

        # Add ROI
        btn_add = QPushButton("+ Add ROI")
        btn_add.clicked.connect(self._on_add_roi)
        lay.addWidget(btn_add)

        lay.addWidget(self._build_calibration_panel())

        lay.addStretch()
        return panel

    def _build_calibration_panel(self) -> QGroupBox:
        gc = QGroupBox("Calibrate — Fe-55")
        gcl = QVBoxLayout(gc)
        gcl.setSpacing(5)

        gcl.addWidget(QLabel(f"Mn Kα  ({_FE55_KA_EV:.1f} eV)"))
        self._spin_ka = QDoubleSpinBox()
        self._spin_ka.setRange(0, 65535)
        self._spin_ka.setDecimals(1)
        self._spin_ka.setSuffix(" ch")
        self._spin_ka.setValue(0.0)
        self._spin_ka.wheelEvent = lambda e: e.ignore()
        self._spin_ka.valueChanged.connect(self._on_cal_channels_changed)
        gcl.addWidget(self._spin_ka)

        gcl.addWidget(QLabel(f"Mn Kβ  ({_FE55_KB_EV:.1f} eV)"))
        self._spin_kb = QDoubleSpinBox()
        self._spin_kb.setRange(0, 65535)
        self._spin_kb.setDecimals(1)
        self._spin_kb.setSuffix(" ch")
        self._spin_kb.setValue(0.0)
        self._spin_kb.wheelEvent = lambda e: e.ignore()
        self._spin_kb.valueChanged.connect(self._on_cal_channels_changed)
        gcl.addWidget(self._spin_kb)

        btn_fit = QPushButton("Auto-fit peaks")
        btn_fit.setToolTip("Fit Gaussians to Mn Kα/Kβ peaks (requires scipy)")
        btn_fit.clicked.connect(self._on_autofit_fe55)
        gcl.addWidget(btn_fit)

        self._cal_result_lbl = QLabel("Gain:   —\nOffset: —")
        self._cal_result_lbl.setStyleSheet("color:#aaa; font-size:11px;")
        gcl.addWidget(self._cal_result_lbl)

        row = QHBoxLayout()
        self._btn_apply_cal = QPushButton("Apply")
        self._btn_apply_cal.setEnabled(False)
        self._btn_apply_cal.clicked.connect(self._on_apply_calibration)
        self._btn_write_ioc = QPushButton("→ IOC")
        self._btn_write_ioc.setEnabled(False)
        self._btn_write_ioc.setToolTip("Write calibration to IOC CALO/CALS PVs")
        self._btn_write_ioc.clicked.connect(self._on_write_cal_to_ioc)
        btn_clear = QPushButton("Clear")
        btn_clear.clicked.connect(self._on_clear_calibration)
        row.addWidget(self._btn_apply_cal)
        row.addWidget(self._btn_write_ioc)
        row.addWidget(btn_clear)
        gcl.addLayout(row)

        return gc

    def _build_roi_table(self) -> QTableWidget:
        cols = ["#", "Name", "Lo Ch", "Hi Ch", "Lo keV", "Hi keV", "Counts", "Del"]
        self._roi_table = QTableWidget(0, len(cols))
        self._roi_table.setHorizontalHeaderLabels(cols)
        self._roi_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents)
        self._roi_table.horizontalHeader().setStretchLastSection(False)
        self._roi_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self._roi_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked |
            QAbstractItemView.EditTrigger.SelectedClicked)
        self._roi_table.itemChanged.connect(self._on_table_name_edited)
        return self._roi_table

    # ── Connection ────────────────────────────────────────────────────────────

    def _on_connect_clicked(self):
        prefix = self._prefix_edit.text().strip()
        if prefix:
            self._connect_mca(prefix)

    def _connect_mca(self, prefix: str):
        try:
            import epics
        except ImportError:
            self._set_status("⚠ pyepics not installed", "#e05050")
            return

        # Tear down old subscriptions
        for pv in self._pvs:
            try:
                pv.clear_callbacks()
                pv.disconnect()
            except Exception:
                pass
        self._pvs.clear()
        self._roi_pv_idx.clear()
        self._regions.clear()
        if _HAS_PG:
            self._plot_widget.clear()
            self._plot_widget.addItem(self._curve)
            self._plot_widget.addItem(self._cursor_line)

        self._prefix = prefix
        self._prefix_edit.setText(prefix)
        self._set_status(f"● Connecting to {prefix}…", "#888888")

        def _mk(pvname, cb, **kw):
            pv = epics.PV(pvname, auto_monitor=True, callback=cb, **kw)
            self._pvs.append(pv)
            return pv

        _mk(f"{prefix}.VAL",  self._on_spectrum_cb)
        _mk(f"{prefix}.ERTM", self._on_status_cb)
        _mk(f"{prefix}.ELTM", self._on_status_cb)
        _mk(f"{prefix}.ACQG", self._on_status_cb)
        _mk(f"{prefix}.CALO", self._on_cal_cb)
        _mk(f"{prefix}.CALS", self._on_cal_cb)

        for n in range(self._n_rois):
            for field, key in (
                (f"{prefix}.R{n}",    'counts'),
                (f"{prefix}.R{n}LO",  'lo'),
                (f"{prefix}.R{n}HI",  'hi'),
                (f"{prefix}.R{n}NM",  'nm'),
            ):
                self._roi_pv_idx[field] = (n, key)
                _mk(field, self._on_roi_cb)

    # ── CA callbacks (background thread) ─────────────────────────────────────

    def _on_spectrum_cb(self, pvname='', value=None, **kw):
        if not self._alive or value is None or not self._live:
            return
        self._spectrum_received.emit(np.asarray(value).copy())

    def _on_status_cb(self, pvname='', value=None, **kw):
        if not self._alive or value is None:
            return
        field = pvname.rsplit('.', 1)[-1] if '.' in pvname else pvname
        if field == 'ERTM':
            self._ertm = float(value)
        elif field == 'ELTM':
            self._eltm = float(value)
        elif field == 'ACQG':
            self._acqg = bool(value)
        self._status_received.emit(self._ertm, self._eltm, self._acqg)

    def _on_cal_cb(self, pvname='', value=None, **kw):
        if not self._alive or value is None:
            return
        field = pvname.rsplit('.', 1)[-1] if '.' in pvname else pvname
        if field == 'CALO':
            self._calo_ioc = float(value)
        elif field == 'CALS':
            self._cals_ioc = float(value)
        self._cal_received.emit(self._calo_ioc, self._cals_ioc)

    def _on_roi_cb(self, pvname='', value=None, **kw):
        if not self._alive or value is None:
            return
        entry = self._roi_pv_idx.get(pvname)
        if entry is None:
            return
        idx, key = entry
        if key == 'nm':
            self._roi_cb_received.emit(idx, {'name': str(value)})
        elif key == 'counts':
            self._roi_cb_received.emit(idx, {'counts': float(value)})
        else:
            self._roi_cb_received.emit(idx, {key: int(value)})

    # ── Qt-thread slots ───────────────────────────────────────────────────────

    def _on_new_spectrum(self, counts: np.ndarray):
        if counts.ndim != 1 or counts.size == 0:
            return
        self._last_counts = counts
        if _HAS_PG:
            x = self._channels_or_kev(np.arange(len(counts), dtype=np.float64))
            self._curve.setData(x, counts.astype(np.float64))
        n = len(counts)
        total = int(counts.sum())
        self._set_status(
            f"● {self._prefix}  |  {n} ch  |  {total:,} cts", "#2ca02c")

    def _on_roi_update(self, idx: int, update: dict):
        self._rois[idx].update(update)
        self._refresh_rois()

    def _on_status_update(self, ertm: float, eltm: float, acqg: bool):
        indicator = "⏺ Acquiring" if acqg else "◼ Idle"
        color = "#e8c44a" if acqg else "#888888"
        extra = self._status_lbl.text()
        # Only update the timing part; leave spectrum info if present
        if "●" in extra:
            base = extra.split("  |")[0]
            self._set_status(
                f"{base}  |  {indicator}  |  RT {ertm:.2f} s  LT {eltm:.2f} s",
                "#2ca02c" if not acqg else color,
            )

    def _on_cal_update(self, calo: float, cals: float):
        self._calo = calo
        self._cals = cals
        has_cal = abs(cals) > 1e-9
        self._chk_kev.setEnabled(has_cal)
        if not has_cal:
            self._chk_kev.setChecked(False)
        # Replot with updated calibration
        if self._last_counts is not None:
            self._on_new_spectrum(self._last_counts)
        self._refresh_rois()

    # ── ROI display ───────────────────────────────────────────────────────────

    def _refresh_rois(self):
        if not _HAS_PG:
            self._rebuild_table()
            return

        active = [(i, r) for i, r in enumerate(self._rois) if r['hi'] > r['lo']]

        # Remove regions for now-inactive ROIs
        for idx in list(self._regions.keys()):
            if idx not in {i for i, _ in active}:
                try:
                    self._plot_widget.removeItem(self._regions.pop(idx))
                except Exception:
                    pass

        show_kev = self._chk_kev.isChecked() and abs(self._cals) > 1e-9

        self._updating_roi = True
        for idx, roi in active:
            lo = roi['lo']
            hi = roi['hi']
            x_lo = self._ch_to_x(lo) if show_kev else float(lo)
            x_hi = self._ch_to_x(hi) if show_kev else float(hi)

            if idx in self._regions:
                self._regions[idx].setRegion((x_lo, x_hi))
            else:
                r, g, b, a = _ROI_COLORS[idx % len(_ROI_COLORS)]
                region = pg.LinearRegionItem(
                    values=(x_lo, x_hi),
                    brush=pg.mkBrush(r, g, b, a),
                    pen=pg.mkPen(r, g, b, 180),
                    movable=True,
                )
                label = pg.InfLineLabel(
                    region.lines[0],
                    text=roi['name'] or f"ROI{idx}",
                    position=0.9,
                    color=(r, g, b),
                )
                region.sigRegionChangeFinished.connect(
                    lambda reg, i=idx: self._on_region_moved(i, reg))
                self._plot_widget.addItem(region)
                self._regions[idx] = region
        self._updating_roi = False

        self._rebuild_table()

    def _on_region_moved(self, idx: int, region):
        if self._updating_roi:
            return
        lo_x, hi_x = region.getRegion()
        show_kev = self._chk_kev.isChecked() and abs(self._cals) > 1e-9
        if show_kev:
            lo_ch = int(round(self._x_to_ch(lo_x)))
            hi_ch = int(round(self._x_to_ch(hi_x)))
        else:
            lo_ch = int(round(lo_x))
            hi_ch = int(round(hi_x))
        lo_ch = max(0, lo_ch)
        hi_ch = max(lo_ch + 1, hi_ch)
        self._rois[idx]['lo'] = lo_ch
        self._rois[idx]['hi'] = hi_ch
        self._ca_put(f'.R{idx}LO', lo_ch)
        self._ca_put(f'.R{idx}HI', hi_ch)
        self._rebuild_table()

    def _rebuild_table(self):
        self._roi_table.blockSignals(True)
        active = [(i, r) for i, r in enumerate(self._rois) if r['hi'] > r['lo']]
        self._roi_table.setRowCount(len(active))
        has_cal = abs(self._cals) > 1e-9

        for row, (idx, roi) in enumerate(active):
            lo, hi = roi['lo'], roi['hi']
            lo_kev = self._ch_to_x(lo) if has_cal else None
            hi_kev = self._ch_to_x(hi) if has_cal else None

            def _ro(text, align=Qt.AlignmentFlag.AlignCenter) -> QTableWidgetItem:
                it = QTableWidgetItem(text)
                it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                it.setTextAlignment(align)
                return it

            self._roi_table.setItem(row, 0, _ro(str(idx)))
            name_item = QTableWidgetItem(roi['name'])
            name_item.setData(Qt.ItemDataRole.UserRole, idx)
            self._roi_table.setItem(row, 1, name_item)
            self._roi_table.setItem(row, 2, _ro(str(lo)))
            self._roi_table.setItem(row, 3, _ro(str(hi)))
            self._roi_table.setItem(row, 4, _ro(f"{lo_kev:.3f}" if lo_kev is not None else "—"))
            self._roi_table.setItem(row, 5, _ro(f"{hi_kev:.3f}" if hi_kev is not None else "—"))
            self._roi_table.setItem(row, 6, _ro(f"{roi['counts']:.0f}"))

            del_btn = QPushButton("✕")
            del_btn.setStyleSheet("color:#dc6d6d; font-weight:bold; padding:0px 4px;")
            del_btn.setFixedWidth(28)
            del_btn.clicked.connect(lambda _c, i=idx: self._delete_roi(i))
            self._roi_table.setCellWidget(row, 7, del_btn)

        self._roi_table.blockSignals(False)

    def _on_table_name_edited(self, item: QTableWidgetItem):
        if item.column() != 1:
            return
        idx = item.data(Qt.ItemDataRole.UserRole)
        if idx is None:
            return
        name = item.text()
        self._rois[idx]['name'] = name
        self._ca_put(f'.R{idx}NM', name)
        # Update region label
        if _HAS_PG and idx in self._regions:
            for line in self._regions[idx].lines:
                for label in line.getViewBox().allChildren():
                    if isinstance(label, pg.InfLineLabel) and label.line is line:
                        label.setText(name or f"ROI{idx}")

    def _delete_roi(self, idx: int):
        self._rois[idx] = {'lo': 0, 'hi': 0, 'name': '', 'counts': 0.0}
        self._ca_put(f'.R{idx}LO', 0)
        self._ca_put(f'.R{idx}HI', 0)
        self._ca_put(f'.R{idx}NM', '')
        if _HAS_PG and idx in self._regions:
            try:
                self._plot_widget.removeItem(self._regions.pop(idx))
            except Exception:
                pass
        self._rebuild_table()

    # ── Add ROI ───────────────────────────────────────────────────────────────

    def _on_add_roi(self):
        # Find first inactive slot
        slot = next((i for i, r in enumerate(self._rois) if r['hi'] <= r['lo']), None)
        if slot is None:
            self._set_status(f"⚠ All {self._n_rois} ROI slots are in use", "#e05050")
            return

        name, ok = QInputDialog.getText(self, "Add ROI", f"Name for ROI {slot}:")
        if not ok:
            return

        if _HAS_PG:
            vr = self._plot_widget.viewRange()[0]
            center = (vr[0] + vr[1]) / 2.0
        else:
            center = 512.0

        show_kev = self._chk_kev.isChecked() and abs(self._cals) > 1e-9
        if show_kev:
            lo_ch = max(0, int(round(self._x_to_ch(center - 0.05))))
            hi_ch = max(lo_ch + 1, int(round(self._x_to_ch(center + 0.05))))
        else:
            lo_ch = max(0, int(round(center)) - 50)
            hi_ch = max(lo_ch + 1, int(round(center)) + 50)

        self._rois[slot] = {'lo': lo_ch, 'hi': hi_ch,
                            'name': name, 'counts': 0.0}
        self._ca_put(f'.R{slot}LO', lo_ch)
        self._ca_put(f'.R{slot}HI', hi_ch)
        self._ca_put(f'.R{slot}NM', name)
        self._refresh_rois()

    # ── Cursor ────────────────────────────────────────────────────────────────

    def _on_mouse_moved(self, pos):
        if not _HAS_PG:
            return
        vb = self._plot_widget.getPlotItem().getViewBox()
        if not vb.sceneBoundingRect().contains(pos):
            self._cursor_lbl.setText("")
            return
        mp = vb.mapSceneToView(pos)
        x = mp.x()
        self._cursor_line.setPos(x)

        counts_str = ""
        if self._last_counts is not None:
            show_kev = self._chk_kev.isChecked() and abs(self._cals) > 1e-9
            ch = int(round(self._x_to_ch(x))) if show_kev else int(round(x))
            if 0 <= ch < len(self._last_counts):
                counts_str = f"  counts: {int(self._last_counts[ch])}"

        show_kev = self._chk_kev.isChecked() and abs(self._cals) > 1e-9
        if show_kev:
            ch = int(round(self._x_to_ch(x)))
            self._cursor_lbl.setText(f"ch: {ch}  keV: {x:.3f}{counts_str}")
        else:
            ch = int(round(x))
            kev_str = ""
            if abs(self._cals) > 1e-9:
                kev_str = f"  keV: {self._ch_to_x(ch):.3f}"
            self._cursor_lbl.setText(f"ch: {ch}{kev_str}{counts_str}")

    # ── Display toggles ───────────────────────────────────────────────────────

    def _on_live_toggled(self, checked: bool):
        self._live = checked

    def _on_read_now(self):
        for pv in self._pvs:
            if pv.pvname == f"{self._prefix}.VAL":
                try:
                    val = pv.get(timeout=2.0)
                    if val is not None:
                        self._spectrum_received.emit(np.asarray(val).copy())
                except Exception:
                    pass
                break

    def _on_logy_toggled(self, checked: bool):
        if not _HAS_PG:
            return
        self._plot_widget.setLogMode(y=checked)

    def _on_kev_toggled(self, _checked: bool):
        if self._last_counts is not None:
            self._on_new_spectrum(self._last_counts)
        self._refresh_rois()
        label = "Energy (keV)" if _checked else "Channel"
        if _HAS_PG:
            self._plot_widget.setLabel('bottom', label)

    # ── Acquire controls ──────────────────────────────────────────────────────

    def _on_erase_start(self):  self._ca_put('.ERST', 1)
    def _on_start(self):        self._ca_put('.STRT', 1)
    def _on_stop(self):         self._ca_put('.STOP', 1)

    def _ca_put(self, field: str, value):
        try:
            import epics
            epics.caput(f"{self._prefix}{field}", value, wait=False)
        except Exception:
            pass

    # ── Calibration helpers ───────────────────────────────────────────────────

    def _ch_to_x(self, ch: float) -> float:
        """Channel → keV (if calibrated)."""
        return (self._calo + self._cals * ch) / 1000.0

    def _x_to_ch(self, x: float) -> float:
        """keV → channel (if calibrated)."""
        if abs(self._cals) < 1e-12:
            return x
        return (x * 1000.0 - self._calo) / self._cals

    def _channels_or_kev(self, channels: np.ndarray) -> np.ndarray:
        if self._chk_kev.isChecked() and abs(self._cals) > 1e-9:
            return (self._calo + self._cals * channels) / 1000.0
        return channels

    # ── Settings ──────────────────────────────────────────────────────────────

    def _restore_settings(self):
        saved = _load_settings().get(self._device_name, {})
        prefix = saved.get('prefix', '')
        if prefix and not self._prefix:
            self._prefix = prefix
            self._prefix_edit.setText(prefix)
        if 'preset' in saved:
            self._spin_preset.setValue(float(saved['preset']))
        if saved.get('log_y'):
            self._chk_logy.setChecked(True)

    def _save_settings(self):
        settings = _load_settings()
        settings.setdefault(self._device_name, {}).update({
            'prefix':  self._prefix,
            'preset':  self._spin_preset.value(),
            'log_y':   self._chk_logy.isChecked(),
            'show_kev': self._chk_kev.isChecked(),
        })
        _save_settings(settings)

    # ── Fe-55 calibration ─────────────────────────────────────────────────────

    def _fit_gaussian_centroid(self, counts: np.ndarray, center: int,
                               half_win: int = 60) -> float | None:
        lo = max(0, center - half_win)
        hi = min(len(counts), center + half_win)
        x = np.arange(lo, hi, dtype=float)
        y = counts[lo:hi].astype(float)
        if y.max() < 10:
            return None
        try:
            def _gauss(x, amp, mu, sig):
                return amp * np.exp(-0.5 * ((x - mu) / sig) ** 2)
            p0 = [y.max(), float(center), 10.0]
            popt, _ = _curve_fit(_gauss, x, y, p0=p0, maxfev=2000)
            return float(popt[1])
        except Exception:
            return None

    def _on_autofit_fe55(self):
        if not _HAS_SCIPY:
            self._set_status("⚠ scipy not installed — pip install scipy", "#e05050")
            return
        if self._last_counts is None:
            self._set_status("⚠ No spectrum loaded", "#e05050")
            return
        counts = self._last_counts
        peaks, props = _find_peaks(counts, height=counts.max() * 0.1,
                                   distance=20, prominence=counts.max() * 0.05)
        if len(peaks) < 2:
            self._set_status("⚠ Could not find two peaks for Fe-55 calibration",
                             "#e05050")
            return
        # Take the two tallest peaks
        heights = props['peak_heights']
        top2 = peaks[np.argsort(heights)[-2:]]
        ka_ch, kb_ch = sorted(top2)
        ka_fit = self._fit_gaussian_centroid(counts, ka_ch)
        kb_fit = self._fit_gaussian_centroid(counts, kb_ch)
        if ka_fit is not None:
            self._spin_ka.setValue(ka_fit)
        if kb_fit is not None:
            self._spin_kb.setValue(kb_fit)

    def _on_cal_channels_changed(self):
        ka_ch = self._spin_ka.value()
        kb_ch = self._spin_kb.value()
        if ka_ch <= 0 or kb_ch <= 0 or abs(kb_ch - ka_ch) < 1:
            self._cal_result_lbl.setText("Gain:   —\nOffset: —")
            self._btn_apply_cal.setEnabled(False)
            self._btn_write_ioc.setEnabled(False)
            return
        # Two-point linear fit: E(ch) = offset + gain * ch  (in eV)
        gain   = (_FE55_KB_EV - _FE55_KA_EV) / (kb_ch - ka_ch)
        offset = _FE55_KA_EV - gain * ka_ch
        self._pending_cal_gain   = gain
        self._pending_cal_offset = offset
        self._cal_result_lbl.setText(
            f"Gain:   {gain:.4f} eV/ch\nOffset: {offset:.2f} eV"
        )
        self._btn_apply_cal.setEnabled(True)
        self._btn_write_ioc.setEnabled(bool(self._prefix))

    def _on_apply_calibration(self):
        self._calo = self._pending_cal_offset
        self._cals = self._pending_cal_gain
        self._chk_kev.setEnabled(True)
        if self._last_counts is not None:
            self._on_new_spectrum(self._last_counts)
        self._refresh_rois()

    def _on_write_cal_to_ioc(self):
        self._ca_put('.CALO', self._pending_cal_offset)
        self._ca_put('.CALS', self._pending_cal_gain)

    def _on_clear_calibration(self):
        self._spin_ka.setValue(0.0)
        self._spin_kb.setValue(0.0)
        self._cal_result_lbl.setText("Gain:   —\nOffset: —")
        self._btn_apply_cal.setEnabled(False)
        self._btn_write_ioc.setEnabled(False)
        # Revert to IOC calibration
        self._calo = self._calo_ioc
        self._cals = self._cals_ioc
        has_cal = abs(self._cals) > 1e-9
        self._chk_kev.setEnabled(has_cal)
        if not has_cal:
            self._chk_kev.setChecked(False)
        if self._last_counts is not None:
            self._on_new_spectrum(self._last_counts)
        self._refresh_rois()

    # ── Status label ─────────────────────────────────────────────────────────

    def _set_status(self, msg: str, color: str = "#888888"):
        self._status_lbl.setText(msg)
        self._status_lbl.setStyleSheet(f"color:{color};")

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def closeEvent(self, event: QCloseEvent):
        self._alive = False
        for pv in self._pvs:
            try:
                pv.clear_callbacks()
                pv.disconnect()
            except Exception:
                pass
        self._pvs.clear()
        self._save_settings()
        super().closeEvent(event)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _btn(text: str, bg: str, fg: str) -> QPushButton:
    b = QPushButton(text)
    b.setStyleSheet(f"background:{bg}; color:{fg}; font-weight:bold;")
    return b
