"""Static guardrails for the v0.5 first-party networking architecture."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NativeArchitectureGuardrails(unittest.TestCase):
    def test_runtime_does_not_import_proxifyre_adapter(self):
        for name in ("app.py", "control_panel.py", "native_wfp.py", "native_redirect.py", "native_proxy.py", "driver_lifecycle.py"):
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertNotIn("from proxifyre_adapter", text, name)
            self.assertNotIn("import proxifyre_adapter", text, name)

    def test_legacy_firewall_cannot_create_new_rules(self):
        legacy = (ROOT / "firewall_rules.py").read_text(encoding="utf-8")
        self.assertNotIn("New-NetFirewallRule", legacy)
        self.assertIn("Remove-NetFirewallRule", legacy)
        panel = (ROOT / "control_panel.py").read_text(encoding="utf-8")
        self.assertNotIn("legacy_firewall.block(", panel)

    def test_proxy_is_not_claimed_ready_without_callout(self):
        redirect = (ROOT / "native_redirect.py").read_text(encoding="utf-8")
        self.assertIn("callout_driver_ready: bool = False", redirect)
        panel = (ROOT / "control_panel.py").read_text(encoding="utf-8")
        self.assertIn("Callout driver WFP firmado/cargado: PENDIENTE", panel)

    def test_driver_install_is_never_automatic_on_app_startup(self):
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        init = app[app.index("class DesktopApp:"):app.index("    def _label")]
        self.assertNotIn(".install(", init)
        self.assertNotIn(".start()", init)
        lifecycle = (ROOT / "driver_lifecycle.py").read_text(encoding="utf-8")
        self.assertNotIn("testsigning on", lifecycle.casefold())
        self.assertNotIn("nointegritychecks", lifecycle.casefold())

    def test_shutdown_order_removes_filters_before_owned_driver_and_transport(self):
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        close = app[app.index("    def close(self):"):]
        proxy = close.index("self.native_proxy.stop()")
        block = close.index("self.native_guard.stop()")
        driver = close.index("self.driver_lifecycle.stop_if_owned()")
        transport = close.index("self.disconnect()")
        self.assertLess(proxy, block)
        self.assertLess(block, driver)
        self.assertLess(driver, transport)

    def test_native_sources_are_first_party_targets(self):
        cmake = (ROOT.parent / "native" / "wfp" / "CMakeLists.txt").read_text(encoding="utf-8")
        self.assertIn("onetunnel-wfp-guard", cmake)
        self.assertIn("onetunnel-transparent-relay", cmake)
        self.assertIn("onetunnel-wfp-control", cmake)
