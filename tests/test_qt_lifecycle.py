import pytest
from PySide6.QtWidgets import QGraphicsView

from graph_renderer import MAX_LIVE_TRAIL_POINTS, GraphRenderer


@pytest.mark.qt
def test_follow_timer_has_explicit_lifecycle(qtbot) -> None:
    view = QGraphicsView()
    qtbot.addWidget(view)
    renderer = GraphRenderer(view)

    assert not renderer._follow_timer.isActive()
    renderer.set_trail_recording_active(True)
    assert renderer._follow_timer.isActive()

    renderer.set_trail_recording_active(False)
    assert not renderer._follow_timer.isActive()
    renderer.shutdown()
    assert not renderer._follow_timer.isActive()


@pytest.mark.qt
def test_preserve_transform_does_not_reset_view(qtbot) -> None:
    view = QGraphicsView()
    qtbot.addWidget(view)
    renderer = GraphRenderer(view)
    paths = [[(0.0, 0.0), (100.0, 100.0)]]

    renderer.render(paths, [], preserve_transform=False)
    view.scale(1.5, 1.5)
    before = view.transform()
    renderer.render(paths, [], preserve_transform=True)

    assert view.transform() == before
    renderer.shutdown()


@pytest.mark.qt
def test_live_trail_buffer_is_bounded(qtbot) -> None:
    view = QGraphicsView()
    qtbot.addWidget(view)
    renderer = GraphRenderer(view)
    renderer.render([[(0.0, 0.0)]], [], preserve_transform=False)
    renderer.set_trail_recording_active(True)

    for index in range(MAX_LIVE_TRAIL_POINTS + 50):
        renderer.add_trail_point(float(index), 0.0)

    assert len(renderer._trail_pts) == MAX_LIVE_TRAIL_POINTS
    assert len(renderer._recording_dot_items) <= 4096
    renderer.shutdown()
