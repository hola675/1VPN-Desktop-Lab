"""Static safety contract for the kernel callout source.

This does not load a driver. It guards architectural invariants that must be
reviewed before any lab deployment.
"""
from pathlib import Path
import struct
import unittest

ROOT = Path(__file__).resolve().parents[2]
DRIVER = ROOT / "native" / "driver" / "onetunnel_redirect.cpp"
CONTRACT = ROOT / "native" / "wfp" / "redirect_contract.h"
CONTROL = ROOT / "native" / "wfp" / "wfp_control.cpp"


class DriverSourceGuardrails(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = DRIVER.read_text(encoding="utf-8")
        cls.contract = CONTRACT.read_text(encoding="utf-8")
        cls.control = CONTROL.read_text(encoding="utf-8")

    def test_redirect_context_binary_sizes_match_relay(self):
        self.assertEqual(struct.calcsize("<IHHHH16s"), 28)
        self.assertEqual(struct.calcsize("<IHHQ"), 16)
        self.assertIn("sizeof(OneTunnelRedirectContext) == 28", self.contract)
        self.assertIn("sizeof(OneTunnelRedirectConfig) == 16", self.contract)

    def test_driver_is_tcp_only_and_has_loop_protection(self):
        self.assertIn("IPPROTO_TCP", self.source)
        self.assertIn("FwpsQueryConnectionRedirectState0", self.source)
        self.assertIn("FWPS_CONNECTION_NOT_REDIRECTED", self.source)

    def test_driver_preserves_original_destination_and_targets_relay(self):
        for token in (
            "localRedirectContext",
            "localRedirectContextSize",
            "localRedirectHandle",
            "localRedirectTargetPID",
            "remoteAddressAndPort",
        ):
            self.assertIn(token, self.source)

    def test_driver_does_not_create_persistent_filters_by_itself(self):
        for forbidden in (
            "FwpmFilterAdd",
            "FwpmProviderAdd",
            "FwpmSubLayerAdd",
            "FwpmEngineOpen",
            "New-NetFirewallRule",
            "ProxiFyre",
        ):
            self.assertNotIn(forbidden, self.source)

    def test_control_plane_is_dynamic_and_gates_filters_on_registered_driver(self):
        self.assertIn("FWPM_SESSION_FLAG_DYNAMIC", self.control)
        self.assertIn("FWPM_CALLOUT_FLAG_REGISTERED", self.control)
        self.assertIn("ERROR_SERVICE_NOT_ACTIVE", self.control)
        self.assertIn("FwpmGetAppIdFromFileName0", self.control)
        self.assertIn("FWPM_CONDITION_ALE_APP_ID", self.control)
        self.assertIn("FWPM_CONDITION_IP_PROTOCOL", self.control)
        self.assertIn("FWP_ACTION_CALLOUT_TERMINATING", self.control)

        # Registration check must occur before the function that adds traffic filters.
        gate = self.control.index("callout_registered(engine.value")
        filters = self.control.index("add_context_and_filters(")
        invocation = self.control.rindex("add_context_and_filters(")
        self.assertLess(gate, invocation)
        self.assertLess(filters, invocation)

    def test_control_plane_does_not_install_or_start_the_driver(self):
        for forbidden in (
            "CreateService",
            "StartService",
            "sc.exe",
            "pnputil",
            "NtLoadDriver",
            "New-NetFirewallRule",
            "ProxiFyre",
        ):
            self.assertNotIn(forbidden, self.control)

    def test_ci_never_loads_or_installs_driver(self):
        workflow = (ROOT / ".github" / "workflows" / "windows.yml").read_text(encoding="utf-8")
        self.assertNotIn("sc.exe create", workflow)
        self.assertNotIn("sc.exe start", workflow)
        self.assertNotIn("pnputil /add-driver", workflow.lower())
        self.assertIn("UNSIGNED", workflow)
