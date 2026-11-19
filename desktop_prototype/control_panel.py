"""Panel integrado de aplicaciones y reglas firewall (sin captura transparente)."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from firewall_rules import FirewallManager, rule_name
from traffic_policy import AppPolicy, PolicyStore, normalize_executable, executable_key
from running_apps import list_running_apps
from proxifyre_adapter import (
    DRAFT_FILE_NAME, DENIED_TARGETS, build_proxifyre_draft, describe_proxifyre_draft,
    save_proxifyre_draft,
)

BG = "#0d1524"
TEXT = "#ecf4ff"
PANEL = "#142238"
ACCENT = "#4bc7e6"

MODE_LABELS = {
    "MANUAL_PROXY": "PROXY MANUAL (app compatible)",
    "DIRECT": "DIRECTO (excluir de ProxiFyre)",
    "BLOCK": "BLOQUEAR (firewall Windows)",
    "TRANSPARENT": "PROXY (ProxiFyre TCP/IPv4)",
}


class TrafficControlPanel:
    def __init__(self, parent: tk.Tk, endpoint_getter, verified_getter=None):
        self.parent = parent
        self.endpoint_getter = endpoint_getter
        self.verified_getter = verified_getter or (lambda: False)
        self.store = PolicyStore()
        self.firewall = FirewallManager()
        self.win = tk.Toplevel(parent)
        self.win.title("1VPN Desktop Lab — Aplicaciones y firewall")
        self.win.geometry("1120x780")
        self.win.minsize(1000, 700)
        self.win.configure(bg=BG)
        self._layout()
        self.refresh()
        self.refresh_running()
        self.win.after(10000, self._periodic_refresh_running)

    def _label(self, parent, text, color=TEXT, size=10):
        return tk.Label(parent, text=text, font=("Segoe UI", size), fg=color, bg=parent["bg"], anchor="w")

    def _button(self, parent, text, callback):
        return tk.Button(parent, text=text, command=callback, font=("Segoe UI", 9, "bold"),
                         bg=PANEL, fg=TEXT, activebackground="#254260", activeforeground=TEXT,
                         relief="flat", padx=10, pady=8)

    def _layout(self):
        body = tk.Frame(self.win, bg=BG, padx=22, pady=18)
        body.pack(fill="both", expand=True)
        self._label(body, "APLICACIONES EN EJECUCIÓN / POLÍTICAS POR .EXE", ACCENT, 15).pack(anchor="w")
        self._label(body, "PROXY: ProxiFyre + Windows Packet Filter externos · DIRECTO: excluido · BLOQUEAR: Firewall (admin)",
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
        external = tk.Frame(body, bg=BG)
        external.pack(fill="x", pady=(0, 10))
        self._button(external, "PREPARAR PERFIL PROXIFYRE (TCP)", self.prepare_proxifyre).pack(side="left")
        self._button(external, "DIAGNÓSTICO DRIVER/SERVICIO", self.check_proxifyre).pack(side="left", padx=8)
        self._label(body, "PROCESOS EN EJECUCIÓN — selecciona un .exe para elegir PROXY / DIRECTO / BLOQUEAR",
                    ACCENT, 10).pack(anchor="w", pady=(4, 3))
        self._button(body, "Actualizar aplicaciones en ejecución", self.refresh_running).pack(anchor="w", pady=(0, 6))
        running_columns = ("exe", "pids", "policy", "path")
        self.running_tree = ttk.Treeview(
            body, columns=running_columns, show="headings", height=8, selectmode="browse"
        )
        for name, title, width in (
            ("exe", "Aplicación (.exe)", 190),
            ("pids", "Procesos (PID)", 140),
            ("policy", "Política", 225),
            ("path", "Ruta del ejecutable", 470),
        ):
            self.running_tree.heading(name, text=title)
            self.running_tree.column(name, width=width, anchor="w")
        self.running_tree.pack(fill="x", pady=(0, 7))
        self.running_tree.bind("<<TreeviewSelect>>", self.select_running)
        self._running_index: dict[str, str] = {}
        self._label(body, "POLÍTICAS GUARDADAS (cualquier instancia del mismo ejecutable)",
                    ACCENT, 10).pack(anchor="w", pady=(4, 3))
        columns = ("path", "mode", "firewall")
        self.tree = ttk.Treeview(body, columns=columns, show="headings", height=7, selectmode="browse")
        for key, label, width in (("path", "Ejecutable", 430), ("mode", "Política", 245),
                                  ("firewall", "Regla gestionada", 135)):
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.select_rule)
        self.info = self._label(body, "PROXY requiere ProxiFyre/WinpkFilter instalado y activo; DIRECTO excluye, BLOQUEAR usa Firewall.", "#a9bdd9")
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
                active = "Firewall activo" if rule_name(rule.executable) in managed else "Sin bloqueo aplicado"
                self.tree.insert("", "end", values=(rule.executable, MODE_LABELS[rule.mode], active))
            self.refresh_running()
        except Exception as e:
            messagebox.showerror("Políticas", str(e), parent=self.win)

    def refresh_running(self):
        """Read-only list of accessible running executables; never infer by hostname."""
        if not hasattr(self, "running_tree"):
            return
        try:
            selected = self.running_tree.selection()
            old_path = self._running_index.get(selected[0], "") if selected else ""
            self.running_tree.delete(*self.running_tree.get_children())
            self._running_index = {}
            modes = {executable_key(rule.executable): rule.mode for rule in self.store.load()}
            for app in list_running_apps():
                iid = self.running_tree.insert(
                    "", "end",
                    values=(
                        app.name,
                        ", ".join(str(pid) for pid in app.pids[:7])
                        + (f" (+{len(app.pids) - 7})" if len(app.pids) > 7 else ""),
                        MODE_LABELS[modes[executable_key(app.executable)]]
                        if executable_key(app.executable) in modes
                        else "SIN REGLA (directo)",
                        app.executable,
                    ),
                )
                self._running_index[iid] = app.executable
                if old_path and executable_key(old_path) == executable_key(app.executable):
                    self.running_tree.selection_set(iid)
        except (OSError, ValueError, RuntimeError) as error:
            self.info.configure(text=f"No se pudo actualizar procesos: {type(error).__name__}")

    def _periodic_refresh_running(self):
        if not self.win.winfo_exists():
            return
        self.refresh_running()
        self.win.after(10000, self._periodic_refresh_running)

    def select_running(self, _event=None):
        selection = self.running_tree.selection()
        if not selection:
            return
        executable = self._running_index.get(selection[0])
        if not executable:
            return
        self.path.delete(0, "end")
        self.path.insert(0, executable)
        policy = next(
            (p for p in self.store.load()
             if executable_key(p.executable) == executable_key(executable)), None
        )
        self.mode.set(MODE_LABELS[policy.mode] if policy else MODE_LABELS["DIRECT"])
        self.info.configure(
            text=f"Seleccionado: {Path(executable).name}. La política se aplica a "
                 "todas las instancias de este .exe, NO a una dirección o dominio."
        )

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
            if mode in {"TRANSPARENT", "BLOCK"} and Path(exe).name.casefold() in DENIED_TARGETS:
                raise ValueError(
                    "No se permite capturar ni bloquear el motor OneTunnel, "
                    "ProxiFyre, Xray o procesos esenciales de Windows"
                )
            if mode != "BLOCK" and rule_name(exe) in self.firewall.managed():
                raise RuntimeError("Retira el bloqueo de firewall antes de cambiar la política")
            self.store.upsert(AppPolicy(exe, mode))
            self.refresh()
            if mode == "BLOCK":
                state = "BLOQUEO guardado; aplica Windows Firewall con su botón y confirmación."
            elif mode == "TRANSPARENT":
                state = "PROXY guardado; prepara el perfil y actívalo manualmente con ProxiFyre."
            else:
                state = "Política guardada. DIRECTO requiere incluir la exclusión en ProxiFyre activo."
            self.info.configure(text=state)
        except Exception as e:
            messagebox.showerror("Guardar política", str(e), parent=self.win)

    def block(self):
        try:
            exe = self._selected()
            if Path(exe).name.casefold() in DENIED_TARGETS:
                raise ValueError("Se ha protegido este proceso esencial o portador de VPN contra bloqueos")
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

    def prepare_proxifyre(self):
        """Create a review-only config, without installing or starting drivers."""
        try:
            endpoints = self.endpoint_getter()
            if endpoints is None:
                raise RuntimeError("Primero inicia el proxy HTTP/SOCKS5 de OneTunnel")
            if not self.verified_getter():
                raise RuntimeError(
                    "Pulsa COMPROBAR SALIDA en la ventana principal y verifica la IP HTTPS "
                    "antes de preparar un perfil de captura por aplicación."
                )
            profile = build_proxifyre_draft(
                self.store.load(), endpoints.socks5_port,
                self.firewall.managed().values(),
            )
            preview = describe_proxifyre_draft(profile)
            if not messagebox.askyesno(
                "ProxiFyre — SOLO BORRADOR",
                preview + "\n\n¿Guardar este borrador sin modificar el sistema?",
                parent=self.win,
            ):
                return
            target = filedialog.asksaveasfilename(
                parent=self.win,
                title="Guardar borrador ProxiFyre (NO app-config.json)",
                initialfile=DRAFT_FILE_NAME,
                defaultextension=".json",
                filetypes=[("Archivo JSON", "*.json")],
            )
            if not target:
                return
            saved = save_proxifyre_draft(target, profile)
            self.info.configure(
                text="Borrador creado. No se modificó el firewall, el servicio ni la red. "
                     "Revisa DNS/UDP antes de aplicar manualmente en ProxiFyre."
            )
            messagebox.showinfo(
                "Borrador exportado",
                f"Archivo: {saved}\n\n"
                "NO se ha activado la redirección. En ProxiFyre oficial "
                "revisa aplicaciones, SOCKS5 TCP/IPv4 y exclusiones. "
                "DNS permanece Directo; UDP no está protegido. "
                "No uses este perfil como kill switch.",
                parent=self.win,
            )
        except (OSError, ValueError, RuntimeError) as error:
            messagebox.showerror(
                "ProxiFyre — preparación",
                str(error), parent=self.win,
            )

    @staticmethod
    def _query_service(service: str) -> str:
        """Read-only sc.exe query; never install, modify or start a service."""
        if os.name != "nt":
            return "Solo disponible en Windows"
        try:
            result = subprocess.run(
                ["sc.exe", "query", service],
                capture_output=True, text=True, timeout=6, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return "No se pudo consultar"
        if result.returncode:
            return "No está registrado o no es accesible"
        output = result.stdout.upper()
        if "RUNNING" in output:
            return "RUNNING (en ejecución)"
        if "STOPPED" in output:
            return "STOPPED (detenido)"
        return "Registrado (estado indeterminado)"

    def check_proxifyre(self):
        """Read-only check for the external service and WinpkFilter driver."""
        service = self._query_service("ProxiFyreService")
        driver = self._query_service("NDISRD")
        messagebox.showinfo(
            "ProxiFyre — estado del equipo (solo lectura)",
            f"ProxiFyreService: {service}\nNDISRD: {driver}\n\n"
            "Este diagnóstico NO instala controladores ni ejecuta reglas. "
            "Un servicio RUNNING tampoco garantiza redirección ni ausencia de fugas. "
            "Antes de aplicar la configuración, comprueba salida TCP real "
            "por el SOCKS5 y el comportamiento de DNS, UDP y IPv6.",
            parent=self.win,
        )

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
