"""1VPN Desktop Lab v0.4: motor HTTP/SOCKS5 y panel firewall integrados."""
from __future__ import annotations

import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import messagebox

from connection_check import probe_exit_ip
from proxycore import Upstream
from network_engine import NetworkEngine
from control_panel import TrafficControlPanel

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
        self.root.title("1VPN Desktop Lab — Control de tráfico v0.4")
        self.root.geometry("1080x780")
        self.root.minsize(960, 710)
        self.root.configure(bg=BG)
        self.engine = NetworkEngine(self._log)
        self.panel = None
        self.events: queue.Queue[tuple[str, str, int | None]] = queue.Queue()
        self.session = 0
        self._layout()
        self._warn_legacy_settings()
        root.after(150, self._poll_events)
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
        self._label(shell, "DESKTOP LAB  /  v0.4  /  HTTP + SOCKS5 + FIREWALL", ACCENT, 11, True).pack(anchor="w")
        self._label(shell, "Proxy y políticas de tráfico para Windows", TEXT, 23, True).pack(anchor="w", pady=(9, 4))
        self._label(
            shell, "Motor integrado sin Wintun ni capturador de paquetes. Firewall solo con aprobación.",
            MUTED, 10,
        ).pack(anchor="w", pady=(0, 17))

        panel = tk.Frame(shell, bg=PANEL, padx=22, pady=14)
        panel.pack(fill="x")
        self.inputs: dict[str, tk.Entry] = {}
        rows = [
            ("host", "Servidor proxy HTTPS remoto", "", False),
            ("port", "Puerto remoto (TLS)", "443", False),
            ("username", "Usuario remoto (opcional)", "", False),
            ("password", "Contraseña (solo memoria)", "", True),
            ("local_port", "Puerto HTTP local (0 = automático)", DEFAULT_LOCAL_PORT, False),
            ("socks_port", "Puerto SOCKS5 local (0 = automático)", "1080", False),
        ]
        for i, (key, name, default, secret) in enumerate(rows):
            self._label(panel, name, TEXT, 10).grid(row=i, column=0, sticky="w", pady=5)
            entry = tk.Entry(panel, bg=BG, fg=TEXT, insertbackground=TEXT, relief="flat",
                             font=("Consolas", 11), show="*" if secret else "")
            entry.insert(0, default)
            entry.grid(row=i, column=1, sticky="ew", padx=(18, 0), pady=5, ipady=7)
            self.inputs[key] = entry
        panel.columnconfigure(1, weight=1)

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
        self.status = self._label(shell, "Desconectado", MUTED, 11, True)
        self.status.pack(anchor="w", pady=(7, 7))
        self.address = self._label(shell, "Dirección local: —", TEXT, 11, True)
        self.address.pack(anchor="w")

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
        except queue.Empty:
            pass
        self.root.after(150, self._poll_events)

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
            upstream = Upstream(
                self.inputs["host"].get().strip(),
                int(self.inputs["port"].get().strip()),
                self.inputs["username"].get(),
                self.inputs["password"].get(),
            ).validated()
            port = int(self.inputs["local_port"].get().strip())
            socks_port = int(self.inputs["socks_port"].get().strip())
            endpoints = self.engine.start(upstream, http_port=port, socks_port=socks_port)
            self.session += 1
            self.btn.configure(text="DETENER PROXY", bg=WARN)
            self.test_btn.configure(state="normal")
            self.copy_btn.configure(state="normal")
            self.status.configure(text="Escuchando localmente · salida sin verificar", fg=WARN)
            self.address.configure(text=f"HTTP http://{LOCAL_HOST}:{endpoints.http_port}    •    SOCKS5 {LOCAL_HOST}:{endpoints.socks5_port}")
            self._log("Ninguna configuración de Windows/Wintun se ha cambiado.")
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
