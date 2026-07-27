from __future__ import annotations
import ctypes
import math
import struct
import sys
from ctypes import c_void_p, c_size_t, c_ulong, c_wchar, c_long, c_int, byref, create_string_buffer, sizeof
from dataclasses import dataclass
from enum import Enum, auto

if sys.platform == "win32":
    kernel32 = ctypes.windll.kernel32

    kernel32.OpenProcess.restype = c_void_p
    kernel32.OpenProcess.argtypes = [c_ulong, c_int, c_ulong]

    kernel32.CloseHandle.restype = c_int
    kernel32.CloseHandle.argtypes = [c_void_p]

    kernel32.ReadProcessMemory.restype = c_int
    kernel32.ReadProcessMemory.argtypes = [c_void_p, c_void_p, c_void_p, c_size_t, ctypes.POINTER(c_size_t)]

    kernel32.CreateToolhelp32Snapshot.restype = c_void_p
    kernel32.CreateToolhelp32Snapshot.argtypes = [c_ulong, c_ulong]

    kernel32.Process32FirstW.restype = c_int
    kernel32.Process32NextW.restype = c_int

    kernel32.Module32FirstW.restype = c_int
    kernel32.Module32NextW.restype = c_int
else:
    kernel32 = None


PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
TH32CS_SNAPPROCESS = 0x00000002
TH32CS_SNAPMODULE = 0x00000008
TH32CS_SNAPMODULE32 = 0x00000010

MAX_MODULE_NAME = 256
INVALID_HANDLE_VALUE = c_void_p(-1).value


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", c_ulong),
        ("cntUsage", c_ulong),
        ("th32ProcessID", c_ulong),
        ("th32DefaultHeapID", c_void_p),
        ("th32ModuleID", c_ulong),
        ("cntThreads", c_ulong),
        ("th32ParentProcessID", c_ulong),
        ("pcPriClassBase", c_long),
        ("dwFlags", c_ulong),
        ("szExeFile", c_wchar * 260),
    ]


class MODULEENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", c_ulong),
        ("th32ModuleID", c_ulong),
        ("th32ProcessID", c_ulong),
        ("GlblcntUsage", c_ulong),
        ("ProccntUsage", c_ulong),
        ("modBaseAddr", c_void_p),
        ("modBaseSize", c_ulong),
        ("hModule", c_void_p),
        ("szModule", c_wchar * 256),
        ("szExePath", c_wchar * 260),
    ]


class AttachStatus(Enum):
    Attached = auto()
    ProcessNotFound = auto()
    AccessDenied = auto()
    Unsupported = auto()


@dataclass
class AddressSpec:
    is_module_relative: bool
    value: int


@dataclass
class ProcessInfo:
    pid: int
    module_base: int
    module_size: int = 0


