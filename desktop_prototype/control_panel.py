"""Panel de políticas por EXE: bloqueo WFP propio; redirección nativa pendiente."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from firewall_rules import FirewallManager  # Exclusivamente retirada de bloqueos heredados.
from native_wfp import NativeWfpGuard, FORBIDDEN_APP_NAMES
from traffic_policy import AppPolicy, PolicyStore, app_name_from_path, normalize_app_name, executable_key
from running_apps import list_running_apps

BG = "#0d1524"
TEXT = "#ecf4ff"
PANEL = "#142238"
ACCENT = "#4bc7e6"

MODE_LABELS = {
    "MANUAL_PROXY": "PROXY MANUAL (app compatible)",
    "DIRECT": "DIRECTO (red normal de Windows)",
    "BLOCK": "BLOQUEAR (WFP nativo)",
    "TRANSPARENT": "PROXY (motor WFP pendiente)",
}


class TrafficControlPanel:
    def __init__(self, parent: tk.Tk, endpoint_getter, verified_getter=None, native_guard=None):
        self.parent = parent
        self.endpoint_getter = endpoint_getter
        self.verified_getter = verified_getter or (lambda: False)
        self.store = PolicyStore()
        self.guard = native_guard or NativeWfpGuard()
        # Read legacy managed Windows Firewall rules only to remove them on request.
        self.legacy_firewall = FirewallManager()
        self._browsed_paths: dict[str, set[str]] = {}
        self.win = tk.Toplevel(parent)
        self.win.title("OneTunnel — Motor WFP nativo por aplicación")
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
        self._label(body, "APLICACIONES EN EJECUCIÓN / REGLAS POR NOMBRE .EXE", ACCENT, 15).pack(anchor="w")
        self._label(body, "DIRECTO: disponible · BLOQUEAR: WFP integrado (admin) · PROXY: requiere callout firmado (pendiente)",
                    "#ffcc87").pack(anchor="w", pady=(5, 14))
        row = tk.Frame(body, bg=BG)
        row.pack(fill="x")
        self.app_name = tk.Entry(row, bg=PANEL, fg=TEXT, insertbackground=TEXT, font=("Consolas", 10))
        self.app_name.insert(0, "chrome.exe")
        self.app_name.pack(side="left", expand=True, fill="x")
        self._button(row, "Buscar aplicación .exe", self.browse).pack(side="left", padx=8)
        modes = list(MODE_LABELS.values())
        self.mode = ttk.Combobox(row, values=modes, state="readonly", width=32)
        self.mode.current(0)
        self.mode.pack(side="left")
        bar = tk.Frame(body, bg=BG)
        bar.pack(fill="x", pady=(12, 10))
        self._button(bar, "Guardar política", self.save_rule).pack(side="left")
        self._button(bar, "APLICAR BLOQUEO WFP", self.block).pack(side="left", padx=7)
        self._button(bar, "RETIRAR BLOQUEO WFP", self.unblock).pack(side="left", padx=7)
        self._button(bar, "Eliminar política", self.delete_rule).pack(side="left", padx=7)
        self._button(bar, "Iniciar con variables proxy", self.launch_with_proxy).pack(side="left", padx=7)
        external = tk.Frame(body, bg=BG)
        external.pack(fill="x", pady=(0, 10))
        self._button(external, "ESTADO DEL MOTOR NATIVO", self.check_native_wfp).pack(side="left")
        self._button(external, "RETIRAR REGLAS HEREDADAS", self.cleanup_legacy_firewall).pack(side="left", padx=8)
        self._label(body, "PROCESOS EN EJECUCIÓN — selecciona un .exe para elegir PROXY / DIRECTO / BLOQUEAR",
                    ACCENT, 10).pack(anchor="w", pady=(4, 3))
        self._button(body, "Actualizar aplicaciones en ejecución", self.refresh_running).pack(anchor="w", pady=(0, 6))
        running_columns = ("exe", "pids", "policy", "instances")
        self.running_tree = ttk.Treeview(
            body, columns=running_columns, show="headings", height=8, selectmode="browse"
        )
        for name, title, width in (
            ("exe", "Aplicación (.exe)", 190),
            ("pids", "Procesos (PID)", 140),
            ("policy", "Política", 225),
            ("instances", "Ubicaciones en ejecución", 180),
        ):
            self.running_tree.heading(name, text=title)
            self.running_tree.column(name, width=width, anchor="w")
        self.running_tree.pack(fill="x", pady=(0, 7))
        self.running_tree.bind("<<TreeviewSelect>>", self.select_running)
        self._running_index: dict[str, str] = {}
        self._label(body, "POLÍTICAS GUARDADAS (cualquier instancia del mismo ejecutable)",
                    ACCENT, 10).pack(anchor="w", pady=(4, 3))
        columns = ("name", "mode", "firewall")
        self.tree = ttk.Treeview(body, columns=columns, show="headings", height=7, selectmode="browse")
        for key, label, width in (("name", "Nombre EXE (cualquier carpeta)", 310), ("mode", "Política", 245),
                                  ("firewall", "Regla gestionada", 135)):
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.select_rule)
        self.info = self._label(body, "El bloqueo WFP dura mientras OneTunnel está abierto. PROXY transparente todavía NO funciona.", "#a9bdd9")
        self.info.pack(anchor="w", pady=10)

    def _choose_name(self, name: str):
        name = normalize_app_name(name)
        self.app_name.delete(0, "end")
        self.app_name.insert(0, name)

    def browse(self):
        path = filedialog.askopenfilename(
            parent=self.win, filetypes=[("Programas Windows", "*.exe")]
        )
        if path:
            name = app_name_from_path(path)
            self._browsed_paths.setdefault(name, set()).add(path)
            self._choose_name(name)
            self.info.configure(
                text=f"{name} seleccionado. La política se guarda por NOMBRE y "
                     "abarca cualquier carpeta; Firewall usa rutas detectadas."
            )

    def _managed_paths(self, app_name: str) -> list[str]:
        name = normalize_app_name(app_name)
        return sorted(
            {p for p in self.guard.managed().values()
             if app_name_from_path(p) == name},
            key=str.casefold,
        )

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        try:
            for rule in self.store.load():
                count = len(self._managed_paths(rule.executable))
                state = f"Bloqueadas {count} ruta(s)" if count else "Sin bloqueo aplicado"
                self.tree.insert(
                    "", "end",
                    values=(rule.executable, MODE_LABELS[rule.mode], state),
                )
            self.refresh_running()
        except (OSError, ValueError, RuntimeError) as error:
            messagebox.showerror("Políticas", str(error), parent=self.win)

    def refresh_running(self):
        """Show one application per basename and all its PID instances."""
        if not hasattr(self, "running_tree"):
            return
        try:
            modes = {p.executable: p.mode for p in self.store.load()}
            new_index: dict[str, str] = {}
            for index, app in enumerate(list_running_apps()):
                iid = "name-" + hashlib.sha256(
                    app.name.encode("utf-8")
                ).hexdigest()[:32]
                pids = ", ".join(str(pid) for pid in app.pids[:7])
                if len(app.pids) > 7:
                    pids += f" (+{len(app.pids) - 7})"
                values = (
                    app.name, pids,
                    MODE_LABELS[modes[app.name]] if app.name in modes
                    else "SIN REGLA (directo)",
                    str(len(app.paths)),
                )
                if self.running_tree.exists(iid):
                    self.running_tree.item(iid, values=values)
                else:
                    self.running_tree.insert("", "end", iid=iid, values=values)
                self.running_tree.move(iid, "", index)
                new_index[iid] = app.name
            for iid in self.running_tree.get_children():
                if iid not in new_index:
                    self.running_tree.delete(iid)
            self._running_index = new_index
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
        name = self._running_index.get(selection[0])
        if not name:
            return
        self._choose_name(name)
        policy = next(
            (p for p in self.store.load() if p.executable == name), None
        )
        self.mode.set(MODE_LABELS[policy.mode] if policy else MODE_LABELS["DIRECT"])
        self.info.configure(
            text=f"Seleccionado {name}: la regla cubre TODOS los procesos con "
                 "ese nombre sin importar su carpeta de instalación."
        )

    def select_rule(self, _event=None):
        items = self.tree.selection()
        if not items:
            return
        name, mode, _ = self.tree.item(items[0], "values")
        self._choose_name(name)
        self.mode.set(mode)

    def _selected(self) -> str:
        return normalize_app_name(self.app_name.get())

    def _mode(self):
        return next(code for code, label in MODE_LABELS.items()
                    if label == self.mode.get())

    def save_rule(self):
        try:
            name = self._selected()
            mode = self._mode()
            if mode in {"TRANSPARENT", "BLOCK"} and name in FORBIDDEN_APP_NAMES:
                raise ValueError(
                    "No se puede capturar ni bloquear el motor VPN "
                    "o un proceso esencial de Windows"
                )
            if mode != "BLOCK" and self._managed_paths(name):
                raise RuntimeError(
                    "Retira primero los bloqueos de firewall de este nombre EXE"
                )
            self.store.upsert(AppPolicy(name, mode))
            self.refresh()
            if mode == "BLOCK":
                state = "BLOQUEAR guardado; pulsa Aplicar BLOQUEO para rutas actuales."
            elif mode == "TRANSPARENT":
                state = "PROXY guardado como preferencia; NO intercepta tráfico hasta desarrollar el callout WFP firmado."
            elif mode == "DIRECT":
                state = "DIRECTO guardado por nombre; usa la red normal del sistema."
            else:
                state = "Solo apps compatibles con variables de entorno pueden usar proxy manual."
            self.info.configure(text=state)
        except (OSError, ValueError, RuntimeError) as error:
            messagebox.showerror("Guardar política", str(error), parent=self.win)

    def _known_paths_for(self, app_name: str) -> list[str]:
        name = normalize_app_name(app_name)
        paths = set(self._managed_paths(name))
        paths.update(self._browsed_paths.get(name, ()))
        for app in list_running_apps():
            if app.name == name:
                paths.update(app.paths)
        # WFP's ALE_APP_ID also uses internal absolute paths, never UI paths.
        return sorted((p for p in paths if Path(p).is_file()), key=str.casefold)

    def block(self):
        try:
            name = self._selected()
            if name in DENIED_TARGETS:
                raise ValueError("Este proceso esencial o portador VPN está protegido")
            paths = self._known_paths_for(name)
            if not paths:
                raise RuntimeError(
                    f"No hay rutas ejecutables detectadas para {name}. "
                    "Abre esa aplicación o utiliza Buscar aplicación .exe."
                )
            prompt = (
                f"Bloquear conexiones salientes de {name} en {len(paths)} "
                "ruta(s) detectada(s).\n\n"
                "WFP necesita identificadores internos de cada ruta: cualquier copia "
                "NUEVA en otra carpeta no quedará bloqueada automáticamente.\n\n"
                "¿Activar filtros WFP temporales con permisos de administrador?"
            )
            if not messagebox.askyesno("Confirmar bloqueo por aplicación",
                                       prompt, parent=self.win):
                return
            existing = set(self.firewall.managed())
            created: list[str] = []
            try:
                for exe in paths:
                    rule_id = self.guard.block(exe)
                    if rule_id not in existing:
                        created.append(exe)
                self.store.upsert(AppPolicy(name, "BLOCK"))
            except Exception:
                # Attempt to roll back only newly created own rules.
                for exe in reversed(created):
                    try:
                        self.guard.unblock(exe)
                    except Exception:
                        pass
                raise
            self.refresh()
            self.info.configure(
                text=f"BLOQUEAR aplicado a {len(paths)} ruta(s) de {name}; "
                     "las copias futuras requieren actualizar el bloqueo. "
                     "Los filtros se retiran al cerrar OneTunnel."
            )
        except (OSError, ValueError, RuntimeError, PermissionError) as error:
            messagebox.showerror("Firewall", str(error), parent=self.win)

    def unblock(self):
        try:
            name = self._selected()
            paths = self._managed_paths(name)
            if not paths:
                self.info.configure(text=f"{name}: no hay bloqueos propios aplicados.")
                return
            if not messagebox.askyesno(
                "Retirar bloqueos",
                f"¿Retirar {len(paths)} filtro(s) WFP propios temporales "
                f"para {name}?\nEsto no afecta reglas de otros productos.",
                parent=self.win,
            ):
                return
            for exe in paths:
                self.guard.unblock(exe)
            # Do not leave a policy displayed as BLOCK when its rules were removed.
            self.store.upsert(AppPolicy(name, "DIRECT"))
            self.refresh()
            self.info.configure(text=f"Bloqueos retirados; {name} queda DIRECTO.")
        except (OSError, ValueError, RuntimeError, PermissionError) as error:
            messagebox.showerror("Firewall", str(error), parent=self.win)

    def delete_rule(self):
        try:
            name = self._selected()
            if self._managed_paths(name):
                raise RuntimeError(
                    "Retira primero los filtros WFP activos de este nombre EXE"
                )
            self.store.delete(name)
            self.refresh()
            self.info.configure(text=f"Política de {name} eliminada.")
        except (OSError, ValueError, RuntimeError) as error:
            messagebox.showerror("Eliminar política", str(error), parent=self.win)

    def check_native_wfp(self):
        active = self.guard.managed()
        messagebox.showinfo(
            "Estado OneTunnel WFP",
            f"Bloqueo nativo WFP: {len(active)} ruta(s) activas.\n"
            "Redirección transparente PROXY: NO DISPONIBLE todavía.\n"
            "Se necesita desarrollar, certificar y firmar un callout driver WFP.\n\n"
            "Sin ProxiFyre y sin Windows Firewall para nuevos bloqueos.\n"
            "Este bloqueo usa filtros efímeros; se retiran al cerrar OneTunnel.\n"
            "No constituye un kill switch y no intercepta aplicaciones automáticamente.",
            parent=self.win,
        )

    def cleanup_legacy_firewall(self):
        """Removal-only compatibility path for rules made by old builds."""
        try:
            legacy = self.legacy_firewall.managed()
            if not legacy:
                self.info.configure(text="No hay reglas antiguas de Windows Firewall administradas.")
                return
            if not messagebox.askyesno(
                "Eliminar solo reglas heredadas",
                f"Hay {len(legacy)} regla(s) antiguas de OneTunnel creadas mediante "
                "Windows Firewall. ¿Retirarlas con permisos de administrador?\n"
                "Esto no crea reglas nuevas ni modifica las de otros programas.",
                parent=self.win,
            ):
                return
            removed = 0
            for exe in list(legacy.values()):
                if self.legacy_firewall.unblock(exe):
                    removed += 1
            self.info.configure(text=f"Retiradas {removed} reglas heredadas de Windows Firewall.")
        except (OSError, ValueError, RuntimeError, PermissionError) as error:
            messagebox.showerror("Retirada de reglas antiguas", str(error), parent=self.win)

    def launch_with_proxy(self):
        try:
            name = self._selected()
            matches = [app for app in list_running_apps() if app.name == name]
            paths = sorted(
                set(matches[0].paths) if matches else set()
            ) if matches else sorted(self._browsed_paths.get(name, ()))
            if not paths:
                raise RuntimeError(
                    f"No encuentro una instalación ejecutable de {name}. "
                    "Abre la aplicación o selecciónala con Buscar aplicación .exe."
                )
            if len(paths) != 1:
                raise RuntimeError(
                    f"Hay {len(paths)} instalaciones activas de {name}. "
                    "No se iniciará ninguna automáticamente: usa la aplicación "
                    "existente para evitar escoger una ruta equivocada."
                )
            endpoints = self.endpoint_getter()
            if endpoints is None:
                raise RuntimeError("Inicia primero el motor integrado HTTP/SOCKS5")
            if not messagebox.askyesno(
                "Iniciar aplicación",
                f"Solo afecta aplicaciones que respetan variables de proxy. "
                f"¿Iniciar otra instancia de {name}?",
                parent=self.win,
            ):
                return
            exe = paths[0]
            env = os.environ.copy()
            env.update({
                "HTTP_PROXY": f"http://127.0.0.1:{endpoints.http_port}",
                "HTTPS_PROXY": f"http://127.0.0.1:{endpoints.http_port}",
                "ALL_PROXY": f"socks5h://127.0.0.1:{endpoints.socks5_port}",
                "NO_PROXY": "localhost,127.0.0.1,::1",
            })
            subprocess.Popen([exe], env=env, cwd=str(Path(exe).parent))
            self.info.configure(text=f"Iniciada {name} con variables proxy; pueden ignorarse.")
        except (OSError, ValueError, RuntimeError) as error:
            messagebox.showerror("Iniciar aplicación", str(error), parent=self.win)
