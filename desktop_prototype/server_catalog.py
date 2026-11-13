"""Catálogo Free de 1VPN: snapshot público + actualización HTTPS verificable.

No contiene tokens ni credenciales. Sólo admite ubicaciones Free conocidas
para evitar confundir ubicaciones Premium con servidores públicos.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
import urllib.request

SOURCE = "https://github.com/1vpn/browser-extension/blob/main/src/utils/freeLocations.js"
API_URL = "https://1vpn.org/api/get_proxy_servers/"
MAX_BYTES = 128 * 1024
COUNTRIES = {"sgp": ("Singapur", "Singapur"), "ams": ("Ámsterdam", "Países Bajos"), "lax": ("Los Ángeles", "Estados Unidos")}
# Dominios presentes en el catálogo Free público (v4.2.1, 2026-11-03).
TRUSTED_SUFFIXES = (".cloudburstcdn.com", ".cloudflingcdn.com", ".cloudflaracdn.com", ".cloudtimecdn.com", ".weathercloudapp.com")
HOST_RE = re.compile(r"^[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?$")

SNAPSHOT = {
    "sgp": [
        "free-singapore-https-1.cloudburstcdn.com",
        "free-singapore-https-2.cloudtimecdn.com",
        "free-singapore-https-3.weathercloudapp.com",
        "free-singapore-https-4.cloudflingcdn.com",
    ],
    "ams": [
        "free-amsterdam-https-1.cloudburstcdn.com",
        "free-amsterdam-https-2.cloudflingcdn.com",
        "free-amsterdam-https-3.cloudflaracdn.com",
        "free-amsterdam-https-4.cloudflaracdn.com",
        "free-amsterdam-https-5.cloudflingcdn.com",
        "free-amsterdam-https-6.cloudflingcdn.com",
    ],
    "lax": [
        "free-los-angeles-https-1.cloudburstcdn.com",
        "free-los-angeles-https-2.cloudtimecdn.com",
        "free-los-angeles-https-3.cloudflaracdn.com",
        "free-los-angeles-https-4.cloudflaracdn.com",
        "free-los-angeles-https-5.cloudflingcdn.com",
        "free-los-angeles-https-6.cloudflingcdn.com",
    ],
}


@dataclass(frozen=True)
class ServerEndpoint:
    region: str
    hostname: str
    port: int = 443

    @property
    def label(self) -> str:
        return f"{COUNTRIES[self.region][0]} · {self.hostname}"


def snapshot_catalogue() -> tuple[ServerEndpoint, ...]:
    return tuple(ServerEndpoint(region, hostname) for region in COUNTRIES for hostname in SNAPSHOT[region])


def _trusted_host(value: object) -> bool:
    if not isinstance(value, str) or not HOST_RE.fullmatch(value):
        return False
    return ".." not in value and any(value.endswith(suffix) for suffix in TRUSTED_SUFFIXES)


def parse_free_catalogue(data: object) -> tuple[ServerEndpoint, ...]:
    """Valida JSON del endpoint público; nunca habilita hosts Premium."""
    if not isinstance(data, dict):
        raise ValueError("Catálogo sin estructura de ubicaciones")
    endpoints: list[ServerEndpoint] = []
    for region in COUNTRIES:
        entry = data.get(region)
        if not isinstance(entry, dict) or entry.get("isPremium") is True:
            continue
        hosts = entry.get("hosts")
        if not isinstance(hosts, list):
            continue
        for host in hosts[:40]:
            if not isinstance(host, dict):
                continue
            hostname, port = host.get("hostname"), host.get("port")
            if _trusted_host(hostname) and type(port) is int and port == 443:
                endpoint = ServerEndpoint(region, hostname.lower(), port)
                if endpoint not in endpoints:
                    endpoints.append(endpoint)
    if not endpoints:
        raise ValueError("No hay servidores Free admisibles")
    return tuple(endpoints)


def refresh_catalogue(timeout: float = 4.0) -> tuple[ServerEndpoint, ...]:
    """HTTPS con validación estándar y límite de descarga; falla sin estado parcial.

    No envía tokens ni contraseñas, solo consulta el catálogo público.
    """
    request = urllib.request.Request(API_URL, headers={"Accept": "application/json", "User-Agent": "1VPN-Desktop-Lab/0.4.1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise ValueError("Catálogo remoto demasiado grande")
    return parse_free_catalogue(json.loads(body.decode("utf-8")))
