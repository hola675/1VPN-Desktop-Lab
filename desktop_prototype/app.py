"""1VPN Desktop Lab v0.4: motor HTTP/SOCKS5 y panel firewall integrados."""
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
from server_catalog import COUNTRIES, refresh_catalogue, snapshot_catalogue
from server_selector import AutoSelector

BG = "#0d1524"
PANEL = "#142238"
TEXT = "#ecf4ff"
MUTED = "#a9bdd9"
ACCENT = "#4bc7e6"
WARN = "#f4b26c"
LOCAL_HOST = "127.0.0.1"
DEFAULT_LOCAL_PORT = "8899"


class DesktopApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("1VPN Desktop Lab — Servidores inteligentes v0.4.1")
        self.root.geometry("1080x780")
        self.root.minsize(960, 710)
        self.root.configure(bg=BG)
        self.engine = NetworkEngine(self._log)
        self.panel = None
        self.selector: AutoSelector | None = None
        self._scanning = False
        self._manual_host = ""
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
        shell = tk.Frame(self.root, bg=BG, padx=32, pady=22)
        shell.pack(fill="both", expand=True)
        self._label(shell, "DESKTOP LAB  /  v0.4.1  /  AUTO + HTTP + SOCKS5 + FIREWALL", ACCENT, 11, True).pack(anchor="w")
        self._label(shell, "Proxy y políticas de tráfico para Windows", TEXT, 23, True).pack(anchor="w", pady=(9, 4))
        self._label(
            shell, "Selección Free automática con preferencia por Singapur. No modifica Wintun ni rutas.",
            MUTED, 10,
        ).pack(anchor="w", pady=(0, 17))

        panel = tk.Frame(shell, bg=PANEL, padx=22, pady=14)
        panel.pack(fill="x")
        self.inputs: dict[str, tk.Entry] = {}
        self._label(panel, "Ubicación / selección", TEXT, 10).grid(row=0, column=0, sticky="w", pady=5)
        choices = ["Automático · Singapur preferido", "Singapur", "Ámsterdam", "Los Ángeles", "Servidor manual"]
        self.location_combo = ttk.Combobox(panel, values=choices, state="readonly", font=("Segoe UI", 11))
        self.location_combo.current(0)
        self.location_combo.grid(row=0, column=1, sticky="ew", padx=(18, 0), pady=5, ipady=5)
        self.location_combo.bind("<<ComboboxSelected>>", self._on_location_changed)
        rows = [
            ("host", "Servidor proxy HTTPS remoto", "", False),
            ("port", "Puerto remoto (TLS)", "443", False),
            ("username", "Usuario remoto (opcional)", "", False),
            ("password", "Contraseña (solo memoria)", "", True),
            ("local_port", "Puerto HTTP local (0 = automático)", DEFAULT_LOCAL_PORT, False),
            ("socks_port", "Puerto SOCKS5 local (0 = automático)", "1080", False),
        ]
        for i, (key, name, default, secret) in enumerate(rows, start=1):
            self._label(panel, name, TEXT, 10).grid(row=i, column=0, sticky="w", pady=5)
            entry = tk.Entry(panel, bg=BG, fg=TEXT, insertbackground=TEXT, relief="flat",
                             font=("Consolas", 11), show="*" if secret else "")
            entry.insert(0, default)
            entry.grid(row=i, column=1, sticky="ew", padx=(18, 0), pady=5, ipady=7)
            self.inputs[key] = entry
        panel.columnconfigure(1, weight=1)
        self._on_location_changed()

        bar = tk.Frame(shell, bg=BG)
        bar.pack(fill="x", pady=(16, 6))
        self.btn = tk.Button(bar, text="INICIAR PROXY", command=self.toggle,
                             bg=ACCENT, fg=BG, activebackground="#93e7fa", relief="flat",
                             font=("Segoe UI", 10, "bold"), padx=15, pady=11)
        self.btn.pack(side="left")
        self.manage_btn = tk.Button(bar, text="APLICACIONES / FIREWALL", command=self.open_traffic_control,
                                    bg=PANEL, fg=ACCENT, relief="flat", font=("Segoe UI", 10, "bold"),
                                    padx=13, pady=11)
        self.manage_btn.pack(side="left", padx=(10, 0))
        self.test_btn = tk.Button(bar, text="COMPROBAR SALIDA", command=self.test_exit,
                                  bg=PANEL, fg=TEXT, relief="flat", state="disabled",
                                  font=("Segoe UI", 10, "bold"), padx=13, pady=11)
        self.test_btn.pack(side="left", padx=(10, 0))
        self.copy_btn = tk.Button(bar, text="COPIAR DIRECCIÓN", command=self.copy_address,
                                  bg=PANEL, fg=TEXT, relief="flat", state="disabled",
                                  font=("Segoe UI", 10, "bold"), padx=13, pady=11)
        self.copy_btn.pack(side="left", padx=(10, 0))
        self.scan_btn = tk.Button(bar, text="MEDIR SERVIDORES", command=self.scan_servers,
                                  bg=PANEL, fg=ACCENT, relief="flat", state="disabled",
                                  font=("Segoe UI", 10, "bold"), padx=10, pady=11)
        self.scan_btn.pack(side="left", padx=(10, 0))
        self.status = self._label(shell, "Desconectado", MUTED, 11, True)
        self.status.pack(anchor="w", pady=(7, 7))
        self.address = self._label(shell, "Dirección local: —", TEXT, 11, True)
        self.address.pack(anchor="w")
        self.server_status = self._label(shell, "Servidor: sin seleccionar", MUTED, 10)
        self.server_status.pack(anchor="w", pady=(5, 1))

        self._label(shell, "RUTAS LOCALES (NO CAMBIAN LA RED DE WINDOWS)", ACCENT, 10, True).pack(anchor="w", pady=(16, 5))
        self._label(shell, "HTTP CONNECT y SOCKS5 TCP activos en el mismo proceso; sin driver de captura.", TEXT, 10).pack(anchor="w")
        self._label(shell, "Usa el panel de aplicaciones para gestionar bloqueos salientes y políticas.", MUTED, 10).pack(anchor="w", pady=(4, 4))

        self._label(shell, "REGISTRO LOCAL (SIN CREDENCIALES NI URLS DE NAVEGACIÓN)", MUTED, 9, True).pack(anchor="w", pady=(14, 5))
        self.logbox = tk.Text(shell, bg="#0a111d", fg=MUTED, insertbackground=TEXT,
                              height=6, relief="flat", padx=11, pady=9,
                              font=("Consolas", 10), state="disabled", wrap="word")
        self.logbox.pack(fill="both", expand=True)
        self._log("Preparado. El estado 'Escuchando' NO demuestra salida a Internet.")

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
                    self.status.configure(text=text, fg=ACCENT if text.startswith("Salida verificada") else WARN)
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
        return {"Automático · Singapur preferido": "auto", "Singapur": "sgp",
                "Ámsterdam": "ams", "Los Ángeles": "lax", "Servidor manual": "manual"}[self.location_combo.get()]

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
            host_field.insert(0, "Elegido por el catálogo Free")
            host_field.configure(state="disabled")

    def _scan_worker(self, selector: AutoSelector, session: int, refresh: bool):
        source = "catálogo incluido"
        if refresh:
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
            region = COUNTRIES[summary["region"]][0]
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
                self.server_status.configure(text=f'Selección actual: {COUNTRIES[summary["region"]][0]} · {summary["host"]}'
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
            username, password = self.inputs["username"].get(), self.inputs["password"].get()
            remote_port = int(self.inputs["port"].get().strip())
            if region != "manual":
                if remote_port != 443:
                    raise ValueError("El catálogo Free utiliza TLS por el puerto 443")
                self.selector = AutoSelector(username=username, password=password, region=region, preferred="sgp")
                upstream = self.selector.candidates()[0]
            else:
                self.selector = None
                upstream = Upstream(self.inputs["host"].get().strip(), remote_port, username, password).validated()
            port = int(self.inputs["local_port"].get().strip())
            socks_port = int(self.inputs["socks_port"].get().strip())
            endpoints = self.engine.start(upstream, http_port=port, socks_port=socks_port, selector=self.selector)
            self.session += 1
            self.btn.configure(text="DETENER PROXY", bg=WARN)
            self.test_btn.configure(state="normal")
            self.copy_btn.configure(state="normal")
            self.location_combo.configure(state="disabled")
            self.scan_btn.configure(state="normal" if self.selector else "disabled")
            self.status.configure(text="Escuchando localmente · salida sin verificar", fg=WARN)
            self.address.configure(text=f"HTTP http://{LOCAL_HOST}:{endpoints.http_port}    •    SOCKS5 {LOCAL_HOST}:{endpoints.socks5_port}")
            self._log("Ninguna configuración de Windows/Wintun se ha cambiado.")
            if self.selector is not None:
                self.scan_servers(refresh=True)
            else:
                self.server_status.configure(text="Servidor manual · no hay selección automática", fg=MUTED)
        except (OSError, ValueError, RuntimeError) as error:
            self._log(f"No se pudo abrir el servicio local: {type(error).__name__}")
            messagebox.showerror("No se pudo iniciar", str(error))

    def open_traffic_control(self):
        if self.panel and self.panel.win.winfo_exists():
            self.panel.win.lift()
            return
        self.panel = TrafficControlPanel(self.root, lambda: self.engine.endpoints if self.engine.active else None)

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
        self.selector = None
        self._scanning = False
        self.location_combo.configure(state="readonly")
        self.scan_btn.configure(state="disabled")
        self.server_status.configure(text="Servidor: sin seleccionar", fg=MUTED)
        self.btn.configure(text="INICIAR PROXY", bg=ACCENT)
        self.test_btn.configure(state="disabled")
        self.copy_btn.configure(state="disabled")
        self.status.configure(text="Desconectado", fg=MUTED)
        self.address.configure(text="Dirección local: —")

    def close(self):
        self.disconnect()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    DesktopApp(root)
    root.mainloop()
