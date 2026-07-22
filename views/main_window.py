from __future__ import annotations

import math
import sys
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QScrollArea,
    QGroupBox,
    QLabel,
    QLineEdit,
    QSpinBox,
    QDoubleSpinBox,
    QPushButton,
    QCheckBox,
    QComboBox,
    QListWidget,
    QListWidgetItem,
    QFileDialog,
    QInputDialog,
    QMessageBox,
    QGraphicsView,
    QSizePolicy,
    QMenu,
)
from PySide6.QtCore import QEvent

from memory_reader import MemoryReader, AttachStatus
from trail_model import TrailModel, TrailPoint, POI, MIN_DISTANCE
from polling_service import PollingService
from graph_renderer import GraphRenderer
from export_service import export_text, import_text, export_png
from hotkey_service import Win32HotkeyService, VK_F8, VK_F10
from settings_service import load as load_settings, save as save_settings, AppSettings, MapCalibration, SETTINGS_DIR, _apply_profile, _save_current_as_profile, save_trail, load_trail
from views.confirm_dialog import ConfirmDialog


KIND_ROLE = Qt.UserRole + 1
A_ROLE = Qt.UserRole + 2
B_ROLE = Qt.UserRole + 3

ROW_KIND_POINT = 0
ROW_KIND_POI = 1
ROW_KIND_SEPARATOR = 2


SUSPICIOUS_THRESHOLD = 1e7


def is_suspicious(value: float) -> bool:
    return not math.isfinite(value) or abs(value) > SUSPICIOUS_THRESHOLD


