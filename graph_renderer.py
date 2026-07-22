from __future__ import annotations
import math
import time

from PySide6.QtCore import Qt, QRectF, QPointF, QTimer, QObject, Signal
from PySide6.QtGui import (
    QColor,
    QPen,
    QBrush,
    QPainterPath,
    QPainter,
    QPixmap,
    QImage,
    QFont,
    QFontMetrics,
    QTransform,
    qAlpha,
    qRgba,
)
from PySide6.QtWidgets import (
    QGraphicsScene,
    QGraphicsView,
    QGraphicsPathItem,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsTextItem,
    QLabel,
)

from settings_service import MapCalibration
from trail_model import POI, MIN_DISTANCE


FOLLOW_ZOOM_INTERVAL = 0.05
FOLLOW_ZOOM_COMFORT = 0.50
FOLLOW_ZOOM_MIN_EXTENT = 280.0
FOLLOW_ZOOM_MAX_EXTENT = 1100.0
FOLLOW_RECENTER_PADDING = 1.35
FOLLOW_ZOOM_TRAIL_PAD = 1.85
FOLLOW_IDLE_SEC = 0.35
FOLLOW_MOVE_THRESH_GAME = 12.0
POI_POLAR_BINS = 40
POI_BIN_DIST_SLACK = 1.1
POI_BIN_DIST_ADD = MIN_DISTANCE * 0.25
POI_MARKER_RADIUS_PX = 14.0
LIVE_BOOTSTRAP_PAD = 400.0
PADDING = 20.0
PATH_COLORS = [
    QColor(0x4A, 0x7B, 0xBF),
    QColor(0xCC, 0x33, 0x33),
    QColor(0x33, 0xCC, 0x33),
    QColor(0xCC, 0x99, 0x33),
    QColor(0x99, 0x33, 0xCC),
    QColor(0x33, 0xCC, 0xCC),
    QColor(0xCC, 0x33, 0x99),
    QColor(0x99, 0xCC, 0x33),
    QColor(0x33, 0x66, 0x99),
    QColor(0xFF, 0x66, 0x00),
]
DOT_PEN = QPen(Qt.NoPen)
DOT_BRUSH = QBrush(QColor(0x4A, 0x7B, 0xBF))
LATEST_PEN = QPen(Qt.NoPen)
LATEST_BRUSH = QBrush(QColor(0xB2, 0x22, 0x22))
POI_PEN = QPen(QColor(0xCC, 0x33, 0x33), 2.0)
POI_BRUSH = QBrush(Qt.NoBrush)
SELECTION_PEN = QPen(Qt.NoPen)
SELECTION_BRUSH = QBrush(QColor(0x32, 0xCD, 0x32))
LIVE_PEN = QPen(Qt.NoPen)
LIVE_BRUSH = QBrush(QColor(0xCC, 0x33, 0x33))
BG_COLOR = QColor(0x1E, 0x1E, 0x1E)

POI_CATEGORY_COLORS: dict[str, QColor] = {
    "Boss": QColor(0xFF, 0x44, 0x44),
    "Loot": QColor(0xFF, 0xCC, 0x00),
    "Entrance": QColor(0x44, 0xCC, 0xFF),
    "Danger": QColor(0xFF, 0x88, 0x00),
    "Checkpoint": QColor(0x66, 0xFF, 0x66),
}

def _poi_category_color(category: str) -> QColor:
    return POI_CATEGORY_COLORS.get(category, QColor(0xFF, 0xCC, 0x00))

def _heat_color(val: int) -> QRgb:
    t = val / 255.0
    if t < 0.25:
        r2 = 0
        g2 = int(t * 4 * 255)
        b2 = 255
    elif t < 0.5:
        r2 = 0
        g2 = 255
        b2 = int((1.0 - (t - 0.25) * 4) * 255)
    elif t < 0.75:
        r2 = int((t - 0.5) * 4 * 255)
        g2 = 255
        b2 = 0
    else:
        r2 = 255
        g2 = int((1.0 - (t - 0.75) * 4) * 255)
        b2 = 0
    return qRgba(r2, g2, b2, min(255, val + 60))


def _path_color(index: int) -> QPen:
    c = PATH_COLORS[index % len(PATH_COLORS)]
    return QPen(c, 1.5, Qt.SolidLine)


def _init_trail_path_item(item: QGraphicsPathItem) -> None:
    item.setZValue(4)


def _dist_sq_point_to_segment(
    px: float, py: float, x1: float, y1: float, x2: float, y2: float
) -> float:
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        ddx = px - x1
        ddy = py - y1
        return ddx * ddx + ddy * ddy
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    cx = x1 + t * dx
    cy = y1 + t * dy
    ddx = px - cx
    ddy = py - cy
    return ddx * ddx + ddy * ddy


def _path_gap(verts: list[tuple[float, float]]) -> float:
    if len(verts) < 2:
        return float("inf")
    dx = verts[0][0] - verts[-1][0]
    dy = verts[0][1] - verts[-1][1]
    return math.sqrt(dx * dx + dy * dy)


def _path_perimeter(verts: list[tuple[float, float]]) -> float:
    total = 0.0
    for i in range(len(verts) - 1):
        dx = verts[i + 1][0] - verts[i][0]
        dy = verts[i + 1][1] - verts[i][1]
        total += math.sqrt(dx * dx + dy * dy)
    return total


def _closest_point_on_segment(
    px: float, py: float, x1: float, y1: float, x2: float, y2: float
) -> tuple[float, float, float]:
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        d = math.hypot(px - x1, py - y1)
        return x1, y1, d
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    cx = x1 + t * dx
    cy = y1 + t * dy
    return cx, cy, math.hypot(px - cx, py - cy)


def _polar_bin_index(poi_x: float, poi_y: float, cx: float, cy: float) -> int:
    ang = math.atan2(cy - poi_y, cx - poi_x)
    if ang < 0:
        ang += 2 * math.pi
    return int(ang / (2 * math.pi) * POI_POLAR_BINS) % POI_POLAR_BINS


