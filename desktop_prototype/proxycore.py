"""Proxy HTTP local -> proxy HTTPS remoto (TLS verificado).

Este módulo es código original de ejemplo. No contiene servidores ni credenciales de 1VPN.
No es un cliente VPN ni intercepta tráfico de aplicaciones que ignoran el proxy del SO.
"""
from __future__ import annotations

import base64
import re
import select
import socket
import socketserver
import ssl
import threading
from dataclasses import dataclass
from typing import Callable, Protocol

MAX_HEADER_BYTES = 65536
HOST_RE = re.compile(r"^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?$")


@dataclass(frozen=True)
class Upstream:
    host: str
    port: int
    username: str = ""
    password: str = ""

    def validated(self) -> "Upstream":
        if not HOST_RE.fullmatch(self.host) or ".." in self.host:
            raise ValueError("Nombre de servidor inválido")
        if not (1 <= self.port <= 65535):
            raise ValueError("El puerto debe estar entre 1 y 65535")
        if any(c in self.username for c in "\r\n:") or any(c in self.password for c in "\r\n"):
            raise ValueError("Credenciales inválidas")
        return self


def _inject_proxy_auth(header: bytes, upstream: Upstream) -> bytes:
    """Reescribe solo el bloque de cabeceras, no el cuerpo de la solicitud."""
    if not header.endswith(b"\r\n\r\n"):
        raise ValueError("Cabeceras incompletas")
    raw_lines = header[:-4].split(b"\r\n")
    if not raw_lines or not raw_lines[0]:
        raise ValueError("Solicitud HTTP inválida")
    # No trasladar credenciales proporcionadas por otro cliente local.
    lines = [raw_lines[0]]
    for line in raw_lines[1:]:
        key = line.split(b":", 1)[0].lower()
        if key not in (b"proxy-authorization", b"proxy-connection"):
            lines.append(line)
    if upstream.username or upstream.password:
        token = base64.b64encode(f"{upstream.username}:{upstream.password}".encode("utf-8"))
        lines.append(b"Proxy-Authorization: Basic " + token)
    lines.append(b"Proxy-Connection: close")
    return b"\r\n".join(lines) + b"\r\n\r\n"


def _recv_header(connection: socket.socket, max_bytes: int = MAX_HEADER_BYTES) -> tuple[bytes, bytes]:
    data = bytearray()
    while b"\r\n\r\n" not in data:
        chunk = connection.recv(min(4096, max_bytes - len(data)))
        if not chunk:
            raise ConnectionError("Se cerró la conexión al leer las cabeceras")
        data.extend(chunk)
        if len(data) >= max_bytes and b"\r\n\r\n" not in data:
            raise ValueError("Cabecera HTTP demasiado grande")
    pos = data.index(b"\r\n\r\n") + 4
    return bytes(data[:pos]), bytes(data[pos:])


def _relay(a: socket.socket, b: socket.socket, stop_event: threading.Event) -> None:
    """Intercambia bytes sin descifrar el contenido HTTPS de destino."""
    a.settimeout(None)
    b.settimeout(None)
    a.setblocking(False)
    b.setblocking(False)
    try:
        while not stop_event.is_set():
            readable, _, exceptional = select.select([a, b], [], [a, b], 1.0)
            if exceptional:
                break
            for source in readable:
                dest = b if source is a else a
                try:
                    chunk = source.recv(32768)
                    if not chunk:
                        return
                    # Sockets TLS no bloqueantes pueden necesitar reintentos.
                    memory = memoryview(chunk)
                    while memory and not stop_event.is_set():
                        try:
                            sent = dest.send(memory)
                            memory = memory[sent:]
                        except (BlockingIOError, ssl.SSLWantWriteError, ssl.SSLWantReadError):
                            select.select([], [dest], [], 0.5)
                except (BlockingIOError, ssl.SSLWantReadError, ssl.SSLWantWriteError):
                    continue
    finally:
        try:
            a.setblocking(True)
            b.setblocking(True)
        except OSError:
            pass


class CandidateSelector(Protocol):
    def candidates(self) -> tuple[Upstream, ...]: ...
    def mark_failure(self, upstream: Upstream, reason: str = "") -> None: ...
    def mark_success(self, upstream: Upstream) -> None: ...


