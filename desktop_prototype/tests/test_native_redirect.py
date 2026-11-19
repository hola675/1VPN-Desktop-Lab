"""Capability checks for packaged transparent relay; no sockets or WFP are changed."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from native_redirect import RedirectCapability, check_redirect_capability


class FakeResult:
    def __init__(self, code=0, stdout="PASS redirect-context/socks5 self-test\n"):
        self.returncode = code
        self.stdout = stdout


class NativeRedirectCapabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.relay = Path(self.temp.name) / "onetunnel-transparent-relay.exe"

    def test_missing_relay_is_not_ready(self):
        cap = check_redirect_capability(self.relay)
        self.assertEqual(cap, RedirectCapability(False, False, False))
        self.assertFalse(cap.transparent_proxy_ready)

    def test_self_test_pass_still_waits_for_callout(self):
        self.relay.write_bytes(b"MZ")
        with patch("native_redirect.subprocess.run", return_value=FakeResult()) as run:
            cap = check_redirect_capability(self.relay)
        self.assertTrue(cap.relay_present)
        self.assertTrue(cap.relay_self_test)
        self.assertFalse(cap.callout_driver_ready)
        self.assertFalse(cap.transparent_proxy_ready)
        run.assert_called_once()

    def test_failed_self_test_is_reported(self):
        self.relay.write_bytes(b"MZ")
        with patch("native_redirect.subprocess.run",
                   return_value=FakeResult(1, "FAIL\n")):
            cap = check_redirect_capability(self.relay)
        self.assertTrue(cap.relay_present)
        self.assertFalse(cap.relay_self_test)
        self.assertFalse(cap.transparent_proxy_ready)

    def test_timeout_fails_closed(self):
        import subprocess
        self.relay.write_bytes(b"MZ")
        with patch("native_redirect.subprocess.run",
                   side_effect=subprocess.TimeoutExpired("relay", 5)):
            cap = check_redirect_capability(self.relay)
        self.assertEqual(cap, RedirectCapability(True, False, False))
