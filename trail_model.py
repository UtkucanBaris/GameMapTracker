from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import NamedTuple


class TrailPoint(NamedTuple):
    x: float
    y: float

    @staticmethod
    def is_finite(val: float) -> bool:
        return math.isfinite(val)

    def format(self) -> str:
        return f"{self.x:.3f}, {self.y:.3f}"


@dataclass
class POI:
    x: float
    y: float
    desc: str = ""
    category: str = ""

    def format(self) -> str:
        if self.desc:
            return f"{self.desc} ({self.x:.1f}, {self.y:.1f})"
        return f"({self.x:.1f}, {self.y:.1f})"


def coerce_finite_point(value: object) -> TrailPoint | None:
    if isinstance(value, TrailPoint):
        x, y = value
    elif isinstance(value, (list, tuple)) and len(value) >= 2:
        try:
            x, y = float(value[0]), float(value[1])
        except (TypeError, ValueError):
            return None
    else:
        return None
    if not math.isfinite(x) or not math.isfinite(y):
        return None
    return TrailPoint(x, y)


def sanitize_paths(paths: object) -> list[list[TrailPoint]]:
    if not isinstance(paths, (list, tuple)):
        return []
    sanitized: list[list[TrailPoint]] = []
    for path in paths:
        if not isinstance(path, (list, tuple)):
            continue
        sanitized.append(
            [point for raw_point in path if (point := coerce_finite_point(raw_point)) is not None]
        )
    return sanitized


def coerce_finite_poi(value: object) -> POI | None:
    if isinstance(value, POI):
        x, y = value.x, value.y
        desc, category = value.desc, value.category
    elif isinstance(value, dict):
        point = coerce_finite_point((value.get("x"), value.get("y")))
        if point is None:
            return None
        x, y = point
        desc = value.get("desc", "")
        category = value.get("category", "")
    else:
        return None
    if not math.isfinite(x) or not math.isfinite(y):
        return None
    return POI(
        x,
        y,
        desc if isinstance(desc, str) else str(desc or ""),
        category if isinstance(category, str) else str(category or ""),
    )


def sanitize_pois(pois: object) -> list[POI]:
    if not isinstance(pois, (list, tuple)):
        return []
    return [
        poi
        for raw_poi in pois
        if (poi := coerce_finite_poi(raw_poi)) is not None
    ]


def sanitize_trail_data(data: object) -> dict:
    if not isinstance(data, dict):
        return {"paths": [], "pois": [], "painted": []}
    painted = data.get("painted", [])
    return {
        "paths": [
            [[point.x, point.y] for point in path]
            for path in sanitize_paths(data.get("paths", []))
        ],
        "pois": [
            {
                "x": poi.x,
                "y": poi.y,
                "desc": poi.desc,
                "category": poi.category,
            }
            for poi in sanitize_pois(data.get("pois", []))
        ],
        "painted": painted if isinstance(painted, list) else [],
    }


MIN_DISTANCE = 28.0
TELEPORT_THRESHOLD = 2000.0


