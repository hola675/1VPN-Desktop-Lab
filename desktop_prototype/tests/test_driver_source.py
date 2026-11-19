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
INF = ROOT / "native" / "driver" / "OneTunnelRedirect.inf"
PROJECT = ROOT / "native" / "driver" / "OneTunnelRedirect.vcxproj"


class DriverSourceGuardrails(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = DRIVER.read_text(encoding="utf-8")
        cls.contract = CONTRACT.read_text(encoding="utf-8")
        cls.control = CONTROL.read_text(encoding="utf-8")
        cls.inf = INF.read_text(encoding="utf-8")
        cls.project = PROJECT.read_text(encoding="utf-8")

    def test_redirect_context_binary_sizes_match_relay(self):
        self.assertEqual(struct.calcsize("<IHHHH16s"), 28)
        self.assertEqual(struct.calcsize("<IHHII"), 16)
        self.assertIn("sizeof(OneTunnelRedirectContext) == 28", self.contract)
        self.assertIn("sizeof(OneTunnelRedirectConfig) == 16", self.contract)

    def test_driver_is_tcp_only_and_has_loop_protection(self):
        self.assertIn("IPPROTO_TCP", self.source)
        self.assertIn("FwpsQueryConnectionRedirectState0", self.source)
        self.assertIn("FWPS_CONNECTION_NOT_REDIRECTED", self.source)

    def test_driver_fails_closed_on_other_redirector_and_exposes_no_device_name(self):
        self.assertIn("FWPS_CONNECTION_REDIRECTED_BY_OTHER", self.source)
        other = self.source.index("FWPS_CONNECTION_REDIRECTED_BY_OTHER")
        blocked = self.source.index("FWP_ACTION_BLOCK", other)
        self.assertGreater(blocked, other)
        self.assertIn("IoCreateDevice(", self.source)
        self.assertIn("driverObject, 0, NULL", self.source)
        self.assertNotIn("\\Device\\OneTunnelWfpRedirect", self.source)

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

    def test_driver_targets_windows_desktop_not_universal_api_subset(self):
        self.assertIn("<DriverTargetPlatform>Desktop</DriverTargetPlatform>", self.project)
        self.assertNotIn("<DriverTargetPlatform>Universal</DriverTargetPlatform>", self.project)
        self.assertIn("<TargetVersion>Windows10</TargetVersion>", self.project)

    def test_driver_package_is_modern_primitive_demand_start(self):
        self.assertIn("Class       = WFPCALLOUTS", self.inf)
        self.assertIn("[DefaultInstall.NTamd64]", self.inf)
        self.assertIn("[DefaultInstall.NTamd64.Services]", self.inf)
        self.assertNotIn("[DefaultUninstall", self.inf)
        self.assertNotIn("[Manufacturer]", self.inf)
        self.assertIn("OneTunnelRedirect.CopyFiles = 13", self.inf)
        self.assertIn("ServiceBinary  = %13%\\onetunnel-wfp-redirect.sys", self.inf)
        self.assertIn("StartType      = 3", self.inf)
        self.assertNotIn("StartType      = 0", self.inf)
        self.assertIn("Dependencies   = BFE", self.inf)
        self.assertIn("PnpLockdown = 1", self.inf)
        self.assertRegex(self.inf, r"DriverVer\s*=\s*\d{2}/\d{2}/\d{4},\d+\.\d+\.\d+\.\d+")

    def test_ci_never_loads_or_installs_driver(self):
        workflow = (ROOT / ".github" / "workflows" / "windows.yml").read_text(encoding="utf-8")
        self.assertNotIn("sc.exe create", workflow)
        self.assertNotIn("sc.exe start", workflow)
        self.assertNotIn("pnputil /add-driver", workflow.lower())
        self.assertIn("UNSIGNED", workflow)
