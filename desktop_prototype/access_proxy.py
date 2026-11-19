"""Proxy de acceso de la red -> servidores 1VPN.

Esta capa se usa SOLO cuando la red local exige un proxy HTTP CONNECT para
salir a Internet. Si está activada y falla, OneTunnel NO hace fallback directo.
"""
from __future__ import annotations

import base64
import re
import socket
from dataclasses import dataclass, field

MAX_HEADER_BYTES = 65536
HOST_RE = re.compile(r"^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?$")
IPV4_RE = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")


@dataclass(frozen=True)
class AccessProxy:
    host: str
    port: int
    username: str = ""
    password: str = field(default="", repr=False)

    def validated(self) -> "AccessProxy":
        host = self.host.strip()
        if not host or any(c in host for c in "\r\n /\\"):
            raise ValueError("Host del proxy de red inválido")
        if not (HOST_RE.fullmatch(host) or IPV4_RE.fullmatch(host)):
            raise ValueError("Host del proxy de red inválido")
        if not isinstance(self.port, int) or not 1 <= self.port <= 65535:
            raise ValueError("Puerto del proxy de red inválido")
        if any(c in self.username for c in "\r\n:") or any(c in self.password for c in "\r\n"):
            raise ValueError("Credenciales del proxy de red inválidas")
        return AccessProxy(host, self.port, self.username, self.password)


def _recv_header(connection: socket.socket, max_bytes: int = MAX_HEADER_BYTES) -> bytes:
    data = bytearray()
    while b"\r\n\r\n" not in data:
        chunk = connection.recv(min(4096, max_bytes - len(data)))
        if not chunk:
            raise ConnectionError("El proxy de red cerró la conexión")
        data.extend(chunk)
        if len(data) >= max_bytes and b"\r\n\r\n" not in data:
            raise ValueError("Respuesta del proxy de red demasiado grande")
    pos = data.index(b"\r\n\r\n") + 4
    return bytes(data[:pos])


def _connect_request(proxy: AccessProxy, target_host: str, target_port: int) -> bytes:
    authority = f"{target_host}:{target_port}"
    lines = [
        f"CONNECT {authority} HTTP/1.1",
        f"Host: {authority}",
        "Proxy-Connection: keep-alive",
        "Connection: keep-alive",
    ]
    if proxy.username or proxy.password:
        token = base64.b64encode(
            f"{proxy.username}:{proxy.password}".encode("utf-8")
        ).decode("ascii")
        lines.append(f"Proxy-Authorization: Basic {token}")
    return ("\r\n".join(lines) + "\r\n\r\n").encode("ascii")


def open_via_access_proxy(
    proxy: AccessProxy,
    target_host: str,
    target_port: int,
    *,
    timeout: float = 6.0,
) -> socket.socket:
    """Abre un túnel TCP CONNECT. Nunca conecta directamente al destino."""
    proxy = proxy.validated()
    if not HOST_RE.fullmatch(target_host) or ".." in target_host:
        raise ValueError("Destino del túnel inválido")
    if not isinstance(target_port, int) or not 1 <= target_port <= 65535:
        raise ValueError("Puerto destino inválido")

    sock = socket.create_connection((proxy.host, proxy.port), timeout=timeout)
    try:
        sock.settimeout(timeout)
        sock.sendall(_connect_request(proxy, target_host, target_port))
        response = _recv_header(sock)
        status_line = response.split(b"\r\n", 1)[0].split(b" ", 2)
        if len(status_line) < 2:
            raise ConnectionError("Respuesta inválida del proxy de red")
        code = status_line[1].decode("ascii", "replace")
        if code != "200":
            if code == "407":
                raise PermissionError(
                    "El proxy de red rechazó la autenticación (HTTP 407)"
                )
            raise ConnectionError(f"El proxy de red rechazó CONNECT (HTTP {code})")
        return sock
    except Exception:
        sock.close()
        raise