@dataclass
class TrailModel:
    paths: list[list[TrailPoint]] = field(default_factory=list)
    pois: list[POI] = field(default_factory=list)
    teleport_threshold: float = TELEPORT_THRESHOLD
    min_distance: float = MIN_DISTANCE
    painted_segments: dict[tuple[int, int], str] = field(default_factory=dict)
    _poll_prev: tuple[float, float] | None = field(default=None, repr=False)
    _walk_since_add: float = field(default=0.0, repr=False)

    def reset_live_sampling(self) -> None:
        self._poll_prev = None
        self._walk_since_add = 0.0

    def set_min_distance(self, value: float) -> None:
        if not math.isfinite(value) or value < 0:
            raise ValueError("min_distance must be finite and non-negative")
        if value != self.min_distance:
            self.min_distance = value
            self._walk_since_add = 0.0

    def start_new_path(self) -> None:
        self.paths.append([])
        self._walk_since_add = 0.0

    def add(self, x: float, y: float) -> bool:
        if not math.isfinite(x) or not math.isfinite(y):
            return False
        if self._poll_prev is not None:
            self._walk_since_add += math.hypot(
                x - self._poll_prev[0], y - self._poll_prev[1]
            )
        self._poll_prev = (x, y)

        if not self.paths:
            self.paths.append([])
        current = self.paths[-1]
        if current:
            last = current[-1]
            d2 = _squared_dist(last, (x, y))
            min_d = self.min_distance
            direct_ok = d2 >= min_d * min_d
            accum_ok = self._walk_since_add >= min_d
            if not direct_ok and not accum_ok:
                return False
            if d2 > self.teleport_threshold * self.teleport_threshold:
                self.start_new_path()
                current = self.paths[-1]
        current.append(TrailPoint(x, y))
        self._walk_since_add = 0.0
        return True

    def smooth(self, epsilon: float = 3.0) -> None:
        def _rdp_iterative(pts, eps):
            if len(pts) < 3:
                return pts[:]
            stack = [(0, len(pts) - 1)]
            keep = {0, len(pts) - 1}
            while stack:
                start, end = stack.pop()
                if end - start < 2:
                    continue
                dmax, idx = 0.0, start
                sx, sy = pts[start]
                ex, ey = pts[end]
                dx = ex - sx
                dy = ey - sy
                denom = dx * dx + dy * dy
                for i in range(start + 1, end):
                    p = pts[i]
                    if denom > 0:
                        d = abs(dy * p[0] - dx * p[1] + ex * sy - ey * sx) / math.sqrt(denom)
                    else:
                        d = math.sqrt(_squared_dist(p, pts[start]))
                    if d > dmax:
                        dmax, idx = d, i
                if dmax > eps:
                    keep.add(idx)
                    stack.append((start, idx))
                    stack.append((idx, end))
            return [pts[i] for i in sorted(keep)]

        self.paths = [
            _rdp_iterative(path, epsilon) if len(path) >= 2 else list(path)
            for path in self.paths
        ]

    def add_poi(self, x: float, y: float, desc: str = "", category: str = "") -> None:
        if not math.isfinite(x) or not math.isfinite(y):
            return
        self.pois.append(POI(x, y, desc, category))

    def update_poi(self, idx: int, x: float, y: float, desc: str, category: str) -> None:
        if 0 <= idx < len(self.pois) and math.isfinite(x) and math.isfinite(y):
            self.pois[idx] = POI(x, y, desc, category)

    @property
    def latest_point(self) -> TrailPoint | None:
        for path in reversed(self.paths):
            if path:
                return path[-1]
        return None

    @property
    def has_data(self) -> bool:
        if self.pois:
            return True
        return any(len(p) > 0 for p in self.paths)

    def remove_point(self, path_idx: int, point_idx: int) -> None:
        if 0 <= path_idx < len(self.paths):
            path = self.paths[path_idx]
            if 0 <= point_idx < len(path):
                del path[point_idx]

    def remove_poi(self, idx: int) -> None:
        if 0 <= idx < len(self.pois):
            del self.pois[idx]

    def prune_empty_current_path(self) -> None:
        if self.paths and not self.paths[-1]:
            self.paths.pop()

    def paint_segment(self, path_idx: int, seg_idx: int, category: str) -> None:
        if category:
            self.painted_segments[(path_idx, seg_idx)] = category

    def erase_segment(self, path_idx: int, seg_idx: int) -> None:
        self.painted_segments.pop((path_idx, seg_idx), None)

    def clear_painted_segments(self) -> None:
        self.painted_segments.clear()

    @staticmethod
    def painted_to_json(painted: dict[tuple[int, int], str]) -> list[dict]:
        return [
            {"path": p, "seg": s, "category": cat}
            for (p, s), cat in sorted(painted.items())
        ]

    @staticmethod
    def painted_from_json(rows: list) -> dict[tuple[int, int], str]:
        out: dict[tuple[int, int], str] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                p = int(row.get("path", -1))
                s = int(row.get("seg", -1))
            except (TypeError, ValueError):
                continue
            cat = str(row.get("category", ""))
            if p >= 0 and s >= 0:
                out[(p, s)] = cat
        return out

    def load(
        self,
        paths: list[list[TrailPoint]],
        pois: list[POI],
        painted: dict[tuple[int, int], str] | None = None,
    ) -> None:
        self.paths = sanitize_paths(paths)
        self.pois = sanitize_pois(pois)
        self.painted_segments = painted if painted is not None else {}
        self.reset_live_sampling()

    def clear(self) -> None:
        self.paths.clear()
        self.pois.clear()
        self.painted_segments.clear()
        self.reset_live_sampling()


def _squared_dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    return dx * dx + dy * dy
