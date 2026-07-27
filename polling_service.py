from __future__ import annotations
from typing import Protocol

from PySide6.QtCore import QTimer, Signal, QObject


class FloatReader(Protocol):
    def try_read_float(self, address: int) -> float | None:
        ...


class PollingService(QObject):
    value_read = Signal(float, float)
    read_failed = Signal()
    idle_paused = Signal()
    idle_resumed = Signal()

    def __init__(self, reader: FloatReader):
        super().__init__()
        self._reader = reader
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._idle_watchdog_timer = QTimer(self)
        self._idle_watchdog_timer.timeout.connect(self._on_idle_watchdog_tick)
        self._x_addr = 0
        self._y_addr = 0
        self._running = False
        self._consecutive_failures = 0
        self._idle_counter: int = 0
        self._idle_threshold: int = 0
        self._last_x: float | None = None
        self._last_y: float | None = None
        self._paused_by_idle: bool = False
        self._interval: int = 0

    def start(self, x_addr: int, y_addr: int, interval_ms: int) -> None:
        self._x_addr = x_addr
        self._y_addr = y_addr
        self._consecutive_failures = 0
        self._interval = max(1, interval_ms)
        self._timer.setInterval(self._interval)
        self._timer.setSingleShot(False)
        self._idle_watchdog_timer.stop()
        self._timer.start()
        self._running = True
        self._paused_by_idle = False
        self._idle_counter = 0
        self._on_tick()

    def stop(self) -> None:
        self._timer.stop()
        self._idle_watchdog_timer.stop()
        self._running = False
        self._idle_counter = 0
        self._last_x = None
        self._last_y = None
        self._paused_by_idle = False

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_idle_paused(self) -> bool:
        return self._paused_by_idle

    def set_interval(self, interval_ms: int) -> None:
        self._interval = max(1, interval_ms)
        self._timer.setInterval(self._interval)
        if self._paused_by_idle:
            self._idle_watchdog_timer.setInterval(self._watchdog_interval())

    @property
    def idle_threshold(self) -> int:
        return self._idle_threshold

    @idle_threshold.setter
    def idle_threshold(self, value: int) -> None:
        self._idle_threshold = max(0, value)

    def _watchdog_interval(self) -> int:
        return max(250, self._interval * 4)

    def _read_position(self) -> tuple[float, float] | None:
        try:
            x = self._reader.try_read_float(self._x_addr)
            y = self._reader.try_read_float(self._y_addr)
            if x is None or y is None:
                self._consecutive_failures += 1
                if self._consecutive_failures <= 3 or self._consecutive_failures % 20 == 0:
                    self.read_failed.emit()
                return None
            self._consecutive_failures = 0
            return x, y
        except Exception as e:
            import sys
            self._consecutive_failures += 1
            print(f"PollingService error: {e}", file=sys.stderr)
            return None

    def _on_tick(self) -> None:
        if not self._running or self._paused_by_idle:
            return
        position = self._read_position()
        if position is None:
            return
        x, y = position
        self.value_read.emit(x, y)
        if self._idle_threshold > 0 and self._last_x is not None:
            if x == self._last_x and y == self._last_y:
                self._idle_counter += 1
            else:
                self._idle_counter = 0
            if self._idle_counter >= self._idle_threshold:
                self._paused_by_idle = True
                self._timer.stop()
                self._idle_watchdog_timer.setInterval(self._watchdog_interval())
                self._idle_watchdog_timer.start()
                self.idle_paused.emit()
        self._last_x = x
        self._last_y = y

    def _on_idle_watchdog_tick(self) -> None:
        if not self._running or not self._paused_by_idle:
            return
        position = self._read_position()
        if position is None:
            return
        x, y = position
        moved = self._last_x is None or x != self._last_x or y != self._last_y
        self._last_x = x
        self._last_y = y
        if not moved:
            return
        self._paused_by_idle = False
        self._idle_counter = 0
        self._idle_watchdog_timer.stop()
        self._timer.start()
        self.value_read.emit(x, y)
        self.idle_resumed.emit()
