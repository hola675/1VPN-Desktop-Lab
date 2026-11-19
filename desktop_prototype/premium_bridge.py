"""Explicit browser-to-desktop Premium handoff. No browser cookie/extension storage reads.

The authenticated 1VPN page, when supported by its API, explicitly returns
the web session to a companion browser extension after user interaction.
That extension POSTs it to one-time, loopback-only, short-lived receiver.

This protocol is experimental: the official website does NOT publish a
desktop auth-code contract. We never claim login success without proxy egress.
"""
from __future__ import annotations

from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import ipaddress
import json
import re
import secrets
import threading
import time
from typing import Callable

from account_auth import AccountSession

MAX_PAYLOAD = 32768
EXPIRES_SECONDS = 300
EXTENSION_ORIGIN = re.compile(r"^chrome-extension://[a-p]{32}$")
DNS_HOST = re.compile(
    r"^(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]*[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+$"
)
CITY_CODE = re.compile(r"^[a-z0-9]{2,10}$")
USER_ID = re.compile(r"^[^\s\r\n]{1,256}$")


def _valid_proxy_host(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    host = raw.lower()
    if not DNS_HOST.fullmatch(host) or ".." in host:
        return None
    if any(len(part) > 63 for part in host.split(".")):
        return None
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return host
    return None


def parse_browser_session(data: object) -> AccountSession:
    """Accept ONLY a minimally valid Premium account and DNS proxy endpoints.

    Hostnames originate from an official-origin HTTPS API call but are
    untrusted until the TLS+CONNECT+egress check. No arbitrary URLs or IPs.
    """
    if not isinstance(data, dict):
        raise ValueError("Respuesta de sesión no válida")
    username, token = data.get("username"), data.get("sessionAuthToken")
    if data.get("isPremium") is not True:
        raise ValueError("La respuesta no acredita una cuenta Premium")
    if not isinstance(username, str) or not USER_ID.fullmatch(username):
        raise ValueError("Identificador Premium no válido")
    if not isinstance(token, str) or not 10 <= len(token) <= 4096:
        raise ValueError("Token Premium ausente o inválido")
    if any(ord(c) < 33 or ord(c) > 126 for c in token):
        raise ValueError("Formato de token Premium inválido")

    locations = data.get("locations")
    if isinstance(locations, dict):
        entries = list(locations.values())
    elif isinstance(locations, list):
        entries = locations
    else:
        raise ValueError("No hay ubicaciones Premium verificables")
    if len(entries) > 256:
        raise ValueError("Demasiadas ubicaciones Premium")

    endpoints: list[tuple[str, str, int]] = []
    for loc in entries:
        if not isinstance(loc, dict):
            continue
        code = loc.get("cityCode")
        if not isinstance(code, str) or not CITY_CODE.fullmatch(code):
            continue
        hosts = loc.get("hosts")
        if not isinstance(hosts, list):
            continue
        for item in hosts[:32]:
            if not isinstance(item, dict):
                continue
            host = _valid_proxy_host(item.get("hostname"))
            port = item.get("port", 443)
            if host and type(port) is int and port == 443:
                entry = (code, host, port)
                if entry not in endpoints:
                    endpoints.append(entry)
            if len(endpoints) >= 256:
                break
    if not endpoints:
        raise ValueError("No se recibieron servidores HTTPS Premium válidos")

    email = data.get("email")
    if not isinstance(email, str) or len(email) > 254 or "@" not in email:
        email = "Cuenta Premium (navegador)"
    return AccountSession(
        email=email,
        username=username,
        is_premium=True,
        session_token=token,
        source="browser_web",
        proxy_locations=tuple(endpoints),
    )


@dataclass(frozen=True)
class PairingDetails:
    port: int
    code: str


class PremiumBrowserBridge:
    """Single-use handoff with bounded body and Chrome-extension origin only."""

    def __init__(self):
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._expires_at = 0.0
        self._code = ""
        self._lock = threading.Lock()

    def start(self, on_session: Callable[[AccountSession], None]) -> PairingDetails:
        with self._lock:
            if self._server is not None:
                raise RuntimeError("Ya hay un emparejamiento abierto")
            self._expires_at = time.monotonic() + EXPIRES_SECONDS
            self._code = secrets.token_urlsafe(24)
            owner = self

            class Handler(BaseHTTPRequestHandler):
                def log_message(self, *_args):
                    # NEVER log request headers/body, tokens or pairing code.
                    pass

                def _origin(self):
                    origin = self.headers.get("Origin", "")
                    return origin if EXTENSION_ORIGIN.fullmatch(origin) else None

                def _reply(self, status: int, message: str):
                    body = json.dumps({"ok": status == 200, "message": message}).encode()
                    self.send_response(status)
                    origin = self._origin()
                    if origin:
                        self.send_header("Access-Control-Allow-Origin", origin)
                        self.send_header("Vary", "Origin")
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

                def do_OPTIONS(self):
                    if self.path != "/premium-session" or not self._origin():
                        self._reply(403, "Origen no autorizado")
                        return
                    self.send_response(204)
                    self.send_header("Access-Control-Allow-Origin", self._origin())
                    self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
                    self.send_header("Access-Control-Allow-Headers", "Content-Type, X-OneTunnel-Pairing")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", "0")
                    self.end_headers()

                def do_POST(self):
                    expected_host = f"127.0.0.1:{self.server.server_port}"
                    if (self.path != "/premium-session"
                            or self.headers.get("Host") != expected_host
                            or not self._origin()):
                        self._reply(403, "Origen no autorizado")
                        return
                    try:
                        size = int(self.headers.get("Content-Length", "-1"))
                    except ValueError:
                        size = -1
                    if size < 1 or size > MAX_PAYLOAD:
                        self._reply(413, "Tamaño no permitido")
                        return
                    if not self.headers.get("Content-Type", "").lower().startswith("application/json"):
                        self._reply(415, "Formato no permitido")
                        return
                    supplied = self.headers.get("X-OneTunnel-Pairing", "")
                    with owner._lock:
                        allowed = (owner._server is self.server
                                   and time.monotonic() < owner._expires_at
                                   and bool(owner._code)
                                   and hmac.compare_digest(supplied, owner._code))
                        if not allowed:
                            self._reply(403, "Emparejamiento no válido o caducado")
                            return
                        try:
                            session = parse_browser_session(json.loads(self.rfile.read(size)))
                        except (ValueError, UnicodeError, json.JSONDecodeError):
                            self._reply(422, "El sitio no entregó una sesión Premium compatible")
                            return
                        # One-time even if callback/UI later fails.
                        owner._code = ""
                    self._reply(200, "Sesión recibida; falta verificar salida proxy")
                    try:
                        on_session(session)
                    finally:
                        threading.Thread(target=owner.stop, daemon=True).start()

            try:
                self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
                self._server.daemon_threads = True
                self._thread = threading.Thread(
                    target=self._server.serve_forever,
                    daemon=True, name="premium-browser-bridge"
                )
                self._thread.start()
            except Exception:
                self._server = None
                self._code = ""
                raise
            return PairingDetails(self._server.server_port, self._code)

    def stop(self):
        with self._lock:
            server = self._server
            self._server = None
            self._code = ""
            self._expires_at = 0
        if server is not None:
            server.shutdown()
            server.server_close()
