"""Read-only discovery of running Windows .exe processes for per-app policies.

Uses documented Win32 APIs without admin rights or third-party packages.
Processes whose full image path is inaccessible are skipped; no attempt to
escalate rights, inject code, read memory, or infer executable from a PID.
"""
from __future__ import annotations

from dataclasses import dataclass
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
from typing import Callable, Iterable

from traffic_policy import executable_key


@dataclass(frozen=True)
class RunningApp:
    executable: str
    pids: tuple[int, ...]

    @property
    def name(self) -> str:
        return Path(self.executable).name


def _windows_processes() -> Iterable[tuple[int, str]]:
    """Enumerate PID and image path; skip inaccessible/system-owned processes."""
    if os.name != "nt":
        return ()

    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    enum = psapi.EnumProcesses
    enum.argtypes = [ctypes.POINTER(wintypes.DWORD), wintypes.DWORD,
                     ctypes.POINTER(wintypes.DWORD)]
    enum.restype = wintypes.BOOL
    open_process = kernel.OpenProcess
    open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    open_process.restype = wintypes.HANDLE
    image_name = kernel.QueryFullProcessImageNameW
    image_name.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                           wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    image_name.restype = wintypes.BOOL
    close_handle = kernel.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL

    slots = 2048
    while True:
        pids = (wintypes.DWORD * slots)()
        size = ctypes.sizeof(pids)
        used = wintypes.DWORD(0)
        if not enum(pids, size, ctypes.byref(used)):
            return ()
        if used.value < size:
            break
        slots *= 2
        if slots > 65536:
            return ()

    found = []
    for pid in pids[:used.value // ctypes.sizeof(wintypes.DWORD)]:
        if pid <= 4:
            continue
        handle = open_process(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            continue
        try:
            buf = ctypes.create_unicode_buffer(32768)
            length = wintypes.DWORD(len(buf))
            if image_name(handle, 0, buf, ctypes.byref(length)):
                path = buf.value
                if path.lower().endswith(".exe") and os.path.isabs(path):
                    found.append((int(pid), path))
        finally:
            close_handle(handle)
    return tuple(found)


def list_running_apps(
    source: Callable[[], Iterable[tuple[int, str]]] | None = None,
) -> list[RunningApp]:
    """Group processes by full .exe path; a policy applies to all its PIDs."""
    entries: dict[str, tuple[str, set[int]]] = {}
    for pid, path in (source or _windows_processes)():
        if type(pid) is not int or pid <= 0:
            continue
        if not isinstance(path, str) or not os.path.isabs(path) or not path.lower().endswith(".exe"):
            continue
        # The image might have exited between enumeration and this read.
        if not Path(path).is_file():
            continue
        key = executable_key(path)
        if key not in entries:
            entries[key] = (path, set())
        entries[key][1].add(pid)
    result = [RunningApp(path, tuple(sorted(pids))) for path, pids in entries.values()]
    return sorted(result, key=lambda x: (x.name.casefold(), x.executable.casefold()))