STYLE = """
QMainWindow, QWidget {
    background-color: #1e1e1e;
    color: #dcdcdc;
}
QGroupBox {
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    margin-top: 12px;
    font-size: 12px;
    font-weight: bold;
    color: #9cdcfe;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}
QLabel {
    color: #dcdcdc;
    font-size: 12px;
}
QLineEdit {
    background-color: #2d2d2d;
    color: #dcdcdc;
    border: 1px solid #3c3c3c;
    padding: 4px 6px;
    font-family: Consolas, monospace;
    font-size: 12px;
}
QLineEdit:focus {
    border-color: #569cd6;
}
QLineEdit:disabled {
    background-color: #252525;
    color: #666;
}
QSpinBox {
    background-color: #2d2d2d;
    color: #dcdcdc;
    border: 1px solid #3c3c3c;
    padding: 4px 6px;
    font-size: 12px;
}
QSpinBox:focus {
    border-color: #569cd6;
}
QPushButton {
    background-color: #0e639c;
    color: #ffffff;
    border: none;
    padding: 6px 14px;
    font-size: 12px;
    border-radius: 3px;
}
QPushButton:hover {
    background-color: #1177bb;
}
QPushButton:pressed {
    background-color: #0d5688;
}
QPushButton:disabled {
    background-color: #3c3c3c;
    color: #666;
}
QListWidget {
    background-color: #252525;
    color: #dcdcdc;
    border: 1px solid #3c3c3c;
    font-family: Consolas, monospace;
    font-size: 11px;
    outline: none;
}
QListWidget::item {
    padding: 2px 4px;
}
QListWidget::item:selected {
    background-color: #094771;
    color: #ffffff;
}
QGraphicsView {
    border: 1px solid #3c3c3c;
    background-color: #1e1e1e;
}
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical {
    background: #2d2d2d; width: 8px;
    border: none; border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #555; min-height: 20px; border-radius: 4px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GameMapTracker")
        self.setMinimumSize(900, 600)
        self.resize(1200, 750)
        self.setStyleSheet(STYLE)

        self._settings = load_settings()

        self._reader = MemoryReader(self._settings.process_name)
        self._trail = TrailModel()
        trail_data = load_trail()
        if trail_data:
            from trail_model import TrailPoint, POI
            paths = [[TrailPoint(*pt) for pt in path] for path in trail_data.get("paths", [])]
            pois = [POI(**p) for p in trail_data.get("pois", [])]
            self._trail.load(paths, pois)
        self._polling = PollingService(self._reader)
        self._hotkey_service: Win32HotkeyService | None = None
        self._graph_renderer: GraphRenderer | None = None

        self._recording = False
        self._recording_start: float = 0.0
        self._total_dist: float = 0.0
        self._last_recorded_pos: tuple[float, float] | None = None
        self._last_live_x: float | None = None
        self._last_live_y: float | None = None

        self._bounds_sync_timer = QTimer(self)
        self._bounds_sync_timer.setSingleShot(True)
        self._bounds_sync_timer.setInterval(700)
        self._bounds_sync_timer.timeout.connect(self._on_bounds_sync_render)

        self._calibrating = False
        self._calib_step = 0


        self._build_ui()
        self._connect_events()

        if self._settings.map_path:
            self._graph_renderer.load_map(self._settings.map_path)
            self._graph_renderer.set_calibration(self._settings.calibration)
        if self._trail.has_data:
            self._render_trail(refit_view=True)
            self._graph_renderer.zoom_to_fit()
        else:
            self._render_trail()
        self._update_ui_state()

        self._rebuild_profile_combo()

        if sys.platform == "win32":
            self._hotkey_service = Win32HotkeyService(self)
            self._hotkey_service.register(VK_F8, self._toggle_recording)
            self._hotkey_service.register(VK_F10, self._mark_poi)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(6)

        proc_group = QGroupBox("Process")
        proc_layout = QVBoxLayout(proc_group)
        proc_layout.setSpacing(4)

        proc_layout.addWidget(QLabel("Process Name:"))
        self._proc_name_input = QLineEdit()
        self._proc_name_input.setText(self._settings.process_name)
        proc_layout.addWidget(self._proc_name_input)

        self._proc_select_btn = QPushButton("Select Process")
        self._proc_select_btn.setEnabled(False)
        proc_layout.addWidget(self._proc_select_btn)

        self._proc_info_label = QLabel("")
        proc_layout.addWidget(self._proc_info_label)

        left_layout.addWidget(proc_group)

        map_group = QGroupBox("Map")
        map_layout = QVBoxLayout(map_group)
        map_layout.setSpacing(4)

        self._load_map_btn = QPushButton("Load Map Image")
        map_layout.addWidget(self._load_map_btn)

        self._clear_map_btn = QPushButton("Clear Map")
        self._clear_map_btn.setEnabled(False)
        map_layout.addWidget(self._clear_map_btn)

        self._calibrate_btn = QPushButton("Calibrate (click 2 points)")
        self._calibrate_btn.setEnabled(False)
        map_layout.addWidget(self._calibrate_btn)

        self._flip_y_check = QCheckBox("Flip Y Axis")
        self._flip_y_check.setEnabled(False)
        map_layout.addWidget(self._flip_y_check)

        self._flip_x_check = QCheckBox("Flip X Axis")
        self._flip_x_check.setEnabled(False)
        map_layout.addWidget(self._flip_x_check)

        self._auto_follow_check = QCheckBox("Auto Follow")
        self._auto_follow_check.setChecked(True)
        self._auto_follow_check.setEnabled(False)
        map_layout.addWidget(self._auto_follow_check)

        self._zoom_follow_check = QCheckBox("Zoom Follow")
        self._zoom_follow_check.setChecked(True)
        self._zoom_follow_check.setEnabled(False)
        map_layout.addWidget(self._zoom_follow_check)

        self._map_status_label = QLabel("")
        map_layout.addWidget(self._map_status_label)

        left_layout.addWidget(map_group)

        addr_group = QGroupBox("Addresses")
        addr_layout = QVBoxLayout(addr_group)
        addr_layout.setSpacing(4)

        addr_layout.addWidget(QLabel("X Address:"))
        self._x_addr_input = QLineEdit()
        self._x_addr_input.setText(self._settings.x_address)
        addr_layout.addWidget(self._x_addr_input)

        addr_layout.addWidget(QLabel("Y Address:"))
        self._y_addr_input = QLineEdit()
        self._y_addr_input.setText(self._settings.y_address)
        addr_layout.addWidget(self._y_addr_input)

        addr_layout.addWidget(QLabel("Interval (ms):"))
        self._interval_input = QSpinBox()
        self._interval_input.setRange(50, 5000)
        self._interval_input.setValue(self._settings.interval_ms)
        self._interval_input.setSingleStep(50)
        addr_layout.addWidget(self._interval_input)

        addr_layout.addWidget(QLabel("Idle Auto-Pause:"))
        self._idle_threshold_spin = QDoubleSpinBox()
        self._idle_threshold_spin.setRange(0, 30)
        self._idle_threshold_spin.setSingleStep(0.5)
        self._idle_threshold_spin.setSuffix(" sec")
        self._idle_threshold_spin.setValue(0.0)
        self._idle_threshold_spin.valueChanged.connect(self._on_idle_threshold_changed)
        addr_layout.addWidget(self._idle_threshold_spin)

        addr_layout.addWidget(QLabel("Teleport Threshold:"))
        self._teleport_input = QDoubleSpinBox()
        self._teleport_input.setRange(100, 100000)
        self._teleport_input.setValue(2000.0)
        self._teleport_input.setSingleStep(100)
        addr_layout.addWidget(self._teleport_input)

        epsilon_layout = QHBoxLayout()
        epsilon_layout.addWidget(QLabel("Smooth Epsilon:"))
        self._epsilon_input = QDoubleSpinBox()
        self._epsilon_input.setRange(0.1, 100.0)
        self._epsilon_input.setValue(3.0)
        self._epsilon_input.setSingleStep(0.5)
        epsilon_layout.addWidget(self._epsilon_input)
        addr_layout.addLayout(epsilon_layout)

        left_layout.addWidget(addr_group)

        ctrl_group = QGroupBox("Controls")
        ctrl_layout = QVBoxLayout(ctrl_group)
        ctrl_layout.setSpacing(6)

        self._start_btn = QPushButton("Start (F8)")
        ctrl_layout.addWidget(self._start_btn)

        self._mark_poi_btn = QPushButton("Mark POI (F10)")
        self._mark_poi_btn.setEnabled(False)
        ctrl_layout.addWidget(self._mark_poi_btn)

        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setEnabled(False)
        ctrl_layout.addWidget(self._clear_btn)

        import_export_layout = QHBoxLayout()
        self._import_btn = QPushButton("Import")
        self._export_txt_btn = QPushButton("Export TXT")
        self._export_png_btn = QPushButton("Export PNG")
        import_export_layout.addWidget(self._import_btn)
        import_export_layout.addWidget(self._export_txt_btn)
        import_export_layout.addWidget(self._export_png_btn)
        ctrl_layout.addLayout(import_export_layout)

        tool_layout = QHBoxLayout()
        self._smooth_btn = QPushButton("Smooth")
        self._smooth_btn.setEnabled(False)
        self._heat_btn = QPushButton("Heat Map")
        self._heat_btn.setCheckable(True)
        self._heat_btn.setEnabled(False)
        self._zoom_fit_btn = QPushButton("Zoom Fit")
        self._zoom_fit_btn.setEnabled(False)
        tool_layout.addWidget(self._smooth_btn)
        tool_layout.addWidget(self._heat_btn)
        self._fade_trail_check = QCheckBox("Fade Trail")
        self._fade_trail_check.setEnabled(False)
        tool_layout.addWidget(self._fade_trail_check)
        tool_layout.addWidget(self._zoom_fit_btn)
        ctrl_layout.addLayout(tool_layout)

        left_layout.addWidget(ctrl_group)

        profile_group = QGroupBox("Profiles")
        profile_layout = QVBoxLayout(profile_group)
        profile_layout.setSpacing(4)

        profile_row = QHBoxLayout()
        self._profile_combo = QComboBox()
        self._profile_combo.setMinimumWidth(100)
        self._profile_save_btn = QPushButton("Save As")
        self._profile_delete_btn = QPushButton("Delete")
        profile_row.addWidget(self._profile_combo, 1)
        profile_row.addWidget(self._profile_save_btn)
        profile_row.addWidget(self._profile_delete_btn)
        profile_layout.addLayout(profile_row)

        left_layout.addWidget(profile_group)

        live_group = QGroupBox("Live")
        live_layout = QVBoxLayout(live_group)
        live_layout.setSpacing(4)

        self._live_x_label = QLabel("X: --")
        self._live_y_label = QLabel("Y: --")
        self._status_label = QLabel("Status: Idle")

        live_layout.addWidget(self._live_x_label)
        live_layout.addWidget(self._live_y_label)
        live_layout.addWidget(self._status_label)

        left_layout.addWidget(live_group)
        left_layout.addStretch()

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 8, 8, 8)
        right_layout.setSpacing(6)

        self._graph_view = QGraphicsView()
        self._graph_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._graph_renderer = GraphRenderer(self._graph_view)
        right_layout.addWidget(self._graph_view, stretch=3)

        self._data_list = QListWidget()
        self._data_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._data_list.setMinimumHeight(120)
        right_layout.addWidget(self._data_list, stretch=1)

        left_scroll.setWidget(left_panel)
        splitter.addWidget(left_scroll)
        splitter.addWidget(right_panel)
        splitter.setSizes([280, 920])

        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

    def _connect_events(self) -> None:
        self._start_btn.clicked.connect(self._toggle_recording)
        self._mark_poi_btn.clicked.connect(self._mark_poi)
        self._clear_btn.clicked.connect(self._on_clear)
        self._import_btn.clicked.connect(self._on_import)
        self._export_txt_btn.clicked.connect(self._on_export_txt)
        self._export_png_btn.clicked.connect(self._on_export_png)
        self._proc_name_input.editingFinished.connect(self._on_process_name_changed)
        self._proc_select_btn.clicked.connect(self._on_select_process)
        self._load_map_btn.clicked.connect(self._on_load_map)
        self._clear_map_btn.clicked.connect(self._on_clear_map)
        self._calibrate_btn.clicked.connect(self._on_calibrate)
        self._flip_y_check.toggled.connect(self._on_flip_y)
        self._flip_x_check.toggled.connect(self._on_flip_x)
        self._auto_follow_check.toggled.connect(self._on_auto_follow)
        self._zoom_follow_check.toggled.connect(self._on_zoom_follow)
        self._smooth_btn.clicked.connect(self._on_smooth)
        self._heat_btn.clicked.connect(self._on_toggle_heat)
        self._fade_trail_check.toggled.connect(self._on_toggle_fade)
        self._zoom_fit_btn.clicked.connect(self._on_zoom_fit)
        self._profile_combo.currentTextChanged.connect(self._on_profile_changed)
        self._profile_save_btn.clicked.connect(self._on_profile_save)
        self._profile_delete_btn.clicked.connect(self._on_profile_delete)
        self._polling.value_read.connect(self._on_value_read)
        self._polling.read_failed.connect(self._on_read_failed)
        self._polling.idle_paused.connect(self._on_idle_paused)
        self._polling.idle_resumed.connect(self._on_idle_resumed)
        self._data_list.currentItemChanged.connect(self._on_data_selection_changed)
        self._data_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._data_list.customContextMenuRequested.connect(self._on_data_context_menu)
        self._data_list.installEventFilter(self)
        self._graph_view.viewport().installEventFilter(self)
        self._interval_input.valueChanged.connect(self._on_interval_changed)
        self._teleport_input.valueChanged.connect(self._on_teleport_changed)

        self._graph_renderer.bounds_expanded.connect(self._schedule_bounds_sync_render)
        self._graph_renderer.poi_moved.connect(self._on_poi_moved)
        self._graph_renderer.poi_edit_requested.connect(self._edit_poi_description)
        self._graph_renderer.poi_delete_requested.connect(self._delete_poi_by_index)

    def _schedule_bounds_sync_render(self) -> None:
        if self._recording:
            self._bounds_sync_timer.start()

    def _render_trail(self, *, refit_view: bool = False) -> None:
        self._graph_renderer.render(
            self._trail.paths,
            self._trail.pois,
            preserve_transform=not refit_view,
        )

    def _on_bounds_sync_render(self) -> None:
        if self._recording:
            self._graph_renderer._suppress_bounds_signal = True
            try:
                self._render_trail()
                self._graph_renderer.note_paths_for_poi_highlights(self._trail.paths)
                if self._last_live_x is not None and self._last_live_y is not None:
                    self._graph_renderer.update_live_marker(
                        self._last_live_x, self._last_live_y, instant=True
                    )
            finally:
                self._graph_renderer._suppress_bounds_signal = False

    def _on_poi_moved(self, idx: int, gx: float, gy: float) -> None:
        if not (0 <= idx < len(self._trail.pois)):
            return
        poi = self._trail.pois[idx]
        self._trail.update_poi(idx, gx, gy, poi.desc, poi.category)
        save_trail(self._trail.paths, self._trail.pois)
        self._graph_renderer.render(self._trail.paths, self._trail.pois, preserve_transform=True)
        self._rebuild_data_list()

    def _delete_poi_by_index(self, idx: int) -> None:
        if not (0 <= idx < len(self._trail.pois)):
            return
        self._trail.remove_poi(idx)
        save_trail(self._trail.paths, self._trail.pois)
        self._rebuild_data_list()
        self._graph_renderer.render(self._trail.paths, self._trail.pois, preserve_transform=True)

    def _toggle_recording(self) -> None:
        if self._recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self) -> None:
        x_text = self._x_addr_input.text().strip()
        y_text = self._y_addr_input.text().strip()

        x_spec = MemoryReader.try_parse_address(x_text)
        y_spec = MemoryReader.try_parse_address(y_text)

        if x_spec is None or y_spec is None:
            self._set_status("Invalid address format", "orange")
            return

        if not self._reader.has_handle:
            status = self._reader.attach()
            if status == AttachStatus.ProcessNotFound:
                self._set_status(f"{self._reader._process_name} not found", "red")
                return
            elif status == AttachStatus.AccessDenied:
                self._set_status("Access denied - run as admin", "red")
                return
            elif status == AttachStatus.Unsupported:
                self._set_status("Windows only", "red")
                return

            proc_name = self._reader._process_name
            pid = self._reader._pid
            base = self._reader._module_base

            lines = [f"{proc_name} (PID {pid})"]
            for info in self._reader.process_candidates:
                selected = " ✓" if info.pid == pid else ""
                lines.append(f"  PID {info.pid} base=0x{info.module_base:X} size={info.module_size//1024}KB{selected}")
            self._proc_info_label.setText("\n".join(lines))

            candidates = self._reader.process_candidates
            if len(candidates) > 1:
                self._proc_select_btn.setEnabled(True)

        x_addr = self._reader.try_resolve(x_spec)
        y_addr = self._reader.try_resolve(y_spec)

        if x_addr is None or y_addr is None:
            self._set_status("Failed to resolve addresses", "red")
            return

        self._trail.teleport_threshold = self._teleport_input.value()
        self._trail.start_new_path()
        self._recording_start = time.monotonic()
        self._total_dist = 0.0
        self._last_recorded_pos = None
        self._rebuild_data_list()

        interval = self._interval_input.value()
        self._polling.start(x_addr, y_addr, interval)

        self._recording = True
        self._graph_renderer.render(self._trail.paths, self._trail.pois, preserve_transform=True)
        self._graph_renderer.follow_zoom_enabled = self._zoom_follow_check.isChecked()
        if self._zoom_follow_check.isChecked():
            self._graph_renderer.recenter_follow_view()
        elif self._trail.has_data:
            self._graph_renderer.zoom_to_fit()
        if self._auto_follow_check.isChecked():
            self._graph_renderer.auto_follow_active = True
        self._update_ui_state()
        self._set_status("Recording...", "#4ec9b0")

    def _stop_recording(self) -> None:
        self._recording = False
        self._graph_renderer.auto_follow_active = False
        self._graph_renderer.hide_stats()
        self._trail.prune_empty_current_path()
        self._rebuild_data_list()
        self._graph_renderer.clear_live_data()
        self._last_live_x = None
        self._last_live_y = None
        self._graph_renderer.render(self._trail.paths, self._trail.pois, preserve_transform=True)
        self._update_ui_state()

        if self._trail.has_data:
            self._set_status("Paused", "orange")
        else:
            self._set_status("Idle", "gray")

    def _on_process_name_changed(self) -> None:
        self._reader.detach()
        self._reader.set_process_name(self._proc_name_input.text().strip() or "Exanima.exe")
        self._proc_info_label.setText("")
        self._proc_select_btn.setEnabled(False)

    def _on_select_process(self) -> None:
        candidates = self._reader.process_candidates
        if not candidates:
            return
        items = [
            f"PID {c.pid}  base=0x{c.module_base:X}  {c.module_size//1024}KB{' (current)' if c.pid == self._reader._pid else ''}"
            for c in candidates
        ]
        text, ok = QInputDialog.getItem(
            self, "Select Process", "Choose a process:", items, 0, False
        )
        if ok and text:
            pid = None
            import re
            m = re.search(r"PID (\d+)", text)
            if m:
                target = int(m.group(1))
                for c in candidates:
                    if c.pid == target:
                        pid = c.pid
                        break
            if pid is None:
                return
            old_pid = self._reader._pid
            was_recording = self._recording

            if was_recording:
                self._polling.stop()

            self._reader.detach()
            status = self._reader.attach_to(pid)
            if status == AttachStatus.Attached:
                self._proc_info_label.setText(
                    f"{self._reader._process_name} (PID {self._reader._pid})"
                )
                self._proc_select_btn.setEnabled(len(candidates) > 1)
                if was_recording:
                    self._start_recording()
            else:
                recovered = False
                if old_pid is not None:
                    status = self._reader.attach_to(old_pid)
                    if status == AttachStatus.Attached:
                        if was_recording:
                            self._start_recording()
                        recovered = True
                if not recovered:
                    self._recording = False
                self._update_ui_state()
                self._set_status(
                    "Recovered previous process" if recovered else f"Failed to attach to PID {pid}",
                    "orange" if recovered else "red"
                )

    def _on_load_map(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Map Image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tiff);;All files (*)"
        )
        if not path:
            return
        self._graph_renderer.load_map(path)
        self._clear_map_btn.setEnabled(True)
        self._calibrate_btn.setEnabled(True)
        self._flip_y_check.setEnabled(True)
        self._calibrating = False
        self._calib_step = 0
        self._map_status_label.setText(f"Map loaded: {path.replace(chr(92), '/').split('/')[-1]}")
        self._graph_renderer.render(self._trail.paths, self._trail.pois, preserve_transform=True)

    def _on_clear_map(self) -> None:
        self._graph_renderer.clear_map()
        self._clear_map_btn.setEnabled(False)
        self._calibrate_btn.setEnabled(False)
        self._flip_y_check.setEnabled(False)
        self._flip_y_check.setChecked(False)
        self._calibrating = False
        self._calib_step = 0
        self._map_status_label.setText("")
        self._graph_renderer.render(self._trail.paths, self._trail.pois, preserve_transform=True)

    def _on_calibrate(self) -> None:
        if not self._graph_renderer.has_map:
            return
        if not self._reader.has_handle:
            self._set_status("Attach to process first", "orange")
            return
        self._calibrating = True
        self._calib_step = 0
        self._map_status_label.setText("Calibration: click point 1 on the map")
        self._set_status("Calibration mode - click on map", "orange")

    def _on_graph_double_click_core(self, event) -> None:
        pos = self._graph_view.mapToScene(event.position().toPoint())

        if self._calibrating:
            self._handle_calib_click(pos)
            return

        if not self._trail.has_data:
            return
        xy = self._graph_renderer.try_canvas_to_data(pos)
        if xy is None:
            return
        x, y = xy

        if is_suspicious(x) or is_suspicious(y):
            self._set_status("Cannot place POI at invalid coordinates", "red")
            return
        result = self._prompt_poi_with_category(x, y)
        if result is not None:
            desc, category = result
            self._trail.add_poi(x, y, desc, category)
            self._rebuild_data_list()
            self._graph_renderer.render(self._trail.paths, self._trail.pois, preserve_transform=True)
            self._graph_renderer.note_paths_for_poi_highlights(self._trail.paths)

    def _handle_calib_click(self, pos) -> None:
        if not self._graph_renderer.has_map:
            self._calibrating = False
            return

        ix = pos.x()
        iy = pos.y()

        gx = self._last_live_x
        gy = self._last_live_y

        if gx is not None and gy is not None:
            text, ok = QInputDialog.getText(
                self, f"Calibration Point {self._calib_step + 1}",
                f"Game coords (clicked image pixel: {ix:.1f}, {iy:.1f}):\nEnter X,Y:",
                QLineEdit.Normal, f"{gx:.4f}, {gy:.4f}"
            )
        else:
            text, ok = QInputDialog.getText(
                self, f"Calibration Point {self._calib_step + 1}",
                f"Game coords (clicked image pixel: {ix:.1f}, {iy:.1f}):\nEnter X,Y:",
                QLineEdit.Normal, "0, 0"
            )

        if not ok or not text:
            return

        try:
            parts = text.replace(",", " ").split()
            gx_val = float(parts[0])
            gy_val = float(parts[1])
        except (ValueError, IndexError):
            QMessageBox.warning(self, "Invalid input", "Enter two numbers: X Y")
            return

        if self._calib_step == 0:
            self._settings.calibration.point1_gx = gx_val
            self._settings.calibration.point1_gy = gy_val
            self._settings.calibration.point1_ix = ix
            self._settings.calibration.point1_iy = iy
            self._calib_step = 1
            self._map_status_label.setText(f"Point 1: game({gx_val:.2f}, {gy_val:.2f}) → img({ix:.1f}, {iy:.1f}). Click point 2.")
        else:
            self._settings.calibration.point2_gx = gx_val
            self._settings.calibration.point2_gy = gy_val
            self._settings.calibration.point2_ix = ix
            self._settings.calibration.point2_iy = iy
            self._graph_renderer.set_calibration(self._settings.calibration)
            self._calibrating = False
            self._calib_step = 0
            self._map_status_label.setText(f"Calibrated: 2 points set")
            self._set_status("Calibration complete", "#4ec9b0")
            self._graph_renderer.render(self._trail.paths, self._trail.pois, preserve_transform=True)

    def _on_flip_y(self, checked: bool) -> None:
        self._graph_renderer.flip_y_map = checked
        self._graph_renderer.render(self._trail.paths, self._trail.pois, preserve_transform=True)
        if self._last_live_x is not None and self._last_live_y is not None:
            self._graph_renderer.update_live_marker(self._last_live_x, self._last_live_y, instant=True)
            if self._recording and self._auto_follow_check.isChecked() and self._last_live_x is not None:
                self._graph_renderer.center_on_position(self._last_live_x, self._last_live_y)

    def _on_flip_x(self, checked: bool) -> None:
        self._graph_renderer.flip_x_map = checked
        self._graph_renderer.render(self._trail.paths, self._trail.pois, preserve_transform=True)
        if self._last_live_x is not None and self._last_live_y is not None:
            self._graph_renderer.update_live_marker(self._last_live_x, self._last_live_y, instant=True)
            if self._recording and self._auto_follow_check.isChecked():
                self._graph_renderer.center_on_position(self._last_live_x, self._last_live_y)

    def _on_auto_follow(self, checked: bool) -> None:
        self._graph_renderer.auto_follow_active = checked

    def _on_zoom_follow(self, checked: bool) -> None:
        self._graph_renderer.follow_zoom_enabled = checked

    def _rebuild_profile_combo(self) -> None:
        current = self._profile_combo.currentText()
        self._profile_combo.blockSignals(True)
        self._profile_combo.clear()
        names = sorted(self._settings.profiles.keys())
        for n in names:
            self._profile_combo.addItem(n)
        if self._settings.active_profile in names:
            self._profile_combo.setCurrentText(self._settings.active_profile)
        elif names:
            self._profile_combo.setCurrentIndex(0)
        self._profile_combo.blockSignals(False)

    def _on_profile_changed(self, name: str) -> None:
        if not name or name not in self._settings.profiles:
            return
        if self._recording:
            self._stop_recording()
        self._settings = _apply_profile(self._settings, name)
        self._sync_ui_from_settings()

    def _on_profile_save(self) -> None:
        text, ok = QInputDialog.getText(
            self, "Save Profile", "Profile name:",
            QLineEdit.Normal, self._profile_combo.currentText()
        )
        if ok and text.strip():
            name = text.strip()
            self._save_current_state_to_settings()
            _save_current_as_profile(self._settings, name)
            self._settings.active_profile = name
            self._rebuild_profile_combo()
            self._profile_combo.setCurrentText(name)
            self._set_status(f"Profile saved: {name}", "#4ec9b0")

    def _on_profile_delete(self) -> None:
        name = self._profile_combo.currentText()
        if not name or name not in self._settings.profiles:
            return
        dlg = ConfirmDialog("Delete Profile", f"Delete profile '{name}'?", self)
        if dlg.exec() == ConfirmDialog.Accepted:
            del self._settings.profiles[name]
            if self._settings.active_profile == name:
                self._settings.active_profile = ""
            self._rebuild_profile_combo()
            self._set_status(f"Profile deleted: {name}", "orange")

    def _sync_ui_from_settings(self) -> None:
        self._proc_name_input.setText(self._settings.process_name)
        self._x_addr_input.setText(self._settings.x_address)
        self._y_addr_input.setText(self._settings.y_address)
        self._interval_input.setValue(self._settings.interval_ms)
        self._graph_renderer.clear_map()
        self._graph_renderer.set_calibration(self._settings.calibration)
        if self._settings.map_path:
            self._graph_renderer.load_map(self._settings.map_path)
            self._graph_renderer.set_calibration(self._settings.calibration)

        old_polling = self._polling
        old_polling.stop()
        old_polling._reader.detach()
        self._reader = MemoryReader(self._settings.process_name)
        self._polling = PollingService(self._reader)
        self._polling.value_read.connect(self._on_value_read)
        self._polling.read_failed.connect(self._on_read_failed)
        self._polling.idle_paused.connect(self._on_idle_paused)
        self._polling.idle_resumed.connect(self._on_idle_resumed)
        old_polling.deleteLater()

        self._graph_renderer.render(self._trail.paths, self._trail.pois, preserve_transform=True)
        self._update_ui_state()

    def _on_smooth(self) -> None:
        epsilon = self._epsilon_input.value()
        self._trail.smooth(epsilon)
        save_trail(self._trail.paths, self._trail.pois)
        self._rebuild_data_list()
        self._graph_renderer.render(self._trail.paths, self._trail.pois, preserve_transform=True)
        self._update_ui_state()
        self._set_status(f"Smoothed (eps={epsilon})", "#4ec9b0")

    def _on_toggle_heat(self) -> None:
        enabled = self._heat_btn.isChecked()
        self._graph_renderer.heat_map_enabled = enabled
        if self._trail.has_data:
            self._graph_renderer.render(self._trail.paths, self._trail.pois, preserve_transform=True)
        self._set_status("Heat map " + ("ON" if enabled else "OFF"), "#4ec9b0")

    def _on_toggle_fade(self, checked: bool) -> None:
        self._graph_renderer.fade_trail_enabled = checked
        if self._trail.has_data:
            self._graph_renderer.render(self._trail.paths, self._trail.pois, preserve_transform=True)
        self._set_status("Fade " + ("ON" if checked else "OFF"), "#4ec9b0")

    def _on_zoom_fit(self) -> None:
        self._graph_renderer.zoom_to_fit()

    def _prompt_poi_with_category(self, x: float, y: float) -> tuple[str, str] | None:
        from PySide6.QtWidgets import QDialog, QFormLayout, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Add POI at ({x:.2f}, {y:.2f})")
        layout = QFormLayout(dlg)
        desc_input = QLineEdit()
        cat_combo = QComboBox()
        categories = ["", "Boss", "Loot", "Entrance", "Danger", "Checkpoint"]
        for c in categories:
            cat_combo.addItem(c if c else "General", c)
        layout.addRow("Description:", desc_input)
        layout.addRow("Category:", cat_combo)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addRow(buttons)
        if dlg.exec() == QDialog.Accepted:
            return desc_input.text(), cat_combo.currentData()
        return None

    def _mark_poi(self) -> None:
        if not self._recording:
            return
        if self._last_live_x is not None and self._last_live_y is not None:
            result = self._prompt_poi_with_category(self._last_live_x, self._last_live_y)
            if result is not None:
                desc, category = result
                self._trail.add_poi(self._last_live_x, self._last_live_y, desc, category)
                save_trail(self._trail.paths, self._trail.pois)
                self._rebuild_data_list()
                self._graph_renderer.render(
                    self._trail.paths, self._trail.pois, preserve_transform=True
                )
                self._graph_renderer.note_paths_for_poi_highlights(self._trail.paths)

    def _on_value_read(self, x: float, y: float) -> None:
        self._last_live_x = x
        self._last_live_y = y

        if not is_suspicious(x) and not is_suspicious(y):
            self._live_x_label.setText(f"X: {x:.4f}")
            self._live_y_label.setText(f"Y: {y:.4f}")
        else:
            self._live_x_label.setText(f"X: {x:.4f} (!)")
            self._live_y_label.setText(f"Y: {y:.4f} (!)")
            self._set_status("Suspicious values - check addresses", "red")

        snap_marker = False
        if self._recording and not is_suspicious(x) and not is_suspicious(y):
            prev_path_count = len(self._trail.paths)
            added = self._trail.add(x, y)
            if added:
                prev = self._last_recorded_pos
                if prev is not None:
                    dx = x - prev[0]
                    dy = y - prev[1]
                    self._total_dist += math.sqrt(dx * dx + dy * dy)
                self._last_recorded_pos = (x, y)
                pt = self._trail.paths[-1][-1]
                path_idx = len(self._trail.paths) - 1
                self._append_point_item(path_idx, len(self._trail.paths[-1]) - 1, pt)
                self._data_list.scrollToBottom()
                start_new = len(self._trail.paths) > prev_path_count
                snap_marker = start_new
                if not self._graph_renderer._tc.is_valid():
                    self._graph_renderer.render(self._trail.paths, self._trail.pois, preserve_transform=True)
                self._graph_renderer.note_paths_for_poi_highlights(self._trail.paths)
                self._graph_renderer.add_trail_point(x, y, start_new_path=start_new)
            elapsed = time.monotonic() - self._recording_start
            speed = self._total_dist / max(0.1, elapsed)
            point_count = sum(len(p) for p in self._trail.paths)
            self._graph_renderer.update_stats(elapsed, point_count, self._total_dist, speed)

        self._graph_renderer.update_live_marker(x, y, instant=snap_marker)

    def _on_read_failed(self) -> None:
        if self._recording:
            err = self._reader._last_error
            self._set_status(f"Cannot read memory at these addresses (error {err})", "red")

    def _on_interval_changed(self, val: int) -> None:
        if self._recording and self._polling.is_running:
            self._polling._timer.setInterval(val)
            self._on_idle_threshold_changed(self._idle_threshold_spin.value())

    def _on_teleport_changed(self, val: float) -> None:
        if self._recording:
            self._trail.teleport_threshold = val

    def _on_idle_threshold_changed(self, val: float) -> None:
        threshold_ticks = int(val * 1000 / max(1, self._interval_input.value()))
        self._polling.idle_threshold = threshold_ticks

    def _on_idle_paused(self) -> None:
        self._set_status("Idle - paused", "orange")

    def _on_idle_resumed(self) -> None:
        self._set_status("Recording...", "#4ec9b0")

    def _on_clear(self) -> None:
        if not self._trail.has_data:
            return
        dlg = ConfirmDialog("Clear Data", "Clear all recorded data?", self)
        if dlg.exec() == ConfirmDialog.Accepted:
            self._polling.stop()
            self._trail.clear()
            self._recording = False
            self._graph_renderer.hide_stats()
            self._rebuild_data_list()
            self._graph_renderer.render([], [])
            self._graph_renderer.set_live_marker_visible(False)
            self._graph_renderer.clear_selection()
            self._update_ui_state()
            self._set_status("Idle", "gray")
            from settings_service import TRAIL_PATH
            try:
                if TRAIL_PATH.exists():
                    TRAIL_PATH.unlink()
            except Exception:
                pass

    def _on_import(self) -> None:
        if self._recording:
            QMessageBox.warning(self, "Warning", "Stop recording before importing.")
            return

        path, _ = QFileDialog.getOpenFileName(
            self, "Import Trails", "", "Text files (*.txt);;All files (*)"
        )
        if not path:
            return

        try:
            result = import_text(path)
            self._trail.load(result.paths, result.pois)
            save_trail(self._trail.paths, self._trail.pois)
            self._rebuild_data_list()
            self._render_trail(refit_view=True)
            self._graph_renderer.zoom_to_fit()
            self._update_ui_state()
            self._set_status(f"Imported from {path}", "#4ec9b0")
        except Exception as e:
            QMessageBox.critical(self, "Import Error", str(e))

    def _on_export_txt(self) -> None:
        if not self._trail.has_data:
            QMessageBox.warning(self, "Warning", "No data to export.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Export Trails", "trail.txt", "Text files (*.txt);;All files (*)"
        )
        if not path:
            return

        try:
            export_text(self._trail.paths, self._trail.pois, path)
            self._set_status(f"Exported to {path}", "#4ec9b0")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))

    def _on_export_png(self) -> None:
        if not self._trail.has_data:
            QMessageBox.warning(self, "Warning", "No data to export.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Export PNG", "trail.png", "PNG images (*.png);;All files (*)"
        )
        if not path:
            return

        try:
            self._graph_renderer.set_live_marker_visible(False)
            w = self._graph_view.width()
            h = self._graph_view.height()
            export_png(self._graph_renderer.scene, path, w * 2, h * 2)
            self._graph_renderer.set_live_marker_visible(
                self._last_live_x is not None
            )
            self._set_status(f"PNG saved to {path}", "#4ec9b0")
        except Exception as e:
            self._graph_renderer.set_live_marker_visible(
                self._last_live_x is not None
            )
            QMessageBox.critical(self, "Export Error", str(e))

    def _on_data_selection_changed(self, current: QListWidgetItem, previous) -> None:
        if current is None:
            self._graph_renderer.clear_selection()
            return
        kind = current.data(KIND_ROLE)
        a = current.data(A_ROLE)
        b = current.data(B_ROLE)

        if kind == ROW_KIND_POINT:
            self._graph_renderer.select_point(a, b, self._trail.paths)
            if 0 <= a < len(self._trail.paths):
                path = self._trail.paths[a]
                if 0 <= b < len(path):
                    pt = path[b]
                    self._graph_renderer.center_on_position(pt.x, pt.y)
        elif kind == ROW_KIND_POI:
            self._graph_renderer.select_poi(a, self._trail.pois)
            if 0 <= a < len(self._trail.pois):
                poi = self._trail.pois[a]
                self._graph_renderer.center_on_position(poi.x, poi.y)
        else:
            self._graph_renderer.clear_selection()

    def _on_data_context_menu(self, pos) -> None:
        item = self._data_list.itemAt(pos)
        if item is None:
            return
        kind = item.data(KIND_ROLE)
        if kind not in (ROW_KIND_POINT, ROW_KIND_POI):
            return
        a = item.data(A_ROLE)
        b = item.data(B_ROLE)

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2d2d2d;
                color: #dcdcdc;
                border: 1px solid #555;
            }
            QMenu::item:selected {
                background-color: #094771;
            }
        """)
        go_action = menu.addAction("Go To")
        menu.addSeparator()
        if kind == ROW_KIND_POI:
            edit_action = menu.addAction("Edit Description")
            menu.addSeparator()
        else:
            edit_action = None
        delete_action = menu.addAction("Delete")
        chosen = menu.exec(self._data_list.mapToGlobal(pos))
        if chosen == go_action:
            if kind == ROW_KIND_POI and 0 <= a < len(self._trail.pois):
                poi = self._trail.pois[a]
                self._graph_renderer.center_on_position(poi.x, poi.y)
            elif kind == ROW_KIND_POINT and 0 <= a < len(self._trail.paths):
                path = self._trail.paths[a]
                if 0 <= b < len(path):
                    x, y = path[b]
                    self._graph_renderer.center_on_position(x, y)
        elif edit_action is not None and chosen == edit_action:
            self._edit_poi_description(a)
        elif chosen == delete_action:
            self._delete_item(item)

    def _edit_poi_description(self, idx: int) -> None:
        if not (0 <= idx < len(self._trail.pois)):
            return
        poi = self._trail.pois[idx]
        from PySide6.QtWidgets import QDialog, QFormLayout, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Edit POI at ({poi.x:.2f}, {poi.y:.2f})")
        layout = QFormLayout(dlg)
        desc_input = QLineEdit(poi.desc)
        cat_combo = QComboBox()
        categories = ["", "Boss", "Loot", "Entrance", "Danger", "Checkpoint"]
        for c in categories:
            cat_combo.addItem(c if c else "General", c)
        idx_cat = max(0, next((i for i, c in enumerate(categories) if c == poi.category), 0))
        cat_combo.setCurrentIndex(idx_cat)
        layout.addRow("Description:", desc_input)
        layout.addRow("Category:", cat_combo)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addRow(buttons)
        if dlg.exec() == QDialog.Accepted:
            self._trail.update_poi(idx, poi.x, poi.y, desc_input.text(), cat_combo.currentData())
            save_trail(self._trail.paths, self._trail.pois)
            self._rebuild_data_list()
            self._graph_renderer.render(
                self._trail.paths, self._trail.pois, preserve_transform=True
            )

    def _delete_item(self, item: QListWidgetItem) -> None:
        kind = item.data(KIND_ROLE)
        a = item.data(A_ROLE)
        b = item.data(B_ROLE)

        if kind == ROW_KIND_POINT:
            dlg = ConfirmDialog("Delete Point", "Delete this point?", self)
            if dlg.exec() == ConfirmDialog.Accepted:
                self._trail.remove_point(a, b)
                save_trail(self._trail.paths, self._trail.pois)
                self._rebuild_data_list()
                self._graph_renderer.render(
                    self._trail.paths, self._trail.pois, preserve_transform=True
                )
                self._update_ui_state()
        elif kind == ROW_KIND_POI:
            dlg = ConfirmDialog("Delete POI", "Delete this POI?", self)
            if dlg.exec() == ConfirmDialog.Accepted:
                self._trail.remove_poi(a)
                save_trail(self._trail.paths, self._trail.pois)
                self._rebuild_data_list()
                self._graph_renderer.render(
                    self._trail.paths, self._trail.pois, preserve_transform=True
                )
                self._update_ui_state()

    def eventFilter(self, obj, event) -> bool:
        if obj == self._data_list and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Backspace or event.key() == Qt.Key_Delete:
                item = self._data_list.currentItem()
                if item:
                    self._delete_item(item)
                return True
        if obj == self._graph_view.viewport() and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
                idx = self._graph_renderer.selected_poi_index()
                if idx is not None:
                    self._delete_poi_by_index(idx)
                    return True
        if obj == self._graph_view.viewport() and event.type() == QEvent.MouseButtonDblClick:
            self._on_graph_double_click_core(event)
            return True
        return super().eventFilter(obj, event)

    def _rebuild_data_list(self) -> None:
        self._data_list.clear()

        for path_idx, path in enumerate(self._trail.paths):
            if not path:
                continue
            if path_idx > 0:
                sep = QListWidgetItem("— new path —")
                sep.setFlags(sep.flags() & ~Qt.ItemIsSelectable)
                sep.setForeground(Qt.gray)
                self._data_list.addItem(sep)

            for pt_idx, pt in enumerate(path):
                self._append_point_item(path_idx, pt_idx, pt)

        if self._trail.pois:
            for poi_idx, poi in enumerate(self._trail.pois):
                cat_tag = f"[{poi.category}] " if poi.category else ""
                item = QListWidgetItem(f"📍 {cat_tag}{poi.format()}")
                item.setData(KIND_ROLE, ROW_KIND_POI)
                item.setData(A_ROLE, poi_idx)
                item.setData(B_ROLE, -1)
                self._data_list.addItem(item)

    def _append_point_item(self, path_idx: int, pt_idx: int, pt: TrailPoint) -> None:
        item = QListWidgetItem(pt.format())
        item.setData(KIND_ROLE, ROW_KIND_POINT)
        item.setData(A_ROLE, path_idx)
        item.setData(B_ROLE, pt_idx)
        self._data_list.addItem(item)

    def _save_current_state_to_settings(self) -> None:
        self._settings.process_name = self._proc_name_input.text().strip() or "Exanima.exe"
        self._settings.x_address = self._x_addr_input.text().strip()
        self._settings.y_address = self._y_addr_input.text().strip()
        self._settings.interval_ms = self._interval_input.value()
        self._settings.map_path = ""
        if self._graph_renderer.has_map:
            pm = self._graph_renderer._map_pixmap
            if pm and not pm.isNull():
                map_dir = SETTINGS_DIR / "maps"
                map_dir.mkdir(parents=True, exist_ok=True)
                map_path = map_dir / "current_map.png"
                if not pm.save(str(map_path)):
                    import sys
                    print("Failed to save map image", file=sys.stderr)
                else:
                    self._settings.map_path = str(map_path)

    def _update_ui_state(self) -> None:
        is_recording = self._recording
        has_data = self._trail.has_data

        self._proc_name_input.setEnabled(not is_recording)
        self._x_addr_input.setEnabled(not is_recording)
        self._y_addr_input.setEnabled(not is_recording)
        self._interval_input.setEnabled(not self._calibrating)
        self._smooth_btn.setEnabled(has_data and not is_recording)
        self._heat_btn.setEnabled(has_data)
        self._fade_trail_check.setEnabled(has_data)
        self._zoom_fit_btn.setEnabled(has_data or self._graph_renderer.has_map)
        self._load_map_btn.setEnabled(not is_recording and not self._calibrating)
        self._clear_map_btn.setEnabled(
            not is_recording and not self._calibrating and self._graph_renderer.has_map
        )
        self._calibrate_btn.setEnabled(
            not is_recording and self._graph_renderer.has_map and not self._calibrating
        )
        self._flip_y_check.setEnabled(not self._calibrating)
        self._flip_x_check.setEnabled(not self._calibrating)
        self._auto_follow_check.setEnabled(is_recording)
        self._zoom_follow_check.setEnabled(is_recording)
        self._teleport_input.setEnabled(not self._calibrating)
        self._epsilon_input.setEnabled(not is_recording)
        self._idle_threshold_spin.setEnabled(is_recording)

        if is_recording:
            self._start_btn.setText("Stop (F8)")
            self._mark_poi_btn.setEnabled(True)
        elif has_data:
            self._start_btn.setText("Resume (F8)")
            self._mark_poi_btn.setEnabled(False)
        else:
            self._start_btn.setText("Start (F8)")
            self._mark_poi_btn.setEnabled(False)

        self._clear_btn.setEnabled(has_data)

    def _set_status(self, text: str, color: str = "gray") -> None:
        self._status_label.setText(f"Status: {text}")
        self._status_label.setStyleSheet(f"color: {color};")

    def closeEvent(self, event) -> None:
        self._polling.stop()
        self._reader.detach()

        if self._hotkey_service:
            self._hotkey_service.dispose()

        self._save_current_state_to_settings()
        save_settings(self._settings)
        save_trail(self._trail.paths, self._trail.pois)

        super().closeEvent(event)
