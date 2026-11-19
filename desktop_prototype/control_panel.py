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
from native_redirect import check_redirect_capability
from native_proxy import NativeProxySession
from driver_lifecycle import (
    DriverLifecycleError, SignedDriverLifecycle, bundled_driver_package_candidate,
)
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
    "TRANSPARENT": "PROXY (WFP nativo firmado)",
}


class TrafficControlPanel:
    def __init__(
        self, parent: tk.Tk, endpoint_getter, verified_getter=None,
        native_guard=None, native_proxy=None, driver_lifecycle=None,
    ):
        self.parent = parent
        self.endpoint_getter = endpoint_getter
        self.verified_getter = verified_getter or (lambda: False)
        self.store = PolicyStore()
        self.guard = native_guard or NativeWfpGuard()
        self.native_proxy = native_proxy or NativeProxySession()
        self.driver_lifecycle = driver_lifecycle or SignedDriverLifecycle()
        self._driver_package_dir: Path | None = bundled_driver_package_candidate()
        self._driver_started_for_proxy = False
        # Read legacy managed Windows Firewall rules only to remove them on request.
        self.legacy_firewall = FirewallManager()
        self._browsed_paths: dict[str, set[str]] = {}
        self.win = tk.Toplevel(parent)
        self.win.title("OneTunnel — Motor WFP nativo por aplicación")
        self.win.geometry("1120x780")
        self.win.minsize(1000, 700)
        self.win.configure(bg=BG)
        self._layout()
        if self._driver_package_dir is not None:
            self.info.configure(
                text="Paquete WFP integrado detectado. Verifica su firma antes de instalar."
            )
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
        self._label(body, "DIRECTO: disponible · BLOQUEAR: WFP integrado · PROXY: driver firmado + relay + BFE",
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
        external.pack(fill="x", pady=(0, 6))
        self._button(external, "ESTADO MOTOR", self.check_native_wfp).pack(side="left")
        self._button(external, "ACTIVAR PROXY WFP", self.activate_native_proxy).pack(side="left", padx=7)
        self._button(external, "DETENER PROXY WFP", self.stop_native_proxy).pack(side="left", padx=7)
        self._button(external, "RETIRAR REGLAS HEREDADAS", self.cleanup_legacy_firewall).pack(side="left", padx=7)

        driverbar = tk.Frame(body, bg=BG)
        driverbar.pack(fill="x", pady=(0, 10))
        self._button(driverbar, "ELEGIR PAQUETE FIRMADO", self.choose_driver_package).pack(side="left")
        self._button(driverbar, "VERIFICAR FIRMA", self.verify_driver_package).pack(side="left", padx=7)
        self._button(driverbar, "INSTALAR MOTOR", self.install_signed_driver).pack(side="left", padx=7)
        self._button(driverbar, "INICIAR DRIVER", self.start_signed_driver).pack(side="left", padx=7)
        self._button(driverbar, "DETENER DRIVER", self.stop_signed_driver).pack(side="left", padx=7)
        self._button(driverbar, "DESINSTALAR", self.uninstall_signed_driver).pack(side="left", padx=7)
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
        self.info = self._label(body, "BLOQUEAR usa WFP efímero. PROXY solo se activa con driver firmado/cargado y salida Premium verificada.", "#a9bdd9")
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
                     "abarca cualquier carpeta; WFP resuelve internamente las rutas detectadas."
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
                    "Retira primero los bloqueos WFP activos de este nombre EXE"
                )
            self.store.upsert(AppPolicy(name, mode))
            self.refresh()
            if mode == "BLOCK":
                state = "BLOQUEAR guardado; pulsa APLICAR BLOQUEO WFP para las rutas actuales."
            elif mode == "TRANSPARENT":
                state = "PROXY guardado como preferencia; NO intercepta tráfico hasta desarrollar el callout WFP firmado."
            elif mode == "DIRECT":
                state = "DIRECTO guardado por nombre; usa la red normal del sistema."
            else:
                state = "PROXY MANUAL solo funciona en aplicaciones que respetan variables de entorno."
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
            if name in FORBIDDEN_APP_NAMES:
                raise ValueError("Este proceso crítico o portador VPN está protegido")
            paths = self._known_paths_for(name)
            if not paths:
                raise RuntimeError(
                    f"No hay rutas ejecutables detectadas para {name}. "
                    "Abre la aplicación o usa Buscar aplicación .exe."
                )
            if not messagebox.askyesno(
                "Activar bloqueo WFP integrado",
                f"Bloquear salidas de {name} en {len(paths)} ruta(s) actualmente "
                "detectadas.\n\n"
                "OneTunnel instalará filtros WFP efímeros, SIN usar reglas "
                "de Windows Firewall ni ProxiFyre.\n"
                "Requiere administrador. Los filtros desaparecen al cerrar "
                "OneTunnel: NO es un kill switch.\n\n"
                "¿Activar bloqueo nativo?",
                parent=self.win,
            ):
                return
            previous = list(self.guard.managed().values())
            self.guard.apply_paths([*previous, *paths])
            try:
                self.store.upsert(AppPolicy(name, "BLOCK"))
            except Exception:
                # Restore previous session atomically on persistence failure.
                self.guard.apply_paths(previous)
                raise
            self.refresh()
            self.info.configure(
                text=f"BLOQUEAR WFP activo para {name}: {len(paths)} ruta(s). "
                     "Copias futuras en carpetas diferentes no están cubiertas."
            )
        except (OSError, ValueError, RuntimeError, PermissionError) as error:
            messagebox.showerror("Bloqueo WFP", str(error), parent=self.win)

    def unblock(self):
        try:
            name = self._selected()
            paths = self._managed_paths(name)
            if not paths:
                self.info.configure(text=f"{name}: sin filtros WFP activos.")
                return
            if not messagebox.askyesno(
                "Retirar filtros WFP",
                f"¿Retirar los {len(paths)} filtros de {name}?\n"
                "Se conservarán los filtros propios de otras aplicaciones.",
                parent=self.win,
            ):
                return
            all_paths = list(self.guard.managed().values())
            remove = {executable_key(p) for p in paths}
            self.guard.apply_paths(
                path for path in all_paths if executable_key(path) not in remove
            )
            self.store.upsert(AppPolicy(name, "DIRECT"))
            self.refresh()
            self.info.configure(text=f"Filtros WFP retirados; {name} queda DIRECTO.")
        except (OSError, ValueError, RuntimeError, PermissionError) as error:
            messagebox.showerror("Bloqueo WFP", str(error), parent=self.win)

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

    def _require_driver_package(self) -> Path:
        if self._driver_package_dir is None:
            raise DriverLifecycleError(
                "Selecciona primero un paquete firmado OneTunnelRedirect.inf/.cat/.sys"
            )
        return self._driver_package_dir

    def choose_driver_package(self):
        inf = filedialog.askopenfilename(
            parent=self.win,
            title="Seleccionar OneTunnelRedirect.inf del paquete FIRMADO",
            filetypes=[("OneTunnel driver INF", "OneTunnelRedirect.inf"), ("INF", "*.inf")],
        )
        if not inf:
            return
        path = Path(inf)
        if path.name.casefold() != "onetunnelredirect.inf":
            messagebox.showerror(
                "Paquete WFP",
                "Selecciona exactamente OneTunnelRedirect.inf.",
                parent=self.win,
            )
            return
        self._driver_package_dir = path.parent
        self.info.configure(
            text=f"Paquete seleccionado: {path.parent}. Aún NO verificado ni instalado."
        )

    def verify_driver_package(self):
        try:
            package = self._require_driver_package()
            result = self.driver_lifecycle.verify(package)
            self.info.configure(
                text=f"Paquete firmado verificado por Windows · firmante: {result.signer}"
            )
            messagebox.showinfo(
                "Firma del driver verificada",
                f"Windows confía en el catálogo del paquete.\n\n"
                f"Firmante: {result.signer}\n"
                f"INF: {result.inf_path.name}\n"
                "No se ha instalado ni iniciado nada.",
                parent=self.win,
            )
        except (OSError, ValueError, DriverLifecycleError) as error:
            messagebox.showerror("Firma del driver", str(error), parent=self.win)

    def install_signed_driver(self):
        try:
            package = self._require_driver_package()
            verification = self.driver_lifecycle.verify(package)
            if not messagebox.askyesno(
                "Instalar motor WFP firmado",
                f"Firmante verificado por Windows:\n{verification.signer}\n\n"
                "Se instalará el paquete OneTunnel en Driver Store y se "
                "arrancará el callout en modo demand-start. Requiere administrador.\n\n"
                "¿Continuar?",
                parent=self.win,
            ):
                return
            result = self.driver_lifecycle.install(package)
            if result.reboot_required:
                text = (
                    "Paquete instalado. Windows requiere reinicio antes de usar PROXY."
                )
            else:
                text = "Paquete instalado y callout WFP RUNNING."
            self.info.configure(text=text)
            messagebox.showinfo("Motor WFP", text, parent=self.win)
        except (OSError, ValueError, PermissionError, DriverLifecycleError) as error:
            messagebox.showerror("Instalar motor WFP", str(error), parent=self.win)

    def start_signed_driver(self):
        try:
            if self.native_proxy.active():
                self.info.configure(text="PROXY WFP ya está activo.")
                return
            if not messagebox.askyesno(
                "Iniciar callout WFP",
                "¿Iniciar el driver OneTunnel ya instalado?\n"
                "No crea todavía filtros PROXY; solo carga el callout kernel.",
                parent=self.win,
            ):
                return
            self.driver_lifecycle.start()
            self.info.configure(text="Callout WFP firmado: RUNNING.")
        except (OSError, PermissionError, DriverLifecycleError) as error:
            messagebox.showerror("Iniciar driver", str(error), parent=self.win)

    def stop_signed_driver(self):
        try:
            if self.native_proxy.active():
                raise DriverLifecycleError(
                    "Detén primero PROXY WFP para retirar los filtros BFE antes del driver."
                )
            if not messagebox.askyesno(
                "Detener callout WFP",
                "¿Detener el driver OneTunnel? BLOQUEAR WFP de la otra sesión "
                "no depende de este callout, pero PROXY quedará no disponible.",
                parent=self.win,
            ):
                return
            self.driver_lifecycle.stop()
            self._driver_started_for_proxy = False
            self.info.configure(text="Callout WFP detenido.")
        except (OSError, PermissionError, DriverLifecycleError) as error:
            messagebox.showerror("Detener driver", str(error), parent=self.win)

    def uninstall_signed_driver(self):
        try:
            if self.native_proxy.active():
                raise DriverLifecycleError(
                    "Detén primero PROXY WFP antes de desinstalar el paquete."
                )
            package = self._require_driver_package()
            verification = self.driver_lifecycle.verify(package)
            if not messagebox.askyesno(
                "Desinstalar motor WFP",
                f"¿Detener y retirar del Driver Store el paquete firmado por\n"
                f"{verification.signer}?\n\n"
                "No se tocarán controladores de otros productos.",
                parent=self.win,
            ):
                return
            result = self.driver_lifecycle.uninstall(package)
            self._driver_started_for_proxy = False
            text = "Motor WFP desinstalado."
            if result.reboot_required:
                text += " Windows solicita reinicio para completar la retirada."
            self.info.configure(text=text)
            messagebox.showinfo("Motor WFP", text, parent=self.win)
        except (OSError, ValueError, PermissionError, DriverLifecycleError) as error:
            messagebox.showerror("Desinstalar motor WFP", str(error), parent=self.win)

    def _proxy_paths(self) -> list[str]:
        proxy_names = {
            rule.executable
            for rule in self.store.load()
            if rule.mode == "TRANSPARENT"
        }
        if not proxy_names:
            raise RuntimeError(
                "No hay aplicaciones con política PROXY. Selecciona nombre .exe, "
                "elige PROXY y guarda la política."
            )
        running = {app.name: app for app in list_running_apps()}
        result: dict[str, str] = {}
        missing = []
        for name in sorted(proxy_names):
            paths = set(self._browsed_paths.get(name, ()))
            app = running.get(name)
            if app:
                paths.update(app.paths)
            valid = [p for p in paths if Path(p).is_file()]
            if not valid:
                missing.append(name)
                continue
            for path in valid:
                result[executable_key(path)] = path
        if missing:
            raise RuntimeError(
                "Abre o selecciona el archivo .exe de estas aplicaciones PROXY: "
                + ", ".join(missing)
            )
        blocked = {executable_key(p) for p in self.guard.managed().values()}
        conflict = [p for key, p in result.items() if key in blocked]
        if conflict:
            raise RuntimeError(
                "Hay aplicaciones PROXY que siguen bloqueadas por WFP. "
                "Retira primero BLOQUEAR."
            )
        return list(result.values())

    def activate_native_proxy(self):
        try:
            if self.native_proxy.active():
                self.info.configure(text="PROXY WFP ya está activo.")
                return
            endpoints = self.endpoint_getter()
            if endpoints is None:
                raise RuntimeError("Inicia primero OneTunnel Premium HTTP/SOCKS5.")
            if not self.verified_getter():
                raise RuntimeError(
                    "Pulsa COMPROBAR SALIDA y verifica primero la IP por el proxy Premium."
                )
            paths = self._proxy_paths()

            was_running = self.driver_lifecycle.service_running()
            if not was_running:
                if not messagebox.askyesno(
                    "Activar PROXY WFP",
                    f"Se capturarán {len(paths)} ruta(s) de aplicaciones PROXY.\n"
                    "El callout firmado está detenido y se iniciará ahora.\n\n"
                    "Si la redirección WFP falla, OneTunnel no hará fallback "
                    "silencioso a DIRECTO.\n\n¿Continuar?",
                    parent=self.win,
                ):
                    return
                self.driver_lifecycle.start()
                self._driver_started_for_proxy = True

            try:
                result = self.native_proxy.start(paths, endpoints.socks5_port)
            except Exception:
                if self._driver_started_for_proxy:
                    try:
                        self.driver_lifecycle.stop()
                    except Exception:
                        pass
                    self._driver_started_for_proxy = False
                raise

            self.info.configure(
                text=f"PROXY WFP ACTIVO · {len(result['application_paths'])} ruta(s) · "
                     f"relay 127.0.0.1:{result['relay_port']}. "
                     "Falta validar la IP desde cada app sin configuración proxy manual."
            )
        except (
            OSError, ValueError, PermissionError, RuntimeError, DriverLifecycleError
        ) as error:
            messagebox.showerror("Activar PROXY WFP", str(error), parent=self.win)

    def stop_native_proxy(self):
        try:
            was_active = self.native_proxy.active()
            self.native_proxy.stop()
            if self._driver_started_for_proxy:
                self.driver_lifecycle.stop()
                self._driver_started_for_proxy = False
            self.info.configure(
                text="PROXY WFP detenido; filtros BFE retirados."
                if was_active else "No había una sesión PROXY WFP activa."
            )
        except (OSError, PermissionError, RuntimeError, DriverLifecycleError) as error:
            messagebox.showerror("Detener PROXY WFP", str(error), parent=self.win)

    def check_native_wfp(self):
        active = self.guard.managed()
        capability = check_redirect_capability()
        relay = (
            "incluido y self-test PASS"
            if capability.relay_self_test
            else "incluido, pero self-test FALLÓ"
            if capability.relay_present
            else "no incluido en esta compilación"
        )
        control = (
            "incluido y self-test PASS"
            if capability.control_self_test
            else "incluido, pero self-test FALLÓ"
            if capability.control_present
            else "no incluido en esta compilación"
        )
        driver_running = self.driver_lifecycle.service_running()
        proxy_active = self.native_proxy.active()
        proxy = "ACTIVO" if proxy_active else "DETENIDO"
        driver = "RUNNING" if driver_running else "NO RUNNING / no instalado"
        messagebox.showinfo(
            "Estado OneTunnel WFP",
            f"Bloqueo nativo WFP: {len(active)} ruta(s) activas.\n"
            f"Relay transparente: {relay}.\n"
            f"Control plane BFE: {control}.\n"
            f"Callout driver firmado/cargado: {driver}.\n"
            f"PROXY transparente: {proxy}.\n\n"
            "La activación real exige que el control plane confirme que los "
            "callouts kernel están registrados antes de añadir filtros.\n"
            "Sin ProxiFyre y sin Windows Firewall para nuevas reglas.\n"
            "Los filtros PROXY/BLOQUEAR se retiran antes de cerrar OneTunnel.",
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
