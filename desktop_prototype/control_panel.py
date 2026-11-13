"""Panel integrado de aplicaciones y reglas firewall (sin captura transparente)."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from firewall_rules import FirewallManager, rule_name
from traffic_policy import AppPolicy, PolicyStore, normalize_executable

BG = "#0d1524"
TEXT = "#ecf4ff"
PANEL = "#142238"
ACCENT = "#4bc7e6"

MODE_LABELS = {
    "MANUAL_PROXY": "PROXY MANUAL (app compatible)",
    "DIRECT": "DIRECTO (no se intercepta)",
    "BLOCK": "BLOQUEAR (firewall Windows)",
    "TRANSPARENT": "TRANSPARENTE (pendiente driver)",
}


class TrafficControlPanel:
    def __init__(self, parent: tk.Tk, endpoint_getter):
        self.parent = parent
        self.endpoint_getter = endpoint_getter
        self.store = PolicyStore()
        self.firewall = FirewallManager()
        self.win = tk.Toplevel(parent)
        self.win.title("1VPN Desktop Lab — Aplicaciones y firewall")
        self.win.geometry("980x620")
        self.win.configure(bg=BG)
        self._layout()
        self.refresh()

    def _label(self, parent, text, color=TEXT, size=10):
        return tk.Label(parent, text=text, font=("Segoe UI", size), fg=color, bg=parent["bg"], anchor="w")

    def _button(self, parent, text, callback):
        return tk.Button(parent, text=text, command=callback, font=("Segoe UI", 9, "bold"),
                         bg=PANEL, fg=TEXT, activebackground="#254260", activeforeground=TEXT,
                         relief="flat", padx=10, pady=8)

    def _layout(self):
        body = tk.Frame(self.win, bg=BG, padx=22, pady=18)
        body.pack(fill="both", expand=True)
        self._label(body, "APLICACIONES Y FIREWALL / v0.4", ACCENT, 15).pack(anchor="w")
        self._label(body, "Sin controlador: PROXY solo manual o por variables de entorno. BLOQUEAR requiere administrador.",
                    "#ffcc87").pack(anchor="w", pady=(5, 14))
        row = tk.Frame(body, bg=BG)
        row.pack(fill="x")
        self.path = tk.Entry(row, bg=PANEL, fg=TEXT, insertbackground=TEXT, font=("Consolas", 10))
        self.path.pack(side="left", expand=True, fill="x")
        self._button(row, "Elegir .exe", self.browse).pack(side="left", padx=8)
        modes = list(MODE_LABELS.values())
        self.mode = ttk.Combobox(row, values=modes, state="readonly", width=32)
        self.mode.current(0)
        self.mode.pack(side="left")
        bar = tk.Frame(body, bg=BG)
        bar.pack(fill="x", pady=(12, 10))
        self._button(bar, "Guardar política", self.save_rule).pack(side="left")
        self._button(bar, "Aplicar BLOQUEO", self.block).pack(side="left", padx=7)
        self._button(bar, "Retirar bloqueo", self.unblock).pack(side="left", padx=7)
        self._button(bar, "Eliminar política", self.delete_rule).pack(side="left", padx=7)
        self._button(bar, "Iniciar con variables proxy", self.launch_with_proxy).pack(side="left", padx=7)
        columns = ("path", "mode", "firewall")
        self.tree = ttk.Treeview(body, columns=columns, show="headings", height=13, selectmode="browse")
        for key, label, width in (("path", "Ejecutable", 430), ("mode", "Política", 245),
                                  ("firewall", "Regla gestionada", 135)):
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.select_rule)
        self.info = self._label(body, "Las reglas PROXY no interceptan aplicaciones sin motor nativo.", "#a9bdd9")
        self.info.pack(anchor="w", pady=10)

    def browse(self):
        path = filedialog.askopenfilename(parent=self.win, filetypes=[("Programas Windows", "*.exe")])
        if path:
            self.path.delete(0, "end")
            self.path.insert(0, path)

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        try:
            managed = self.firewall.managed()
            for rule in self.store.load():
                active = "Registrada" if rule_name(rule.executable) in managed else "No registrada"
                self.tree.insert("", "end", values=(rule.executable, MODE_LABELS[rule.mode], active))
        except Exception as e:
            messagebox.showerror("Políticas", str(e), parent=self.win)

    def select_rule(self, _event=None):
        items = self.tree.selection()
        if not items:
            return
        exe, mode, _ = self.tree.item(items[0], "values")
        self.path.delete(0, "end")
        self.path.insert(0, exe)
        self.mode.set(mode)

    def _selected(self):
        return normalize_executable(self.path.get())

    def _mode(self):
        return next(code for code, label in MODE_LABELS.items() if label == self.mode.get())

    def save_rule(self):
        try:
            exe = self._selected()
            mode = self._mode()
            if mode != "BLOCK" and rule_name(exe) in self.firewall.managed():
                raise RuntimeError("Retira el bloqueo de firewall antes de cambiar la política")
            self.store.upsert(AppPolicy(exe, mode))
            self.refresh()
            self.info.configure(text="Política guardada. No se ha modificado la red del sistema.")
        except Exception as e:
            messagebox.showerror("Guardar política", str(e), parent=self.win)

    def block(self):
        try:
            exe = self._selected()
            if not messagebox.askyesno("Confirmar bloqueo", f"Se bloquearán las conexiones SALIENTES de:\n{exe}\n\n"
                                       "Esto puede desconectar el programa. ¿Continuar?", parent=self.win):
                return
            self.firewall.block(exe)
            self.store.upsert(AppPolicy(exe, "BLOCK"))
            self.refresh()
            self.info.configure(text="Regla de bloqueo aplicada. Puede retirarse desde este panel.")
        except Exception as e:
            messagebox.showerror("Firewall", str(e), parent=self.win)

    def unblock(self):
        try:
            # Permitir retirar una regla incluso si el archivo EXE fue desinstalado.
            exe = self.path.get().strip().strip('"')
            if not os.path.isabs(exe) or not exe.lower().endswith(".exe"):
                raise ValueError("Es necesaria una ruta absoluta a un ejecutable .exe")
            if messagebox.askyesno("Retirar bloqueo", f"¿Retirar la regla gestionada de {Path(exe).name}?", parent=self.win):
                removed = self.firewall.unblock(exe)
                self.refresh()
                self.info.configure(text="Regla retirada." if removed else "No existía una regla gestionada.")
        except Exception as e:
            messagebox.showerror("Firewall", str(e), parent=self.win)

    def delete_rule(self):
        try:
            exe = self._selected()
            if rule_name(exe) in self.firewall.managed():
                raise RuntimeError("Retira primero la regla de firewall y luego elimina la política")
            self.store.delete(exe)
            self.refresh()
        except Exception as e:
            messagebox.showerror("Eliminar política", str(e), parent=self.win)

    def launch_with_proxy(self):
        try:
            exe = self._selected()
            endpoints = self.endpoint_getter()
            if endpoints is None:
                raise RuntimeError("Inicia primero el motor integrado HTTP/SOCKS5")
            if not messagebox.askyesno("Iniciar aplicación", "Solo afecta programas que respetan HTTP_PROXY/HTTPS_PROXY/ALL_PROXY.\n"
                                       "No es captura transparente. ¿Abrir el programa?", parent=self.win):
                return
            env = os.environ.copy()
            env.update({
                "HTTP_PROXY": f"http://127.0.0.1:{endpoints.http_port}",
                "HTTPS_PROXY": f"http://127.0.0.1:{endpoints.http_port}",
                "ALL_PROXY": f"socks5h://127.0.0.1:{endpoints.socks5_port}",
                "NO_PROXY": "localhost,127.0.0.1,::1",
            })
            subprocess.Popen([exe], env=env, cwd=str(Path(exe).parent))
            self.info.configure(text=f"Iniciada {Path(exe).name} con variables proxy. La aplicación puede ignorarlas.")
        except Exception as e:
            messagebox.showerror("Iniciar aplicación", str(e), parent=self.win)
