"""Interfaz de prueba para Windows. Solo proxies HTTPS con permiso de uso."""
from __future__ import annotations

import atexit
import platform
import queue
import tkinter as tk
from tkinter import messagebox, ttk

from proxycore import ProxyRelay, Upstream
from windows_proxy import WindowsProxy

BG = "#0d1524"
PANEL = "#142238"
TEXT = "#ecf4ff"
MUTED = "#9db3cf"
ACCENT = "#4bc7e6"


class DesktopApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("1VPN Desktop Lab — Prototipo de proxy HTTPS")
        self.root.geometry("800x580")
        self.root.minsize(690, 540)
        self.root.configure(bg=BG)
        self.proxy = WindowsProxy()
        self.relay: ProxyRelay | None = None
        self.apply_windows = tk.BooleanVar(value=False)
        self.message_queue: queue.Queue[str] = queue.Queue()
        self.connected = False
        self._layout()
        self._recover()
        root.after(150, self._poll_log)
        root.protocol("WM_DELETE_WINDOW", self.close)
        atexit.register(self.disconnect)

    def _label(self, parent, text: str, color=MUTED, size=11, bold=False):
        return tk.Label(parent, text=text, fg=color, bg=parent["bg"], font=("Segoe UI", size, "bold" if bold else "normal"), anchor="w")

    def _layout(self):
        shell = tk.Frame(self.root, bg=BG, padx=32, pady=24)
        shell.pack(fill="both", expand=True)
        self._label(shell, "DESKTOP LAB  /  v0.1", ACCENT, 11, True).pack(anchor="w")
        self._label(shell, "Cliente local de proxy HTTPS", TEXT, 24, True).pack(anchor="w", pady=(10, 2))
        self._label(shell, "Una prueba independiente. No es una VPN ni un cliente oficial de 1VPN.", MUTED, 10).pack(anchor="w", pady=(0, 20))
        panel = tk.Frame(shell, bg=PANEL, padx=22, pady=16)
        panel.pack(fill="x")
        self.inputs = {}
        for row, (key, caption, default, secret) in enumerate([
            ("host", "Servidor proxy HTTPS", "", False),
            ("port", "Puerto TLS", "443", False),
            ("username", "Usuario (opcional)", "", False),
            ("password", "Contraseña (solo en memoria)", "", True),
        ]):
            lbl = self._label(panel, caption, TEXT, 10)
            lbl.grid(row=row, column=0, sticky="w", pady=6)
            entry = tk.Entry(panel, bg=BG, fg=TEXT, insertbackground=TEXT, relief="flat", font=("Consolas", 11), show="*" if secret else "")
            entry.insert(0, default)
            entry.grid(row=row, column=1, padx=(18, 0), pady=6, sticky="ew", ipady=7)
            self.inputs[key] = entry
        panel.columnconfigure(1, weight=1)
        tk.Checkbutton(shell, text="Aplicar temporalmente como proxy de Windows (WinINET; modifica HKCU)", variable=self.apply_windows,
                       bg=BG, fg=TEXT, selectcolor=PANEL, activebackground=BG, activeforeground=TEXT,
                       font=("Segoe UI", 10), anchor="w").pack(anchor="w", pady=(17, 5))
        self._label(shell, "Sin marcar, solo inicia un proxy en 127.0.0.1 y muestra el puerto.", MUTED, 10).pack(anchor="w")
        bar = tk.Frame(shell, bg=BG)
        bar.pack(fill="x", pady=(18, 8))
        self.btn = tk.Button(bar, text="INICIAR PROXY", command=self.toggle, bg=ACCENT, fg=BG,
                             activebackground="#93e7fa", relief="flat", font=("Segoe UI", 11, "bold"), padx=24, pady=11)
        self.btn.pack(side="left")
        self.status = self._label(bar, "Desconectado", MUTED, 11, True)
        self.status.pack(side="left", padx=18)
        self._label(shell, "REGISTRO LOCAL (SIN URL NI CREDENCIALES)", MUTED, 9, True).pack(anchor="w", pady=(12, 5))
        self.logbox = tk.Text(shell, bg="#0a111d", fg=MUTED, insertbackground=TEXT, height=5, relief="flat", padx=10, pady=8, font=("Consolas", 10), state="disabled")
        self.logbox.pack(fill="both", expand=True)
        self._log("Preparado. Necesitas un proxy HTTPS propio o autorizado.")

    def _log(self, msg: str):
        self.message_queue.put(msg)

    def _poll_log(self):
        try:
            while True:
                msg = self.message_queue.get_nowait()
                self.logbox.configure(state="normal")
                self.logbox.insert("end", f"• {msg}\n")
                self.logbox.see("end")
                self.logbox.configure(state="disabled")
        except queue.Empty:
            pass
        self.root.after(150, self._poll_log)

    def _recover(self):
        if platform.system() != "Windows":
            self._log("Interfaz de prueba: Windows requerido para activar el proxy del sistema.")
            return
        try:
            if self.proxy.recover_stale():
                self._log("Se restauró la configuración WinINET anterior de una sesión interrumpida.")
        except Exception as error:
            self._log(f"Recuperación de WinINET pendiente: {error}")
            messagebox.showwarning("Configuración pendiente", str(error))

    def toggle(self):
        if self.connected:
            self.disconnect()
            return
        try:
            port = int(self.inputs["port"].get().strip())
            upstream = Upstream(
                self.inputs["host"].get().strip(), port,
                self.inputs["username"].get(), self.inputs["password"].get()
            ).validated()
            self.relay = ProxyRelay(upstream, self._log)
            local_port = self.relay.start()
            if self.apply_windows.get():
                if platform.system() != "Windows":
                    raise RuntimeError("Windows requerido para cambiar el proxy del sistema")
                self.proxy.activate(local_port)
                self._log("Proxy WinINET aplicado para el usuario actual; se restaurará al detener.")
            else:
                self._log(f"Configura manualmente HTTP proxy 127.0.0.1:{local_port} en tu navegador.")
            self.connected = True
            self.btn.configure(text="DETENER Y RESTAURAR", bg="#f4b26c")
            self.status.configure(text=f"Proxy local activo · :{local_port}", fg=ACCENT)
        except (ValueError, RuntimeError, OSError) as error:
            self.disconnect()
            messagebox.showerror("No se pudo iniciar", str(error))

    def disconnect(self):
        if self.proxy.active:
            try:
                self.proxy.restore()
                self._log("Configuración de proxy Windows restaurada.")
            except Exception as error:
                self._log(f"ATENCIÓN: restauración pendiente: {error}")
        if self.relay:
            self.relay.stop()
            self.relay = None
        self.connected = False
        try:
            self.btn.configure(text="INICIAR PROXY", bg=ACCENT)
            self.status.configure(text="Desconectado", fg=MUTED)
        except tk.TclError:
            pass

    def close(self):
        self.disconnect()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    DesktopApp(root)
    root.mainloop()
