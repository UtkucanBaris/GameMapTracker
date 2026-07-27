import json

import settings_service
from settings_service import load_trail, save_trail
from trail_model import POI, TrailPoint


def test_save_trail_filters_non_finite_data(tmp_path, monkeypatch) -> None:
    trail_path = tmp_path / "trail.json"
    monkeypatch.setattr(settings_service, "SETTINGS_DIR", tmp_path)
    monkeypatch.setattr(settings_service, "TRAIL_PATH", trail_path)

    save_trail(
        [[TrailPoint(1.0, 2.0), TrailPoint(float("nan"), 3.0)]],
        [POI(4.0, 5.0)],
    )

    data = json.loads(trail_path.read_text(encoding="utf-8"))
    assert data["paths"] == [[[1.0, 2.0]]]


def test_load_trail_normalizes_json_shape(tmp_path, monkeypatch) -> None:
    trail_path = tmp_path / "trail.json"
    trail_path.write_text(
        '{"paths":[[[NaN,2],[3,4]]],'
        '"pois":[{"x":5,"y":6,"desc":"POI","category":"Loot"},'
        '{"x":"bad","y":7}],'
        '"painted":[{"path":0,"seg":1,"category":"Loot"}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_service, "TRAIL_PATH", trail_path)

    data = load_trail()

    assert data == {
        "paths": [[[3.0, 4.0]]],
        "pois": [{"x": 5.0, "y": 6.0, "desc": "POI", "category": "Loot"}],
        "painted": [{"path": 0, "seg": 1, "category": "Loot"}],
    }
