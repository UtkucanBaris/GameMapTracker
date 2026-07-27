import json
import math
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, TypeAlias


JsonObject: TypeAlias = dict[str, Any]


_UNSET = float("nan")


@dataclass
class MapCalibration:
    point1_gx: float = _UNSET
    point1_gy: float = _UNSET
    point1_ix: float = _UNSET
    point1_iy: float = _UNSET
    point2_gx: float = _UNSET
    point2_gy: float = _UNSET
    point2_ix: float = _UNSET
    point2_iy: float = _UNSET

    def is_complete(self) -> bool:
        return (
            math.isfinite(self.point1_gx) and
            math.isfinite(self.point1_gy) and
            math.isfinite(self.point1_ix) and
            math.isfinite(self.point1_iy) and
            math.isfinite(self.point2_gx) and
            math.isfinite(self.point2_gy) and
            math.isfinite(self.point2_ix) and
            math.isfinite(self.point2_iy)
        )


PROFILE_DEFAULTS = {
    "process_name": "Exanima.exe",
    "x_address": "Exanima.exe+48DDD0",
    "y_address": "Exanima.exe+48DDD8",
    "interval_ms": 500,
    "map_path": "",
    "calibration": {},
}


@dataclass
class AppSettings:
    process_name: str = "Exanima.exe"
    x_address: str = "Exanima.exe+48DDD0"
    y_address: str = "Exanima.exe+48DDD8"
    interval_ms: int = 500
    map_path: str = ""
    calibration: MapCalibration = field(default_factory=MapCalibration)
    profiles: dict[str, JsonObject] = field(default_factory=dict)
    active_profile: str = ""


SETTINGS_DIR = Path(os.path.expanduser("~")) / ".exanimap_helper"
SETTINGS_PATH = SETTINGS_DIR / "settings.json"
TRAIL_PATH = SETTINGS_DIR / "trail.json"


def save_trail(
    paths: Sequence[object],
    pois: Sequence[object],
    painted: Mapping[tuple[int, int], str] | None = None,
) -> None:
    try:
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        from trail_model import TrailModel, sanitize_paths, sanitize_pois

        clean_paths = sanitize_paths(paths)
        clean_pois = sanitize_pois(pois)
        data = {
            "paths": [[[float(v) for v in pt] for pt in path] for path in clean_paths],
            "pois": [
                {"x": p.x, "y": p.y, "desc": p.desc, "category": p.category}
                for p in clean_pois
            ],
        }
        if painted:
            data["painted"] = TrailModel.painted_to_json(dict(painted))
        TRAIL_PATH.write_text(
            json.dumps(data, indent=2, allow_nan=False),
            encoding="utf-8",
        )
    except Exception as e:
        import sys
        print(f"Trail save error: {e}", file=sys.stderr)


def load_trail() -> JsonObject | None:
    try:
        if TRAIL_PATH.exists():
            from trail_model import sanitize_trail_data

            return sanitize_trail_data(
                json.loads(TRAIL_PATH.read_text(encoding="utf-8"))
            )
    except Exception:
        pass
    return None


def _dict_to_calib(d: Mapping[str, Any]) -> MapCalibration:
    return MapCalibration(
        point1_gx=d.get("point1_gx", _UNSET),
        point1_gy=d.get("point1_gy", _UNSET),
        point1_ix=d.get("point1_ix", _UNSET),
        point1_iy=d.get("point1_iy", _UNSET),
        point2_gx=d.get("point2_gx", _UNSET),
        point2_gy=d.get("point2_gy", _UNSET),
        point2_ix=d.get("point2_ix", _UNSET),
        point2_iy=d.get("point2_iy", _UNSET),
    )


def _profile_to_dict(settings: AppSettings) -> JsonObject:
    return {
        "process_name": settings.process_name,
        "x_address": settings.x_address,
        "y_address": settings.y_address,
        "interval_ms": settings.interval_ms,
        "map_path": settings.map_path,
        "calibration": {
            "point1_gx": settings.calibration.point1_gx,
            "point1_gy": settings.calibration.point1_gy,
            "point1_ix": settings.calibration.point1_ix,
            "point1_iy": settings.calibration.point1_iy,
            "point2_gx": settings.calibration.point2_gx,
            "point2_gy": settings.calibration.point2_gy,
            "point2_ix": settings.calibration.point2_ix,
            "point2_iy": settings.calibration.point2_iy,
        },
    }


def _dict_to_settings(profile: Mapping[str, Any]) -> AppSettings:
    calib = profile.get("calibration", {})
    return AppSettings(
        process_name=profile.get("process_name", "Exanima.exe"),
        x_address=profile.get("x_address", "Exanima.exe+48DDD0"),
        y_address=profile.get("y_address", "Exanima.exe+48DDD8"),
        interval_ms=profile.get("interval_ms", 500),
        map_path=profile.get("map_path", ""),
        calibration=_dict_to_calib(calib) if calib else MapCalibration(),
    )


def _apply_profile(settings: AppSettings, profile_name: str) -> AppSettings:
    p = settings.profiles.get(profile_name)
    if p:
        s = _dict_to_settings(p)
        s.profiles = settings.profiles
        s.active_profile = profile_name
        return s
    raise KeyError(f"Profile '{profile_name}' not found")


def _save_current_as_profile(settings: AppSettings, profile_name: str) -> None:
    settings.profiles[profile_name] = _profile_to_dict(settings)


def load() -> AppSettings:
    try:
        if SETTINGS_PATH.exists():
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            active = data.get("active_profile", "")
            profiles = data.get("profiles", {})

            if active and active in profiles:
                s = _dict_to_settings(profiles[active])
            else:
                calib_data = data.get("calibration", {})
                s = AppSettings(
                    process_name=data.get("process_name", AppSettings.process_name),
                    x_address=data.get("x_address", AppSettings.x_address),
                    y_address=data.get("y_address", AppSettings.y_address),
                    interval_ms=data.get("interval_ms", AppSettings.interval_ms),
                    map_path=data.get("map_path", ""),
                    calibration=_dict_to_calib(calib_data) if calib_data else MapCalibration(),
                )
            s.profiles = profiles
            s.active_profile = active
            return s
    except Exception:
        pass
    return AppSettings()


def save(settings: AppSettings) -> None:
    try:
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        d = asdict(settings)
        SETTINGS_PATH.write_text(
            json.dumps(d, indent=2), encoding="utf-8"
        )
    except Exception as e:
        import sys
        print(f"Settings save error: {e}", file=sys.stderr)
