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
SAFE_RESPONSE_FIELDS = ("code", "error", "detail", "message", "non_field_errors", "errors")
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class AccountAuthError(Exception):
    """Fallos predecibles. Nunca incluye credenciales ni payload HTTP."""

    MESSAGES = {
        "bad_email": "Introduce un correo electrónico válido.",
        "missing_password": "Introduce la contraseña de tu cuenta 1VPN.",
        "two_factor_required": "1VPN solicita el código de verificación (2FA).",
        "rejected": "La API rechazó la solicitud de cuenta. Comprueba los datos.",
        "forbidden": "1VPN respondió HTTP 403: posible restricción de acceso, seguridad, 2FA o credenciales. Revisa el esquema JSON del diagnóstico.",
        "rate_limited": "1VPN indicó un posible límite temporal de solicitudes (HTTP 403 o 429). Evita repetir intentos.",
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
    # A mobile/Xray token must never be re-used as an HTTPS browser proxy password.
    source: str = field(default="xray", repr=False, compare=False)
    proxy_locations: tuple[tuple[str, str, int], ...] = field(default_factory=tuple, repr=False, compare=False)

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
                 domains: tuple[str, ...] = API_DOMAINS, timeout: float = 10.0,
                 on_event: Callable[[dict], None] | None = None):
        self.transport = transport or _urllib_transport
        self.domains = tuple(domains)
        self.timeout = timeout
        self.on_event = on_event
        if not self.domains or any(d not in API_DOMAINS for d in self.domains):
            raise ValueError("Los dominios de cuentas deben ser oficiales de 1VPN")

    def _emit(self, **event) -> None:
        if self.on_event is not None:
            try:
                self.on_event(event)
            except Exception:
                # Un logger/UI de diagnóstico nunca debe interrumpir el login.
                pass

    @staticmethod
    def _response_category(data: dict | None) -> str:
        if data is None:
            return "non_json_or_invalid"
        for key in ("code", "error", "detail"):
            if key in data:
                return key
        return "json_without_error_fields"

    @staticmethod
    def _safe_response_schema(data: dict | None) -> str:
        if data is None:
            return "no-json-object"
        # Mostrar solo nombres de campos permitidos y tipos: nunca valores.
        parts = [
            f"{key}:{type(data[key]).__name__}"
            for key in SAFE_RESPONSE_FIELDS if key in data
        ]
        return ", ".join(parts) if parts else "json-sin-campos-de-error-conocidos"

    @staticmethod
    def _safe_api_code(data: dict | None) -> int | None:
        if data is None:
            return None
        code = data.get("code")
        return code if type(code) is int and 0 <= code <= 999999 else None

    @staticmethod
    def _safe_403_hint(status: int, data: dict | None) -> str:
        """Solo clasificación cerrada; nunca devuelve texto arbitrario de la API.

        La aplicación Android oficial trata 403 como rate limit, pero en
        nuestro cliente no lo afirmamos sin indicios en detail/error.
        """
        if status != 403 or data is None:
            return "none"
        message = data.get("detail")
        if not isinstance(message, str):
            message = data.get("error")
        if not isinstance(message, str):
            return "unknown"
        text = message.casefold()
        if any(phrase in text for phrase in (
            "throttl", "rate limit", "too many requests", "too many attempts",
            "demasiados intentos", "demasiadas solicitudes",
        )):
            return "rate_limit_indicated"
        return "unknown"

    @staticmethod
    def _genuine_api_rejection(data: dict | None) -> bool:
        if data is None:
            return False
        return (
            type(data.get("code")) is int
            or isinstance(data.get("error"), str)
            or isinstance(data.get("detail"), str)
        )

    def login(self, email: str, password: str, two_factor: str = "") -> AccountSession:
        email, password, two_factor = validate_login(email, password, two_factor)
        payload = {"email": email, "password": password}
        if two_factor:
            payload["token"] = two_factor
        request_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        # No se sigue una redirección HTTPS a dominios no autorizados.
        # Los fallos de red no se presentan como contraseñas incorrectas.
        self._emit(stage="start", method="POST", path=API_PATH,
                   request_fields=("email", "password", "token") if two_factor else ("email", "password"),
                   message="Solicitud POST JSON: email, password" + (", token(2FA)" if two_factor else "") + " (valores ocultos)")
        for attempt, domain in enumerate(self.domains, start=1):
            self._emit(stage="request", attempt=attempt, total=len(self.domains), host=domain,
                       message=f"Conectando con {domain} por HTTPS (intento {attempt}/{len(self.domains)})")
            try:
                status, raw = self.transport(f"https://{domain}{API_PATH}", request_bytes, self.timeout)
            except Exception as error:
                self._emit(stage="transport_error", host=domain, transport_error=type(error).__name__,
                           message=f"Error de conexión con {domain}: {type(error).__name__}")
                continue
            data = _decode(raw)
            schema = self._safe_response_schema(data)
            code = self._safe_api_code(data)
            hint = self._safe_403_hint(status, data)
            self._emit(stage="response", host=domain, http_status=status,
                       response_category=self._response_category(data),
                       response_schema=schema, api_code=code, rejection_hint=hint,
                       message=f"Respuesta HTTPS de {domain}: HTTP {status} · JSON {schema}"
                               + (f" · código API {code}" if code is not None else ""))
            if 200 <= status < 300:
                if data is None:
                    self._emit(stage="invalid_response", host=domain,
                               message="La respuesta no es JSON válido o excede el límite permitido")
                    continue
                token = data.get("sessionAuthToken")
                premium = data.get("isPremium")
                if not isinstance(token, str) or not token or not isinstance(premium, bool):
                    self._emit(stage="complete", result="malformed", message="Respuesta JSON sin sesión válida")
                    raise AccountAuthError("malformed")
                username = data.get("username")
                server_email = data.get("email")
                session = AccountSession(
                    email=server_email if isinstance(server_email, str) and server_email else email,
                    username=username if isinstance(username, str) else "",
                    is_premium=premium,
                    session_token=token,
                )
                self._emit(stage="complete", result="success", message="Inicio de sesión completado")
                return session
            # HTTP 429 es un límite de solicitudes aunque la respuesta no sea JSON.
            # No reenviar credenciales a otros dominios durante un rate limit.
            if status == 429:
                self._emit(stage="complete", result="rate_limited",
                           message="HTTP 429: límite temporal; no reintentar automáticamente")
                raise AccountAuthError("rate_limited")
            if 400 <= status < 500 and self._genuine_api_rejection(data):
                if code == 1001:
                    self._emit(stage="complete", result="two_factor_required", message="1VPN solicita 2FA")
                    raise AccountAuthError("two_factor_required")
                reason = ("rate_limited" if hint == "rate_limit_indicated"
                          else "forbidden" if status == 403 else "rejected")
                self._emit(stage="complete", result=reason,
                           message=f"Respuesta API: HTTP {status}, clasificación {reason}. Valores ocultos.")
                raise AccountAuthError(reason)
            # HTML 403, portales cautivos y errores 5xx no son un rechazo
            # confirmado de la cuenta. Probar el siguiente dominio oficial.
        self._emit(stage="complete", result="unavailable", message="No hubo respuesta válida de los dominios configurados")
        raise AccountAuthError("unavailable")
