"""Pruebas de presentación y exportación segura del diagnóstico de cuenta."""
import unittest
from types import SimpleNamespace

from account_panel import AccountPanel


class TestAccountPanelDiagnostics(unittest.TestCase):
    def test_copy_uses_only_the_sanitized_report_buffer(self):
        class Clipboard:
            def __init__(self):
                self.value = ""

            def clipboard_clear(self):
                self.value = ""

            def clipboard_append(self, value):
                self.value += value

        clipboard = Clipboard()
        panel = object.__new__(AccountPanel)
        panel.safe_report = ["HTTP 403", "JSON: code:int"]
        panel.win = clipboard
        panel.status = SimpleNamespace(configure=lambda **_: None)
        panel.copy_diagnostic()
        self.assertEqual(clipboard.value, "HTTP 403\nJSON: code:int")

    def test_formats_request_using_only_method_and_allowed_field_names(self):
        lines = AccountPanel.format_diagnostic_event({
            "stage": "start",
            "method": "POST",
            "path": "/api/login/?type=xray",
            "request_fields": ("email", "password", "token", "unexpected"),
            "message": "private@example.org password-secret",
        })
        report = "\n".join(lines)
        self.assertIn("Método: POST", report)
        self.assertIn("Claves JSON enviadas: email, password, token", report)
        self.assertNotIn("private@example.org", report)
        self.assertNotIn("password-secret", report)
        self.assertNotIn("unexpected", report)

    def test_formats_http_and_json_schema_without_response_values(self):
        lines = AccountPanel.format_diagnostic_event({
            "stage": "response", "host": "1vpn.org", "http_status": 403,
            "response_schema": "code:int, detail:str, errors:dict, sessionAuthToken:str, cookie:str",
            "api_code": 1001,
            "message": "server echoed user@example.org and a-secret-token",
        })
        report = "\n".join(lines)
        self.assertIn("HTTP 403", report)
        self.assertIn("JSON: code:int, detail:str, errors:dict", report)
        self.assertIn("Código API: 1001", report)
        self.assertIn("HTTP 403 no confirma credenciales incorrectas", report)
        for secret in ("user@example.org", "a-secret-token", "sessionAuthToken", "cookie"):
            self.assertNotIn(secret, report)

    def test_differentiates_401_429_2fa_tls_and_connectivity(self):
        cases = [
            ({"stage": "response", "http_status": 401}, "HTTP 401"),
            ({"stage": "response", "http_status": 429}, "HTTP 429: límite temporal; no volver a intentar automáticamente"),
            ({"stage": "response", "http_status": 403, "api_code": 1001}, "Código API 1001: se requiere verificación 2FA"),
            ({"stage": "transport_error", "transport_error": "SSLCertVerificationError"}, "Error TLS/certificado"),
            ({"stage": "transport_error", "transport_error": "TimeoutError"}, "Sin conexión: tiempo de espera agotado"),
        ]
        for event, expected in cases:
            with self.subTest(event=event):
                self.assertIn(expected, "\n".join(AccountPanel.format_diagnostic_event(event)))

    def test_html_and_unknown_json_are_reported_as_schema_only(self):
        html = "\n".join(AccountPanel.format_diagnostic_event({
            "stage": "response", "http_status": 403,
            "response_schema": "no-json-object", "api_code": None,
        }))
        unknown = "\n".join(AccountPanel.format_diagnostic_event({
            "stage": "response", "http_status": 403,
            "response_schema": "code:str, message:str, email:str",
            "api_code": "403 with private data",
        }))
        self.assertIn("JSON: no-json-object", html)
        self.assertIn("HTTP 403 no confirma credenciales incorrectas", html)
        self.assertIn("JSON: code:str, message:str", unknown)
        self.assertNotIn("email", unknown)
        self.assertNotIn("private data", unknown)

    def test_malformed_event_types_are_handled_without_rendering_raw_values(self):
        report = "\n".join(AccountPanel.format_diagnostic_event({
            "stage": "transport_error", "transport_error": ["password", "secret"],
            "message": "private@example.org",
        }))
        self.assertIn("Error de transporte", report)
        self.assertNotIn("password", report)
        self.assertNotIn("secret", report)
        self.assertNotIn("private@example.org", report)


if __name__ == "__main__":
    unittest.main()
