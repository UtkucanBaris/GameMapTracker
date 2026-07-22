from __future__ import annotations
import math
import time

from PySide6.QtCore import Qt, QRectF, QPointF, QTimer, QObject
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
from trail_model import POI


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


class TransformCache:
    def __init__(self):
        self.scale = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.min_x = 0.0
        self.max_y = 0.0
        self.min_y = 0.0
        self.flip_y = True
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
            sx = x
            sy = self.max_y - y
        return sx, sy

    def screen_to_game(self, sx: float, sy: float) -> tuple[float, float]:
        if self.map_mode:
            ix = (sx - self.offset_x) / self.scale * (-1.0 if self.flip_x_map else 1.0)
            iy = (sy - self.offset_y) / self.scale * (-1.0 if self.flip_y_map else 1.0)
            gx = (ix - self.cal_ox) / self.cal_sx if self.cal_sx != 0 else ix
            gy = (iy - self.cal_oy) / self.cal_sy if self.cal_sy != 0 else iy
        else:
            gx = sx
            gy = self.max_y - sy
        return gx, gy


class GraphRenderer(QObject):
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
        self._last_zoom_rect: QRectF | None = None
        self._last_game_pos: tuple[float, float] | None = None
        self._smooth_marker_target: QPointF | None = None
        self._smooth_marker_speed: float = 50.0
        self._smooth_marker_time: float = 0.0
        self._incr_prev: tuple[float, float] | None = None
        self._incr_path_count: int = 0
        self._active_path: QPainterPath | None = None
        self._active_path_item: QGraphicsPathItem | None = None
        self._trail_pts: list[tuple[float, float]] = []
        self._tail_line_item = QGraphicsPathItem()
        self._tail_line_item.setPen(_path_color(0))
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

    @property
    def flip_x_map(self) -> bool:
        return self._flip_x_map

    @flip_x_map.setter
    def flip_x_map(self, val: bool) -> None:
        self._flip_x_map = val

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

    @property
    def follow_zoom_enabled(self) -> bool:
        return self._follow_zoom_enabled

    @follow_zoom_enabled.setter
    def follow_zoom_enabled(self, val: bool) -> None:
        self._follow_zoom_enabled = val

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
            self._last_zoom_rect = QRectF(self._scene.itemsBoundingRect())

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
            elif self._follow_active:
                self.auto_follow_active = False
        if obj is vp and event.type() == event.Type.MouseButtonPress:
            if self._follow_active:
                self.auto_follow_active = False
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
            self._render_map_mode(paths, pois)
        else:
            self._render_auto_fit(paths, pois)

        if self._heat_map_enabled:
            self._render_heat_map(paths)

        if paths and paths[-1] and self._auto_fit_max_y is not None:
            last_gx, last_gy = paths[-1][-1]
            self._incr_prev = (last_gx, self._auto_fit_max_y - last_gy)
            self._incr_path_count = max(0, len(paths) - 1)

        if self._last_game_pos is not None and self._tc.is_valid():
            sx, sy = self._tc.game_to_screen(*self._last_game_pos)
            self._live_marker.setVisible(True)
            self.set_smooth_marker_target(sx, sy)

    def _update_smooth_marker(self) -> None:
        if self._smooth_marker_target is None:
            return
        pos = self._live_marker.pos()
        dx = self._smooth_marker_target.x() - pos.x()
        dy = self._smooth_marker_target.y() - pos.y()
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < 0.5:
            self._live_marker.setPos(self._smooth_marker_target)
        else:
            step = self._smooth_marker_speed * 0.016
            if step >= dist:
                self._live_marker.setPos(self._smooth_marker_target)
            else:
                self._live_marker.setPos(pos.x() + dx / dist * step,
                                         pos.y() + dy / dist * step)

    def set_smooth_marker_target(self, sx: float, sy: float) -> None:
        now = time.monotonic()
        if self._smooth_marker_target is not None:
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

    def _render_map_mode(self, paths, pois) -> None:
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

        for p in pois:
            cat_color = _poi_category_color(p.category)
            gx, gy = p.x, p.y
            ix, iy = self.game_to_img(gx, gy)
            sx = offset_x + ix * scale * flip_x
            sy = offset_y + iy * scale * flip_y
            ring = QGraphicsEllipseItem(sx - 25, sy - 25, 50, 50)
            ring.setPen(QPen(cat_color, 2.0))
            ring.setBrush(Qt.NoBrush)
            self._scene.addItem(ring)
            self._poi_ring_items.append(ring)
            txt = QGraphicsTextItem(p.desc if p.desc else f"({gx:.0f},{gy:.0f})")
            txt.setDefaultTextColor(cat_color)
            txt.setFont(QFont("Consolas", 8))
            txt.setPos(sx + 28, sy - 8)
            txt.setZValue(5)
            self._scene.addItem(txt)
            self._poi_text_items.append(txt)

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

    def _render_auto_fit(self, paths, pois) -> None:
        all_pts = [(x, y) for path in paths for (x, y) in path]
        poi_coords = [(p.x, p.y) for p in pois]
        all_coords = all_pts + poi_coords

        if not all_coords:
            self._tc = TransformCache()
            self._tc._valid = False
            return

        ys = [p[1] for p in all_coords]
        max_y = max(ys)
        if self._auto_fit_max_y is None:
            self._auto_fit_max_y = max_y
        else:
            self._auto_fit_max_y = max(self._auto_fit_max_y, max_y)

        for pidx, path in enumerate(paths):
            if len(path) < 2:
                continue
            if self._fade_trail_enabled:
                pts = [(x, self._auto_fit_max_y - y) for x, y in path]
                for i in range(len(pts) - 1):
                    seg = QPainterPath()
                    seg.moveTo(pts[i][0], pts[i][1])
                    seg.lineTo(pts[i+1][0], pts[i+1][1])
                    alpha = 60 + int((i / max(1, len(pts) - 2)) * 195) if len(pts) > 2 else 255
                    c = QColor(PATH_COLORS[pidx % len(PATH_COLORS)])
                    c.setAlpha(alpha)
                    item = QGraphicsPathItem(seg)
                    item.setPen(QPen(c, 1.5, Qt.SolidLine))
                    self._scene.addItem(item)
                    self._path_items.append(item)
            else:
                p = QPainterPath()
                first = True
                for x, y in path:
                    sy = self._auto_fit_max_y - y
                    if first:
                        p.moveTo(x, sy)
                        first = False
                    else:
                        p.lineTo(x, sy)
                item = QGraphicsPathItem(p)
                item.setPen(_path_color(pidx))
                self._scene.addItem(item)
                self._path_items.append(item)

        for x, y in all_pts:
            sy = self._auto_fit_max_y - y
            dot = QGraphicsEllipseItem(-2.5, -2.5, 5, 5)
            dot.setPos(x, sy)
            dot.setPen(DOT_PEN)
            dot.setBrush(DOT_BRUSH)
            dot.setFlag(QGraphicsItem.ItemIgnoresTransformations)
            self._scene.addItem(dot)
            self._dot_items.append(dot)

        for p in pois:
            cat_color = _poi_category_color(p.category)
            sy = self._auto_fit_max_y - p.y
            ring = QGraphicsEllipseItem(-25, -25, 50, 50)
            ring.setPos(p.x, sy)
            ring.setPen(QPen(cat_color, 2.0))
            ring.setBrush(Qt.NoBrush)
            ring.setFlag(QGraphicsItem.ItemIgnoresTransformations)
            self._scene.addItem(ring)
            self._poi_ring_items.append(ring)
            txt = QGraphicsTextItem(p.desc if p.desc else f"({p.x:.0f},{p.y:.0f})")
            txt.setDefaultTextColor(cat_color)
            txt.setFont(QFont("Consolas", 8))
            txt.setPos(p.x, sy)
            txt.setZValue(5)
            txt.setFlag(QGraphicsItem.ItemIgnoresTransformations)
            self._scene.addItem(txt)
            self._poi_text_items.append(txt)

        self._tc.scale = 1.0
        self._tc.offset_x = 0.0
        self._tc.offset_y = 0.0
        self._tc.min_x = 0.0
        self._tc.min_y = 0.0
        self._tc.max_y = self._auto_fit_max_y
        self._tc.flip_y = True
        self._tc.map_mode = False
        self._tc._valid = True

    def update_live_marker(self, x: float, y: float) -> None:
        if not self._tc.is_valid() or not math.isfinite(x) or not math.isfinite(y):
            return
        self._last_game_pos = (x, y)
        sx, sy = self._tc.game_to_screen(x, y)
        self._live_marker.setVisible(True)
        self.set_smooth_marker_target(sx, sy)

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
            self._scene.addItem(self._active_path_item)
            self._tail_line_item.setPath(QPainterPath())
            self._tail_line_item.setVisible(False)

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
            self._scene.addItem(self._active_path_item)
            self._tail_line_item.setPath(QPainterPath())
            self._tail_line_item.setVisible(False)

        self._live_dot_path.addEllipse(pt[0] - 2.5, pt[1] - 2.5, 5, 5)
        self._live_dot_item.setPath(self._live_dot_path)
        self._incr_prev = pt

    def _follow_tick(self) -> None:
        self._update_smooth_marker()

        # Update tail line anchor → smooth marker
        if self._tail_line_item.isVisible() and len(self._trail_pts) >= 2:
            anchor = self._trail_pts[-2]
            mp = self._live_marker.pos()
            tail = QPainterPath()
            tail.moveTo(*anchor)
            tail.lineTo(mp.x(), mp.y())
            self._tail_line_item.setPath(tail)

        if not self._follow_active:
            return

        mp = self._live_marker.pos()
        vr = self._view.mapToScene(self._view.viewport().rect()).boundingRect()
        current = vr.center()
        dx = mp.x() - current.x()
        dy = mp.y() - current.y()
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < 4.0:
            self._view.centerOn(mp)
        else:
            t = 0.3
            nx = current.x() + dx * t
            ny = current.y() + dy * t
            self._view.centerOn(nx, ny)

        if self._follow_zoom_enabled:
            r = None
            for it in self._scene.items():
                if it is self._map_item or it is self._live_marker:
                    continue
                ir = it.sceneBoundingRect()
                if ir.isValid() and not ir.isEmpty():
                    r = ir if r is None else r.united(ir)
            if r is not None and r.width() > 1 and r.height() > 1:
                if self._last_zoom_rect is None or not self._last_zoom_rect.contains(r):
                    self._last_zoom_rect = QRectF(r)
                    self.zoom_to_fit()
                    self._view.centerOn(mp)

    def set_live_marker_visible(self, visible: bool) -> None:
        self._live_marker.setVisible(visible)

    def clear_live_data(self) -> None:
        self._last_game_pos = None
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
            x, y = paths[path_idx][point_idx]
            self._place_selection_item(x, y)

    def select_poi(self, poi_idx: int, pois: list) -> None:
        self.clear_selection()
        if 0 <= poi_idx < len(pois):
            p = pois[poi_idx]
            self._place_selection_item(p.x, p.y)

    def clear_selection(self) -> None:
        if self._selection_item:
            self._scene.removeItem(self._selection_item)
            self._selection_item = None

    def _place_selection_item(self, x: float, y: float) -> None:
        if not self._tc.is_valid():
            return
        self._selection_item = QGraphicsEllipseItem(-5, -5, 10, 10)
        self._selection_item.setPos(x, y)
        self._selection_item.setPen(SELECTION_PEN)
        self._selection_item.setBrush(SELECTION_BRUSH)
        self._selection_item.setZValue(10)
        self._selection_item.setFlag(QGraphicsItem.ItemIgnoresTransformations)
        self._scene.addItem(self._selection_item)

    def try_canvas_to_data(self, pos: QPointF) -> tuple[float, float] | None:
        if not self._tc.is_valid():
            return None
        return self._tc.screen_to_game(pos.x(), pos.y())
