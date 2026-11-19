"""Explicit lab certification for OneTunnel's transparent WFP PROXY.

This does not install or sign a driver and never runs automatically. It requires:
- Premium HTTP/SOCKS transport already verified;
- a trusted callout driver already installed and RUNNING;
- no existing transparent PROXY session;
- explicit UI confirmation.

A bundled WinHTTP probe is captured by WFP and makes one HTTPS request with
WINHTTP_ACCESS_TYPE_NO_PROXY. Matching the Premium egress IP demonstrates that
traffic was redirected below the application proxy layer.
"""
from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import os
from pathlib import Path
import subprocess
import sys

from driver_lifecycle import SignedDriverLifecycle
from native_proxy import NativeProxySession


@dataclass(frozen=True)
class CertificationResult:
    expected_ip: str
    observed_ip: str
    transparent_proxy_verified: bool


def bundled_egress_probe_path() -> Path:
    name = "onetunnel-egress-probe.exe"
    locations = [
        Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / name,
        Path(__file__).resolve().parent.parent / "native" / "wfp" / "build" / "Release" / name,
    ]
    return next((p for p in locations if p.is_file()), locations[0])


def _clean_environment() -> dict[str, str]:
    env = os.environ.copy()
    for key in (
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
        "http_proxy", "https_proxy", "all_proxy", "no_proxy",
    ):
        env.pop(key, None)
    return env


def _parse_probe_output(output: str) -> str:
    line = output.strip()
    if not line.startswith("PASS "):
        raise RuntimeError("El probe nativo no confirmó una salida HTTPS válida")
    candidate = line[5:].strip()
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError as error:
        raise RuntimeError("El probe nativo devolvió una IP inválida") from error


def certify_transparent_proxy(
    *,
    native_proxy: NativeProxySession,
    driver_lifecycle: SignedDriverLifecycle,
    socks5_port: int,
    expected_ip: str,
    probe_path: Path | None = None,
    runner=subprocess.run,
    platform: str | None = None,
) -> CertificationResult:
    """Run one bounded, reversible certification transaction.

    The routine never changes driver installation state. It only creates a
    temporary dynamic WFP PROXY session for the dedicated probe executable,
    performs one HTTPS request, compares egress, then removes the filters.
    """
    platform = platform or os.name
    if platform != "nt":
        raise OSError("La certificación WFP solo está disponible en Windows")
    if native_proxy.active():
        raise RuntimeError(
            "Detén primero cualquier sesión PROXY WFP activa; la certificación "
            "no interrumpe ni reemplaza sesiones existentes."
        )
    if not driver_lifecycle.service_running():
        raise RuntimeError(
            "El callout WFP firmado no está RUNNING. Verifica/instala/inicia "
            "el paquete firmado antes de certificar."
        )
    if type(socks5_port) is not int or not 1 <= socks5_port <= 65535:
        raise ValueError("Puerto SOCKS5 local inválido")
    try:
        expected = str(ipaddress.ip_address(expected_ip))
    except ValueError as error:
        raise ValueError("La IP Premium esperada no es válida") from error

    probe = Path(probe_path) if probe_path else bundled_egress_probe_path()
    if not probe.is_file():
        raise FileNotFoundError(
            "Esta compilación no contiene onetunnel-egress-probe.exe"
        )

    started = False
    try:
        native_proxy.start([str(probe)], socks5_port)
        started = True
        result = runner(
            [str(probe)],
            capture_output=True,
            text=True,
            timeout=25,
            check=False,
            env=_clean_environment(),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0:
            raise RuntimeError(
                "El probe HTTPS no pudo completar la conexión mediante WFP "
                f"(código {result.returncode})."
            )
        observed = _parse_probe_output(result.stdout)
        if observed != expected:
            raise RuntimeError(
                "La IP observada por el probe no coincide con la salida Premium "
                "verificada. No se certifica PROXY transparente."
            )
        return CertificationResult(expected, observed, True)
    finally:
        if started:
            native_proxy.stop()
