import base64
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

from firewall_rules import FirewallManager, encoded_powershell, rule_name


class TestFirewall(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "My App's.test.exe"
        self.path.write_bytes(b"MZTEST")
        self.scripts = []

        def fake_runner(argv):
            self.assertEqual(argv[:3], ["powershell.exe", "-NoProfile", "-NonInteractive"])
            script = base64.b64decode(argv[-1]).decode("utf-16le")
            self.scripts.append(script)
            return SimpleNamespace(returncode=0)

        self.manager = FirewallManager(Path(self.temp.name) / "fw.json", fake_runner, lambda: True)

    def test_created_and_removed_by_own_stable_id(self):
        name = self.manager.block(str(self.path))
        self.assertEqual(name, rule_name(str(self.path)))
        self.assertIn("New-NetFirewallRule", self.scripts[0])
        self.assertIn("-Direction Outbound", self.scripts[0])
        self.assertIn("-Action Block", self.scripts[0])
        self.assertIn("My App''s.test.exe", self.scripts[0])
        self.assertIn(name, self.manager.managed())
        self.assertTrue(self.manager.unblock(str(self.path)))
        self.assertIn("Remove-NetFirewallRule -Name", self.scripts[-1])
        self.assertNotIn(name, self.manager.managed())

    def test_no_admin_no_change(self):
        manager = FirewallManager(self.manager.journal, self.manager.runner, lambda: False)
        with self.assertRaises(PermissionError):
            manager.block(str(self.path))
        self.assertEqual(self.scripts, [])

    def test_unmanaged_rule_is_never_removed(self):
        self.assertFalse(self.manager.unblock(str(self.path)))
        self.assertEqual(self.scripts, [])

    def test_powershell_encoding(self):
        encoded = encoded_powershell("Write-Output 'prueba'")
        self.assertEqual(base64.b64decode(encoded[-1]).decode("utf-16le"), "Write-Output 'prueba'")
