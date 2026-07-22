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


MIN_DISTANCE = 50.0
TELEPORT_THRESHOLD = 2000.0


@dataclass
class TrailModel:
    paths: list[list[TrailPoint]] = field(default_factory=list)
    pois: list[POI] = field(default_factory=list)
    teleport_threshold: float = TELEPORT_THRESHOLD

    def start_new_path(self) -> None:
        self.paths.append([])

    def add(self, x: float, y: float) -> bool:
        if not math.isfinite(x) or not math.isfinite(y):
            return False
        if not self.paths:
            self.paths.append([])
        current = self.paths[-1]
        if current:
            last = current[-1]
            d2 = _squared_dist(last, (x, y))
            if d2 < MIN_DISTANCE * MIN_DISTANCE:
                return False
            if d2 > self.teleport_threshold * self.teleport_threshold:
                self.start_new_path()
                current = self.paths[-1]
        current.append(TrailPoint(x, y))
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
        self.pois.append(POI(x, y, desc, category))

    def update_poi(self, idx: int, x: float, y: float, desc: str, category: str) -> None:
        if 0 <= idx < len(self.pois):
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

    def load(self, paths: list[list[TrailPoint]], pois: list[POI]) -> None:
        self.paths = paths
        self.pois = pois

    def clear(self) -> None:
        self.paths.clear()
        self.pois.clear()


def _squared_dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    return dx * dx + dy * dy
