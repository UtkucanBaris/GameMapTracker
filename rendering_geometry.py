from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class XYPoint(Protocol):
    x: float
    y: float


def game_xy(point: object) -> tuple[float, float]:
    if isinstance(point, (list, tuple)) and len(point) >= 2:
        return float(point[0]), float(point[1])
    if isinstance(point, XYPoint):
        return float(point.x), float(point.y)
    raise TypeError(f"Unsupported point value: {point!r}")


def dist_sq_point_to_segment(
    px: float,
    py: float,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
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
