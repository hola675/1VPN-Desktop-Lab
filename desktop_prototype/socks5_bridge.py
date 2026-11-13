"""SOCKS5 CONNECT TCP (127.0.0.1) -> proxy HTTP CONNECT del laboratorio.

No implementa UDP, BIND, redirección transparente ni Wintun.
Uso: python socks5_bridge.py --http-port 8899 --port 1080
"""
from __future__ import annotations

import argparse
import ipaddress
import re
import socket
import socketserver
import struct
import threading

from proxycore import _recv_header, _relay


def read_exact(sock, size):
    out = bytearray()
    while len(out) < size:
        piece = sock.recv(size - len(out))
        if not piece:
            raise ConnectionError("SOCKS5: conexión cerrada")
        out.extend(piece)
    return bytes(out)


def target_from_request(sock):
    version, command, reserved, atyp = read_exact(sock, 4)
    if version != 5 or reserved != 0:
        raise ValueError("SOCKS5 request incorrecto")
    if command != 1:
        raise NotImplementedError("Solo CONNECT TCP, no UDP/BIND")
    if atyp == 1:
        host = str(ipaddress.IPv4Address(read_exact(sock, 4)))
    elif atyp == 4:
        host = f"[{ipaddress.IPv6Address(read_exact(sock, 16))}]"
    elif atyp == 3:
        length = read_exact(sock, 1)[0]
        if not length:
            raise ValueError("Dominio vacío")
        host = read_exact(sock, length).decode("ascii")
        if not re.fullmatch(r"(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", host) or ".." in host:
            raise ValueError("Dominio inválido")
    else:
        raise ValueError("ATYP no soportado")
    port = struct.unpack("!H", read_exact(sock, 2))[0]
    if not port:
        raise ValueError("Puerto destino inválido")
    return f"{host}:{port}"


def send_reply(sock, code):
    sock.sendall(bytes((5, code, 0, 1)) + b"\x00" * 6)


class Socks5Bridge:
    def __init__(self, http_port):
        if not isinstance(http_port, int) or not 1 <= http_port <= 65535:
            raise ValueError("Puerto HTTP local inválido")
        self.http_port = http_port
        self.stop_event = threading.Event()
        self.server = None
        self.thread = None

    def start(self, port=1080):
        if not isinstance(port, int) or not 0 <= port <= 65535:
            raise ValueError("Puerto SOCKS5 inválido")
        if self.server is not None:
            raise RuntimeError("Ya iniciado")
        bridge = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                client = self.request
                client.settimeout(15)
                sent_success = False
                try:
                    version, count = read_exact(client, 2)
                    if version != 5 or count == 0:
                        return
                    offered = read_exact(client, count)
                    if 0 not in offered:
                        client.sendall(b"\x05\xff")
                        return
                    client.sendall(b"\x05\x00")
                    try:
                        target = target_from_request(client)
                    except NotImplementedError:
                        send_reply(client, 7)
                        return
                    except (ValueError, UnicodeError):
                        send_reply(client, 8)
                        return
                    with socket.create_connection(("127.0.0.1", bridge.http_port), timeout=10) as proxy:
                        proxy.settimeout(15)
                        request = f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n"
                        proxy.sendall(request.encode("ascii"))
                        headers, excess = _recv_header(proxy)
                        line = headers.split(b"\r\n", 1)[0]
                        if not re.match(rb"^HTTP/1\.[01] 200(?: |$)", line):
                            send_reply(client, 5)
                            return
                        send_reply(client, 0)
                        sent_success = True
                        if excess:
                            client.sendall(excess)
                        _relay(client, proxy, bridge.stop_event)
                except (OSError, ValueError, ConnectionError):
                    if not sent_success:
                        try:
                            send_reply(client, 1)
                        except OSError:
                            pass

        class Server(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True

        self.server = Server(("127.0.0.1", port), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, name="SOCKS5-bridge", daemon=True)
        self.thread.start()
        return self.server.server_address[1]

    def stop(self):
        self.stop_event.set()
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        if self.thread is not None:
            self.thread.join(timeout=2)
            self.thread = None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--http-port", type=int, default=8899)
    parser.add_argument("--port", type=int, default=1080)
    opts = parser.parse_args()
    bridge = Socks5Bridge(opts.http_port)
    port = bridge.start(opts.port)
    print(f"SOCKS5 TCP en 127.0.0.1:{port}; conectando a HTTP CONNECT en 127.0.0.1:{opts.http_port}")
    print("Controlador de captura NO instalado. Detener con Ctrl+C.")
    try:
        while True:
            threading.Event().wait(1)
    except KeyboardInterrupt:
        bridge.stop()
