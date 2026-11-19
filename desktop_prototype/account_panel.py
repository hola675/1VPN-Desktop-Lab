"""Inicio de sesión de CUENTA 1VPN separado de credenciales del proxy HTTPS."""
from __future__ import annotations

import queue
import re
import threading
import tkinter as tk
import webbrowser
from datetime import datetime

from account_auth import API_DOMAINS, API_PATH, AccountClient, AccountSession, AccountAuthError
from premium_bridge import PremiumBrowserBridge
import ui_theme as ui

BG, PANEL, TEXT, MUTED, ACCENT, WARN = (
    ui.BG, ui.SURFACE, ui.TEXT, ui.MUTED, ui.ACCENT, ui.WARN
)


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
        "rate_limited": "Posible límite temporal (HTTP 403/429): no repetir automáticamente",
        "unavailable": "Sin conexión o sin respuesta válida de la API",
        "malformed": "Respuesta exitosa con estructura de sesión inesperada",
    }

    def __init__(self, parent: tk.Tk, on_session, client: AccountClient | None = None):
        self.parent = parent
        self.on_session = on_session
        self.client = client or AccountClient(on_event=self._queue_diagnostic)
        self.win = tk.Toplevel(parent)
        ui.apply_root(
            self.win,
            title="OneTunnel — Cuenta Premium",
            geometry="720x620",
            minsize=(640, 560),
        )
        ui.configure_ttk(self.win)
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.events = queue.Queue()
        self.pending = False
        self.session: AccountSession | None = None
        self.browser_bridge: PremiumBrowserBridge | None = None
        self.bridge_window: tk.Toplevel | None = None

        content = tk.Frame(self.win, bg=BG, padx=24, pady=20)
        content.pack(fill="both", expand=True)

        header = tk.Frame(content, bg=BG)
        header.pack(fill="x", pady=(0, 14))
        title = tk.Frame(header, bg=BG)
        title.pack(side="left")
        ui.label(title, "Cuenta", color=TEXT, size=20, bold=True).pack(anchor="w")
        ui.label(
            title,
            "Vincula Premium de forma segura. Las credenciales nunca se guardan en disco.",
            color=MUTED,
            size=9,
        ).pack(anchor="w", pady=(3, 0))
        ui.badge(header, "1VPN", tone="accent").pack(side="right", pady=(6, 0))

        self.status = ui.label(
            content,
            "Sin cuenta vinculada",
            color=MUTED,
            size=10,
            bold=True,
        )
        self.status.pack(fill="x", pady=(0, 12))

        notebook = ttk.Notebook(content, style="OneTunnel.TNotebook")
        notebook.pack(fill="both", expand=True)

        web_tab = tk.Frame(notebook, bg=BG, padx=2, pady=2)
        login_tab = tk.Frame(notebook, bg=BG, padx=2, pady=2)
        diag_tab = tk.Frame(notebook, bg=BG, padx=2, pady=2)
        notebook.add(web_tab, text="  Premium web  ")
        notebook.add(login_tab, text="  Email / 2FA  ")
        notebook.add(diag_tab, text="  Diagnóstico  ")

        # Preferred flow: browser consent bridge.
        web_card = ui.card(web_tab, padx=20, pady=18)
        web_card.pack(fill="x", pady=(14, 10))
        ui.label(web_card, "Vincular Premium desde el navegador", color=TEXT, size=13, bold=True).pack(anchor="w")
        ui.label(
            web_card,
            "Usa tu sesión ya abierta en 1vpn.org. OneTunnel recibe solo los datos "
            "necesarios mediante un código temporal y consentimiento explícito.",
            color=MUTED,
            size=9,
            wraplength=610,
        ).pack(anchor="w", pady=(5, 14))
        self.browser_button = ui.button(
            web_card,
            "VINCULAR PREMIUM WEB",
            self.open_browser_bridge,
            variant="primary",
        )
        self.browser_button.pack(anchor="w")

        security_card = ui.card(web_tab, padx=18, pady=15, bg=ui.SURFACE)
        security_card.pack(fill="x", pady=(0, 12))
        ui.label(security_card, "Privacidad", color=TEXT, size=10, bold=True).pack(anchor="w")
        ui.label(
            security_card,
            "No leemos cookies, almacenamiento privado de extensiones ni contraseñas del navegador. "
            "El código de vinculación caduca y se copia separado del puerto.",
            color=MUTED,
            size=9,
            wraplength=610,
        ).pack(anchor="w", pady=(4, 0))

        # Fallback flow: official account API.
        login_card = ui.card(login_tab, padx=20, pady=18)
        login_card.pack(fill="x", pady=(14, 10))
        ui.label(login_card, "Inicio de sesión clásico", color=TEXT, size=13, bold=True).pack(anchor="w")
        ui.label(
            login_card,
            "Úsalo solo si necesitas probar la API de cuenta. Premium web es el flujo recomendado.",
            color=MUTED,
            size=9,
        ).pack(anchor="w", pady=(4, 12))

        fields = (
            ("Correo electrónico", "email", ""),
            ("Contraseña", "password", "*"),
            ("Código 2FA (si se solicita)", "two_factor", "*"),
        )
        for caption, key, mask in fields:
            ui.label(login_card, caption, color=MUTED, size=8, bold=True).pack(anchor="w", pady=(7, 3))
            field = ui.entry(login_card, secret=bool(mask))
            field.pack(fill="x", ipady=7)
            setattr(self, key, field)

        login_actions = tk.Frame(login_card, bg=login_card["bg"])
        login_actions.pack(fill="x", pady=(14, 0))
        self.button = ui.button(
            login_actions, "INICIAR SESIÓN", self.login, variant="primary"
        )
        self.button.pack(side="left")
        ui.button(
            login_actions, "CERRAR SESIÓN", self.logout, variant="secondary"
        ).pack(side="left", padx=(8, 0))

        # Diagnostic content remains available without occupying primary UI.
        diag_card = ui.card(diag_tab, padx=16, pady=14)
        diag_card.pack(fill="both", expand=True, pady=(14, 12))
        diag_header = tk.Frame(diag_card, bg=diag_card["bg"])
        diag_header.pack(fill="x", pady=(0, 8))
        ui.label(diag_header, "Registro seguro", color=TEXT, size=11, bold=True).pack(side="left")
        self.copy_button = ui.button(
            diag_header,
            "COPIAR",
            self.copy_diagnostic,
            variant="secondary",
            compact=True,
        )
        self.copy_button.pack(side="right")

        log_frame = tk.Frame(diag_card, bg="#050c16")
        log_frame.pack(fill="both", expand=True)
        scrollbar = tk.Scrollbar(log_frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")
        self.diagnostics = tk.Text(
            log_frame,
            bg="#050c16",
            fg=MUTED,
            height=10,
            relief="flat",
            padx=10,
            pady=9,
            font=(ui.MONO, 9),
            state="disabled",
            wrap="word",
            yscrollcommand=scrollbar.set,
        )
        self.diagnostics.pack(side="left", fill="both", expand=True)
        scrollbar.configure(command=self.diagnostics.yview)

        self.safe_report: list[str] = []
        self.diagnostic_lines = 0
        self._queue_diagnostic({
            "stage": "ready",
            "message": "Listo. El registro no almacena correo, contraseña, código 2FA ni respuestas completas.",
        })
        self.privacy_note = ui.label(
            diag_card,
            "Diagnóstico limitado a metadatos seguros de la API; nunca guarda valores de credenciales.",
            color=MUTED,
            size=8,
        )
        self.privacy_note.pack(fill="x", anchor="w", pady=(8, 0))
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
            hint = event.get("rejection_hint")
            if status == 403 and hint == "rate_limit_indicated":
                lines.append("Indicio 403: limitación de frecuencia indicada por la API; no repetir intentos")
            elif status == 403:
                lines.append("Indicio 403: causa concreta sin identificar; Android trata este estado como posible límite")
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
                if kind == "browser_session":
                    self.session = data
                    self.password.delete(0, "end")
                    self.two_factor.delete(0, "end")
                    self.status.configure(
                        text="Premium recibido desde navegador. Inicia el proxy y verifica salida HTTPS.",
                        fg=ACCENT,
                    )
                    self.on_session(data)
                    self._cancel_browser_bridge()
                elif kind == "success":
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


    def _cancel_browser_bridge(self):
        bridge, window = self.browser_bridge, self.bridge_window
        self.browser_bridge = None
        self.bridge_window = None
        if bridge is not None:
            bridge.stop()
        if window is not None:
            try:
                if window.winfo_exists():
                    window.destroy()
            except tk.TclError:
                pass

    @staticmethod
    def _copy_pairing_text(window, value: str) -> bool:
        """Copy exactly one pairing field; never combine port and secret."""
        try:
            window.clipboard_clear()
            window.clipboard_append(value)
            window.update_idletasks()
            return True
        except tk.TclError:
            return False

    def open_browser_bridge(self):
        """Start a user-approved, one-time local transfer from official website.

        Does not inspect browser storage, cookies or another extension.
        """
        if self.browser_bridge is not None:
            if self.bridge_window is not None and self.bridge_window.winfo_exists():
                self.bridge_window.lift()
            return
        bridge = PremiumBrowserBridge()
        try:
            details = bridge.start(lambda session: self.events.put(("browser_session", session)))
        except OSError:
            self.status.configure(text="No se pudo abrir el puerto local de vinculación.", fg=WARN)
            return
        self.browser_bridge = bridge
        popup = tk.Toplevel(self.win)
        self.bridge_window = popup
        popup.title("OneTunnel — Vincular Premium")
        popup.geometry("700x390")
        popup.minsize(640, 350)
        popup.configure(bg=BG)\n        ui.configure_ttk(popup)
        popup.protocol("WM_DELETE_WINDOW", self._cancel_browser_bridge)
        panel = tk.Frame(popup, bg=BG, padx=22, pady=15)
        panel.pack(fill="both", expand=True)
        tk.Label(panel, text="VINCULAR PREMIUM", fg=ACCENT,
                 bg=BG, font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 10))
        instructions = (
            "1. Instala la extensión complementaria local desde browser_companion/.\n"
            "2. Abre tu cuenta en https://1vpn.org/account/ en ese mismo navegador.\n"
            "3. En la extensión complementaria, introduce puerto y código temporal.\n"
            "4. Pulsa «Vincular» en la extensión. Caduca en 5 minutos.\n"
            "Nota: no lee automáticamente la sesión privada de la extensión oficial."
        )
        tk.Label(panel, text=instructions, fg=TEXT, bg=BG, anchor="w",
                 justify="left", font=("Segoe UI", 9)).pack(anchor="w")
        copy_status = tk.Label(panel, text="Copia cada dato por separado; no compartas el código.",
                               fg=MUTED, bg=BG, font=("Segoe UI", 9), anchor="w")
        fields = tk.Frame(panel, bg=BG)
        fields.pack(fill="x", pady=(10, 4))
        fields.columnconfigure(1, weight=1)

        def copy_field(value: str, field_name: str):
            copied = self._copy_pairing_text(popup, value)
            copy_status.configure(
                text=f"{field_name} copiado al portapapeles." if copied
                else f"No se pudo copiar el {field_name.lower()}.",
                fg=ACCENT if copied else WARN,
            )

        for row_index, (caption, value, button_text) in enumerate((
            ("Puerto local", str(details.port), "COPIAR PUERTO"),
            ("Código temporal", details.code, "COPIAR CÓDIGO"),
        )):
            tk.Label(fields, text=caption, bg=BG, fg=ACCENT if row_index == 0 else TEXT,
                     font=("Segoe UI", 10), anchor="w").grid(
                         row=row_index, column=0, sticky="w", pady=4, padx=(0, 10))
            entry = tk.Entry(fields, bg=PANEL, fg=TEXT, readonlybackground=PANEL,
                             font=("Consolas", 10), relief="flat", width=33)
            entry.insert(0, value)
            entry.configure(state="readonly")
            entry.grid(row=row_index, column=1, sticky="ew", pady=4, ipady=5)
            tk.Button(fields, text=button_text,
                      command=lambda v=value, name=caption: copy_field(v, name),
                      bg=ACCENT, fg=BG, relief="flat", padx=8, pady=5).grid(
                          row=row_index, column=2, sticky="e", padx=(10, 0), pady=4)

        copy_status.pack(fill="x", pady=(2, 8))
        bar = tk.Frame(panel, bg=BG)
        bar.pack(fill="x")
        tk.Button(bar, text="ABRIR CUENTA OFICIAL", command=lambda: webbrowser.open("https://1vpn.org/account/"),
                  bg=PANEL, fg=TEXT, relief="flat", padx=9, pady=6).pack(side="left")
        tk.Button(bar, text="CANCELAR", command=self._cancel_browser_bridge,
                  bg=PANEL, fg=WARN, relief="flat", padx=9, pady=6).pack(side="left", padx=8)
        self.status.configure(text="Vinculación Premium esperando consentimiento del navegador.", fg=WARN)

    def logout(self):
        self._cancel_browser_bridge()
        self.session = None
        self.password.delete(0, "end")
        self.two_factor.delete(0, "end")
        self.on_session(None)
        self.status.configure(text="Sesión local cerrada. No se ha modificado el proxy.", fg=MUTED)

    def close(self):
        self._cancel_browser_bridge()
        self.password.delete(0, "end")
        self.two_factor.delete(0, "end")
        self.win.destroy()
