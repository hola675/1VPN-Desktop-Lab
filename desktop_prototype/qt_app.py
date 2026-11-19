"""OneTunnel v0.7 Qt Preview.

PySide6/Qt frontend over the existing Premium, proxy, selector and WFP backends.
The stable Tkinter v0.6.1 app remains untouched while this frontend matures.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
import threading
import webbrowser

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QCloseEvent, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from access_proxy import AccessProxy, open_via_access_proxy
from account_auth import AccountAuthError, AccountClient, AccountSession
from connection_check import probe_exit_ip
from driver_lifecycle import SignedDriverLifecycle
from native_proxy import NativeProxySession
from native_wfp import NativeWfpGuard
from network_engine import NetworkEngine
from premium_bridge import PremiumBrowserBridge
from proxycore import Upstream
from qt_theme import (
    ACCENT,
    APP_QSS,
    DANGER,
    MUTED,
    SUCCESS,
    TEXT,
    WARN,
)
from running_apps import list_running_apps
from server_catalog import COUNTRIES, ServerEndpoint
from server_selector import AutoSelector
from traffic_policy import AppPolicy, PolicyStore


LOCAL_HOST = "127.0.0.1"
DEFAULT_HTTP_PORT = 8899
DEFAULT_SOCKS_PORT = 1080


class UiSignals(QObject):
    log = Signal(str)
    connected = Signal(object)
    connect_failed = Signal(str)
    exit_result = Signal(object)
    scan_result = Signal(object)
    premium_session = Signal(object)
    account_result = Signal(object)
    account_failed = Signal(str)


def _button(text: str, role: str = "Secondary", checkable: bool = False) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName(role)
    button.setCheckable(checkable)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


def _label(text: str, role: str | None = None) -> QLabel:
    label = QLabel(text)
    if role:
        label.setObjectName(role)
    label.setWordWrap(True)
    return label


def _card(strong: bool = False) -> QFrame:
    frame = QFrame()
    frame.setObjectName("CardStrong" if strong else "Card")
    return frame


class OneTunnelQt(QMainWindow):
    NAV = ("Inicio", "Aplicaciones", "Cuenta", "Ajustes", "Actividad")

    def __init__(self):
        super().__init__()
        self.setWindowTitle("OneTunnel — Qt Preview v0.7")
        self.resize(1240, 800)
        self.setMinimumSize(1060, 700)

        self.signals = UiSignals()
        self.engine = NetworkEngine(self.signals.log.emit)
        self.native_guard = NativeWfpGuard()
        self.native_proxy = NativeProxySession()
        self.driver_lifecycle = SignedDriverLifecycle()
        self.policy_store = PolicyStore()
        self.account_client = AccountClient(on_event=self._safe_account_event)
        self.browser_bridge: PremiumBrowserBridge | None = None

        self.account_session: AccountSession | None = None
        self.selector: AutoSelector | None = None
        self.active_access_proxy: AccessProxy | None = None
        self.verified_exit_ip: str | None = None
        self._scanning = False
        self._busy = False
        self._running_apps = []
        self._selected_app = ""

        self._build_ui()
        self._wire_signals()
        self._refresh_apps()
        self._update_connection_ui(False)

        self.server_timer = QTimer(self)
        self.server_timer.timeout.connect(self._refresh_server_state)
        self.server_timer.start(5000)

        self.apps_timer = QTimer(self)
        self.apps_timer.timeout.connect(self._refresh_apps)
        self.apps_timer.start(7000)

    # ---------- structure ----------
    def _build_ui(self):
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(210)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(18, 22, 18, 18)
        side.setSpacing(8)

        brand = QLabel("OneTunnel")
        brand.setObjectName("Brand")
        side.addWidget(brand)
        version = QLabel("v0.7 · QT PREVIEW")
        version.setObjectName("VersionBadge")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version.setFixedWidth(112)
        side.addWidget(version)
        side.addSpacing(18)

        self.nav_buttons: list[QPushButton] = []
        self.stack = QStackedWidget()
        for index, name in enumerate(self.NAV):
            button = _button(name, "NavButton", checkable=True)
            button.clicked.connect(lambda _checked=False, i=index: self._show_page(i))
            self.nav_buttons.append(button)
            side.addWidget(button)
        side.addStretch(1)

        engine_badge = _label("● Motor WFP nativo", "Success")
        side.addWidget(engine_badge)
        side.addWidget(_label("Qt frontend sobre el backend existente.", "Muted"))

        outer.addWidget(sidebar)
        outer.addWidget(self.stack, 1)

        self.home_page = self._build_home()
        self.apps_page = self._build_apps()
        self.account_page = self._build_account()
        self.settings_page = self._build_settings()
        self.activity_page = self._build_activity()
        for page in (
            self.home_page,
            self.apps_page,
            self.account_page,
            self.settings_page,
            self.activity_page,
        ):
            self.stack.addWidget(page)
        self._show_page(0)

    def _page_shell(self, title: str, subtitle: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 23px; font-weight: 750;")
        layout.addWidget(title_label)
        layout.addWidget(_label(subtitle, "Muted"))
        return page, layout

    def _build_home(self) -> QWidget:
        page, layout = self._page_shell(
            "Inicio",
            "Conexión, servidor, salida y estado del motor en una sola vista.",
        )

        hero = _card(strong=True)
        h = QVBoxLayout(hero)
        h.setContentsMargins(22, 20, 22, 20)
        top = QHBoxLayout()
        status_box = QVBoxLayout()
        status_box.addWidget(_label("CONEXIÓN", "Eyebrow"))
        self.status_label = _label("Desconectado", "HeroStatus")
        status_box.addWidget(self.status_label)
        self.status_detail = _label("Listo para conectar", "Muted")
        status_box.addWidget(self.status_detail)
        top.addLayout(status_box, 1)
        self.connect_button = _button("CONECTAR", "Primary")
        self.connect_button.setMinimumWidth(150)
        self.connect_button.clicked.connect(self.toggle_connection)
        top.addWidget(self.connect_button)
        h.addLayout(top)

        controls = QGridLayout()
        controls.setHorizontalSpacing(16)
        controls.addWidget(_label("UBICACIÓN", "Eyebrow"), 0, 0)
        controls.addWidget(_label("CUENTA", "Eyebrow"), 0, 1)
        self.location_combo = QComboBox()
        for label, code in (
            ("Automático · Singapur preferido", "auto"),
            ("Singapur", "sgp"),
            ("Ámsterdam", "ams"),
            ("Los Ángeles", "lax"),
            ("Servidor manual", "manual"),
        ):
            self.location_combo.addItem(label, code)
        controls.addWidget(self.location_combo, 1, 0)
        account_row = QHBoxLayout()
        self.account_home = _label("Sin cuenta vinculada", "Muted")
        account_row.addWidget(self.account_home, 1)
        account_btn = _button("CUENTA", "Secondary")
        account_btn.clicked.connect(lambda: self._show_page(2))
        account_row.addWidget(account_btn)
        controls.addLayout(account_row, 1, 1)
        h.addLayout(controls)
        layout.addWidget(hero)

        cards = QHBoxLayout()
        self.exit_value = _label("IP sin verificar", "CardValue")
        self.server_value = _label("Automático · sin medir", "CardValue")
        self.route_value = _label("Red directa", "CardValue")
        for title, value in (
            ("SALIDA", self.exit_value),
            ("SERVIDOR", self.server_value),
            ("ACCESO A RED", self.route_value),
        ):
            card = _card()
            box = QVBoxLayout(card)
            box.setContentsMargins(16, 14, 16, 14)
            box.addWidget(_label(title, "Eyebrow"))
            box.addWidget(value)
            cards.addWidget(card, 1)
        layout.addLayout(cards)

        actions = QHBoxLayout()
        self.verify_button = _button("VERIFICAR SALIDA", "Secondary")
        self.verify_button.clicked.connect(self.verify_exit)
        self.scan_button = _button("ELEGIR MEJOR SERVIDOR", "Secondary")
        self.scan_button.clicked.connect(self.scan_servers)
        apps_button = _button("APLICACIONES", "Secondary")
        apps_button.clicked.connect(lambda: self._show_page(1))
        settings_button = _button("AJUSTES", "Ghost")
        settings_button.clicked.connect(lambda: self._show_page(3))
        actions.addWidget(apps_button)
        actions.addWidget(self.verify_button)
        actions.addWidget(self.scan_button)
        actions.addStretch(1)
        actions.addWidget(settings_button)
        layout.addLayout(actions)
        layout.addStretch(1)
        return page

    def _build_apps(self) -> QWidget:
        page, layout = self._page_shell(
            "Aplicaciones",
            "Reglas por nombre de proceso: DIRECTO, PROXY VPN o BLOQUEAR.",
        )

        editor = _card()
        grid = QGridLayout(editor)
        grid.setContentsMargins(18, 16, 18, 16)
        grid.addWidget(_label("APLICACIÓN", "Eyebrow"), 0, 0)
        grid.addWidget(_label("POLÍTICA", "Eyebrow"), 0, 1)
        self.app_name = QLineEdit()
        self.app_name.setPlaceholderText("chrome.exe")
        self.policy_combo = QComboBox()
        self.policy_combo.addItem("DIRECTO", "DIRECT")
        self.policy_combo.addItem("PROXY VPN", "TRANSPARENT")
        self.policy_combo.addItem("BLOQUEAR", "BLOCK")
        grid.addWidget(self.app_name, 1, 0)
        grid.addWidget(self.policy_combo, 1, 1)
        save = _button("GUARDAR REGLA", "Primary")
        save.clicked.connect(self.save_policy)
        refresh = _button("ACTUALIZAR", "Secondary")
        refresh.clicked.connect(self._refresh_apps)
        grid.addWidget(save, 1, 2)
        grid.addWidget(refresh, 1, 3)
        layout.addWidget(editor)

        self.apps_table = QTableWidget(0, 4)
        self.apps_table.setHorizontalHeaderLabels(("Aplicación", "PID", "Política", "Instancias"))
        self.apps_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.apps_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.apps_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.apps_table.setAlternatingRowColors(True)
        self.apps_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.apps_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.apps_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.apps_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.apps_table.itemSelectionChanged.connect(self._select_app_row)
        layout.addWidget(self.apps_table, 1)

        actions = QHBoxLayout()
        self.block_button = _button("APLICAR BLOQUEO WFP", "DangerButton")
        self.block_button.clicked.connect(self.apply_block)
        self.unblock_button = _button("RETIRAR BLOQUEO", "Secondary")
        self.unblock_button.clicked.connect(self.remove_block)
        self.proxy_start_button = _button("ACTIVAR PROXY WFP", "Primary")
        self.proxy_start_button.clicked.connect(self.start_native_proxy)
        self.proxy_stop_button = _button("DETENER PROXY WFP", "Secondary")
        self.proxy_stop_button.clicked.connect(self.stop_native_proxy)
        actions.addWidget(self.block_button)
        actions.addWidget(self.unblock_button)
        actions.addStretch(1)
        actions.addWidget(self.proxy_start_button)
        actions.addWidget(self.proxy_stop_button)
        layout.addLayout(actions)

        self.apps_info = _label(
            "Las políticas se guardan por nombre .exe; WFP usa las rutas reales detectadas internamente.",
            "Muted",
        )
        layout.addWidget(self.apps_info)
        return page

    def _build_account(self) -> QWidget:
        page, layout = self._page_shell(
            "Cuenta",
            "Premium web es el flujo recomendado; el login clásico queda como alternativa.",
        )
        tabs = QTabWidget()

        web = QWidget()
        w = QVBoxLayout(web)
        w.setContentsMargins(0, 14, 0, 0)
        web_card = _card()
        wc = QVBoxLayout(web_card)
        wc.setContentsMargins(20, 18, 20, 18)
        wc.addWidget(_label("Vincular Premium desde navegador", "CardValue"))
        wc.addWidget(_label(
            "Usa una sesión abierta en 1vpn.org y el Browser Companion. "
            "OneTunnel no lee cookies ni almacenamiento privado del navegador.",
            "Muted",
        ))
        self.pair_button = _button("INICIAR VINCULACIÓN", "Primary")
        self.pair_button.clicked.connect(self.start_premium_pairing)
        wc.addWidget(self.pair_button, alignment=Qt.AlignmentFlag.AlignLeft)
        self.pairing_box = _card()
        pb = QGridLayout(self.pairing_box)
        self.pair_port = QLineEdit()
        self.pair_port.setReadOnly(True)
        self.pair_code = QLineEdit()
        self.pair_code.setReadOnly(True)
        copy_port = _button("COPIAR PUERTO", "Secondary")
        copy_code = _button("COPIAR CÓDIGO", "Secondary")
        copy_port.clicked.connect(lambda: QApplication.clipboard().setText(self.pair_port.text()))
        copy_code.clicked.connect(lambda: QApplication.clipboard().setText(self.pair_code.text()))
        open_account = _button("ABRIR 1VPN.ORG/ACCOUNT", "Secondary")
        open_account.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://1vpn.org/account/"))
        )
        pb.addWidget(_label("Puerto", "Eyebrow"), 0, 0)
        pb.addWidget(_label("Código temporal", "Eyebrow"), 0, 2)
        pb.addWidget(self.pair_port, 1, 0)
        pb.addWidget(copy_port, 1, 1)
        pb.addWidget(self.pair_code, 1, 2)
        pb.addWidget(copy_code, 1, 3)
        pb.addWidget(open_account, 2, 0, 1, 4)
        self.pairing_box.setVisible(False)
        wc.addWidget(self.pairing_box)
        w.addWidget(web_card)
        w.addStretch(1)

        classic = QWidget()
        c = QVBoxLayout(classic)
        c.setContentsMargins(0, 14, 0, 0)
        classic_card = _card()
        cc = QGridLayout(classic_card)
        cc.setContentsMargins(20, 18, 20, 18)
        self.email_input = QLineEdit()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.twofa_input = QLineEdit()
        self.twofa_input.setEchoMode(QLineEdit.EchoMode.Password)
        cc.addWidget(_label("Correo", "Eyebrow"), 0, 0)
        cc.addWidget(self.email_input, 1, 0, 1, 2)
        cc.addWidget(_label("Contraseña", "Eyebrow"), 2, 0)
        cc.addWidget(self.password_input, 3, 0)
        cc.addWidget(_label("2FA (opcional)", "Eyebrow"), 2, 1)
        cc.addWidget(self.twofa_input, 3, 1)
        login = _button("INICIAR SESIÓN", "Primary")
        login.clicked.connect(self.classic_login)
        logout = _button("CERRAR SESIÓN", "Secondary")
        logout.clicked.connect(self.logout_account)
        cc.addWidget(login, 4, 0)
        cc.addWidget(logout, 4, 1)
        c.addWidget(classic_card)
        c.addStretch(1)

        tabs.addTab(web, "Premium web")
        tabs.addTab(classic, "Email / 2FA")
        layout.addWidget(tabs, 1)

        self.account_state = _label("Sin cuenta vinculada", "Muted")
        layout.addWidget(self.account_state)
        return page

    def _build_settings(self) -> QWidget:
        page, layout = self._page_shell(
            "Ajustes",
            "La complejidad técnica vive aquí; la pantalla Inicio permanece simple.",
        )
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 0, 8, 0)
        v.setSpacing(12)

        access = _card()
        a = QGridLayout(access)
        a.setContentsMargins(18, 16, 18, 16)
        self.access_enabled = QCheckBox("Usar proxy de la red para conectar a 1VPN")
        self.access_enabled.toggled.connect(self._update_access_settings)
        self.access_host = QLineEdit()
        self.access_port = QSpinBox()
        self.access_port.setRange(1, 65535)
        self.access_port.setValue(3128)
        self.access_user = QLineEdit()
        self.access_password = QLineEdit()
        self.access_password.setEchoMode(QLineEdit.EchoMode.Password)
        a.addWidget(self.access_enabled, 0, 0, 1, 4)
        a.addWidget(_label(
            "HTTP CONNECT · fail-closed: si este proxy falla, OneTunnel no intenta salida directa.",
            "Muted",
        ), 1, 0, 1, 4)
        for col, (caption, widget) in enumerate((
            ("Host / IP", self.access_host),
            ("Puerto", self.access_port),
            ("Usuario", self.access_user),
            ("Clave", self.access_password),
        )):
            a.addWidget(_label(caption, "Eyebrow"), 2, col)
            a.addWidget(widget, 3, col)
        v.addWidget(access)

        tunnel = _card()
        t = QGridLayout(tunnel)
        t.setContentsMargins(18, 16, 18, 16)
        self.remote_host = QLineEdit()
        self.remote_host.setPlaceholderText("Solo modo manual")
        self.remote_port = QSpinBox()
        self.remote_port.setRange(1, 65535)
        self.remote_port.setValue(443)
        self.proxy_user = QLineEdit()
        self.proxy_password = QLineEdit()
        self.proxy_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.http_port = QSpinBox()
        self.http_port.setRange(1024, 65535)
        self.http_port.setValue(DEFAULT_HTTP_PORT)
        self.socks_port = QSpinBox()
        self.socks_port.setRange(1024, 65535)
        self.socks_port.setValue(DEFAULT_SOCKS_PORT)
        fields = (
            ("Servidor remoto", self.remote_host),
            ("Puerto TLS", self.remote_port),
            ("Usuario proxy 1VPN", self.proxy_user),
            ("Clave proxy 1VPN", self.proxy_password),
            ("Puerto HTTP local", self.http_port),
            ("Puerto SOCKS5 local", self.socks_port),
        )
        for i, (caption, widget) in enumerate(fields):
            row, col = divmod(i, 2)
            col *= 2
            t.addWidget(_label(caption, "Eyebrow"), row * 2, col)
            t.addWidget(widget, row * 2 + 1, col, 1, 2)
        v.addWidget(tunnel)

        driver = _card()
        d = QVBoxLayout(driver)
        d.setContentsMargins(18, 16, 18, 16)
        d.addWidget(_label("Motor nativo", "CardValue"))
        self.driver_state = _label("Callout firmado: estado no consultado", "Muted")
        d.addWidget(self.driver_state)
        check = _button("COMPROBAR ESTADO", "Secondary")
        check.clicked.connect(self.check_driver_state)
        d.addWidget(check, alignment=Qt.AlignmentFlag.AlignLeft)
        v.addWidget(driver)
        v.addStretch(1)

        scroll.setWidget(container)
        layout.addWidget(scroll, 1)
        self._update_access_settings()
        return page

    def _build_activity(self) -> QWidget:
        page, layout = self._page_shell(
            "Actividad",
            "Registro seguro: no debe contener contraseñas, tokens ni cuerpos completos.",
        )
        self.activity = QPlainTextEdit()
        self.activity.setReadOnly(True)
        self.activity.setMaximumBlockCount(700)
        layout.addWidget(self.activity, 1)
        clear = _button("LIMPIAR", "Secondary")
        clear.clicked.connect(self.activity.clear)
        layout.addWidget(clear, alignment=Qt.AlignmentFlag.AlignLeft)
        return page

    def _wire_signals(self):
        self.signals.log.connect(self._append_log)
        self.signals.connected.connect(self._on_connected)
        self.signals.connect_failed.connect(self._on_connect_failed)
        self.signals.exit_result.connect(self._on_exit_result)
        self.signals.scan_result.connect(self._on_scan_result)
        self.signals.premium_session.connect(self._on_premium_session)
        self.signals.account_result.connect(self._on_premium_session)
        self.signals.account_failed.connect(
            lambda msg: QMessageBox.warning(self, "Cuenta 1VPN", msg)
        )

    def _show_page(self, index: int):
        self.stack.setCurrentIndex(index)
        for i, button in enumerate(self.nav_buttons):
            button.setChecked(i == index)

    # ---------- connection ----------
    def _current_region(self) -> str:
        return str(self.location_combo.currentData() or "auto")

    def _access_proxy(self) -> AccessProxy | None:
        if not self.access_enabled.isChecked():
            return None
        return AccessProxy(
            self.access_host.text().strip(),
            self.access_port.value(),
            self.access_user.text(),
            self.access_password.text(),
        ).validated()

    def toggle_connection(self):
        if self.engine.active:
            self.disconnect()
            return
        if self._busy:
            return
        try:
            config = {
                "region": self._current_region(),
                "access_proxy": self._access_proxy(),
                "username": self.proxy_user.text(),
                "password": self.proxy_password.text(),
                "remote_host": self.remote_host.text().strip(),
                "remote_port": self.remote_port.value(),
                "http_port": self.http_port.value(),
                "socks_port": self.socks_port.value(),
                "account_session": self.account_session,
            }
        except ValueError as error:
            QMessageBox.warning(self, "Configuración", str(error))
            return

        self._busy = True
        self.connect_button.setEnabled(False)
        self.status_label.setText("Conectando…")
        self.status_detail.setText("Preparando ruta segura hacia 1VPN")
        threading.Thread(
            target=self._connect_worker,
            args=(config,),
            daemon=True,
            name="qt-connect",
        ).start()

    def _connect_worker(self, config: dict):
        try:
            region = config["region"]
            access_proxy = config["access_proxy"]
            username, password = config["username"], config["password"]
            remote_port = config["remote_port"]
            session = config["account_session"]
            browser_premium = (
                session is not None
                and session.source == "browser_web"
                and session.is_premium
                and region != "manual"
            )

            if region != "manual":
                if remote_port != 443:
                    raise ValueError("Los servidores HTTPS de 1VPN utilizan el puerto 443")
                if browser_premium:
                    endpoints = tuple(
                        ServerEndpoint(r, host, port)
                        for r, host, port in session.proxy_locations
                    )
                    if region != "auto" and not any(e.region == region for e in endpoints):
                        raise ValueError("La cuenta Premium no tiene servidores en esta ubicación")
                    selector = AutoSelector(
                        endpoints=endpoints,
                        username=session.username,
                        password=session.session_token,
                        region=region,
                        preferred="sgp",
                        access_proxy=access_proxy,
                    )
                else:
                    selector = AutoSelector(
                        username=username,
                        password=password,
                        region=region,
                        preferred="sgp",
                        access_proxy=access_proxy,
                    )
                candidates = selector.candidates()
                if not candidates:
                    raise ValueError("No hay servidores disponibles en esta ubicación")
                upstream = candidates[0]
            else:
                selector = None
                upstream = Upstream(
                    config["remote_host"],
                    remote_port,
                    username,
                    password,
                ).validated()

            if access_proxy is not None:
                probe = open_via_access_proxy(
                    access_proxy, upstream.host, upstream.port, timeout=6
                )
                probe.close()

            endpoints = self.engine.start(
                upstream,
                http_port=config["http_port"],
                socks_port=config["socks_port"],
                selector=selector,
                access_proxy=access_proxy,
            )
            self.signals.connected.emit({
                "selector": selector,
                "access_proxy": access_proxy,
                "browser_premium": browser_premium,
                "endpoints": endpoints,
            })
        except Exception as error:
            self.signals.connect_failed.emit(str(error))

    def _on_connected(self, data: dict):
        self.selector = data["selector"]
        self.active_access_proxy = data["access_proxy"]
        self.verified_exit_ip = None
        self._busy = False
        self.connect_button.setEnabled(True)
        self.location_combo.setEnabled(False)
        self._lock_settings(True)
        self._update_connection_ui(True)
        self.status_label.setText("Conectado")
        self.status_detail.setText("Salida aún sin verificar")
        if self.active_access_proxy:
            self.route_value.setText(
                f"Proxy {self.active_access_proxy.host}:{self.active_access_proxy.port}"
            )
        else:
            self.route_value.setText("Red directa")
        self._append_log("Motor local iniciado. Verifica la IP de salida antes de asumir protección.")

    def _on_connect_failed(self, message: str):
        self._busy = False
        self.connect_button.setEnabled(True)
        self.status_label.setText("Desconectado")
        self.status_detail.setText("No se pudo iniciar la conexión")
        QMessageBox.warning(self, "No se pudo conectar", message)

    def disconnect(self):
        self.native_proxy.stop()
        self.native_guard.stop()
        self.engine.stop()
        self.selector = None
        self.active_access_proxy = None
        self.verified_exit_ip = None
        self.location_combo.setEnabled(True)
        self._lock_settings(False)
        self._update_connection_ui(False)
        self.exit_value.setText("IP sin verificar")
        self.server_value.setText("Automático · sin medir")
        self.route_value.setText("Red directa")
        self._append_log("Conexión detenida.")

    def _update_connection_ui(self, active: bool):
        self.connect_button.setText("DESCONECTAR" if active else "CONECTAR")
        self.connect_button.setObjectName("DangerButton" if active else "Primary")
        self.connect_button.style().unpolish(self.connect_button)
        self.connect_button.style().polish(self.connect_button)
        self.verify_button.setEnabled(active)
        self.scan_button.setEnabled(active and self.selector is not None)
        if not active:
            self.status_label.setText("Desconectado")
            self.status_detail.setText("Listo para conectar")

    def _lock_settings(self, locked: bool):
        for widget in (
            self.access_enabled,
            self.access_host,
            self.access_port,
            self.access_user,
            self.access_password,
            self.remote_host,
            self.remote_port,
            self.proxy_user,
            self.proxy_password,
            self.http_port,
            self.socks_port,
        ):
            widget.setEnabled(not locked)
        if not locked:
            self._update_access_settings()

    def verify_exit(self):
        if not self.engine.active or not self.engine.endpoints:
            return
        self.verify_button.setEnabled(False)
        self.exit_value.setText("Verificando…")
        port = self.engine.endpoints.http_port

        def worker():
            try:
                ip = probe_exit_ip(port)
                self.signals.exit_result.emit({"ok": True, "ip": ip})
            except Exception as error:
                self.signals.exit_result.emit({"ok": False, "error": str(error)})

        threading.Thread(target=worker, daemon=True, name="qt-egress-check").start()

    def _on_exit_result(self, result: dict):
        self.verify_button.setEnabled(self.engine.active)
        if result["ok"]:
            self.verified_exit_ip = result["ip"]
            self.exit_value.setText(f"IP {result['ip']}")
            self.exit_value.setObjectName("Success")
            self.status_detail.setText("Salida Premium verificada")
            self._append_log("Salida HTTPS verificada por el proxy local.")
        else:
            self.verified_exit_ip = None
            self.exit_value.setText("Sin verificar")
            self.exit_value.setObjectName("Warning")
            self.status_detail.setText("La salida no pudo verificarse")
            QMessageBox.warning(self, "Verificar salida", result["error"])
        self.exit_value.style().unpolish(self.exit_value)
        self.exit_value.style().polish(self.exit_value)

    def scan_servers(self):
        if self._scanning or self.selector is None:
            return
        self._scanning = True
        self.scan_button.setEnabled(False)
        self.server_value.setText("Midiendo…")
        selector = self.selector

        def worker():
            try:
                results = selector.scan()
                summary = selector.summary()
                self.signals.scan_result.emit({
                    "ok": True,
                    "results": results,
                    "summary": summary,
                })
            except Exception as error:
                self.signals.scan_result.emit({"ok": False, "error": str(error)})

        threading.Thread(target=worker, daemon=True, name="qt-server-scan").start()

    def _on_scan_result(self, result: dict):
        self._scanning = False
        self.scan_button.setEnabled(self.engine.active and self.selector is not None)
        if not result["ok"]:
            self.server_value.setText("Medición fallida")
            QMessageBox.warning(self, "Servidores", result["error"])
            return
        summary = result["summary"]
        if summary["ok"] and summary["host"]:
            region = COUNTRIES.get(
                summary["region"], (str(summary["region"]).upper(), "")
            )[0]
            rtt = (
                f" · {summary['rtt_ms']} ms"
                if summary["rtt_ms"] is not None else ""
            )
            self.server_value.setText(f"{region}{rtt}")
            self._append_log(
                f"Servidor seleccionado: {region}; "
                f"{summary['ok']} válidos de {len(result['results'])}."
            )
        else:
            self.server_value.setText("Sin servidores verificados")

    def _refresh_server_state(self):
        if self.engine.active and self.selector is not None and not self._scanning:
            summary = self.selector.summary()
            if summary["host"]:
                region = COUNTRIES.get(
                    summary["region"], (str(summary["region"]).upper(), "")
                )[0]
                rtt = (
                    f" · {summary['rtt_ms']} ms"
                    if summary["rtt_ms"] is not None else ""
                )
                self.server_value.setText(f"{region}{rtt}")

    # ---------- applications ----------
    def _refresh_apps(self):
        try:
            apps = list_running_apps()
            policies = {p.executable: p.mode for p in self.policy_store.load()}
        except Exception as error:
            self.apps_info.setText(f"No se pudo actualizar: {type(error).__name__}")
            return
        self._running_apps = apps
        self.apps_table.setRowCount(len(apps))
        mode_labels = {
            "DIRECT": "DIRECTO",
            "TRANSPARENT": "PROXY VPN",
            "BLOCK": "BLOQUEAR",
            "MANUAL_PROXY": "PROXY MANUAL",
        }
        for row, app in enumerate(apps):
            pids = ", ".join(str(pid) for pid in app.pids[:6])
            if len(app.pids) > 6:
                pids += f" (+{len(app.pids)-6})"
            values = (
                app.name,
                pids,
                mode_labels.get(policies.get(app.name), "SIN REGLA"),
                str(len(app.paths)),
            )
            for col, value in enumerate(values):
                self.apps_table.setItem(row, col, QTableWidgetItem(value))

    def _select_app_row(self):
        rows = self.apps_table.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        if not 0 <= row < len(self._running_apps):
            return
        app = self._running_apps[row]
        self._selected_app = app.name
        self.app_name.setText(app.name)
        policy = next(
            (p for p in self.policy_store.load() if p.executable == app.name),
            None,
        )
        target = policy.mode if policy else "DIRECT"
        idx = self.policy_combo.findData(target)
        if idx >= 0:
            self.policy_combo.setCurrentIndex(idx)

    def save_policy(self):
        name = self.app_name.text().strip()
        mode = str(self.policy_combo.currentData())
        try:
            self.policy_store.upsert(AppPolicy(name, mode))
            self.apps_info.setText(f"{name}: política {self.policy_combo.currentText()} guardada.")
            self._refresh_apps()
        except Exception as error:
            QMessageBox.warning(self, "Política", str(error))

    def _paths_for_name(self, name: str) -> list[str]:
        return [
            path
            for app in self._running_apps if app.name == name
            for path in app.paths
        ]

    def apply_block(self):
        name = self.app_name.text().strip()
        paths = self._paths_for_name(name)
        if not paths:
            QMessageBox.warning(
                self, "Bloqueo WFP",
                "La aplicación debe estar en ejecución para resolver sus rutas reales.",
            )
            return
        if QMessageBox.question(
            self,
            "Aplicar bloqueo",
            f"¿Bloquear salidas de {name} mediante WFP nativo?\n"
            "Los filtros son temporales y requieren permisos de administrador.",
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            current = list(self.native_guard.managed().values())
            self.native_guard.apply_paths([*current, *paths])
            self.policy_store.upsert(AppPolicy(name, "BLOCK"))
            self.apps_info.setText(f"BLOQUEAR WFP activo para {name}.")
            self._refresh_apps()
        except Exception as error:
            QMessageBox.warning(self, "Bloqueo WFP", str(error))

    def remove_block(self):
        name = self.app_name.text().strip()
        remove = set(self._paths_for_name(name))
        if not remove:
            remove = {
                path for path in self.native_guard.managed().values()
                if Path(path).name.casefold() == name.casefold()
            }
        try:
            keep = [
                path for path in self.native_guard.managed().values()
                if path not in remove
            ]
            self.native_guard.apply_paths(keep)
            self.policy_store.upsert(AppPolicy(name, "DIRECT"))
            self.apps_info.setText(f"Filtros retirados; {name} queda DIRECTO.")
            self._refresh_apps()
        except Exception as error:
            QMessageBox.warning(self, "Bloqueo WFP", str(error))

    def start_native_proxy(self):
        if not self.engine.active or not self.engine.endpoints:
            QMessageBox.warning(
                self, "PROXY WFP",
                "Conecta primero OneTunnel; el relay necesita el SOCKS5 local activo.",
            )
            return
        if self.native_proxy.active():
            QMessageBox.information(self, "PROXY WFP", "La sesión PROXY ya está activa.")
            return
        try:
            policies = [
                p.executable
                for p in self.policy_store.load()
                if p.mode == "TRANSPARENT"
            ]
            paths = [
                path
                for app in self._running_apps
                if app.name in policies
                for path in app.paths
            ]
            result = self.native_proxy.start(
                paths, self.engine.endpoints.socks5_port
            )
            self.apps_info.setText(
                f"PROXY WFP activo · {len(result['application_paths'])} ruta(s)."
            )
        except Exception as error:
            QMessageBox.warning(self, "PROXY WFP", str(error))

    def stop_native_proxy(self):
        self.native_proxy.stop()
        self.apps_info.setText("Sesión PROXY WFP detenida.")

    # ---------- account ----------
    def start_premium_pairing(self):
        if self.browser_bridge is not None:
            self.browser_bridge.stop()
        self.browser_bridge = PremiumBrowserBridge()
        try:
            details = self.browser_bridge.start(
                lambda session: self.signals.premium_session.emit(session)
            )
        except Exception as error:
            QMessageBox.warning(self, "Premium web", str(error))
            self.browser_bridge = None
            return
        self.pair_port.setText(str(details.port))
        self.pair_code.setText(details.code)
        self.pairing_box.setVisible(True)
        self.account_state.setText(
            "Vinculación abierta durante 5 minutos. Usa el Browser Companion."
        )

    def _on_premium_session(self, session: AccountSession):
        self.account_session = session
        self.account_state.setText(f"{session.tier} · {session.email}")
        self.account_home.setText(f"{session.tier} · {session.email}")
        self.pairing_box.setVisible(False)
        self.password_input.clear()
        self.twofa_input.clear()
        self._update_premium_locations()
        self._append_log("Cuenta Premium vinculada. Falta verificar salida del proxy.")

    def _update_premium_locations(self):
        if not (
            self.account_session
            and self.account_session.source == "browser_web"
            and self.account_session.is_premium
        ):
            return
        current = self._current_region()
        codes = []
        for region, _host, _port in self.account_session.proxy_locations:
            if region not in codes:
                codes.append(region)
        self.location_combo.clear()
        self.location_combo.addItem("Automático · Premium", "auto")
        for code in codes:
            label = COUNTRIES.get(code, (code.upper(), ""))[0]
            self.location_combo.addItem(label, code)
        self.location_combo.addItem("Servidor manual", "manual")
        idx = self.location_combo.findData(current)
        self.location_combo.setCurrentIndex(idx if idx >= 0 else 0)

    def classic_login(self):
        email = self.email_input.text()
        password = self.password_input.text()
        twofa = self.twofa_input.text()
        self.account_state.setText("Autenticando…")

        def worker():
            try:
                session = self.account_client.login(email, password, twofa)
                self.signals.account_result.emit(session)
            except AccountAuthError as error:
                self.signals.account_failed.emit(str(error))
            except Exception:
                self.signals.account_failed.emit(
                    "No se pudo completar el inicio de sesión."
                )

        threading.Thread(target=worker, daemon=True, name="qt-account-login").start()

    def logout_account(self):
        self.account_session = None
        self.account_state.setText("Sin cuenta vinculada")
        self.account_home.setText("Sin cuenta vinculada")
        self.password_input.clear()
        self.twofa_input.clear()
        if self.browser_bridge is not None:
            self.browser_bridge.stop()
            self.browser_bridge = None
        self.pairing_box.setVisible(False)

    def _safe_account_event(self, event: dict):
        stage = event.get("stage")
        if stage == "response":
            status = event.get("http_status")
            self.signals.log.emit(f"Cuenta 1VPN: respuesta HTTP {status}.")
        elif stage == "complete":
            self.signals.log.emit(
                f"Cuenta 1VPN: resultado {event.get('result', 'desconocido')}."
            )

    # ---------- settings / diagnostics ----------
    def _update_access_settings(self):
        enabled = self.access_enabled.isChecked()
        locked = self.engine.active
        for widget in (
            self.access_host,
            self.access_port,
            self.access_user,
            self.access_password,
        ):
            widget.setEnabled(enabled and not locked)

    def check_driver_state(self):
        try:
            state = self.driver_lifecycle.state()
            self.driver_state.setText(str(state))
        except Exception as error:
            self.driver_state.setText(f"Estado no disponible · {type(error).__name__}")

    def _append_log(self, message: str):
        self.activity.appendPlainText(message)

    # ---------- lifecycle ----------
    def closeEvent(self, event: QCloseEvent):
        try:
            if self.browser_bridge is not None:
                self.browser_bridge.stop()
            self.native_proxy.stop()
            self.native_guard.stop()
            self.engine.stop()
        finally:
            event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("OneTunnel")
    app.setOrganizationName("OneTunnel")
    app.setStyleSheet(APP_QSS)
    window = OneTunnelQt()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
