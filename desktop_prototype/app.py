"""OneTunnel v0.6: interfaz premium sobre motor Premium/WFP nativo v0.5.5."""
from __future__ import annotations

import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from connection_check import probe_exit_ip
from proxycore import Upstream
from network_engine import NetworkEngine
from control_panel import TrafficControlPanel
from native_wfp import NativeWfpGuard
from native_proxy import NativeProxySession
from driver_lifecycle import SignedDriverLifecycle
from server_catalog import COUNTRIES, ServerEndpoint, refresh_catalogue, snapshot_catalogue
from server_selector import AutoSelector
from account_panel import AccountPanel
from account_auth import AccountSession
from access_proxy import AccessProxy, open_via_access_proxy
import ui_theme as ui

BG = ui.BG
PANEL = ui.SURFACE
TEXT = ui.TEXT
MUTED = ui.MUTED
ACCENT = ui.ACCENT
WARN = ui.WARN
LOCAL_HOST = "127.0.0.1"
DEFAULT_LOCAL_PORT = "8899"


class DesktopApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        ui.apply_root(
            self.root,
            title="OneTunnel — VPN por aplicación",
            geometry="1120x760",
            minsize=(980, 700),
        )
        ui.configure_ttk(self.root)
        self.engine = NetworkEngine(self._log)
        self.native_guard = NativeWfpGuard()
        self.native_proxy = NativeProxySession()  # active only with signed/loaded callout
        self.driver_lifecycle = SignedDriverLifecycle()
        self.panel = None
        self.account_panel = None
        self.account_session: AccountSession | None = None
        self._premium_proxy_active = False
        self._active_access_proxy = None
        self._egress_verified = False
        self._verified_exit_ip: str | None = None
        self.selector: AutoSelector | None = None
        self._scanning = False
        self._manual_host = ""
        self.access_proxy_enabled = tk.BooleanVar(value=False)
        self._active_access_proxy: AccessProxy | None = None
        self.location_mode = tk.StringVar(value="auto")
        self.events: queue.Queue[tuple[str, str, int | None]] = queue.Queue()
        self.session = 0
        self._layout()
        self._warn_legacy_settings()
        root.after(150, self._poll_events)
        root.after(5000, self._update_active_server)
        root.protocol("WM_DELETE_WINDOW", self.close)

    def _label(self, parent, value: str, color=MUTED, size=11, bold=False):
        return tk.Label(
            parent, text=value, fg=color, bg=parent["bg"],
            font=("Segoe UI", size, "bold" if bold else "normal"),
            anchor="w", justify="left",
        )

    def _layout(self):
        self._advanced_visible = False
        self._activity_visible = False

        shell = tk.Frame(self.root, bg=BG, padx=28, pady=22)
        shell.pack(fill="both", expand=True)

        # Header: brand + minimal product state.
        header = tk.Frame(shell, bg=BG)
        header.pack(fill="x", pady=(0, 18))
        brand = tk.Frame(header, bg=BG)
        brand.pack(side="left")
        ui.label(brand, "OneTunnel", color=TEXT, size=22, bold=True).pack(side="left")
        ui.badge(brand, "v0.6 PREMIUM UI", tone="accent").pack(side="left", padx=(10, 0))
        ui.label(
            header,
            "VPN por aplicación · motor WFP nativo",
            color=MUTED,
            size=9,
        ).pack(side="right", pady=(7, 0))

        # Main connection card.
        hero = ui.card(shell, padx=22, pady=20)
        hero.pack(fill="x")

        hero_top = tk.Frame(hero, bg=hero["bg"])
        hero_top.pack(fill="x")
        title_area = tk.Frame(hero_top, bg=hero["bg"])
        title_area.pack(side="left", fill="x", expand=True)
        ui.label(title_area, "Conexión", color=MUTED, size=9, bold=True).pack(anchor="w")
        self.status = ui.label(
            title_area, "Desconectado", color=TEXT, size=18, bold=True
        )
        self.status.pack(anchor="w", pady=(4, 0))

        self.btn = ui.button(
            hero_top, "CONECTAR", self.toggle, variant="primary", width=15
        )
        self.btn.pack(side="right")

        controls = tk.Frame(hero, bg=hero["bg"])
        controls.pack(fill="x", pady=(18, 0))
        controls.columnconfigure(0, weight=1)
        controls.columnconfigure(1, weight=1)

        location_card = tk.Frame(controls, bg=hero["bg"])
        location_card.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        ui.label(location_card, "UBICACIÓN", color=MUTED, size=8, bold=True).pack(anchor="w")
        self._location_modes = {
            "Automático · Singapur preferido": "auto",
            "Singapur": "sgp",
            "Ámsterdam": "ams",
            "Los Ángeles": "lax",
            "Servidor manual": "manual",
        }
        self.location_combo = ttk.Combobox(
            location_card,
            values=list(self._location_modes),
            state="readonly",
            style="OneTunnel.TCombobox",
        )
        self.location_combo.current(0)
        self.location_combo.pack(fill="x", pady=(5, 0))
        self.location_combo.bind("<<ComboboxSelected>>", self._on_location_changed)

        account_card = tk.Frame(controls, bg=hero["bg"])
        account_card.grid(row=0, column=1, sticky="ew", padx=(10, 0))
        ui.label(account_card, "CUENTA", color=MUTED, size=8, bold=True).pack(anchor="w")
        account_line = tk.Frame(account_card, bg=hero["bg"])
        account_line.pack(fill="x", pady=(5, 0))
        self.account_status = ui.label(
            account_line,
            "Sin cuenta vinculada",
            color=MUTED,
            size=9,
        )
        self.account_status.pack(side="left", fill="x", expand=True)
        self.account_btn = ui.button(
            account_line, "CUENTA", self.open_account, variant="secondary", compact=True
        )
        self.account_btn.pack(side="right")

        # At-a-glance state. Technical values are readable but never dominate.
        stats = tk.Frame(shell, bg=BG)
        stats.pack(fill="x", pady=(14, 0))
        for column in range(3):
            stats.columnconfigure(column, weight=1)

        ip_card = ui.card(stats, padx=16, pady=13)
        ip_card.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        ui.label(ip_card, "SALIDA", color=MUTED, size=8, bold=True).pack(anchor="w")
        self.address = ui.label(ip_card, "IP sin verificar", color=TEXT, size=10, bold=True)
        self.address.pack(anchor="w", pady=(5, 0))

        server_card = ui.card(stats, padx=16, pady=13)
        server_card.grid(row=0, column=1, sticky="nsew", padx=7)
        ui.label(server_card, "SERVIDOR", color=MUTED, size=8, bold=True).pack(anchor="w")
        self.server_status = ui.label(
            server_card, "Automático · sin medir", color=TEXT, size=10, bold=True
        )
        self.server_status.pack(anchor="w", pady=(5, 0))

        engine_card = ui.card(stats, padx=16, pady=13)
        engine_card.grid(row=0, column=2, sticky="nsew", padx=(7, 0))
        ui.label(engine_card, "MOTOR", color=MUTED, size=8, bold=True).pack(anchor="w")
        self.engine_status = ui.label(
            engine_card,
            "WFP nativo · red directa",
            color=ui.SUCCESS,
            size=10,
            bold=True,
        )
        self.engine_status.pack(anchor="w", pady=(5, 0))

        # Primary actions: user goals, not implementation details.
        actions = tk.Frame(shell, bg=BG)
        actions.pack(fill="x", pady=(14, 0))
        self.manage_btn = ui.button(
            actions, "APLICACIONES", self.open_traffic_control, variant="secondary"
        )
        self.manage_btn.pack(side="left")
        self.test_btn = ui.button(
            actions, "VERIFICAR SALIDA", self.test_exit, variant="secondary"
        )
        self.test_btn.configure(state="disabled")
        self.test_btn.pack(side="left", padx=(8, 0))
        self.scan_btn = ui.button(
            actions, "ELEGIR MEJOR SERVIDOR", self.scan_servers, variant="secondary"
        )
        self.scan_btn.configure(state="disabled")
        self.scan_btn.pack(side="left", padx=(8, 0))
        self.advanced_btn = ui.button(
            actions, "AVANZADO", self._toggle_advanced, variant="ghost"
        )
        self.advanced_btn.pack(side="right")
        self.activity_btn = ui.button(
            actions, "ACTIVIDAD", self._toggle_activity, variant="ghost"
        )
        self.activity_btn.pack(side="right", padx=(0, 8))

        # Progressive disclosure: all legacy inputs remain available and functional.
        self.advanced_frame = ui.card(shell, padx=18, pady=16, bg=ui.SURFACE)
        advanced_title = tk.Frame(self.advanced_frame, bg=self.advanced_frame["bg"])
        advanced_title.pack(fill="x", pady=(0, 10))
        ui.label(
            advanced_title,
            "Configuración avanzada",
            color=TEXT,
            size=11,
            bold=True,
        ).pack(side="left")
        ui.label(
            advanced_title,
            "Solo para diagnóstico, servidor manual y puertos locales",
            color=MUTED,
            size=9,
        ).pack(side="right")

        advanced_grid = tk.Frame(self.advanced_frame, bg=self.advanced_frame["bg"])
        advanced_grid.pack(fill="x")
        advanced_grid.columnconfigure(0, weight=1)
        advanced_grid.columnconfigure(2, weight=1)

        self.inputs: dict[str, tk.Entry] = {}
        rows = [
            ("host", "Servidor remoto", "", False),
            ("port", "Puerto TLS", "443", False),
            ("username", "Usuario del proxy", "", False),
            ("password", "Clave del proxy", "", True),
            ("local_port", "Puerto HTTP local", DEFAULT_LOCAL_PORT, False),
            ("socks_port", "Puerto SOCKS5 local", "1080", False),
        ]
        for index, (key, caption, default, secret) in enumerate(rows):
            row, pair = divmod(index, 2)
            col = pair * 2
            ui.label(
                advanced_grid, caption, color=MUTED, size=8, bold=True
            ).grid(row=row * 2, column=col, sticky="w", padx=(0, 8), pady=(3, 0))
            field = ui.entry(advanced_grid, secret=secret, mono=True)
            field.insert(0, default)
            field.grid(
                row=row * 2 + 1,
                column=col,
                columnspan=1,
                sticky="ew",
                padx=(0 if col == 0 else 12, 10 if col == 0 else 0),
                pady=(3, 8),
                ipady=6,
            )
            self.inputs[key] = field

        access_card = tk.Frame(
            self.advanced_frame,
            bg=ui.SURFACE_2,
            padx=14,
            pady=12,
            highlightbackground=ui.BORDER,
            highlightthickness=1,
        )
        access_card.pack(fill="x", pady=(6, 12))
        access_head = tk.Frame(access_card, bg=access_card["bg"])
        access_head.pack(fill="x")
        self.access_proxy_check = tk.Checkbutton(
            access_head,
            text="Usar proxy de la red para conectar a 1VPN",
            variable=self.access_proxy_enabled,
            command=self._update_access_proxy_ui,
            bg=access_card["bg"],
            fg=TEXT,
            activebackground=access_card["bg"],
            activeforeground=TEXT,
            selectcolor=ui.SURFACE_3,
            font=(ui.FONT, 9, "bold"),
            relief="flat",
            bd=0,
            highlightthickness=0,
        )
        self.access_proxy_check.pack(side="left")
        self.access_proxy_status = ui.label(
            access_head, "DESACTIVADO", color=MUTED, size=8, bold=True
        )
        self.access_proxy_status.pack(side="right")

        ui.label(
            access_card,
            "Para redes corporativas que exigen HTTP CONNECT antes de salir a Internet. "
            "Si este proxy falla, OneTunnel no intenta conexión directa.",
            color=MUTED,
            size=8,
            wraplength=900,
        ).pack(anchor="w", pady=(5, 10))

        access_grid = tk.Frame(access_card, bg=access_card["bg"])
        access_grid.pack(fill="x")
        for column in range(4):
            access_grid.columnconfigure(column, weight=1)

        access_fields = (
            ("access_host", "Host / IP", "", False),
            ("access_port", "Puerto", "3128", False),
            ("access_username", "Usuario (opcional)", "", False),
            ("access_password", "Clave (opcional)", "", True),
        )
        for column, (key, caption, default, secret) in enumerate(access_fields):
            box = tk.Frame(access_grid, bg=access_grid["bg"])
            box.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 8, 0))
            ui.label(box, caption, color=MUTED, size=8, bold=True).pack(anchor="w")
            field = ui.entry(box, secret=secret, mono=True)
            field.insert(0, default)
            field.pack(fill="x", pady=(3, 0), ipady=6)
            self.inputs[key] = field

        self._update_access_proxy_ui()

        advanced_actions = tk.Frame(self.advanced_frame, bg=self.advanced_frame["bg"])
        advanced_actions.pack(fill="x", pady=(4, 0))
        self.copy_btn = ui.button(
            advanced_actions,
            "COPIAR PROXY LOCAL",
            self.copy_address,
            variant="secondary",
            compact=True,
        )
        self.copy_btn.configure(state="disabled")
        self.copy_btn.pack(side="left")
        ui.label(
            advanced_actions,
            "HTTP CONNECT + SOCKS5 locales. No cambia Wintun ni el proxy global de Windows.",
            color=MUTED,
            size=8,
        ).pack(side="left", padx=(12, 0))
        self._on_location_changed()

        # Activity log stays hidden unless explicitly requested.
        self.activity_frame = ui.card(shell, padx=14, pady=12, bg="#07101c")
        activity_head = tk.Frame(self.activity_frame, bg=self.activity_frame["bg"])
        activity_head.pack(fill="x", pady=(0, 6))
        ui.label(activity_head, "Actividad segura", color=TEXT, size=10, bold=True).pack(side="left")
        ui.label(
            activity_head,
            "Sin credenciales, tokens ni URLs de navegación",
            color=MUTED,
            size=8,
        ).pack(side="right")
        self.logbox = tk.Text(
            self.activity_frame,
            bg="#050c16",
            fg=MUTED,
            insertbackground=TEXT,
            height=7,
            relief="flat",
            padx=10,
            pady=8,
            font=(ui.MONO, 9),
            state="disabled",
            wrap="word",
        )
        self.logbox.pack(fill="both", expand=True)
        self._log("OneTunnel listo. Conecta y verifica la salida antes de activar políticas PROXY.")

    def _update_access_proxy_ui(self):
        enabled = bool(self.access_proxy_enabled.get())
        locked = self.engine.active
        if hasattr(self, "access_proxy_status"):
            self.access_proxy_status.configure(
                text=(
                    "EN USO · HTTP CONNECT" if enabled and locked
                    else "ACTIVO · HTTP CONNECT" if enabled
                    else "DESACTIVADO"
                ),
                fg=ui.ACCENT if enabled and locked else ui.SUCCESS if enabled else MUTED,
            )
        for key in (
            "access_host", "access_port", "access_username", "access_password"
        ):
            field = self.inputs.get(key)
            if field is not None:
                field.configure(state="disabled" if locked or not enabled else "normal")
        if hasattr(self, "access_proxy_check"):
            self.access_proxy_check.configure(state="disabled" if locked else "normal")

    def _access_proxy_config(self) -> AccessProxy | None:
        if not self.access_proxy_enabled.get():
            return None
        host = self.inputs["access_host"].get().strip()
        port_text = self.inputs["access_port"].get().strip()
        if not host:
            raise ValueError("Indica el host o IP del proxy de la red")
        try:
            port = int(port_text)
        except ValueError as error:
            raise ValueError("El puerto del proxy de la red debe ser numérico") from error
        return AccessProxy(
            host,
            port,
            self.inputs["access_username"].get(),
            self.inputs["access_password"].get(),
        ).validated()

    def _toggle_advanced(self):
        self._advanced_visible = not self._advanced_visible
        if self._advanced_visible:
            if self._activity_visible:
                self.activity_frame.pack_forget()
            self.advanced_frame.pack(fill="x", pady=(14, 0))
            if self._activity_visible:
                self.activity_frame.pack(fill="both", expand=True, pady=(14, 0))
            self.advanced_btn.configure(text="OCULTAR AVANZADO")
        else:
            self.advanced_frame.pack_forget()
            self.advanced_btn.configure(text="AVANZADO")

    def _toggle_activity(self):
        self._activity_visible = not self._activity_visible
        if self._activity_visible:
            self.activity_frame.pack(fill="both", expand=True, pady=(14, 0))
            self.activity_btn.configure(text="OCULTAR ACTIVIDAD")
        else:
            self.activity_frame.pack_forget()
            self.activity_btn.configure(text="ACTIVIDAD")

    def _log(self, message: str):
        self.events.put(("log", message, None))

    def _poll_events(self):
        try:
            while True:
                kind, text, session = self.events.get_nowait()
                if kind == "log":
                    self.logbox.configure(state="normal")
                    self.logbox.insert("end", f"• {text}\n")
                    self.logbox.see("end")
                    self.logbox.configure(state="disabled")
                elif kind == "check" and session == self.session and self.engine.active:
                    self._egress_verified = text.startswith("Salida verificada por el proxy")
                    if self._egress_verified:
                        self._verified_exit_ip = text.rsplit(" ", 1)[-1].strip()
                        self.address.configure(text=f"IP {self._verified_exit_ip}", fg=ui.SUCCESS)
                    else:
                        self._verified_exit_ip = None
                        self.address.configure(text="IP sin verificar", fg=WARN)
                    self.status.configure(text=text, fg=ui.SUCCESS if self._egress_verified else WARN)
                    self._log(text)
                    self.test_btn.configure(state="normal")
                elif kind == "scan" and session == self.session and self.engine.active:
                    self._scanning = False
                    self.server_status.configure(text=text, fg=ACCENT if "válidos" in text else WARN)
                    self._log(text)
                    self.scan_btn.configure(state="normal" if self.selector else "disabled")
        except queue.Empty:
            pass
        self.root.after(150, self._poll_events)

    def _current_mode(self) -> str:
        return self._location_modes.get(self.location_combo.get(), "auto")

    def _on_location_changed(self, _event=None):
        host_field = self.inputs.get("host")
        if not host_field:
            return
        was_editable = str(host_field.cget("state")) == "normal"
        if was_editable:
            self._manual_host = host_field.get().strip()
        host_field.configure(state="normal")
        host_field.delete(0, "end")
        if self._current_mode() == "manual":
            host_field.insert(0, self._manual_host)
        else:
            label = "Elegido por la sesión Premium" if (
                self.account_session is not None
                and self.account_session.source == "browser_web"
            ) else "Elegido por el catálogo Free"
            host_field.insert(0, label)
            host_field.configure(state="disabled")

    def _scan_worker(self, selector: AutoSelector, session: int, refresh: bool):
        source = "ubicaciones Premium entregadas por la sesión web" if self._premium_proxy_active else "catálogo incluido"
        if refresh and not self._premium_proxy_active:
            try:
                updated = refresh_catalogue(timeout=4)
                selector.set_catalogue(updated)
                source = "catálogo oficial actualizado"
            except Exception as error:
                # No bloquear el servicio si la API de catálogo falla.
                self._log(f"Actualización de catálogo no disponible ({type(error).__name__}); usando respaldo Free.")
        results = selector.scan()
        summary = selector.summary()
        if summary["ok"]:
            region = COUNTRIES.get(summary["region"], (summary["region"], ""))[0]
            rtt = f'{summary["rtt_ms"]} ms' if summary["rtt_ms"] is not None else "sin RTT"
            message = f'Servidor: {region} / {summary["host"]} / {rtt} · {summary["ok"]} válidos de {len(results)} ({source})'
        else:
            message = f'Servidores sin conexión confirmada: 0 de {len(results)}. No hay salida directa. ({source})'
        self.events.put(("scan", message, session))

    def scan_servers(self, refresh: bool = False):
        if not self.engine.active or self.selector is None or self._scanning:
            return
        self._scanning = True
        self.scan_btn.configure(state="disabled")
        self.server_status.configure(text="Midiendo TLS y CONNECT a través de servidores Free…", fg=WARN)
        threading.Thread(target=self._scan_worker, args=(self.selector, self.session, refresh),
                         name="catalogue-scan", daemon=True).start()

    def _update_active_server(self):
        if self.engine.active and self.selector is not None and not self._scanning:
            summary = self.selector.summary()
            if summary["tested"] and not summary["ok"]:
                self.server_status.configure(text="Sin servidores validados; nueva medición disponible", fg=WARN)
            elif summary["host"]:
                self.server_status.configure(text=f'Selección actual: {COUNTRIES.get(summary["region"], (summary["region"], ""))[0]} · {summary["host"]}'
                                             + (f' · {summary["rtt_ms"]} ms medidos' if summary["rtt_ms"] is not None else ' · sin medición'),
                                             fg=ACCENT)
        self.root.after(5000, self._update_active_server)

    def _warn_legacy_settings(self):
        if os.name == "nt":
            state = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "1VPNDesktopLab" / "proxy_restore.json"
            if state.is_file():
                self._log("ATENCIÓN: v0.1 dejó un respaldo de WinINET pendiente. Restaura desde v0.1 antes de seguir.")
                messagebox.showwarning(
                    "Configuración de v0.1 pendiente",
                    "Hay un respaldo del proxy de Windows creado por v0.1. "
                    "Abre la aplicación anterior y pulsa DETENER Y RESTAURAR. "
                    "Esta versión no modifica ni restaura WinINET automáticamente.",
                )

    def toggle(self):
        if self.engine.active:
            self.disconnect()
            return
        try:
            region = self._current_mode()
            access_proxy = self._access_proxy_config()
            username, password = self.inputs["username"].get(), self.inputs["password"].get()
            remote_port = int(self.inputs["port"].get().strip())
            browser_premium = (
                self.account_session is not None
                and self.account_session.source == "browser_web"
                and self.account_session.is_premium
                and region != "manual"
            )
            if region != "manual":
                if remote_port != 443:
                    raise ValueError("Los servidores HTTPS de 1VPN utilizan el puerto 443")
                if browser_premium:
                    session = self.account_session
                    endpoints = tuple(ServerEndpoint(r, host, port) for r, host, port in session.proxy_locations)
                    if region != "auto" and not any(e.region == region for e in endpoints):
                        raise ValueError("La cuenta Premium no tiene servidores en esta ubicación")
                    self.selector = AutoSelector(
                        endpoints=endpoints,
                        username=session.username,
                        password=session.session_token,
                        region=region, preferred="sgp",
                        access_proxy=access_proxy,
                    )
                else:
                    self.selector = AutoSelector(
                        username=username,
                        password=password,
                        region=region,
                        preferred="sgp",
                        access_proxy=access_proxy,
                    )
                candidates = self.selector.candidates()
                if not candidates:
                    raise ValueError("No hay servidores disponibles en esta ubicación")
                upstream = candidates[0]
            else:
                self.selector = None
                upstream = Upstream(self.inputs["host"].get().strip(), remote_port, username, password).validated()
            if access_proxy is not None:
                self.status.configure(
                    text="Comprobando proxy de acceso de la red…",
                    fg=WARN,
                )
                probe = open_via_access_proxy(
                    access_proxy, upstream.host, upstream.port, timeout=6
                )
                probe.close()
                self._log(
                    f"Proxy de acceso validado para 1VPN · {access_proxy.host}:{access_proxy.port}."
                )

            port = int(self.inputs["local_port"].get().strip())
            socks_port = int(self.inputs["socks_port"].get().strip())
            endpoints = self.engine.start(
                upstream,
                http_port=port,
                socks_port=socks_port,
                selector=self.selector,
                access_proxy=access_proxy,
            )
            self._active_access_proxy = access_proxy
            self._update_access_proxy_ui()
            self._premium_proxy_active = bool(browser_premium)
            self._egress_verified = False
            self.session += 1
            self.btn.configure(text="DESCONECTAR", bg=ui.DANGER, fg=TEXT)
            self.test_btn.configure(state="normal")
            self.copy_btn.configure(state="normal")
            self.location_combo.configure(state="disabled")
            self.scan_btn.configure(state="normal" if self.selector else "disabled")
            self.status.configure(text="Escuchando localmente · salida sin verificar", fg=WARN)
            self.address.configure(text="Pendiente de verificar · pulsa VERIFICAR SALIDA")
            if access_proxy is None:
                self.engine_status.configure(text="WFP nativo · red directa", fg=ui.SUCCESS)
                self._log("Conexión a 1VPN: acceso directo desde la red local.")
            else:
                self.engine_status.configure(
                    text=f"WFP nativo · vía proxy {access_proxy.host}:{access_proxy.port}",
                    fg=ui.ACCENT,
                )
                self._log(
                    f"Conexión a 1VPN: vía proxy de acceso {access_proxy.host}:{access_proxy.port}. "
                    "Sin fallback directo."
                )
            self._log("Ninguna configuración global de Windows/Wintun se ha cambiado.")
            if self.selector is not None:
                self.scan_servers(refresh=True)
            else:
                self.server_status.configure(text="Servidor manual · no hay selección automática", fg=MUTED)
        except (OSError, ValueError, RuntimeError) as error:
            self._log(f"No se pudo abrir el servicio local: {type(error).__name__}")
            messagebox.showerror("No se pudo iniciar", str(error))

    def _set_account_session(self, session: AccountSession | None):
        if self._premium_proxy_active and self.engine.active:
            # Always disconnect old Premium proxy if account is changed/logged out.
            self.disconnect()
        self.account_session = session
        self._location_modes = {
            "Automático · Singapur preferido": "auto",
            "Singapur": "sgp", "Ámsterdam": "ams",
            "Los Ángeles": "lax", "Servidor manual": "manual",
        }
        if session is not None and session.source == "browser_web":
            # Only list regions actually authorized by this Premium session.
            self._location_modes = {"Automático · Singapur preferido": "auto"}
            for code in sorted({region for region, _, _ in session.proxy_locations}):
                if code in ("sgp", "ams", "lax"):
                    name = COUNTRIES[code][0]
                else:
                    name = f"{code.upper()} · Premium"
                self._location_modes[name] = code
            self._location_modes["Servidor manual"] = "manual"
        self.location_combo.configure(values=list(self._location_modes))
        self.location_combo.current(0)
        self._on_location_changed()
        if session is None:
            self.account_status.configure(text="Sin cuenta vinculada", fg=MUTED)
        elif session.source == "browser_web":
            self.account_status.configure(
                text="Premium vinculada · salida sin verificar", fg=WARN
            )
        else:
            self.account_status.configure(text=f"Cuenta 1VPN: {session.email} · {session.tier} (API móvil)", fg=ACCENT)
        # Never copy an Xray token into HTTPS proxy credentials.
        # Web Premium proxy tokens stay in RAM and are not placed into text fields.

    def open_account(self):
        if self.account_panel is not None and self.account_panel.win.winfo_exists():
            self.account_panel.win.lift()
            return
        self.account_panel = AccountPanel(self.root, self._set_account_session)
        if self.account_session is not None:
            self.account_panel.session = self.account_session
            self.account_panel.status.configure(
                text=f"Sesión en memoria: {self.account_session.email} · {self.account_session.tier}", fg=ACCENT)

    def open_traffic_control(self):
        if self.panel and self.panel.win.winfo_exists():
            self.panel.win.lift()
            return
        self.panel = TrafficControlPanel(
            self.root,
            lambda: self.engine.endpoints if self.engine.active else None,
            verified_getter=lambda: self.engine.active and self._egress_verified,
            verified_ip_getter=lambda: self._verified_exit_ip,
            native_guard=self.native_guard,
            native_proxy=self.native_proxy,
            driver_lifecycle=self.driver_lifecycle,
        )

    def copy_address(self):
        if self.engine.active:
            self.root.clipboard_clear()
            self.root.clipboard_append(f"http://{LOCAL_HOST}:{self.engine.endpoints.http_port}")
            self.root.update_idletasks()
            self._log("Dirección del proxy local copiada.")

    def test_exit(self):
        if not self.engine.active:
            return
        port = self.engine.endpoints.http_port
        session = self.session
        self.test_btn.configure(state="disabled")
        self.status.configure(text="Comprobando túnel y salida HTTPS…", fg=WARN)

        def worker():
            try:
                ip = probe_exit_ip(port)
                result = f"Salida verificada por el proxy · IP pública {ip}"
            except Exception as error:
                # No registrar el mensaje completo: podría incluir material de una URL externa.
                result = f"Sin salida verificada ({type(error).__name__}); revisa servidor, credenciales y red"
            self.events.put(("check", result, session))

        threading.Thread(target=worker, name="check-proxy-exit", daemon=True).start()

    def disconnect(self):
        self.session += 1
        self.engine.stop()
        self._premium_proxy_active = False
        self._active_access_proxy = None
        self._egress_verified = False
        self._verified_exit_ip = None
        self.selector = None
        self._scanning = False
        self.location_combo.configure(state="readonly")
        self.scan_btn.configure(state="disabled")
        self.server_status.configure(text="Automático · sin medir", fg=MUTED)
        self.btn.configure(text="CONECTAR", bg=ACCENT)
        self.test_btn.configure(state="disabled")
        self.copy_btn.configure(state="disabled")
        self.status.configure(text="Desconectado", fg=TEXT)
        self.address.configure(text="IP sin verificar", fg=TEXT)
        self.engine_status.configure(text="WFP nativo · red directa", fg=ui.SUCCESS)
        self._update_access_proxy_ui()

    def close(self):
        # Teardown order: PROXY BFE filters -> ephemeral BLOCK filters ->
        # callout only if this OneTunnel instance started it -> Premium transport.
        self.native_proxy.stop()
        self.native_guard.stop()
        try:
            self.driver_lifecycle.stop_if_owned()
        except Exception:
            # Dynamic PROXY/BLOCK filters are already gone; do not trap UI shutdown.
            pass
        self.disconnect()
        self.account_session = None
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    DesktopApp(root)
    root.mainloop()
