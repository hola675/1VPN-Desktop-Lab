import base64
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

from firewall_rules import FirewallManager, encoded_powershell, rule_name


class TestLegacyFirewallCleanup(unittest.TestCase):
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

        self.journal = Path(self.temp.name) / "fw.json"
        self.manager = FirewallManager(self.journal, fake_runner, lambda: True)

    def _write_legacy_rule(self):
        name = rule_name(str(self.path))
        self.journal.write_text(
            json.dumps({"schema_version": 1, "managed": {name: str(self.path.resolve())}}),
            encoding="utf-8",
        )
        return name

    def test_new_firewall_rule_creation_is_permanently_disabled(self):
        with self.assertRaisesRegex(RuntimeError, "v0.5 no crea reglas"):
            self.manager.block(str(self.path))
        self.assertEqual(self.scripts, [])
        self.assertFalse(self.journal.exists())

    def test_removes_only_a_rule_recorded_by_old_onetunnel(self):
        name = self._write_legacy_rule()
        self.assertIn(name, self.manager.managed())
        self.assertTrue(self.manager.unblock(str(self.path)))
        self.assertIn("Remove-NetFirewallRule -Name", self.scripts[-1])
        self.assertNotIn("New-NetFirewallRule", self.scripts[-1])
        self.assertNotIn(name, self.manager.managed())

    def test_no_admin_keeps_legacy_journal_unchanged(self):
        name = self._write_legacy_rule()
        manager = FirewallManager(self.journal, self.manager.runner, lambda: False)
        with self.assertRaises(PermissionError):
            manager.unblock(str(self.path))
        self.assertIn(name, manager.managed())
        self.assertEqual(self.scripts, [])

    def test_unmanaged_rule_is_never_removed(self):
        self.assertFalse(self.manager.unblock(str(self.path)))
        self.assertEqual(self.scripts, [])

    def test_powershell_encoding_for_removal_compatibility(self):
        encoded = encoded_powershell("Write-Output 'prueba'")
        self.assertEqual(base64.b64decode(encoded[-1]).decode("utf-16le"), "Write-Output 'prueba'")
