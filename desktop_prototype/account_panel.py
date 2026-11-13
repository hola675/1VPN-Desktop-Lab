"""Inicio de sesión de CUENTA 1VPN separado de credenciales del proxy HTTPS."""
from __future__ import annotations

import queue
import threading
import tkinter as tk

from account_auth import AccountClient, AccountSession, AccountAuthError

BG, PANEL, TEXT, MUTED, ACCENT, WARN = "#0d1524", "#142238", "#ecf4ff", "#a9bdd9", "#4bc7e6", "#f4b26c"


class AccountPanel:
    def __init__(self, parent: tk.Tk, on_session, client: AccountClient | None = None):
        self.parent = parent
        self.on_session = on_session
        self.client = client or AccountClient()
        self.win = tk.Toplevel(parent)
        self.win.title("1VPN Desktop Lab — Autenticación de cuenta")
        self.win.geometry("640x430")
        self.win.minsize(570, 410)
        self.win.configure(bg=BG)
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.events = queue.Queue()
        self.pending = False
        self.session: AccountSession | None = None

        content = tk.Frame(self.win, bg=BG, padx=25, pady=20)
        content.pack(fill="both", expand=True)
        tk.Label(content, text="CUENTA 1VPN — EMAIL Y CONTRASEÑA", fg=ACCENT, bg=BG,
                 font=("Segoe UI", 13, "bold")).pack(anchor="w")
        tk.Label(content, text="Esta autenticación es de tu cuenta, NO del proxy HTTPS local.",
                 fg=MUTED, bg=BG, font=("Segoe UI", 10)).pack(anchor="w", pady=(4, 10))
        for caption, key, mask in (
            ("Correo electrónico de 1VPN", "email", ""),
            ("Contraseña de la cuenta", "password", "*"),
            ("Código 2FA (solo si 1VPN lo solicita)", "two_factor", ""),
        ):
            tk.Label(content, text=caption, bg=BG, fg=TEXT, font=("Segoe UI", 10)).pack(anchor="w", pady=(9, 2))
            entry = tk.Entry(content, bg=PANEL, fg=TEXT, relief="flat", insertbackground=TEXT,
                             font=("Segoe UI", 11), show=mask)
            entry.pack(fill="x", ipady=6)
            setattr(self, key, entry)
        btns = tk.Frame(content, bg=BG)
        btns.pack(fill="x", pady=(18, 8))
        self.button = tk.Button(btns, text="INICIAR SESIÓN", command=self.login, bg=ACCENT,
                                fg=BG, relief="flat", font=("Segoe UI", 10, "bold"), padx=13, pady=8)
        self.button.pack(side="left")
        tk.Button(btns, text="CERRAR SESIÓN LOCAL", command=self.logout, bg=PANEL,
                  fg=TEXT, relief="flat", font=("Segoe UI", 10), padx=10, pady=8).pack(side="left", padx=8)
        self.status = tk.Label(content, text="Cuenta sin iniciar sesión", bg=BG, fg=MUTED,
                               font=("Segoe UI", 10), anchor="w", wraplength=550, justify="left")
        self.status.pack(anchor="w")
        tk.Label(content, text="Correo y clave: POST HTTPS JSON a 1VPN. Sesión en memoria, sin guardar contraseña.",
                 fg=MUTED, bg=BG, font=("Segoe UI", 9), wraplength=560, justify="left").pack(anchor="w", pady=(9, 0))
        self.win.after(120, self.poll)

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
