from __future__ import annotations
from dataclasses import dataclass, field
from PySide6.QtGui import QPainter, QImage, QColor
from trail_model import TrailPoint, POI


@dataclass
class ExportResult:
    paths: list[list[TrailPoint]] = field(default_factory=list)
    pois: list[POI] = field(default_factory=list)


def export_text(paths: list[list[TrailPoint]], pois: list[POI], filepath: str) -> None:
    lines: list[str] = []
    first = True
    for path in paths:
        if not path:
            continue
        if not first:
            lines.append("")
        first = False
        for pt in path:
            lines.append(f"{pt.x}, {pt.y}")
    if pois:
        lines.append("")
        lines.append("--- POI ---")
        for poi in pois:
            parts = [f"{poi.x}", f"{poi.y}", poi.desc, poi.category]
            lines.append(", ".join(parts))
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def import_text(filepath: str) -> ExportResult:
    paths: list[list[TrailPoint]] = []
    pois: list[POI] = []
    current_path: list[TrailPoint] = []
    in_poi = False

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                if not in_poi and current_path:
                    paths.append(current_path)
                    current_path = []
                continue
            if line == "--- POI ---":
                if not in_poi and current_path:
                    paths.append(current_path)
                    current_path = []
                in_poi = True
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 2:
                try:
                    x = float(parts[0])
                    y = float(parts[1])
                except ValueError:
                    continue
                desc = parts[2] if len(parts) > 2 else ""
                category = parts[3] if len(parts) > 3 else ""
                if in_poi:
                    pois.append(POI(x, y, desc, category))
                else:
                    current_path.append(TrailPoint(x, y))

    if not in_poi and current_path:
        paths.append(current_path)

    return ExportResult(paths=paths, pois=pois)


def export_png(scene, filepath: str, width: int, height: int) -> None:
    image = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
    image.fill(QColor(0xF0, 0xF0, 0xF0))
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.Antialiasing)
        scene.render(painter)
    finally:
        painter.end()
    if not image.save(filepath, "PNG"):
        raise RuntimeError(f"Failed to save PNG to {filepath}")
