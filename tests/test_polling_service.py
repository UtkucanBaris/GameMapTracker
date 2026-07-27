import pytest

from polling_service import PollingService


class FakeReader:
    def __init__(self, positions: list[tuple[float, float]]) -> None:
        self.positions = positions
        self.calls = 0

    def try_read_float(self, address: int) -> float | None:
        del address
        self.calls += 1
        index = min((self.calls - 1) // 2, len(self.positions) - 1)
        x, y = self.positions[index]
        return x if self.calls % 2 else y


@pytest.mark.qt
def test_idle_pause_uses_watchdog_to_resume(qtbot) -> None:
    reader = FakeReader([(10.0, 20.0), (10.0, 20.0), (10.0, 20.0), (11.0, 20.0)])
    service = PollingService(reader)
    values: list[tuple[float, float]] = []
    paused: list[bool] = []
    resumed: list[bool] = []
    service.value_read.connect(lambda x, y: values.append((x, y)))
    service.idle_paused.connect(lambda: paused.append(True))
    service.idle_resumed.connect(lambda: resumed.append(True))
    service.idle_threshold = 2

    service.start(1, 2, 10)
    service._on_tick()
    service._on_tick()

    assert service.is_running
    assert service.is_idle_paused
    assert paused == [True]

    service._on_idle_watchdog_tick()

    assert not service.is_idle_paused
    assert resumed == [True]
    assert values[-1] == (11.0, 20.0)

    service.stop()
    service.deleteLater()
    qtbot.wait(0)


@pytest.mark.qt
def test_stop_prevents_future_reads(qtbot) -> None:
    reader = FakeReader([(1.0, 2.0)])
    service = PollingService(reader)

    service.start(1, 2, 10)
    calls_after_start = reader.calls
    service.stop()
    service._on_tick()
    service._on_idle_watchdog_tick()

    assert reader.calls == calls_after_start
    service.deleteLater()
    qtbot.wait(0)
