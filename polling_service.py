from __future__ import annotations
from PySide6.QtCore import QTimer, Signal, QObject


class PollingService(QObject):
    value_read = Signal(float, float)
    read_failed = Signal()
    idle_paused = Signal()
    idle_resumed = Signal()

    def __init__(self, reader):
        super().__init__()
        self._reader = reader
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
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
        self._interval = interval_ms
        self._timer.setInterval(interval_ms)
        self._timer.setSingleShot(False)
        self._timer.start()
        self._running = True
        self._on_tick()

    def stop(self) -> None:
        self._timer.stop()
        self._running = False
        self._idle_counter = 0
        self._last_x = None
        self._last_y = None
        self._paused_by_idle = False

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def idle_threshold(self) -> int:
        return self._idle_threshold

    @idle_threshold.setter
    def idle_threshold(self, value: int) -> None:
        self._idle_threshold = value

    def _on_tick(self) -> None:
        try:
            x = self._reader.try_read_float(self._x_addr)
            y = self._reader.try_read_float(self._y_addr)
            if x is not None and y is not None:
                self._consecutive_failures = 0
                self.value_read.emit(x, y)
                if self._idle_threshold > 0 and self._last_x is not None:
                    if x == self._last_x and y == self._last_y:
                        self._idle_counter += 1
                    else:
                        self._idle_counter = 0
                    if self._idle_counter >= self._idle_threshold:
                        self.stop()
                        self.idle_paused.emit()
                        self._paused_by_idle = True
                    elif self._paused_by_idle and (x != self._last_x or y != self._last_y):
                        self.start(self._x_addr, self._y_addr, self._interval)
                        self.idle_resumed.emit()
                        self._paused_by_idle = False
                self._last_x = x
                self._last_y = y
            else:
                self._consecutive_failures += 1
                if self._consecutive_failures <= 3 or self._consecutive_failures % 20 == 0:
                    self.read_failed.emit()
        except Exception as e:
            import sys
            self._consecutive_failures += 1
            print(f"PollingService error: {e}", file=sys.stderr)
