from export_service import import_text
from trail_model import POI, TrailPoint


def test_import_text_skips_non_finite_points(tmp_path) -> None:
    path = tmp_path / "trail.txt"
    path.write_text(
        "1, 2\n"
        "nan, 3\n"
        "4, inf\n"
        "5, 6\n\n"
        "--- POI ---\n"
        "7, 8, Entrance, Entrance\n"
        "nan, 9, Invalid, Danger\n",
        encoding="utf-8",
    )

    result = import_text(str(path))

    assert result.paths == [[TrailPoint(1.0, 2.0), TrailPoint(5.0, 6.0)]]
    assert result.pois == [POI(7.0, 8.0, "Entrance", "Entrance")]
