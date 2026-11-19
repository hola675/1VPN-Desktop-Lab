"""Static guardrails for the v0.5 first-party networking architecture."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NativeArchitectureGuardrails(unittest.TestCase):
    def test_runtime_does_not_import_proxifyre_adapter(self):
        for name in ("app.py", "control_panel.py", "native_wfp.py", "native_redirect.py"):
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

    def test_native_sources_are_first_party_targets(self):
        cmake = (ROOT.parent / "native" / "wfp" / "CMakeLists.txt").read_text(encoding="utf-8")
        self.assertIn("onetunnel-wfp-guard", cmake)
        self.assertIn("onetunnel-transparent-relay", cmake)
        self.assertIn("onetunnel-wfp-control", cmake)
