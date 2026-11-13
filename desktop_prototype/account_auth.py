"""Inicio de sesión de CUENTA 1VPN (no autenticación HTTP de un proxy).

El backend de cuentas recibe JSON {email, password, token?} mediante HTTPS.
No se guarda la contraseña ni el token en disco, registros o mensajes de error.
El token devuelto por /api/login/?type=xray NO es automáticamente una
credencial para los proxies HTTPS del navegador.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Callable
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

API_DOMAINS = ("1vpn.org", "1vpn.co", "onevpn.com", "cloudlogcdn.com")
API_PATH = "/api/login/?type=xray"
MAX_RESPONSE = 65536
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class AccountAuthError(Exception):
    """Fallos predecibles. Nunca incluye credenciales ni payload HTTP."""

    MESSAGES = {
        "bad_email": "Introduce un correo electrónico válido.",
        "missing_password": "Introduce la contraseña de tu cuenta 1VPN.",
        "two_factor_required": "1VPN solicita el código de verificación (2FA).",
        "rejected": "La cuenta rechazó las credenciales o el código 2FA. Comprueba los datos.",
        "unavailable": "No se pudo contactar con la API de cuentas 1VPN por HTTPS.",
        "malformed": "1VPN respondió, pero la sesión no tiene el formato esperado.",
    }

    def __init__(self, reason: str):
        if reason not in self.MESSAGES:
            reason = "unavailable"
        self.reason = reason
        super().__init__(self.MESSAGES[reason])


@dataclass(frozen=True)
class AccountSession:
    email: str
    username: str
    is_premium: bool
    session_token: str = field(repr=False, compare=False)

    @property
    def tier(self) -> str:
        return "Premium" if self.is_premium else "Free"


def validate_login(email: str, password: str, two_factor: str = "") -> tuple[str, str, str]:
    if not isinstance(email, str):
        raise AccountAuthError("bad_email")
    email = email.strip()
    if len(email) > 254 or not EMAIL_PATTERN.fullmatch(email):
        raise AccountAuthError("bad_email")
    if not isinstance(password, str) or not password:
        raise AccountAuthError("missing_password")
    if not isinstance(two_factor, str) or any(c in two_factor for c in "\r\n"):
        raise AccountAuthError("rejected")
    # No alterar la contraseña: espacios y mayúsculas pueden ser significativos.
    return email, password, two_factor.strip()


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def _urllib_transport(url: str, payload: bytes, timeout: float) -> tuple[int, bytes]:
    opener = build_opener(_NoRedirect())
    request = Request(url, data=payload, method="POST", headers={
        "Content-Type": "application/json",
        "Client-Type": "app",
        "Accept": "application/json",
    })
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, response.read(MAX_RESPONSE + 1)
    except HTTPError as response:
        try:
            return response.code, response.read(MAX_RESPONSE + 1)
        finally:
            response.close()


def _decode(raw: bytes) -> dict | None:
    if len(raw) > MAX_RESPONSE:
        return None
    try:
        payload = json.loads(raw)
    except (UnicodeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


class AccountClient:
    def __init__(self, transport: Callable[[str, bytes, float], tuple[int, bytes]] | None = None,
                 domains: tuple[str, ...] = API_DOMAINS, timeout: float = 10.0):
        self.transport = transport or _urllib_transport
        self.domains = tuple(domains)
        self.timeout = timeout
        if not self.domains or any(d not in API_DOMAINS for d in self.domains):
            raise ValueError("Los dominios de cuentas deben ser oficiales de 1VPN")

    def login(self, email: str, password: str, two_factor: str = "") -> AccountSession:
        email, password, two_factor = validate_login(email, password, two_factor)
        payload = {"email": email, "password": password}
        if two_factor:
            payload["token"] = two_factor
        request_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        # No se sigue una redirección HTTPS a dominios no autorizados.
        # Los fallos de red no se presentan como contraseñas incorrectas.
        for domain in self.domains:
            try:
                status, raw = self.transport(f"https://{domain}{API_PATH}", request_bytes, self.timeout)
            except Exception:
                continue
            data = _decode(raw)
            if 200 <= status < 300:
                if data is None:
                    continue
                token = data.get("sessionAuthToken")
                premium = data.get("isPremium")
                if not isinstance(token, str) or not token or not isinstance(premium, bool):
                    raise AccountAuthError("malformed")
                username = data.get("username")
                server_email = data.get("email")
                return AccountSession(
                    email=server_email if isinstance(server_email, str) and server_email else email,
                    username=username if isinstance(username, str) else "",
                    is_premium=premium,
                    session_token=token,
                )
            if 400 <= status < 500 and data is not None and any(k in data for k in ("code", "error", "detail")):
                if data.get("code") == 1001:
                    raise AccountAuthError("two_factor_required")
                raise AccountAuthError("rejected")
            # HTML 403, portales cautivos y errores 5xx no son un rechazo
            # confirmado de la cuenta. Probar el siguiente dominio oficial.
        raise AccountAuthError("unavailable")
