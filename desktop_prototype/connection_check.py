"""Prueba de salida HTTPS obligatoriamente A TRAVÉS del proxy HTTP local.

No consulta direcciones IP mediante una conexión directa, no altera variables de
entorno ni establece un proxy de sistema. No registra tokens ni credenciales.
"""
from __future__ import annotations

import http.client
import ipaddress
import json
import ssl

VERIFY_HOST = "api.ipify.org"
VERIFY_PATH = "/?format=json"


def probe_exit_ip(local_port: int, timeout: float = 15.0) -> str:
    """Devuelve la IP pública observada por el servicio de comprobación.

    HTTPSConnection hacia 127.0.0.1 establece HTTP CONNECT primero, y SOLO
    después negocia TLS con api.ipify.org dentro del túnel. No hay fallback
    directo si el proxy falla. La CA y el hostname de destino se verifican.
    """
    if not isinstance(local_port, int) or not 1 <= local_port <= 65535:
        raise ValueError("Puerto local no válido")
    conn = http.client.HTTPSConnection(
        "127.0.0.1", local_port,
        timeout=timeout,
        context=ssl.create_default_context(),
    )
    conn.set_tunnel(VERIFY_HOST, 443)
    try:
        conn.request(
            "GET", VERIFY_PATH,
            headers={"Host": VERIFY_HOST, "Accept": "application/json", "Connection": "close"},
        )
        response = conn.getresponse()
        if response.status != 200:
            raise ConnectionError(f"La comprobación de salida respondió HTTP {response.status}")
        raw = response.read(4096)
        data = json.loads(raw.decode("utf-8"))
        ip = data.get("ip")
        if not isinstance(ip, str):
            raise ValueError("No se recibió una dirección IP")
        return str(ipaddress.ip_address(ip))
    finally:
        conn.close()
