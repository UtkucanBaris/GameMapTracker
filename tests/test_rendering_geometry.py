import pytest

from rendering_geometry import dist_sq_point_to_segment, game_xy
from trail_model import TrailPoint


def test_game_xy_supports_model_and_tuple_points() -> None:
    assert game_xy(TrailPoint(1.0, 2.0)) == (1.0, 2.0)
    assert game_xy((3, 4)) == (3.0, 4.0)


def test_game_xy_rejects_unknown_values() -> None:
    with pytest.raises(TypeError):
        game_xy("not a point")


def test_point_to_segment_distance_handles_degenerate_segment() -> None:
    assert dist_sq_point_to_segment(3.0, 4.0, 0.0, 0.0, 0.0, 0.0) == 25.0
    assert dist_sq_point_to_segment(2.0, 1.0, 0.0, 0.0, 4.0, 0.0) == 1.0
