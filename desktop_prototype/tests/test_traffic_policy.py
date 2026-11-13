import json
from pathlib import Path
import tempfile
import unittest

from traffic_policy import AppPolicy, PolicyStore


class TestPolicies(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        self.exe = self.dir / "Navegador.exe"
        self.exe.write_bytes(b"TEST")
        self.store = PolicyStore(self.dir / "policies.json")

    def test_save_replace_and_delete(self):
        self.store.upsert(AppPolicy(str(self.exe), "MANUAL_PROXY"))
        self.assertEqual(self.store.load()[0].mode, "MANUAL_PROXY")
        self.store.upsert(AppPolicy(str(self.exe), "DIRECT"))
        self.assertEqual(len(self.store.load()), 1)
        self.assertEqual(self.store.load()[0].mode, "DIRECT")
        self.store.delete(str(self.exe))
        self.assertEqual(self.store.load(), [])

    def test_invalid_exe_and_modes(self):
        with self.assertRaises(ValueError):
            self.store.upsert(AppPolicy("relative.exe", "BLOCK"))
        with self.assertRaises(ValueError):
            self.store.upsert(AppPolicy(str(self.exe), "VPN_WORKING"))

    def test_no_credentials_are_persisted(self):
        self.store.upsert(AppPolicy(str(self.exe), "TRANSPARENT"))
        text = self.store.path.read_text()
        self.assertNotIn("password", text)
        self.assertNotIn("username", text)
        self.assertEqual(json.loads(text)["schema_version"], 1)