class MemoryReader:
    def __init__(self, process_name: str = "Exanima.exe", module_name: str | None = None):
        self._process_name = process_name
        self._module_name = (module_name or process_name).removesuffix(".exe").lower()
        self._handle = None
        self._pid = None
        self._module_base = None
        self._last_error = 0
        self._candidates: list[ProcessInfo] = []

    @property
    def has_handle(self) -> bool:
        return self._handle is not None

    @property
    def process_name(self) -> str:
        return self._process_name

    @property
    def pid(self) -> int | None:
        return self._pid

    @property
    def module_base(self) -> int | None:
        return self._module_base

    @property
    def last_error(self) -> int:
        return self._last_error

    def set_process_name(self, name: str) -> None:
        self._process_name = name
        self._module_name = name.removesuffix(".exe").lower()

    def _find_process_pids(self) -> list[int]:
        snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if not snapshot or snapshot == INVALID_HANDLE_VALUE:
            return []

        target_lower = self._process_name.lower()
        pids: list[int] = []
        pe = PROCESSENTRY32W()
        pe.dwSize = sizeof(PROCESSENTRY32W)
        try:
            ok = kernel32.Process32FirstW(snapshot, byref(pe))
            while ok:
                exe = pe.szExeFile.lower()
                if target_lower in exe or self._module_name in exe:
                    pids.append(pe.th32ProcessID)
                ok = kernel32.Process32NextW(snapshot, byref(pe))
        finally:
            kernel32.CloseHandle(snapshot)
        return pids

    @property
    def process_candidates(self) -> list[ProcessInfo]:
        return self._candidates.copy()

    def attach_to(self, pid: int) -> AttachStatus:
        if sys.platform != "win32" or kernel32 is None:
            return AttachStatus.Unsupported

        self.detach()

        handle = kernel32.OpenProcess(
            PROCESS_VM_READ | PROCESS_QUERY_INFORMATION,
            False,
            pid,
        )
        if not handle:
            return AttachStatus.AccessDenied

        self._pid = pid
        self._handle = handle
        result = self._get_main_module_base(pid)
        if result is not None:
            self._module_base = result[0]
            return AttachStatus.Attached

        kernel32.CloseHandle(handle)
        self._pid = None
        self._handle = None
        return AttachStatus.Unsupported

    def attach(self) -> AttachStatus:
        if sys.platform != "win32" or kernel32 is None:
            return AttachStatus.Unsupported

        self.detach()

        pids = self._find_process_pids()
        if not pids:
            return AttachStatus.ProcessNotFound

        opened: list[tuple[int, int, int, c_void_p]] = []
        all_handles: list[c_void_p] = []
        chosen: tuple[int, int, int, c_void_p] | None = None
        try:
            for pid in pids:
                handle = kernel32.OpenProcess(
                    PROCESS_VM_READ | PROCESS_QUERY_INFORMATION,
                    False,
                    pid,
                )
                if not handle:
                    continue
                all_handles.append(handle)

                result = self._get_main_module_base(pid)
                if result is not None:
                    base, size = result
                    opened.append((pid, base, size, handle))
                else:
                    kernel32.CloseHandle(handle)
                    all_handles.remove(handle)

            opened.sort(key=lambda c: c[2], reverse=True)

            self._candidates = [
                ProcessInfo(pid=c[0], module_base=c[1], module_size=c[2])
                for c in opened
            ]

            if opened:
                chosen = opened[0]
                self._pid = chosen[0]
                self._module_base = chosen[1]
                self._handle = chosen[3]
                return AttachStatus.Attached

            return AttachStatus.AccessDenied
        finally:
            chosen_handle = chosen[3] if chosen else None
            for handle in all_handles:
                if handle != chosen_handle:
                    kernel32.CloseHandle(handle)

    def _get_main_module_base(self, pid: int | None = None) -> tuple[int, int] | None:
        pid = pid if pid is not None else self._pid
        if pid is None:
            return None

        snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid)
        if not snapshot or snapshot == INVALID_HANDLE_VALUE:
            return None

        me = MODULEENTRY32W()
        me.dwSize = sizeof(MODULEENTRY32W)
        try:
            first_base = 0
            first_size = 0
            ok = kernel32.Module32FirstW(snapshot, byref(me))
            while ok:
                if first_base == 0 and me.modBaseAddr:
                    first_base = me.modBaseAddr
                    first_size = me.modBaseSize

                mod = me.szModule.lower()
                if self._module_name in mod or self._process_name.lower().replace(".exe", "") in mod:
                    base = me.modBaseAddr
                    size = me.modBaseSize
                    return (base, size) if base else None

                ok = kernel32.Module32NextW(snapshot, byref(me))

            return (first_base, first_size) if first_base else None
        finally:
            kernel32.CloseHandle(snapshot)

    def detach(self) -> None:
        if self._handle:
            kernel32.CloseHandle(self._handle)
            self._handle = None
        self._pid = None
        self._module_base = None
        self._candidates.clear()

    def try_read_float(self, address: int) -> float | None:
        if sys.platform != "win32" or kernel32 is None or not self._handle:
            return None

        buf = create_string_buffer(4)
        read = c_size_t()
        ok = kernel32.ReadProcessMemory(
            self._handle,
            c_void_p(address),
            buf,
            4,
            byref(read),
        )
        if ok and read.value == 4:
            self._last_error = 0
            val = struct.unpack("<f", buf.raw)[0]
            return val if math.isfinite(val) else None
        self._last_error = kernel32.GetLastError() if not ok else 0
        return None

    @staticmethod
    def try_parse_address(text: str) -> AddressSpec | None:
        text = text.strip()
        if not text:
            return None

        if "+" in text:
            parts = text.split("+", 1)
            hex_part = parts[1].strip()
            if hex_part.lower().startswith("0x"):
                hex_part = hex_part[2:]
            try:
                offset = int(hex_part, 16)
            except ValueError:
                return None
            return AddressSpec(is_module_relative=True, value=offset)
        else:
            clean = text.lower()
            if clean.startswith("0x"):
                clean = clean[2:]
            try:
                return AddressSpec(is_module_relative=False, value=int(clean, 16))
            except ValueError:
                return None

    def try_resolve(self, spec: AddressSpec) -> int | None:
        if spec.is_module_relative:
            if self._module_base is None:
                return None
            return int(self._module_base) + spec.value
        return spec.value
