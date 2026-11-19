"""Static safety contract for the first-party transparent egress probe."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "native" / "wfp" / "egress_probe.cpp"
CMAKE = ROOT / "native" / "wfp" / "CMakeLists.txt"


class EgressProbeSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.cmake = CMAKE.read_text(encoding="utf-8")

    def test_probe_explicitly_disables_application_proxy(self):
        self.assertIn("WINHTTP_ACCESS_TYPE_NO_PROXY", self.source)
        self.assertIn("api.ipify.org", self.source)
        self.assertIn("WINHTTP_FLAG_SECURE", self.source)
        self.assertNotIn("WINHTTP_ACCESS_TYPE_DEFAULT_PROXY", self.source)
        self.assertNotIn("WinHttpSetOption", self.source)
        self.assertNotIn("HTTP_PROXY", self.source)
        self.assertNotIn("HTTPS_PROXY", self.source)

    def test_probe_has_no_driver_or_wfp_mutation_api(self):
        for forbidden in (
            "FwpmEngineOpen", "FwpmFilterAdd", "FwpmSubLayerAdd",
            "DiInstallDriver", "StartService", "CreateService",
            "New-NetFirewallRule", "bcdedit", "ProxiFyre",
        ):
            self.assertNotIn(forbidden, self.source)

    def test_probe_is_bundled_as_separate_native_target(self):
        self.assertIn("add_executable(onetunnel-egress-probe", self.cmake)
        self.assertIn("Winhttp", self.cmake)
        self.assertIn("Ws2_32", self.cmake)

    def test_probe_network_action_is_not_part_of_self_test(self):
        self.assertIn("--self-test", self.source)
        self.assertIn("PASS no-proxy HTTPS probe self-test", self.source)
        self.assertIn("if (argc == 2", self.source)
