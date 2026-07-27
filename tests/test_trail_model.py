import math

from trail_model import POI, TrailModel, TrailPoint


def test_add_rejects_non_finite_coordinates() -> None:
    model = TrailModel()

    assert not model.add(math.nan, 0.0)
    assert not model.add(0.0, math.inf)
    model.add_poi(math.nan, 1.0)

    assert model.paths == []
    assert model.pois == []


def test_accumulated_walk_allows_slow_progress() -> None:
    model = TrailModel(min_distance=28.0)

    assert model.add(0.0, 0.0)
    assert not model.add(10.0, 0.0)
    assert not model.add(20.0, 0.0)
    assert model.add(30.0, 0.0)
    assert model.paths == [[TrailPoint(0.0, 0.0), TrailPoint(30.0, 0.0)]]


def test_teleport_starts_new_path() -> None:
    model = TrailModel(min_distance=28.0, teleport_threshold=2_000.0)

    assert model.add(0.0, 0.0)
    assert model.add(3_000.0, 0.0)

    assert model.paths == [[TrailPoint(0.0, 0.0)], [TrailPoint(3_000.0, 0.0)]]


def test_load_sanitizes_points_and_pois() -> None:
    model = TrailModel()

    model.load(
        [
            [TrailPoint(1.0, 2.0), (math.inf, 3.0), ("bad", 4.0)],
            [],
        ],
        [
            POI(3.0, 4.0),
            POI(math.nan, 5.0),
        ],
    )

    assert model.paths == [[TrailPoint(1.0, 2.0)], []]
    assert model.pois == [POI(3.0, 4.0)]
    assert model._poll_prev is None


def test_painted_json_skips_malformed_rows() -> None:
    painted = TrailModel.painted_from_json(
        [
            {"path": "bad", "seg": 0, "category": "Boss"},
            {"path": 1, "seg": 2, "category": "Loot"},
        ]
    )

    assert painted == {(1, 2): "Loot"}