def _poi_polar_nearest_segment_pick(
    poi_x: float,
    poi_y: float,
    verts: list[tuple[float, float]],
    extra_seg: tuple[float, float, float, float] | None = None,
) -> tuple[set[int], bool, bool]:
    """
    Per direction around POI, only segments near the closest line in that wedge
    (farther lines in the same direction stay un-painted).
    """
    nseg = len(verts) - 1
    if nseg < 1 and extra_seg is None:
        return set(), False, False

    bins: dict[int, list[tuple[str, int, float]]] = {}

    def _add(seg_kind: str, seg_i: int, x1: float, y1: float, x2: float, y2: float) -> None:
        cx, cy, d = _closest_point_on_segment(poi_x, poi_y, x1, y1, x2, y2)
        b = _polar_bin_index(poi_x, poi_y, cx, cy)
        bins.setdefault(b, []).append((seg_kind, seg_i, d))

    for i in range(nseg):
        gx1, gy1 = verts[i]
        gx2, gy2 = verts[i + 1]
        _add("path", i, gx1, gy1, gx2, gy2)

    if len(verts) >= 3:
        perim = _path_perimeter(verts)
        gap = _path_gap(verts)
        if gap <= perim * 0.28:
            _add("close", -1, verts[-1][0], verts[-1][1], verts[0][0], verts[0][1])

    if extra_seg is not None:
        _add("extra", -2, extra_seg[0], extra_seg[1], extra_seg[2], extra_seg[3])

    chosen: set[int] = set()
    draw_close = False
    draw_extra = False
    for items in bins.values():
        d_min = min(d for _, _, d in items)
        cap = d_min * POI_BIN_DIST_SLACK + POI_BIN_DIST_ADD
        for kind, idx, d in items:
            if d > cap:
                continue
            if kind == "path":
                chosen.add(idx)
            elif kind == "close":
                draw_close = True
            elif kind == "extra":
                draw_extra = True
    return chosen, draw_close, draw_extra


def _highlight_poi_polar_nearest(
    poi_x: float,
    poi_y: float,
    verts: list[tuple[float, float]],
    game_to_screen,
    pen: QPen,
    _highlight_segment,
    extra_seg: tuple[float, float, float, float] | None = None,
) -> int:
    chosen, draw_close, draw_extra = _poi_polar_nearest_segment_pick(
        poi_x, poi_y, verts, extra_seg
    )
    count = 0
    for i in sorted(chosen):
        gx1, gy1 = verts[i]
        gx2, gy2 = verts[i + 1]
        sx1, sy1 = game_to_screen(gx1, gy1)
        sx2, sy2 = game_to_screen(gx2, gy2)
        _highlight_segment(sx1, sy1, sx2, sy2, pen)
        count += 1
    if draw_close and len(verts) >= 2:
        gx1, gy1 = verts[-1]
        gx2, gy2 = verts[0]
        sx1, sy1 = game_to_screen(gx1, gy1)
        sx2, sy2 = game_to_screen(gx2, gy2)
        _highlight_segment(sx1, sy1, sx2, sy2, pen)
        count += 1
    if draw_extra and extra_seg is not None:
        sx1, sy1 = game_to_screen(extra_seg[0], extra_seg[1])
        sx2, sy2 = game_to_screen(extra_seg[2], extra_seg[3])
        _highlight_segment(sx1, sy1, sx2, sy2, pen)
        count += 1
    return count


class PoiMarkerItem(QGraphicsEllipseItem):
    def __init__(
        self,
        poi_idx: int,
        renderer,
        sx: float,
        sy: float,
        cat_color: QColor,
        label: str,
    ):
        r = POI_MARKER_RADIUS_PX
        super().__init__(-r, -r, r * 2, r * 2)
        self._poi_idx = poi_idx
        self._renderer = renderer
        self.setPos(sx, sy)
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations)
        ring = QPen(cat_color, 3.0, Qt.SolidLine)
        ring.setCosmetic(True)
        self.setPen(ring)
        self.setBrush(Qt.NoBrush)
        self.setZValue(6)
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        inner = QGraphicsEllipseItem(-5, -5, 10, 10, self)
        inner.setPen(Qt.NoPen)
        inner.setBrush(QBrush(cat_color))
        inner.setFlag(QGraphicsItem.ItemIgnoresTransformations)
        self._label = QGraphicsTextItem(label)
        self._label.setDefaultTextColor(cat_color)
        self._label.setFont(QFont("Consolas", 9))
        self._label.setParentItem(self)
        self._label.setFlag(QGraphicsItem.ItemIgnoresTransformations)
        self._label.setPos(r + 4, -8)

    def poi_index(self) -> int:
        return self._poi_idx

    def mousePressEvent(self, event) -> None:
        self._renderer.set_selected_poi(self._poi_idx)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        if event.button() == Qt.LeftButton:
            self._renderer._on_poi_drag_finished(self._poi_idx)

    def contextMenuEvent(self, event) -> None:
        self._renderer._on_poi_context_menu(self._poi_idx, event.screenPos())


class TransformCache:
    def __init__(self):
        self.scale = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.min_x = 0.0
        self.max_x = 0.0
        self.max_y = 0.0
        self.min_y = 0.0
        self.flip_y_map = False
        self.flip_x_map = False
        self.map_mode = False
        self.cal_sx = 1.0
        self.cal_sy = 1.0
        self.cal_ox = 0.0
        self.cal_oy = 0.0
        self._valid = False

    def is_valid(self) -> bool:
        return self._valid

    def game_to_screen(self, x: float, y: float) -> tuple[float, float]:
        if self.map_mode:
            ix = x * self.cal_sx + self.cal_ox
            iy = y * self.cal_sy + self.cal_oy
            sx = self.offset_x + ix * self.scale * (-1.0 if self.flip_x_map else 1.0)
            sy = self.offset_y + iy * self.scale * (-1.0 if self.flip_y_map else 1.0)
        else:
            if self.flip_y_map:
                sy = y - self.min_y
            else:
                sy = self.max_y - y
            sx = x
            if self.flip_x_map:
                mid_x = (self.min_x + self.max_x) * 0.5
                sx = 2.0 * mid_x - x
        return sx, sy

    def screen_to_game(self, sx: float, sy: float) -> tuple[float, float]:
        if self.map_mode:
            ix = (sx - self.offset_x) / self.scale * (-1.0 if self.flip_x_map else 1.0)
            iy = (sy - self.offset_y) / self.scale * (-1.0 if self.flip_y_map else 1.0)
            gx = (ix - self.cal_ox) / self.cal_sx if self.cal_sx != 0 else ix
            gy = (iy - self.cal_oy) / self.cal_sy if self.cal_sy != 0 else iy
        else:
            gx = sx
            if self.flip_x_map:
                mid_x = (self.min_x + self.max_x) * 0.5
                gx = 2.0 * mid_x - sx
            if self.flip_y_map:
                gy = sy + self.min_y
            else:
                gy = self.max_y - sy
        return gx, gy


