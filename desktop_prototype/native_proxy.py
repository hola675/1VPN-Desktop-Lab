"""Supervisor for OneTunnel's first-party transparent TCP PROXY session.

This module does not install or load a kernel driver. start() succeeds only if
the signed callout driver is ALREADY loaded and registered in BFE: the native
control process checks that invariant before adding any traffic filter.

The UI may select policies by EXE basename, but this supervisor intentionally
accepts concrete, existing executable paths resolved from current processes.
"""
from __future__ import annotations

from pathlib import Path
import os
import queue
import subprocess
import sys
import threading
from typing import Iterable

from native_wfp import FORBIDDEN_APP_NAMES
from traffic_policy import app_name_from_path, executable_key, normalize_executable

_START_TIMEOUT_SECONDS = 8
_MAX_APPS = 24


def _bundled(name: str) -> Path:
    locations = [
        Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / name,
        Path(__file__).resolve().parent.parent / "native" / "wfp" / "build" / "Release" / name,
    ]
    return next((p for p in locations if p.is_file()), locations[0])


def bundled_relay_path() -> Path:
    return _bundled("onetunnel-transparent-relay.exe")


def bundled_control_path() -> Path:
    return _bundled("onetunnel-wfp-control.exe")


def _normalized_apps(paths: Iterable[str]) -> list[str]:
    result: dict[str, str] = {}
    for raw in paths:
        path = normalize_executable(raw)
        if app_name_from_path(path) in FORBIDDEN_APP_NAMES:
            raise ValueError("No se permite redirigir el motor VPN o procesos críticos")
        result[executable_key(path)] = path
        if len(result) > _MAX_APPS:
            raise ValueError("Máximo temporal: 24 rutas PROXY por sesión")
    if not result:
        raise ValueError("No hay rutas de aplicaciones para PROXY")
    return list(result.values())


class NativeProxySession:
    """Own relay + dynamic BFE controller as one transactional session."""

    def __init__(
        self,
        relay: Path | None = None,
        control: Path | None = None,
        launcher=None,
        platform: str | None = None,
    ):
        self.relay = Path(relay) if relay else bundled_relay_path()
        self.control = Path(control) if control else bundled_control_path()
        self.launcher = launcher or subprocess.Popen
        self.platform = platform or os.name
        self._lock = threading.RLock()
        self._relay_process = None
        self._control_process = None
        self._relay_port = None
        self._apps: tuple[str, ...] = ()

    @staticmethod
    def _readline_with_timeout(process, seconds=_START_TIMEOUT_SECONDS) -> str:
        result = queue.Queue(maxsize=1)

        def reader():
            try:
                result.put(process.stdout.readline())
            except (OSError, ValueError):
                result.put("")

        threading.Thread(target=reader, daemon=True).start()
        try:
            return result.get(timeout=seconds).strip()
        except queue.Empty:
            return ""

    @staticmethod
    def _stop(process):
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
            if getattr(process, "stdout", None):
                try:
                    process.stdout.close()
                except (OSError, ValueError):
                    pass

    def active(self) -> bool:
        with self._lock:
            return (
                self._relay_process is not None
                and self._control_process is not None
                and self._relay_process.poll() is None
                and self._control_process.poll() is None
            )

    @property
    def relay_port(self) -> int | None:
        return self._relay_port if self.active() else None

    @property
    def apps(self) -> tuple[str, ...]:
        return self._apps if self.active() else ()

    def start(self, executable_paths: Iterable[str], socks5_port: int):
        apps = _normalized_apps(executable_paths)
        if self.platform != "nt":
            raise OSError("PROXY WFP nativo solo está disponible en Windows")
        if type(socks5_port) is not int or not 1 <= socks5_port <= 65535:
            raise ValueError("Puerto SOCKS5 local inválido")
        if not self.relay.is_file() or not self.control.is_file():
            raise FileNotFoundError(
                "Esta compilación no contiene relay/control WFP nativos completos"
            )

        with self._lock:
            if self.active():
                raise RuntimeError("Ya existe una sesión PROXY WFP activa")

            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            relay = self.launcher(
                [str(self.relay), "--listen-port", "0",
                 "--socks-port", str(socks5_port)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, creationflags=flags,
            )
            line = self._readline_with_timeout(relay)
            fields = line.split()
            if (len(fields) != 3 or fields[0] != "READY"
                    or not fields[1].isdigit()
                    or int(fields[2]) != socks5_port
                    or relay.poll() is not None):
                self._stop(relay)
                raise RuntimeError("El relay transparente no pudo iniciar de forma segura")
            relay_port = int(fields[1])
            if not 1 <= relay_port <= 65535:
                self._stop(relay)
                raise RuntimeError("El relay devolvió un puerto inválido")

            args = [
                str(self.control),
                "--relay-pid", str(relay.pid),
                "--relay-port", str(relay_port),
            ]
            for path in apps:
                args.extend(["--app", path])

            control = self.launcher(
                args,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, creationflags=flags,
            )
            control_line = self._readline_with_timeout(control)
            if (control_line != f"READY {len(apps)}" or control.poll() is not None):
                # If callout driver is absent/unregistered, controller exits before
                # traffic filters are committed. Always stop the relay too.
                self._stop(control)
                self._stop(relay)
                raise RuntimeError(
                    "El callout WFP firmado no está cargado/registrado o BFE "
                    "rechazó la sesión. No se activó PROXY transparente."
                )

            self._relay_process = relay
            self._control_process = control
            self._relay_port = relay_port
            self._apps = tuple(apps)
            return {
                "relay_port": relay_port,
                "application_paths": self._apps,
            }

    def stop(self):
        with self._lock:
            control = self._control_process
            relay = self._relay_process
            self._control_process = None
            self._relay_process = None
            self._relay_port = None
            self._apps = ()
            # Control first: closing its dynamic BFE session removes filters.
            self._stop(control)
            self._stop(relay)
