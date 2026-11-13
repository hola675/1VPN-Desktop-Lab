"""Motor integrado HTTP CONNECT + SOCKS5 TCP. No instala drivers ni captura procesos."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from proxycore import ProxyRelay, Upstream
from socks5_bridge import Socks5Bridge


@dataclass(frozen=True)
class LocalEndpoints:
    http_port: int
    socks5_port: int


class NetworkEngine:
    """Arranque transaccional de ambos listeners. Fallar uno revierte el otro."""

    def __init__(self, logger: Callable[[str], None] | None = None):
        self.logger = logger or (lambda _: None)
        self.http: ProxyRelay | None = None
        self.socks: Socks5Bridge | None = None

    @property
    def active(self) -> bool:
        return self.http is not None and self.socks is not None

    def start(self, upstream: Upstream, http_port: int = 8899, socks_port: int = 1080) -> LocalEndpoints:
        if self.http is not None or self.socks is not None:
            raise RuntimeError("Motor de proxy ya iniciado")
        if not isinstance(http_port, int) or not 0 <= http_port <= 65535:
            raise ValueError("Puerto HTTP local inválido")
        if not isinstance(socks_port, int) or not 0 <= socks_port <= 65535:
            raise ValueError("Puerto SOCKS5 local inválido")
        if http_port != 0 and http_port == socks_port:
            raise ValueError("HTTP y SOCKS5 deben escuchar en puertos diferentes")
        http = ProxyRelay(upstream.validated(), self.logger)
        try:
            actual_http_port = http.start(local_port=http_port)
            socks = Socks5Bridge(actual_http_port)
            try:
                actual_socks_port = socks.start(port=socks_port)
            except Exception:
                socks.stop()
                raise
            self.http = http
            self.socks = socks
            self.logger(
                f"Motor integrado activo: HTTP 127.0.0.1:{actual_http_port} "
                f"y SOCKS5 127.0.0.1:{actual_socks_port}"
            )
            return LocalEndpoints(actual_http_port, actual_socks_port)
        except Exception:
            http.stop()
            raise

    @property
    def endpoints(self) -> LocalEndpoints:
        if not self.active:
            raise RuntimeError("Motor de red detenido")
        return LocalEndpoints(self.http.port, self.socks.server.server_address[1])

    def stop(self):
        socks, http = self.socks, self.http
        self.socks = None
        self.http = None
        if socks is not None:
            socks.stop()
        if http is not None:
            http.stop()