class GraphRenderer(QObject):
    poi_moved = Signal(int, float, float)
    poi_edit_requested = Signal(int)
    poi_delete_requested = Signal(int)
    bounds_expanded = Signal()

    def __init__(self, view: QGraphicsView):
        super().__init__()
        self._view = view
        self._scene = QGraphicsScene(view)
        self._scene.setBackgroundBrush(BG_COLOR)
        view.setScene(self._scene)
        view.setRenderHint(QPainter.Antialiasing)
        view.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        view.setDragMode(QGraphicsView.ScrollHandDrag)
        view.setTransformationAnchor(QGraphicsView.NoAnchor)
        view.setResizeAnchor(QGraphicsView.NoAnchor)

        view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self._live_marker = QGraphicsEllipseItem(-3, -3, 6, 6)
        self._live_marker.setPen(LIVE_PEN)
        self._live_marker.setBrush(LIVE_BRUSH)
        self._live_marker.setVisible(False)
        self._live_marker.setFlag(QGraphicsItem.ItemIgnoresTransformations)
        self._scene.addItem(self._live_marker)

        self._map_item: QGraphicsPixmapItem | None = None
        self._map_pixmap: QPixmap | None = None

        self._path_items: list[QGraphicsPathItem] = []
        self._dot_items: list[QGraphicsEllipseItem] = []
        self._dot_group: QGraphicsPathItem | None = None
        self._heat_group: QGraphicsItem | None = None
        self._poi_group: QGraphicsItem | None = None
        self._poi_text_items: list[QGraphicsTextItem] = []
        self._poi_ring_items: list[QGraphicsEllipseItem] = []
        self._poi_marker_items: list[PoiMarkerItem] = []
        self._poi_highlight_items: list[QGraphicsPathItem] = []
        self._selected_poi_idx: int | None = None
        self._cached_paths: list = []
        self._cached_pois: list = []
        self._suppress_bounds_signal = False
        self._selection_item: QGraphicsEllipseItem | None = None

        self._tc = TransformCache()
        self._auto_fit_max_y: float | None = None
        self._calib_sx = 1.0
        self._calib_sy = 1.0
        self._calib_ox = 0.0
        self._calib_oy = 0.0
        self._calib_valid = False
        self._heat_map_enabled = False
        self._auto_center_enabled = True
        self._flip_y_map = False
        self._flip_x_map = False
        self._stats_label: QLabel | None = None
        self._fade_trail_enabled = False

        self._follow_timer = QTimer(self)
        self._follow_timer.setInterval(16)
        self._follow_timer.timeout.connect(self._follow_tick)

        self._follow_active = False
        self._follow_zoom_enabled = False
        self._last_game_pos: tuple[float, float] | None = None
        self._smooth_marker_target: QPointF | None = None
        self._smooth_marker_speed: float = 50.0
        self._smooth_marker_time: float = 0.0
        self._follow_last_mono: float = time.monotonic()
        self._zoom_follow_last_mono: float = 0.0
        self._last_marker_move_time: float = time.monotonic()
        self._follow_paused_by_user: bool = False
        self._view_drag_active: bool = False
        self._poi_highlight_live_pos: tuple[float, float] | None = None
        self._prev_follow_game_pos: tuple[float, float] | None = None
        self._incr_prev: tuple[float, float] | None = None
        self._incr_path_count: int = 0
        self._active_path: QPainterPath | None = None
        self._active_path_item: QGraphicsPathItem | None = None
        self._trail_pts: list[tuple[float, float]] = []
        self._tail_line_item = QGraphicsPathItem()
        self._tail_line_item.setPen(_path_color(0))
        self._tail_line_item.setZValue(4)
        self._tail_line_item.setVisible(False)
        self._scene.addItem(self._tail_line_item)

        self._live_dot_path = QPainterPath()
        self._live_dot_item = QGraphicsPathItem(self._live_dot_path)
        self._live_dot_item.setPen(Qt.NoPen)
        self._live_dot_item.setBrush(DOT_BRUSH)
        self._live_dot_item.setZValue(1)
        self._scene.addItem(self._live_dot_item)

        self._follow_timer.start()
        view.viewport().installEventFilter(self)

    @property
    def scene(self) -> QGraphicsScene:
        return self._scene

    @property
    def has_map(self) -> bool:
        return self._map_pixmap is not None

    @property
    def heat_map_enabled(self) -> bool:
        return self._heat_map_enabled

    @heat_map_enabled.setter
    def heat_map_enabled(self, val: bool) -> None:
        self._heat_map_enabled = val

    @property
    def flip_y_map(self) -> bool:
        return self._flip_y_map

    @flip_y_map.setter
    def flip_y_map(self, val: bool) -> None:
        self._flip_y_map = val
        self._tc.flip_y_map = val

    @property
    def flip_x_map(self) -> bool:
        return self._flip_x_map

    @flip_x_map.setter
    def flip_x_map(self, val: bool) -> None:
        self._flip_x_map = val
        self._tc.flip_x_map = val

    @property
    def fade_trail_enabled(self) -> bool:
        return self._fade_trail_enabled

    @fade_trail_enabled.setter
    def fade_trail_enabled(self, val: bool) -> None:
        self._fade_trail_enabled = val

    @property
    def auto_follow_active(self) -> bool:
        return self._follow_active

    @auto_follow_active.setter
    def auto_follow_active(self, val: bool) -> None:
        self._follow_active = val
        if val:
            self._follow_paused_by_user = False

    @property
    def follow_zoom_enabled(self) -> bool:
        return self._follow_zoom_enabled

    @follow_zoom_enabled.setter
    def follow_zoom_enabled(self, val: bool) -> None:
        self._follow_zoom_enabled = val
        if val:
            self._follow_paused_by_user = False

    def zoom_to_fit(self) -> None:
        rect = self._scene.itemsBoundingRect()
        if rect.isValid() and not rect.isEmpty():
            min_size = 600.0
            if rect.width() < min_size:
                pad = (min_size - rect.width()) / 2
                rect = rect.adjusted(-pad, 0, pad, 0)
            if rect.height() < min_size:
                pad = (min_size - rect.height()) / 2
                rect = rect.adjusted(0, -pad, 0, pad)
            self._view.fitInView(rect, Qt.KeepAspectRatio)

    def _visible_scene_rect(self) -> QRectF:
        return self._view.mapToScene(self._view.viewport().rect()).boundingRect()

    def center_on_position(self, x: float, y: float) -> None:
        if not self._tc.is_valid():
            return
        sx, sy = self._tc.game_to_screen(x, y)
        self._view.centerOn(sx, sy)

    def eventFilter(self, obj, event) -> bool:
        try:
            vp = self._view.viewport()
        except RuntimeError:
            return False
        if obj is vp and event.type() == event.Type.Wheel:
            modifiers = event.modifiers()
            if modifiers & Qt.ControlModifier:
                factor = 1.15
                if event.angleDelta().y() > 0:
                    self._view.scale(factor, factor)
                else:
                    self._view.scale(1 / factor, 1 / factor)
                return True
            elif self._follow_active or self._follow_zoom_enabled:
                self._follow_paused_by_user = True
        if obj is vp and event.type() == event.Type.MouseButtonPress:
            if event.button() == Qt.LeftButton:
                self._view_drag_active = True
                if self._follow_active or self._follow_zoom_enabled:
                    self._follow_paused_by_user = True
        if obj is vp and event.type() == event.Type.MouseButtonRelease:
            if event.button() == Qt.LeftButton:
                self._view_drag_active = False
        return super().eventFilter(obj, event)

    def load_map(self, path: str) -> None:
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return
        self.clear_map()
        self._map_pixmap = pixmap
        self._map_item = QGraphicsPixmapItem(pixmap)
        self._map_item.setZValue(-100)
        self._scene.addItem(self._map_item)

    def clear_map(self) -> None:
        if self._map_item:
            self._scene.removeItem(self._map_item)
            self._map_item = None
        self._map_pixmap = None
        self._calib_valid = False

    def set_calibration(self, calib: MapCalibration) -> None:
        if not calib.is_complete():
            self._calib_valid = False
            return
        dx_g = calib.point2_gx - calib.point1_gx
        dy_g = calib.point2_gy - calib.point1_gy
        dx_i = calib.point2_ix - calib.point1_ix
        dy_i = calib.point2_iy - calib.point1_iy
        if not math.isfinite(dx_g) or not math.isfinite(dy_g) or not math.isfinite(dx_i) or not math.isfinite(dy_i):
            self._calib_valid = False
            return
        sx = dx_i / dx_g if dx_g != 0 else 1.0
        sy = dy_i / dy_g if dy_g != 0 else 1.0
        ox = calib.point1_ix - calib.point1_gx * sx
        oy = calib.point1_iy - calib.point1_gy * sy
        self._calib_sx = sx
        self._calib_sy = sy
        self._calib_ox = ox
        self._calib_oy = oy
        self._calib_valid = True

    def game_to_img(self, x: float, y: float) -> tuple[float, float]:
        if not self._calib_valid:
            return (x, y)
        return (
            x * self._calib_sx + self._calib_ox,
            y * self._calib_sy + self._calib_oy,
        )

    def _clear_render_items(self) -> None:
        for item in self._path_items:
            self._scene.removeItem(item)
        self._path_items.clear()
        for item in self._dot_items:
            self._scene.removeItem(item)
        self._dot_items.clear()
        if self._heat_group:
            self._scene.removeItem(self._heat_group)
            self._heat_group = None
        if self._poi_group:
            self._scene.removeItem(self._poi_group)
            self._poi_group = None
        for item in self._poi_ring_items:
            self._scene.removeItem(item)
        self._poi_ring_items.clear()
        for item in self._poi_marker_items:
            self._scene.removeItem(item)
        self._poi_marker_items.clear()
        for item in self._poi_highlight_items:
            self._scene.removeItem(item)
        self._poi_highlight_items.clear()
        for item in self._poi_text_items:
            self._scene.removeItem(item)
        self._poi_text_items.clear()
        if self._dot_group:
            self._scene.removeItem(self._dot_group)
            self._dot_group = None
        if self._active_path_item:
            self._scene.removeItem(self._active_path_item)
            self._active_path_item = None
        self._active_path = None
        self._tail_line_item.setPath(QPainterPath())
        self._tail_line_item.setVisible(False)
        self._live_dot_path = QPainterPath()
        self._live_dot_item.setPath(self._live_dot_path)
        self._incr_prev = None
        self._incr_path_count = 0
        self._trail_pts.clear()
        self.clear_selection()

    def render(self, paths: list[list[tuple[float, float]]], pois: list, preserve_transform: bool = False) -> None:
        if not preserve_transform:
            self._view.resetTransform()
            self._auto_fit_max_y = None
        self._clear_render_items()

        if self._calib_valid and self._map_pixmap:
            self._render_map_mode(paths, pois, preserve_transform)
        else:
            self._render_auto_fit(paths, pois, preserve_transform)

        if self._heat_map_enabled:
            self._render_heat_map(paths)

        self._cached_paths = paths
        self._cached_pois = list(pois)
        self._render_poi_segment_highlights(paths, pois)

        self._sync_incremental_from_paths(paths)

        if self._last_game_pos is not None and self._tc.is_valid():
            sx, sy = self._tc.game_to_screen(*self._last_game_pos)
            self._live_marker.setVisible(True)
            self.set_smooth_marker_target(sx, sy, instant=True)

    @staticmethod
    def _game_xy(pt) -> tuple[float, float]:
        if hasattr(pt, "x"):
            return pt.x, pt.y
        return pt[0], pt[1]

    def _sync_incremental_from_paths(self, paths) -> None:
        if not self._tc.is_valid():
            return
        self._incr_path_count = max(0, len(paths) - 1) if paths else 0
        self._incr_prev = None
        self._trail_pts.clear()
        self._active_path = None
        self._active_path_item = None
        if not paths:
            return
        last_path = paths[-1]
        if not last_path:
            return
        gx, gy = self._game_xy(last_path[-1])
        sx, sy = self._tc.game_to_screen(gx, gy)
        self._incr_prev = (sx, sy)

    def _update_smooth_marker(self, dt: float) -> None:
        if self._smooth_marker_target is None:
            return
        pos = self._live_marker.pos()
        dx = self._smooth_marker_target.x() - pos.x()
        dy = self._smooth_marker_target.y() - pos.y()
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < 0.5:
            self._live_marker.setPos(self._smooth_marker_target)
        else:
            step = self._smooth_marker_speed * dt
            if step >= dist:
                self._live_marker.setPos(self._smooth_marker_target)
            else:
                self._live_marker.setPos(pos.x() + dx / dist * step,
                                         pos.y() + dy / dist * step)

    def set_smooth_marker_target(self, sx: float, sy: float, instant: bool = False) -> None:
        now = time.monotonic()
        if instant:
            self._live_marker.setPos(sx, sy)
            self._smooth_marker_speed = 50.0
        elif self._smooth_marker_target is not None:
            dt = now - self._smooth_marker_time
            if 0.001 < dt < 10.0:
                dx = sx - self._smooth_marker_target.x()
                dy = sy - self._smooth_marker_target.y()
                dist = math.sqrt(dx * dx + dy * dy)
                self._smooth_marker_speed = max(1.0, dist / dt)
        else:
            self._live_marker.setPos(sx, sy)
        self._smooth_marker_target = QPointF(sx, sy)
        self._smooth_marker_time = now


    def _render_heat_map(self, paths) -> None:
        if not self._tc.is_valid():
            return
        r = 8
        path = QPainterPath()
        for subpath in paths:
            for x, y in subpath:
                sx, sy = self._tc.game_to_screen(x, y)
                path.addEllipse(QRectF(sx - r, sy - r, r * 2, r * 2))
        self._heat_group = QGraphicsPathItem(path)
        self._heat_group.setPen(Qt.NoPen)
        self._heat_group.setBrush(QColor(0xFF, 0x44, 0x44, 60))
        self._heat_group.setZValue(-1)
        self._scene.addItem(self._heat_group)

    def _render_map_mode(self, paths, pois, preserve_transform: bool = False) -> None:
        img_w = self._map_pixmap.width()
        img_h = self._map_pixmap.height()

        view_w = self._view.width() - PADDING * 2
        view_h = self._view.height() - PADDING * 2
        if view_w <= 0 or view_h <= 0 or img_w <= 0 or img_h <= 0:
            return

        scale = min(view_w / img_w, view_h / img_h)
        offset_x = PADDING
        offset_y = PADDING
        flip_x = -1.0 if self._flip_x_map else 1.0
        flip_y = -1.0 if self._flip_y_map else 1.0

        if preserve_transform and self._tc.is_valid() and self._tc.map_mode:
            scale = self._tc.scale
            offset_x = self._tc.offset_x
            offset_y = self._tc.offset_y

        if self._map_item:
            self._map_item.setPos(offset_x, offset_y)
            self._map_item.setScale(scale)
            self._map_item.setTransform(QTransform.fromScale(flip_x, flip_y))

        all_pts = [(x, y) for path in paths for (x, y) in path]

        for pidx, path in enumerate(paths):
            if len(path) < 2:
                continue
            if self._fade_trail_enabled:
                pts = []
                for gx, gy in path:
                    ix, iy = self.game_to_img(gx, gy)
                    sx = offset_x + ix * scale * flip_x
                    sy = offset_y + iy * scale * flip_y
                    pts.append((sx, sy))
                for i in range(len(pts) - 1):
                    seg = QPainterPath()
                    seg.moveTo(pts[i][0], pts[i][1])
                    seg.lineTo(pts[i+1][0], pts[i+1][1])
                    alpha = 60 + int((i / max(1, len(pts) - 2)) * 195) if len(pts) > 2 else 255
                    c = QColor(PATH_COLORS[pidx % len(PATH_COLORS)])
                    c.setAlpha(alpha)
                    item = QGraphicsPathItem(seg)
                    item.setPen(QPen(c, 1.5, Qt.SolidLine))
                    _init_trail_path_item(item)
                    self._scene.addItem(item)
                    self._path_items.append(item)
            else:
                p = QPainterPath()
                first = True
                for gx, gy in path:
                    ix, iy = self.game_to_img(gx, gy)
                    sx = offset_x + ix * scale * flip_x
                    sy = offset_y + iy * scale * flip_y
                    if first:
                        p.moveTo(sx, sy)
                        first = False
                    else:
                        p.lineTo(sx, sy)
                item = QGraphicsPathItem(p)
                item.setPen(_path_color(pidx))
                _init_trail_path_item(item)
                self._scene.addItem(item)
                self._path_items.append(item)

        dot_path = QPainterPath()
        for gx, gy in all_pts:
            ix, iy = self.game_to_img(gx, gy)
            sx = offset_x + ix * scale * flip_x
            sy = offset_y + iy * scale * flip_y
            dot_path.addEllipse(QRectF(sx - 2.5, sy - 2.5, 5, 5))
        self._dot_group = QGraphicsPathItem(dot_path)
        self._dot_group.setPen(DOT_PEN)
        self._dot_group.setBrush(DOT_BRUSH)
        self._scene.addItem(self._dot_group)

        for idx, p in enumerate(pois):
            self._add_poi_marker(p, idx)

        self._tc.scale = scale
        self._tc.offset_x = offset_x
        self._tc.offset_y = offset_y
        self._tc.cal_sx = self._calib_sx
        self._tc.cal_sy = self._calib_sy
        self._tc.cal_ox = self._calib_ox
        self._tc.cal_oy = self._calib_oy
        self._tc.map_mode = True
        self._tc.flip_y_map = self._flip_y_map
        self._tc.flip_x_map = self._flip_x_map
        self._tc._valid = True

    def _render_auto_fit(self, paths, pois, preserve_transform: bool = False) -> None:
        all_pts = [(x, y) for path in paths for (x, y) in path]
        poi_coords = [(p.x, p.y) for p in pois]
        all_coords = all_pts + poi_coords

        if not all_coords:
            self._tc = TransformCache()
            self._tc._valid = False
            return

        if preserve_transform and self._tc.is_valid() and not self._tc.map_mode:
            for x, y in all_coords:
                self._expand_auto_fit_bounds(x, y)
        else:
            ys = [p[1] for p in all_coords]
            xs = [p[0] for p in all_coords]
            min_y = min(ys)
            max_y = max(ys)
            if self._auto_fit_max_y is None:
                self._auto_fit_max_y = max_y
            else:
                self._auto_fit_max_y = max(self._auto_fit_max_y, max_y)

            self._tc.scale = 1.0
            self._tc.offset_x = 0.0
            self._tc.offset_y = 0.0
            self._tc.min_x = min(xs)
            self._tc.max_x = max(xs)
            self._tc.min_y = min_y
            self._tc.max_y = self._auto_fit_max_y
            self._tc.flip_y_map = self._flip_y_map
            self._tc.flip_x_map = self._flip_x_map
            self._tc.map_mode = False
            self._tc._valid = True

        for pidx, path in enumerate(paths):
            if len(path) < 2:
                continue
            if self._fade_trail_enabled:
                pts = [self._tc.game_to_screen(x, y) for x, y in path]
                for i in range(len(pts) - 1):
                    seg = QPainterPath()
                    seg.moveTo(pts[i][0], pts[i][1])
                    seg.lineTo(pts[i+1][0], pts[i+1][1])
                    alpha = 60 + int((i / max(1, len(pts) - 2)) * 195) if len(pts) > 2 else 255
                    c = QColor(PATH_COLORS[pidx % len(PATH_COLORS)])
                    c.setAlpha(alpha)
                    item = QGraphicsPathItem(seg)
                    item.setPen(QPen(c, 1.5, Qt.SolidLine))
                    _init_trail_path_item(item)
                    self._scene.addItem(item)
                    self._path_items.append(item)
            else:
                p = QPainterPath()
                first = True
                for x, y in path:
                    sx, sy = self._tc.game_to_screen(x, y)
                    if first:
                        p.moveTo(sx, sy)
                        first = False
                    else:
                        p.lineTo(sx, sy)
                item = QGraphicsPathItem(p)
                item.setPen(_path_color(pidx))
                _init_trail_path_item(item)
                self._scene.addItem(item)
                self._path_items.append(item)

        for x, y in all_pts:
            sx, sy = self._tc.game_to_screen(x, y)
            dot = QGraphicsEllipseItem(-2.5, -2.5, 5, 5)
            dot.setPos(sx, sy)
            dot.setPen(DOT_PEN)
            dot.setBrush(DOT_BRUSH)
            dot.setFlag(QGraphicsItem.ItemIgnoresTransformations)
            self._scene.addItem(dot)
            self._dot_items.append(dot)

        for idx, p in enumerate(pois):
            self._add_poi_marker(p, idx)

    def _add_poi_marker(self, p: POI, idx: int) -> None:
        if not self._tc.is_valid():
            return
        sx, sy = self._tc.game_to_screen(p.x, p.y)
        cat_color = _poi_category_color(p.category)
        label = p.desc if p.desc else f"({p.x:.0f},{p.y:.0f})"
        item = PoiMarkerItem(idx, self, sx, sy, cat_color, label)
        self._scene.addItem(item)
        self._poi_marker_items.append(item)

    def note_paths_for_poi_highlights(self, paths) -> None:
        self._cached_paths = paths
        if self._cached_pois:
            self._refresh_poi_highlights()

    def _refresh_poi_highlights(self) -> None:
        for item in self._poi_highlight_items:
            self._scene.removeItem(item)
        self._poi_highlight_items.clear()
        if self._cached_paths and self._cached_pois:
            self._render_poi_segment_highlights(self._cached_paths, self._cached_pois)

    def _path_vertices(self, path) -> list[tuple[float, float]]:
        return [self._game_xy(p) for p in path]

    def _render_poi_segment_highlights(self, paths, pois) -> None:
        if not self._tc.is_valid() or not pois:
            return
        drawn: set[tuple[tuple[float, float], tuple[float, float]]] = set()

        def _highlight_segment(sx1, sy1, sx2, sy2, pen: QPen) -> None:
            key = (
                (round(sx1, 2), round(sy1, 2)),
                (round(sx2, 2), round(sy2, 2)),
            )
            rev = (key[1], key[0])
            if key in drawn or rev in drawn:
                return
            drawn.add(key)
            seg = QPainterPath()
            seg.moveTo(sx1, sy1)
            seg.lineTo(sx2, sy2)
            hi = QGraphicsPathItem(seg)
            hi.setPen(pen)
            hi.setZValue(15)
            self._scene.addItem(hi)
            self._poi_highlight_items.append(hi)

        g2s = self._tc.game_to_screen

        for poi in pois:
            cat_color = _poi_category_color(poi.category)
            pen = QPen(cat_color, 6.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            pen.setCosmetic(True)

            for pidx, path in enumerate(paths):
                if len(path) < 2:
                    continue
                verts = self._path_vertices(path)
                extra = None
                if (
                    pidx == len(paths) - 1
                    and self._last_game_pos is not None
                ):
                    lx, ly = self._game_xy(path[-1])
                    gx, gy = self._last_game_pos
                    if (lx - gx) ** 2 + (ly - gy) ** 2 > 1.0:
                        extra = (lx, ly, gx, gy)
                _highlight_poi_polar_nearest(
                    poi.x, poi.y, verts, g2s, pen, _highlight_segment, extra
                )

    def _bootstrap_transform_from_live(self, gx: float, gy: float) -> None:
        if self._tc.map_mode or self._tc.is_valid():
            return
        pad = LIVE_BOOTSTRAP_PAD
        self._tc.min_x = gx - pad
        self._tc.max_x = gx + pad
        self._tc.min_y = gy - pad
        self._tc.max_y = gy + pad
        self._auto_fit_max_y = gy + pad
        self._tc.flip_y_map = self._flip_y_map
        self._tc.flip_x_map = self._flip_x_map
        self._tc.map_mode = False
        self._tc.scale = 1.0
        self._tc._valid = True

    def _expand_auto_fit_bounds(self, gx: float, gy: float) -> bool:
        if self._tc.map_mode or not self._tc.is_valid():
            return False
        changed = False
        if gx < self._tc.min_x:
            self._tc.min_x = gx
            changed = True
        if gx > self._tc.max_x:
            self._tc.max_x = gx
            changed = True
        if gy < self._tc.min_y:
            self._tc.min_y = gy
            changed = True
        if gy > self._tc.max_y:
            self._tc.max_y = gy
            self._auto_fit_max_y = gy
            changed = True
        return changed

    def _follow_zoom_content_rect(self, mp: QPointF) -> QRectF:
        """Marker-centered window including recent trail so zoom-out shows where you have been."""
        r: QRectF | None = None
        for pt in self._trail_pts:
            pr = QRectF(pt[0] - 24, pt[1] - 24, 48, 48)
            r = pr if r is None else r.united(pr)
        if self._active_path_item is not None:
            br = self._active_path_item.sceneBoundingRect()
            if br.isValid() and not br.isEmpty():
                r = br if r is None else r.united(br)
        for item in self._path_items[-6:]:
            br = item.sceneBoundingRect()
            if br.isValid() and not br.isEmpty():
                r = br if r is None else r.united(br)
        marker_r = QRectF(mp.x() - 40, mp.y() - 40, 80, 80)
        r = marker_r if r is None else r.united(marker_r)
        if self._smooth_marker_target is not None:
            tx = self._smooth_marker_target.x()
            ty = self._smooth_marker_target.y()
            r = r.united(QRectF(tx - 24, ty - 24, 48, 48))

        cx, cy = r.center().x(), r.center().y()
        w = max(r.width() * FOLLOW_ZOOM_TRAIL_PAD, FOLLOW_ZOOM_MIN_EXTENT * 2)
        h = max(r.height() * FOLLOW_ZOOM_TRAIL_PAD, FOLLOW_ZOOM_MIN_EXTENT * 2)
        w = min(w, FOLLOW_ZOOM_MAX_EXTENT * 2)
        h = min(h, FOLLOW_ZOOM_MAX_EXTENT * 2)
        return QRectF(cx - w / 2, cy - h / 2, w, h)

    def _note_game_motion(self, gx: float, gy: float) -> None:
        now = time.monotonic()
        if self._prev_follow_game_pos is not None:
            dx = gx - self._prev_follow_game_pos[0]
            dy = gy - self._prev_follow_game_pos[1]
            if dx * dx + dy * dy >= FOLLOW_MOVE_THRESH_GAME ** 2:
                self._last_marker_move_time = now
                self._follow_paused_by_user = False
        self._prev_follow_game_pos = (gx, gy)

    def _should_apply_follow_camera(self, now: float) -> bool:
        if self._follow_paused_by_user or self._view_drag_active:
            return False
        return (now - self._last_marker_move_time) < FOLLOW_IDLE_SEC

    def _apply_zoom_follow(self, mp: QPointF) -> None:
        content = self._follow_zoom_content_rect(mp)
        visible = self._visible_scene_rect()
        if not visible.isValid() or visible.width() < 2 or visible.height() < 2:
            return

        fill = max(content.width() / visible.width(), content.height() / visible.height())
        self._view.setTransformationAnchor(QGraphicsView.AnchorViewCenter)
        self._view.centerOn(mp)

        if fill > FOLLOW_ZOOM_COMFORT:
            target_factor = FOLLOW_ZOOM_COMFORT / fill
            overshoot = min(1.0, (fill - FOLLOW_ZOOM_COMFORT) / 0.3)
            factor = 1.0 + (target_factor - 1.0) * (0.4 + 0.6 * overshoot)
            factor = max(factor, 0.90)
            self._view.centerOn(mp)
            self._view.scale(factor, factor)
            self._view.centerOn(mp)

    def _pan_to_marker(self, mp: QPointF) -> None:
        self._view.centerOn(mp)

    def update_live_marker(self, x: float, y: float, instant: bool = False) -> None:
        if not math.isfinite(x) or not math.isfinite(y):
            return
        if not self._tc.is_valid() and not self._tc.map_mode:
            self._bootstrap_transform_from_live(x, y)
        if not self._tc.is_valid():
            return
        bounds_changed = self._expand_auto_fit_bounds(x, y)
        self._last_game_pos = (x, y)
        self._note_game_motion(x, y)
        sx, sy = self._tc.game_to_screen(x, y)
        self._live_marker.setVisible(True)
        self.set_smooth_marker_target(sx, sy, instant=instant)
        if bounds_changed and not self._suppress_bounds_signal:
            self.bounds_expanded.emit()
        if self._cached_pois:
            prev = self._poi_highlight_live_pos
            moved = (
                prev is None
                or (x - prev[0]) ** 2 + (y - prev[1]) ** 2
                >= (MIN_DISTANCE * 0.4) ** 2
            )
            if moved:
                self._poi_highlight_live_pos = (x, y)
                self._refresh_poi_highlights()

    def add_trail_point(self, gx: float, gy: float, start_new_path: bool = False) -> None:
        if not self._tc.is_valid():
            return
        sx, sy = self._tc.game_to_screen(gx, gy)
        pt = (sx, sy)

        if start_new_path:
            if self._active_path_item is not None:
                self._path_items.append(self._active_path_item)
            self._incr_path_count += 1
            self._incr_prev = None
            self._trail_pts = [pt]
            self._active_path = QPainterPath()
            self._active_path.moveTo(*pt)
            self._active_path_item = QGraphicsPathItem(self._active_path)
            self._active_path_item.setPen(_path_color(self._incr_path_count))
            _init_trail_path_item(self._active_path_item)
            self._scene.addItem(self._active_path_item)
            self._tail_line_item.setPath(QPainterPath())
            self._tail_line_item.setVisible(False)
            self.set_smooth_marker_target(sx, sy, instant=True)

        elif self._incr_prev is not None:
            if not self._trail_pts:
                self._trail_pts = [self._incr_prev]
            self._trail_pts.append(pt)
            n = len(self._trail_pts)

            # Segment P[n-3] → P[n-2] is finalized once next point provides context
            if n >= 3:
                if self._active_path is None:
                    self._active_path = QPainterPath()
                    self._active_path.moveTo(*self._trail_pts[0])
                    self._active_path_item = QGraphicsPathItem(self._active_path)
                    self._active_path_item.setPen(_path_color(self._incr_path_count))
                    _init_trail_path_item(self._active_path_item)
                    self._scene.addItem(self._active_path_item)
                pts = self._trail_pts
                p0 = pts[n-4] if n >= 4 else pts[n-3]
                p1 = pts[n-3]
                p2 = pts[n-2]
                c1x = p1[0] + (p2[0] - p0[0]) / 6
                c1y = p1[1] + (p2[1] - p0[1]) / 6
                c2x = p2[0] - (pt[0] - p1[0]) / 6
                c2y = p2[1] - (pt[1] - p1[1]) / 6
                self._active_path.cubicTo(c1x, c1y, c2x, c2y, *p2)
                self._active_path_item.setPath(self._active_path)

            # Tail line: last finalized anchor → latest raw point
            if n >= 2:
                anchor = self._trail_pts[-2]
                tail = QPainterPath()
                tail.moveTo(*anchor)
                tail.lineTo(*pt)
                self._tail_line_item.setPath(tail)
                self._tail_line_item.setVisible(True)
                c = QColor(PATH_COLORS[self._incr_path_count % len(PATH_COLORS)])
                c.setAlpha(120)
                tail_pen = QPen(c, 1.5, Qt.SolidLine)
                self._tail_line_item.setPen(tail_pen)

        else:
            self._trail_pts = [pt]
            self._active_path = QPainterPath()
            self._active_path.moveTo(*pt)
            self._active_path_item = QGraphicsPathItem(self._active_path)
            self._active_path_item.setPen(_path_color(self._incr_path_count))
            _init_trail_path_item(self._active_path_item)
            self._scene.addItem(self._active_path_item)
            self._tail_line_item.setPath(QPainterPath())
            self._tail_line_item.setVisible(False)

        self._live_dot_path.addEllipse(pt[0] - 2.5, pt[1] - 2.5, 5, 5)
        self._live_dot_item.setPath(self._live_dot_path)
        self._incr_prev = pt

    def _follow_tick(self) -> None:
        now = time.monotonic()
        dt = now - self._follow_last_mono
        self._follow_last_mono = now
        dt = min(max(dt, 0.001), 0.1)
        self._update_smooth_marker(dt)

        # Update tail line anchor → smooth marker
        if self._tail_line_item.isVisible() and len(self._trail_pts) >= 2:
            anchor = self._trail_pts[-2]
            mp = self._live_marker.pos()
            tail = QPainterPath()
            tail.moveTo(*anchor)
            tail.lineTo(mp.x(), mp.y())
            self._tail_line_item.setPath(tail)

        mp = self._live_marker.pos()
        following = self._follow_active or self._follow_zoom_enabled
        if not following or not self._live_marker.isVisible():
            return

        apply_camera = self._should_apply_follow_camera(now)

        if apply_camera and self._follow_zoom_enabled and now - self._zoom_follow_last_mono >= FOLLOW_ZOOM_INTERVAL:
            self._zoom_follow_last_mono = now
            self._apply_zoom_follow(mp)

        if apply_camera and self._follow_active:
            self._pan_to_marker(mp)

    def recenter_follow_view(self) -> None:
        if not self._tc.is_valid() or not self._live_marker.isVisible():
            return
        mp = self._live_marker.pos()
        if self._follow_zoom_enabled:
            content = self._follow_zoom_content_rect(mp)
            cx = content.center().x()
            cy = content.center().y()
            w = content.width() * FOLLOW_RECENTER_PADDING
            h = content.height() * FOLLOW_RECENTER_PADDING
            padded = QRectF(cx - w / 2, cy - h / 2, w, h)
            self._view.fitInView(padded, Qt.KeepAspectRatio)
        self._view.centerOn(mp)

    def set_live_marker_visible(self, visible: bool) -> None:
        self._live_marker.setVisible(visible)

    def clear_live_data(self) -> None:
        self._last_game_pos = None
        self._smooth_marker_target = None
        self._smooth_marker_speed = 50.0
        self._smooth_marker_time = 0.0
        self._live_marker.setVisible(False)

    def update_stats(self, elapsed: float, point_count: int, total_dist: float, speed: float) -> None:
        if self._stats_label is None:
            self._stats_label = QLabel(self._view.viewport())
            self._stats_label.setStyleSheet(
                "background-color: rgba(0,0,0,140); color: #ccc; "
                "padding: 4px 8px; font: 9px Consolas; border-radius: 4px;"
            )
            self._stats_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        text = f"{mins:02d}:{secs:02d} | {point_count} pts | {total_dist:.0f} u | {speed:.1f} u/s"
        self._stats_label.setText(text)
        self._stats_label.adjustSize()
        vp = self._view.viewport()
        self._stats_label.move(vp.width() - self._stats_label.width() - 8,
                               vp.height() - self._stats_label.height() - 4)
        self._stats_label.show()

    def hide_stats(self) -> None:
        if self._stats_label:
            self._stats_label.hide()
            self._stats_label.deleteLater()
            self._stats_label = None

    def select_point(self, path_idx: int, point_idx: int,
                     paths: list[list[tuple[float, float]]]) -> None:
        self.clear_selection()
        if 0 <= path_idx < len(paths) and 0 <= point_idx < len(paths[path_idx]):
            gx, gy = self._game_xy(paths[path_idx][point_idx])
            self._place_selection_item(gx, gy)

    def select_poi(self, poi_idx: int, pois: list) -> None:
        self.clear_selection()
        if 0 <= poi_idx < len(pois):
            p = pois[poi_idx]
            self._place_selection_item(p.x, p.y)
            self.set_selected_poi(poi_idx)

    def selected_poi_index(self) -> int | None:
        return self._selected_poi_idx

    def set_selected_poi(self, idx: int) -> None:
        self._selected_poi_idx = idx
        for i, item in enumerate(self._poi_marker_items):
            item.setSelected(i == idx)

    def _on_poi_drag_finished(self, idx: int) -> None:
        if not (0 <= idx < len(self._poi_marker_items)) or not self._tc.is_valid():
            return
        pos = self._poi_marker_items[idx].pos()
        gx, gy = self._tc.screen_to_game(pos.x(), pos.y())
        self.poi_moved.emit(idx, gx, gy)

    def _on_poi_context_menu(self, idx: int, global_pos) -> None:
        from PySide6.QtWidgets import QMenu
        menu = QMenu()
        edit_action = menu.addAction("Edit Description")
        delete_action = menu.addAction("Delete")
        chosen = menu.exec(global_pos)
        if chosen == edit_action:
            self.poi_edit_requested.emit(idx)
        elif chosen == delete_action:
            self.poi_delete_requested.emit(idx)

    def clear_selection(self) -> None:
        if self._selection_item:
            self._scene.removeItem(self._selection_item)
            self._selection_item = None
        self._selected_poi_idx = None
        for item in self._poi_marker_items:
            item.setSelected(False)

    def _place_selection_item(self, x: float, y: float) -> None:
        if not self._tc.is_valid():
            return
        sx, sy = self._tc.game_to_screen(x, y)
        self._selection_item = QGraphicsEllipseItem(-5, -5, 10, 10)
        self._selection_item.setPos(sx, sy)
        self._selection_item.setPen(SELECTION_PEN)
        self._selection_item.setBrush(SELECTION_BRUSH)
        self._selection_item.setZValue(10)
        self._selection_item.setFlag(QGraphicsItem.ItemIgnoresTransformations)
        self._scene.addItem(self._selection_item)

    def try_canvas_to_data(self, pos: QPointF) -> tuple[float, float] | None:
        if not self._tc.is_valid():
            return None
        return self._tc.screen_to_game(pos.x(), pos.y())
