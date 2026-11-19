"""OneTunnel first-party Windows Filtering Platform BLOCK backend (no firewall cmdlets).

The companion program is compiled from native/wfp/ and bundled with the EXE.
It installs WFP ALE_AUTH_CONNECT IPv4+IPv6 temporary filters in a DYNAMIC
session. No Windows Firewall rules, ProxiFyre service or external NDIS driver.

Transparent PROXY interception is NOT implemented: it requires a future
signed kernel WFP callout and original-destination-aware local proxy.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
from typing import Callable, Iterable

from traffic_policy import app_name_from_path, executable_key, normalize_executable

FORBIDDEN_APP_NAMES = frozenset({
    "1vpn-desktop-lab.exe", "onetunnel-wfp-guard.exe",
    "proxifyre.exe", "xray.exe", "python.exe", "pythonw.exe",
    "svchost.exe", "lsass.exe", "services.exe", "winlogon.exe",
    "smss.exe", "csrss.exe", "dwm.exe", "system.exe",
})
MAX_PATHS = 24


def running_as_admin() -> bool:
    if os.name != "nt":
        return False
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def bundled_guard_path() -> Path:
    name = "onetunnel-wfp-guard.exe"
    locations = [
        Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / name,
        Path(__file__).resolve().parent.parent / "native" / "wfp" / "build" / "Release" / name,
    ]
    return next((p for p in locations if p.is_file()), locations[0])


def _validate_path(executable: str) -> str:
    path = normalize_executable(executable)
    if app_name_from_path(path) in FORBIDDEN_APP_NAMES:
        raise ValueError("Se prohíbe bloquear el motor VPN y procesos críticos")
    if os.name == "nt":
        windir = os.environ.get("WINDIR", r"C:\Windows")
        # Prevent bulk blocking of executables from the Windows system tree.
        system = os.path.normcase(os.path.abspath(windir)) + os.sep
        if os.path.normcase(os.path.abspath(path)).startswith(system):
            raise ValueError("Los ejecutables del sistema Windows están protegidos")
    return path


class NativeWfpGuard:
    """Owns a subprocess whose lifetime defines a temporary WFP session.

    Each reconfiguration launches the NEW session first. Only once its READY
    signal arrives is the OLD one stopped; failure keeps the prior policy.
    This design is intentionally fail-open on application crash (no kill switch).
    """

    def __init__(
        self,
        helper: Path | None = None,
        launcher: Callable | None = None,
        elevated: Callable[[], bool] = running_as_admin,
        platform: str | None = None,
    ):
        self.helper = Path(helper) if helper else bundled_guard_path()
        self.launcher = launcher or subprocess.Popen
        self.elevated = elevated
        self.platform = platform or os.name
        self._lock = threading.RLock()
        self._process = None
        self._paths: dict[str, str] = {}

    def _is_running(self) -> bool:
        if self._process is None:
            return False
        if self._process.poll() is not None:
            self._process = None
            self._paths.clear()
            return False
        return True

    def managed(self) -> dict[str, str]:
        with self._lock:
            if not self._is_running():
                return {}
            return {
                hashlib.sha256(k.encode("utf-8")).hexdigest()[:20]: v
                for k, v in self._paths.items()
            }

    def _spawn(self, paths: list[str]):
        if self.platform != "nt":
            raise OSError("El motor WFP solo funciona en Windows")
        if not self.elevated():
            raise PermissionError(
                "BLOQUEAR con WFP necesita privilegios de administrador. "
                "Abre OneTunnel como administrador para aplicar filtros."
            )
        if not self.helper.is_file():
            raise FileNotFoundError(
                "No está incluido el motor nativo onetunnel-wfp-guard.exe. "
                "Usa el ejecutable Windows completo del pipeline actual."
            )
        args = [str(self.helper), "--block", *paths]
        process = self.launcher(
            args,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        # A bounded handshake avoids freezing Tk if the helper fails or hangs.
        ready = queue.Queue(maxsize=1)

        def read_ready():
            try:
                ready.put(process.stdout.readline())
            except (OSError, ValueError):
                ready.put("")

        threading.Thread(target=read_ready, daemon=True).start()
        try:
            line = ready.get(timeout=8)
            if line.strip() != f"READY {len(paths)}" or process.poll() is not None:
                raise RuntimeError(
                    "El motor WFP no confirmó la instalación de los filtros. "
                    "Comprueba permisos de administrador y el servicio BFE."
                )
        except (queue.Empty, RuntimeError):
            self._stop_process(process)
            raise RuntimeError(
                "No se pudo activar el bloqueo WFP nativo. "
                "No se han añadido filtros desde OneTunnel."
            )
        return process

    @staticmethod
    def _stop_process(process):
        if process is None:
            return
        try:
            if process.poll() is None:
                try:
                    process.stdin.write("stop\n")
                    process.stdin.flush()
                    process.stdin.close()
                except (OSError, ValueError):
                    pass
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
        finally:
            if process.stdout:
                process.stdout.close()

    def apply_paths(self, executables: Iterable[str]) -> dict[str, str]:
        paths = {}
        for raw in executables:
            path = _validate_path(raw)
            paths[executable_key(path)] = path
            if len(paths) > MAX_PATHS:
                raise ValueError("Límite temporal de 24 rutas WFP por sesión")
        with self._lock:
            self._is_running()
            if paths == self._paths:
                return self.managed()
            new_process = self._spawn(list(paths.values())) if paths else None
            old_process = self._process
            self._process = new_process
            self._paths = paths
            self._stop_process(old_process)
            return self.managed()

    def block(self, executable: str) -> str:
        path = _validate_path(executable)
        current = list(self.managed().values())
        self.apply_paths([*current, path])
        return hashlib.sha256(executable_key(path).encode("utf-8")).hexdigest()[:20]

    def unblock(self, executable: str) -> bool:
        key = executable_key(executable)
        current = self.managed()
        if not any(executable_key(path) == key for path in current.values()):
            return False
        self.apply_paths(path for path in current.values()
                         if executable_key(path) != key)
        return True

    def stop(self):
        with self._lock:
            old = self._process
            self._process = None
            self._paths.clear()
            self._stop_process(old)