class ProxyRelay:
    def __init__(self, upstream: Upstream, log: Callable[[str], None] | None = None,
                 selector: CandidateSelector | None = None):
        self.upstream = upstream.validated()
        self.log = log or (lambda msg: None)
        self.selector = selector
        self.stop_event = threading.Event()
        self.server: socketserver.ThreadingTCPServer | None = None
        self.thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        if self.server is None:
            raise RuntimeError("Servidor local no iniciado")
        return int(self.server.server_address[1])

    def start(self, local_port: int = 0) -> int:
        """Escucha solo en 127.0.0.1; 0 elige un puerto libre."""
        if not isinstance(local_port, int) or not 0 <= local_port <= 65535:
            raise ValueError("Puerto local inválido")
        if self.server:
            raise RuntimeError("El proxy ya está iniciado")
        relay = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self) -> None:
                client = self.request
                client.settimeout(15)
                established = False
                destination_port = "no identificado"
                stage = "lectura de solicitud local"
                last_error: Exception | None = None
                try:
                    header, extra = _recv_header(client)
                    first = header.split(b"\r\n", 1)[0]
                    is_connect = first.startswith(b"CONNECT ")
                    if not (is_connect or first.startswith((b"GET ", b"POST ", b"HEAD ", b"PUT ", b"DELETE ", b"OPTIONS ", b"PATCH "))):
                        client.sendall(b"HTTP/1.1 405 Method Not Allowed\r\nContent-Length: 0\r\n\r\n")
                        return
                    if is_connect:
                        authority = first.split(b" ", 2)[1]
                        candidate = authority.rsplit(b":", 1)[-1]
                        if candidate.isdigit() and 1 <= int(candidate) <= 65535:
                            destination_port = candidate.decode("ascii")
                    choices = relay.selector.candidates() if relay.selector is not None else (relay.upstream,)
                    if not choices:
                        raise RuntimeError("No hay servidores elegibles")
                    # No repetimos solicitudes HTTP normales (especialmente POST) después
                    # de enviarlas al upstream: podrían producir efectos duplicados.
                    if not is_connect:
                        choices = choices[:1]
                    for index, upstream in enumerate(choices):
                        try:
                            stage = "conexión TCP al proxy remoto"
                            with socket.create_connection((upstream.host, upstream.port), timeout=5) as raw:
                                stage = "negociación TLS con proxy remoto"
                                context = ssl.create_default_context()
                                with context.wrap_socket(raw, server_hostname=upstream.host) as remote:
                                    remote.settimeout(10)
                                    stage = "envío de solicitud al proxy remoto"
                                    remote.sendall(_inject_proxy_auth(header, upstream) + extra)
                                    if is_connect:
                                        stage = "respuesta CONNECT del proxy remoto"
                                        response, leftover = _recv_header(remote)
                                        parts = response.split(b"\r\n", 1)[0].split(b" ", 2)
                                        success = len(parts) >= 2 and parts[1] == b"200"
                                        if not success:
                                            status = parts[1].decode("ascii", "replace") if len(parts) > 1 else "?"
                                            if relay.selector is not None:
                                                relay.selector.mark_failure(upstream, f"HTTP {status}")
                                            relay.log(f"CONNECT remoto rechazado: HTTP {status}; puerto destino {destination_port}; "
                                                      f"candidato {index + 1}/{len(choices)}")
                                            if index + 1 < len(choices):
                                                continue
                                            # Conserva respuesta original del servidor (incluye 407).
                                            client.sendall(response)
                                            return
                                        client.sendall(response)
                                        if leftover:
                                            client.sendall(leftover)
                                        established = True
                                    if relay.selector is not None:
                                        relay.selector.mark_success(upstream)
                                    stage = "retransmisión de datos"
                                    _relay(client, remote, relay.stop_event)
                                    return
                        except (OSError, ssl.SSLError, ConnectionError, ValueError) as exc:
                            last_error = exc
                            if relay.selector is not None and not established:
                                relay.selector.mark_failure(upstream, type(exc).__name__)
                            relay.log(f"Fallo en {stage}: {type(exc).__name__}; puerto destino {destination_port}; "
                                      f"candidato {index + 1}/{len(choices)}. Sin salida directa.")
                            if established or index + 1 == len(choices):
                                break
                    if not established:
                        timeout = isinstance(last_error, TimeoutError)
                        status = b"HTTP/1.1 504 Gateway Timeout\r\n" if timeout else b"HTTP/1.1 502 Bad Gateway\r\n"
                        client.sendall(status + b"Content-Length: 0\r\nConnection: close\r\n\r\n")
                except (OSError, ssl.SSLError, ConnectionError, ValueError, RuntimeError) as exc:
                    relay.log(f"Fallo en {stage}: {type(exc).__name__}; puerto destino {destination_port}. Sin salida directa.")
                    if not established:
                        try:
                            client.sendall(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                        except OSError:
                            pass

        class Server(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True

        # Escuchar SOLO en bucle local; no se crea un proxy abierto a la LAN.
        self.server = Server(("127.0.0.1", local_port), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, name="local-proxy", daemon=True)
        self.thread.start()
        self.log(f"Proxy local iniciado en 127.0.0.1:{self.port}")
        return self.port

    def stop(self) -> None:
        self.stop_event.set()
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        if self.thread:
            self.thread.join(timeout=2)
            self.thread = None
        self.log("Proxy local detenido")
