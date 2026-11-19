"""Static guardrails for OneTunnel v0.6 premium progressive-disclosure UI."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PremiumUiGuardrails(unittest.TestCase):
    def test_shared_design_system_exists(self):
        theme = (ROOT / "ui_theme.py").read_text(encoding="utf-8")
        for token in (
            "SURFACE", "BORDER", "TEXT", "MUTED", "ACCENT",
            "SUCCESS", "WARN", "DANGER",
            "OneTunnel.TCombobox", "OneTunnel.Treeview", "OneTunnel.TNotebook",
        ):
            self.assertIn(token, theme)

    def test_main_window_uses_progressive_disclosure(self):
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("v0.6.1 PREMIUM UI", app)
        self.assertIn("self.advanced_frame", app)
        self.assertIn("self.activity_frame", app)
        self.assertIn("def _toggle_advanced", app)
        self.assertIn("def _toggle_activity", app)
        self.assertIn('"CONECTAR"', app)
        self.assertIn('"APLICACIONES"', app)
        self.assertIn('"VERIFICAR SALIDA"', app)
        self.assertIn('"ELEGIR MEJOR SERVIDOR"', app)

    def test_advanced_inputs_remain_available_but_not_primary(self):
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        layout = app[app.index("    def _layout(self):"):app.index("    def _log", app.index("    def _layout(self):"))]
        for key in ("host", "port", "username", "password", "local_port", "socks_port"):
            self.assertIn(f'("{key}"', layout)
        for key in ("access_host", "access_port", "access_username", "access_password"):
            self.assertIn(f'("{key}"', layout)
        self.assertIn("Usar proxy de la red para conectar a 1VPN", layout)
        self.assertIn("Sin fallback directo", app)
        # The advanced frame is created but not initially packed.
        creation = layout.index("self.advanced_frame =")
        toggle = layout.index("def _toggle_advanced")
        self.assertNotIn("self.advanced_frame.pack(", layout[creation:toggle])

    def test_applications_window_separates_daily_and_engine_tasks(self):
        panel = (ROOT / "control_panel.py").read_text(encoding="utf-8")
        for label in ("Aplicaciones", "Motor WFP", "Diagnóstico"):
            self.assertIn(label, panel)
        self.assertIn('"DIRECTO"', panel)
        self.assertIn('"PROXY VPN"', panel)
        self.assertIn('"BLOQUEAR"', panel)
        self.assertIn("CERTIFICAR PROXY (LAB)", panel)
        self.assertNotIn("PREPARAR PERFIL PROXIFYRE", panel)

    def test_account_window_prioritizes_premium_web(self):
        account = (ROOT / "account_panel.py").read_text(encoding="utf-8")
        premium = account.index('notebook.add(web_tab, text="  Premium web  ")')
        classic = account.index('notebook.add(login_tab, text="  Email / 2FA  ")')
        diagnostic = account.index('notebook.add(diag_tab, text="  Diagnóstico  ")')
        self.assertLess(premium, classic)
        self.assertLess(classic, diagnostic)
        self.assertIn("VINCULAR PREMIUM WEB", account)
        self.assertIn("Las credenciales nunca se guardan en disco", account)

    def test_redesign_does_not_change_native_network_architecture(self):
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        panel = (ROOT / "control_panel.py").read_text(encoding="utf-8")
        self.assertIn("NativeWfpGuard", app)
        self.assertIn("NativeProxySession", app)
        self.assertIn("SignedDriverLifecycle", app)
        self.assertIn("certify_transparent_proxy", panel)
        for text in (app, panel):
            self.assertNotIn("from proxifyre_adapter", text)
