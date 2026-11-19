"""External ProxiFyre adapter: prepare a safe, reviewable application-routing draft.

This module NEVER installs drivers/services, applies Windows Firewall rules,
reads credentials, changes default routes, or starts ProxiFyre. The native
application/packet capture belongs to the separately installed ProxiFyre
(AGPL-3.0) and Windows Packet Filter.

Current 1VPN Desktop Lab SOCKS5 endpoint is TCP CONNECT only. Therefore this
draft deliberately advertises TCP+IPv4 only and DNS Direct, with warnings.
UDP, DNS, DoH, IPv6, and a kill switch are NOT guaranteed by this profile.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable

from traffic_policy import AppPolicy, executable_key, normalize_executable

# ProxiFyre performs permissive name matching for its excludes; keep these
# focused on transport owners/critical processes, not generic broad names.
EXCLUDED_CARRIERS = (
    "1VPN-Desktop-Lab.exe",
    "ProxiFyre.exe",
    "python.exe",
    "pythonw.exe",
    "xray.exe",
)
DENIED_TARGETS = frozenset(name.casefold() for name in EXCLUDED_CARRIERS) | {
    "svchost.exe", "lsass.exe", "services.exe", "winlogon.exe",
    "smss.exe", "csrss.exe", "dwm.exe",
}

MAX_TARGET_APPS = 24
DRAFT_FILE_NAME = "onetunnel-proxifyre-tcp-draft.json"


def build_proxifyre_draft(
    policies: Iterable[AppPolicy],
    socks5_port: int,
    managed_firewall_programs: Iterable[str] = (),
) -> dict:
    """Build a *non-active*, secret-free app-config draft from explicit choices.

    Only saved TRANSPARENT policies are exported. Targets must exist, be
    unique and not be an essential Windows process, the proxy carrier, or
    an executable with a known outbound BLOCK firewall rule.
    """
    if type(socks5_port) is not int or not 1 <= socks5_port <= 65535:
        raise ValueError("Puerto SOCKS5 local inválido")
    blocked = {executable_key(p) for p in managed_firewall_programs}
    chosen: list[str] = []
    seen: set[str] = set()
    for policy in policies:
        if policy.mode != "TRANSPARENT":
            continue
        exe = normalize_executable(policy.executable)
        name = Path(exe).name.casefold()
        if name in DENIED_TARGETS:
            raise ValueError(
                "No se permite redirigir el ejecutable del motor, ProxiFyre "
                "o un proceso esencial de Windows"
            )
        key = executable_key(exe)
        if key in blocked:
            raise ValueError(
                "Una aplicación seleccionada tiene BLOQUEO saliente "
                "gestionado; retira esa regla antes de configurar ProxiFyre"
            )
        if key in seen:
            raise ValueError("Hay ejecutables duplicados")
        seen.add(key)
        chosen.append(exe)
        if len(chosen) > MAX_TARGET_APPS:
            raise ValueError("Demasiadas aplicaciones seleccionadas para este laboratorio")

    if not chosen:
        raise ValueError(
            "Guarda una política TRANSPARENTE para un .exe concreto "
            "antes de preparar el perfil ProxiFyre"
        )

    return {
        "logLevel": "Info",
        # Explicit choice: local private networks bypass this proxy.
        "bypassLan": True,
        "proxies": [{
            "id": "onetunnel-tcp-only",
            # Absolute paths are an explicit opt-in; never catch all ("").
            "appNames": chosen,
            "socks5ProxyEndpoint": f"127.0.0.1:{socks5_port}",
            "socks5Transport": "TCP",
            # The current SOCKS5 -> HTTP CONNECT bridge cannot forward UDP.
            "supportedProtocols": ["TCP"],
            # ProxiFyre blocks unsupported address families for matched traffic.
            "supportedAddressFamilies": ["IPv4"],
        }],
        "excludes": list(EXCLUDED_CARRIERS),
        # DNS Direct can leak queries: never claim leak protection.
        "dns": {"mode": "Direct"},
    }


def describe_proxifyre_draft(config: dict) -> str:
    """Human-readable warnings without credentials or external services."""
    rule = config["proxies"][0]
    targets = rule["appNames"]
    lines = [
        "BORRADOR PROXIFYRE — NO ACTIVADO",
        f"Aplicaciones seleccionadas: {len(targets)}",
        *(f"  - {Path(app).name}" for app in targets),
        f"SOCKS5 local: {rule['socks5ProxyEndpoint']}",
        "Protocolo: TCP CONNECT; IPv4 solamente",
        "DNS: DIRECTO (riesgo de fuga DNS)",
        "UDP/QUIC: NO protegido por este puente; puede salir directo",
        "LAN: DIRECTA por decisión explícita",
        "Sin kill switch; NO garantiza ausencia de fugas",
        "No se instaló ningún controlador ni se modificó el firewall",
        "Debe aplicarse manualmente con ProxiFyre oficial, tras revisar sus opciones",
        "No configures simultáneamente BLOQUEO saliente de Windows para esta app",
    ]
    return "\n".join(lines)


def save_proxifyre_draft(destination: str | Path, config: dict) -> Path:
    """Write once to a review file, never overwrite a live ProxiFyre config."""
    path = Path(destination)
    if path.suffix.lower() != ".json":
        raise ValueError("El borrador debe guardarse como archivo .json")
    if path.name.casefold() == "app-config.json":
        raise ValueError(
            "No está permitido sustituir directamente el archivo app-config.json "
            "de ProxiFyre; utiliza un borrador y aplica cambios desde su GUI"
        )
    if not path.parent.is_dir():
        raise ValueError("La carpeta de destino no existe")
    # Reject all external endpoint/secrets fields even if a caller edited config.
    if set(config) != {"logLevel", "bypassLan", "proxies", "excludes", "dns"}:
        raise ValueError("Configuración inesperada")
    serialized = json.dumps(config, ensure_ascii=False, indent=2) + "\n"
    # Never overwrite and never follow an existing link: no unexpected changes
    # to an installed service or a file someone else manages.
    with path.open("x", encoding="utf-8") as file:
        file.write(serialized)
    return path
