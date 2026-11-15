"""Inicio de sesión de CUENTA 1VPN separado de credenciales del proxy HTTPS."""
from __future__ import annotations

import queue
import re
import threading
import tkinter as tk
from datetime import datetime

from account_auth import API_DOMAINS, API_PATH, AccountClient, AccountSession, AccountAuthError

BG, PANEL, TEXT, MUTED, ACCENT, WARN = "#0d1524", "#142238", "#ecf4ff", "#a9bdd9", "#4bc7e6", "#f4b26c"


class AccountPanel:
    REQUEST_FIELDS = {"email", "password", "token"}
    RESPONSE_FIELDS = {
        "code": {"int", "str"}, "error": {"str"}, "detail": {"str"}, "message": {"str"},
        "non_field_errors": {"list"}, "errors": {"dict", "list"},
    }
    API_RESULT_TEXT = {
        "success": "Autenticación correcta",
        "forbidden": "Acceso denegado por la API; HTTP 403 no confirma credenciales incorrectas",
        "rejected": "La API rechazó la solicitud (HTTP 4xx)",
        "two_factor_required": "La API solicita verificación 2FA",
        "rate_limited": "Límite temporal: no repetir automáticamente (HTTP 429)",
        "unavailable": "Sin conexión o sin respuesta válida de la API",
        "malformed": "Respuesta exitosa con estructura de sesión inesperada",
    }

    def __init__(self, parent: tk.Tk, on_session, client: AccountClient | None = None):
        self.parent = parent
        self.on_session = on_session
        self.client = client or AccountClient(on_event=self._queue_diagnostic)
        self.win = tk.Toplevel(parent)
        self.win.title("1VPN Desktop Lab — Autenticación de cuenta")
        self.win.geometry("640x540")
        self.win.minsize(570, 500)
        self.win.configure(bg=BG)
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.events = queue.Queue()
        self.pending = False
        self.session: AccountSession | None = None

        content = tk.Frame(self.win, bg=BG, padx=18, pady=12)
        content.pack(fill="both", expand=True)
        tk.Label(content, text="CUENTA 1VPN — EMAIL Y CONTRASEÑA", fg=ACCENT, bg=BG,
                 font=("Segoe UI", 13, "bold")).pack(anchor="w")
        tk.Label(content, text="Esta autenticación es de tu cuenta, NO del proxy HTTPS local.",
                 fg=MUTED, bg=BG, font=("Segoe UI", 10)).pack(anchor="w", pady=(4, 10))
        for caption, key, mask in (
            ("Correo electrónico de 1VPN", "email", ""),
            ("Contraseña de la cuenta", "password", "*"),
            ("Código 2FA (solo si 1VPN lo solicita)", "two_factor", "*"),
        ):
            tk.Label(content, text=caption, bg=BG, fg=TEXT, font=("Segoe UI", 10)).pack(anchor="w", pady=(5, 1))
            entry = tk.Entry(content, bg=PANEL, fg=TEXT, relief="flat", insertbackground=TEXT,
                             font=("Segoe UI", 11), show=mask)
            entry.pack(fill="x", ipady=6)
            setattr(self, key, entry)
        btns = tk.Frame(content, bg=BG)
        btns.pack(fill="x", pady=(6, 4))
        self.button = tk.Button(btns, text="INICIAR SESIÓN", command=self.login, bg=ACCENT,
                                fg=BG, relief="flat", font=("Segoe UI", 10, "bold"), padx=13, pady=8)
        self.button.pack(side="left")
        tk.Button(btns, text="CERRAR SESIÓN", command=self.logout, bg=PANEL,
                  fg=TEXT, relief="flat", font=("Segoe UI", 10), padx=10, pady=8).pack(side="left", padx=8)
        self.status = tk.Label(content, text="Cuenta sin iniciar sesión", bg=BG, fg=MUTED,
                               font=("Segoe UI", 10), anchor="w", justify="left")
        self.status.pack(fill="x", anchor="w")
        diagnostic_header = tk.Frame(content, bg=BG)
        diagnostic_header.pack(fill="x", pady=(7, 3))
        tk.Label(diagnostic_header, text="REGISTRO DE DIAGNÓSTICO SEGURO", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 9, "bold")).pack(side="left")
        self.copy_button = tk.Button(diagnostic_header, text="COPIAR DIAGNÓSTICO SEGURO",
                                     command=self.copy_diagnostic, bg=PANEL, fg=ACCENT,
                                     relief="flat", font=("Segoe UI", 9, "bold"), padx=9, pady=4)
        self.copy_button.pack(side="right")
        log_frame = tk.Frame(content, bg="#0a111d")
        log_frame.pack(fill="both", expand=True, pady=(0, 2))
        scrollbar = tk.Scrollbar(log_frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")
        self.diagnostics = tk.Text(log_frame, bg="#0a111d", fg=MUTED, height=5, relief="flat",
                                   padx=9, pady=7, font=("Consolas", 9), state="disabled", wrap="word",
                                   yscrollcommand=scrollbar.set)
        self.diagnostics.pack(side="left", fill="both", expand=True)
        scrollbar.configure(command=self.diagnostics.yview)
        self.safe_report: list[str] = []
        self.diagnostic_lines = 0
        self._queue_diagnostic({"stage": "ready", "message": "Listo. El registro no almacena correo, contraseña, código 2FA ni respuestas completas."})
        self.privacy_note = tk.Label(content, text="POST HTTPS JSON a 1VPN. El registro omite valores personales y respuestas completas.",
                                     fg=MUTED, bg=BG, font=("Segoe UI", 9), justify="left")
        self.privacy_note.pack(fill="x", anchor="w", pady=(5, 0))
        content.bind("<Configure>", self._resize_text)
        self.win.after(120, self.poll)

    def _queue_diagnostic(self, event: dict):
        self.events.put(("diagnostic", event))

    @classmethod
    def format_diagnostic_event(cls, event: dict) -> list[str]:
        """Construye texto diagnóstico desde una lista cerrada de metadatos seguros."""
        if not isinstance(event, dict):
            return ["Evento diagnóstico ignorado: formato desconocido"]
        stage = event.get("stage")
        lines: list[str] = []
        if stage == "start":
            method = event.get("method")
            if method == "POST":
                lines.append("Método: POST · HTTPS JSON · " + API_PATH)
            fields = event.get("request_fields")
            if isinstance(fields, (tuple, list)):
                allowed = [name for name in fields if isinstance(name, str) and name in cls.REQUEST_FIELDS]
                if allowed:
                    lines.append("Claves JSON enviadas: " + ", ".join(dict.fromkeys(allowed)) + " (valores ocultos)")
        elif stage == "request":
            host = event.get("host")
            attempt, total = event.get("attempt"), event.get("total")
            if isinstance(host, str) and host in API_DOMAINS:
                line = f"Conexión HTTPS a {host}"
                if type(attempt) is int and type(total) is int and 1 <= attempt <= total <= len(API_DOMAINS):
                    line += f" (intento {attempt}/{total})"
                lines.append(line)
        elif stage == "response":
            host = event.get("host")
            if isinstance(host, str) and host in API_DOMAINS:
                lines.append(f"Host: {host}")
            status = event.get("http_status")
            if type(status) is int and 100 <= status <= 599:
                lines.append(f"Respuesta HTTP {status}")
                if status == 403:
                    lines.append("HTTP 403 no confirma credenciales incorrectas")
                elif status == 401:
                    lines.append("HTTP 401: la API no autorizó la solicitud; causa exacta no confirmada")
                elif status == 429:
                    lines.append("HTTP 429: límite temporal; no volver a intentar automáticamente")
            schema = cls._safe_schema(event.get("response_schema"))
            if schema:
                lines.append("Estructura JSON: " + schema)
            code = event.get("api_code")
            if type(code) is int and 0 <= code <= 999999:
                lines.append(f"Código API: {code}")
                if code == 1001:
                    lines.append("Código API 1001: se requiere verificación 2FA")
        elif stage == "transport_error":
            error_type = event.get("transport_error")
            if isinstance(error_type, str) and error_type in {"SSLError", "CertificateError", "SSLCertVerificationError", "ssl.SSLError"}:
                lines.append("Error TLS/certificado: no se pudo validar o completar la conexión segura")
            elif isinstance(error_type, str) and error_type in {"TimeoutError", "socket.timeout"}:
                lines.append("Sin conexión: tiempo de espera agotado")
            elif isinstance(error_type, str) and error_type in {"URLError", "ConnectionError", "OSError", "gaierror"}:
                lines.append("Sin conexión: no se pudo establecer la conexión HTTPS")
            else:
                lines.append("Error de transporte: conexión HTTPS no completada")
        elif stage == "complete":
            result = event.get("result")
            if isinstance(result, str) and result in cls.API_RESULT_TEXT:
                lines.append("Resultado: " + cls.API_RESULT_TEXT[result])
        elif stage == "ready":
            lines.append("Listo para iniciar una autenticación")
        return lines or ["Etapa diagnóstica recibida; sin metadatos seguros reconocidos"]

    @classmethod
    def _safe_schema(cls, schema) -> str:
        if not isinstance(schema, str):
            return ""
        if schema == "no-json-object":
            return schema
        safe = []
        for entry in schema.split(","):
            match = re.fullmatch(r"\s*([a-z_]+)\s*:\s*([a-z]+)\s*", entry)
            if not match:
                continue
            name, value_type = match.groups()
            if value_type in cls.RESPONSE_FIELDS.get(name, set()):
                safe.append(f"{name}:{value_type}")
        return ", ".join(dict.fromkeys(safe)) or "JSON sin campos de error reconocidos"

    def _show_diagnostic(self, event: dict):
        timestamp = datetime.now().astimezone().strftime("%H:%M:%S")
        lines = [f"{timestamp} · {line}" for line in self.format_diagnostic_event(event)]
        self.safe_report.extend(lines)
        self.diagnostic_lines += len(lines)
        self.diagnostics.configure(state="normal")
        self.diagnostics.insert("end", "\n".join(lines) + "\n")
        while self.diagnostic_lines > 100:
            self.diagnostics.delete("1.0", "2.0")
            self.diagnostic_lines -= 1
            if self.safe_report:
                self.safe_report.pop(0)
        self.diagnostics.see("end")
        self.diagnostics.configure(state="disabled")

    def copy_diagnostic(self):
        report = "\n".join(self.safe_report) or "No hay eventos de diagnóstico todavía."
        try:
            self.win.clipboard_clear()
            self.win.clipboard_append(report)
            self.status.configure(text="Diagnóstico seguro copiado al portapapeles.", fg=ACCENT)
        except tk.TclError:
            self.status.configure(text="No se pudo copiar el diagnóstico al portapapeles.", fg=WARN)

    def _resize_text(self, event):
        wraplength = max(220, event.width - 52)
        self.status.configure(wraplength=wraplength)
        self.privacy_note.configure(wraplength=wraplength)

    def login(self):
        if self.pending:
            return
        email, password, code = self.email.get(), self.password.get(), self.two_factor.get()
        try:
            from account_auth import validate_login
            validate_login(email, password, code)
        except AccountAuthError as error:
            self.status.configure(text=str(error), fg=WARN)
            return
        self.pending = True
        self.button.configure(state="disabled")
        self.status.configure(text="Autenticando con la API oficial por HTTPS...", fg=WARN)

        def worker():
            try:
                session = self.client.login(email, password, code)
                self.events.put(("success", session))
            except AccountAuthError as error:
                self.events.put(("error", error.reason))
            except Exception:
                self.events.put(("error", "unavailable"))

        threading.Thread(target=worker, daemon=True, name="1vpn-account-login").start()

    def poll(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == "diagnostic":
                    self._show_diagnostic(data)
                    continue
                self.pending = False
                self.button.configure(state="normal")
                if kind == "success":
                    self.session = data
                    self.password.delete(0, "end")
                    self.two_factor.delete(0, "end")
                    self.status.configure(text=f"Sesión de cuenta verificada: {data.email} · {data.tier}", fg=ACCENT)
                    self.on_session(data)
                else:
                    error = AccountAuthError(data)
                    self.status.configure(text=str(error), fg=WARN)
                    if data != "two_factor_required":
                        self.password.delete(0, "end")
        except queue.Empty:
            pass
        if self.win.winfo_exists():
            self.win.after(120, self.poll)

    def logout(self):
        self.session = None
        self.password.delete(0, "end")
        self.two_factor.delete(0, "end")
        self.on_session(None)
        self.status.configure(text="Sesión local cerrada. No se ha modificado el proxy.", fg=MUTED)

    def close(self):
        self.password.delete(0, "end")
        self.two_factor.delete(0, "end")
        self.win.destroy()
