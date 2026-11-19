"""Static guardrails for the v0.7 PySide6 preview.

These tests run without importing PySide6 so the stable Tkinter test job stays
lightweight. A separate Windows CI job performs the real Qt smoke test.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class QtPreviewSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = (ROOT / "qt_app.py").read_text(encoding="utf-8")
        cls.theme = (ROOT / "qt_theme.py").read_text(encoding="utf-8")

    def test_qt_frontend_is_parallel_not_replacing_stable_tk(self):
        self.assertTrue((ROOT / "app.py").is_file())
        self.assertIn("from PySide6.", self.qt)
        self.assertNotIn("import tkinter", self.qt)
        self.assertIn("class OneTunnelQt(QMainWindow)", self.qt)

    def test_qt_reuses_existing_backend(self):
        for name in (
            "NetworkEngine",
            "AutoSelector",
            "AccessProxy",
            "NativeWfpGuard",
            "NativeProxySession",
            "SignedDriverLifecycle",
            "PremiumBrowserBridge",
            "PolicyStore",
        ):
            self.assertIn(name, self.qt)

    def test_information_architecture(self):
        self.assertIn(
            'NAV = ("Inicio", "Aplicaciones", "Cuenta", "Ajustes", "Actividad")',
            self.qt,
        )
        for text in (
            "CONECTAR",
            "VERIFICAR SALIDA",
            "ELEGIR MEJOR SERVIDOR",
            "PROXY VPN",
            "BLOQUEAR",
            "Premium web",
            "Usar proxy de la red para conectar a 1VPN",
        ):
            self.assertIn(text, self.qt)

    def test_access_proxy_remains_fail_closed(self):
        self.assertIn("open_via_access_proxy", self.qt)
        self.assertIn("access_proxy=access_proxy", self.qt)
        self.assertNotIn("set_proxy", self.qt.casefold())
        self.assertNotIn("WinINET", self.qt)

    def test_theme_has_professional_hierarchy(self):
        for token in (
            "QWidget#Sidebar",
            "QFrame#Card",
            "QPushButton#Primary",
            "QPushButton#NavButton",
            "QTableWidget",
            "QPlainTextEdit",
        ):
            self.assertIn(token, self.theme)

    def test_no_external_proxifier_dependency_returns(self):
        self.assertNotIn("ProxiFyre", self.qt)
        self.assertNotIn("proxifier", self.qt.casefold())
