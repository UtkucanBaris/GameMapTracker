from __future__ import annotations
import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter
from PySide6.QtWidgets import QApplication

if sys.platform == "win32":
    user32 = ctypes.windll.user32
    user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
    user32.RegisterHotKey.restype = wintypes.BOOL
    user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.UnregisterHotKey.restype = wintypes.BOOL
else:
    user32 = None

WM_HOTKEY = 0x0312
MOD_NONE = 0x0000
VK_F8 = 0x77
VK_F10 = 0x79


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    ]


class Win32HotkeyService(QAbstractNativeEventFilter):
    def __init__(self, parent_widget):
        super().__init__()
        self._parent = parent_widget
        self._callbacks: dict[int, callable] = {}
        self._next_id = 0xB001
        app = QApplication.instance()
        if app:
            app.installNativeEventFilter(self)

    def register(self, key: int, callback: callable) -> bool:
        if sys.platform != "win32" or user32 is None:
            return False
        hwnd = int(self._parent.winId())
        id_ = self._next_id
        self._next_id += 1
        ok = user32.RegisterHotKey(hwnd, id_, MOD_NONE, key)
        if ok:
            self._callbacks[id_] = callback
            return True
        return False

    def dispose(self) -> None:
        if sys.platform != "win32" or user32 is None:
            return
        hwnd = int(self._parent.winId())
        for id_ in self._callbacks:
            user32.UnregisterHotKey(hwnd, id_)
        self._callbacks.clear()
        app = QApplication.instance()
        if app:
            app.removeNativeEventFilter(self)

    def nativeEventFilter(self, event_type: bytes, message) -> tuple[bool, int]:
        if sys.platform != "win32":
            return False, 0

        if event_type == b"windows_generic_MSG":
            try:
                if isinstance(message, int):
                    msg = MSG.from_address(message)
                else:
                    msg_id = getattr(message, "message", None)
                    wparam = getattr(message, "wParam", None)

                if isinstance(message, int):
                    if msg.message == WM_HOTKEY and msg.wParam in self._callbacks:
                        self._callbacks[msg.wParam]()
                        return True, 0
                else:
                    if (msg_id == WM_HOTKEY
                            and wparam is not None
                            and wparam in self._callbacks):
                        self._callbacks[wparam]()
                        return True, 0
            except Exception:
                pass
        return False, 0
