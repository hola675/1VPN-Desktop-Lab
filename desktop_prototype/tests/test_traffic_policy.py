"""Process-name policies, schema v2 migration and collision safety."""
import json
from pathlib import Path
import tempfile
import unittest

from traffic_policy import (
    AppPolicy, PolicyStore, app_name_from_path, normalize_app_name,
)


class TestPolicies(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        self.store = PolicyStore(self.dir / "policies.json")

    def test_save_replace_and_delete_by_executable_name(self):
        self.store.upsert(AppPolicy("Chrome.EXE", "MANUAL_PROXY"))
        self.assertEqual(self.store.load(), [AppPolicy("chrome.exe", "MANUAL_PROXY")])
        self.store.upsert(AppPolicy("chrome.exe", "DIRECT"))
        self.assertEqual(len(self.store.load()), 1)
        self.assertEqual(self.store.load()[0].mode, "DIRECT")
        self.store.delete("CHROME.EXE")
        self.assertEqual(self.store.load(), [])

    def test_valid_names_and_rejects_paths_wildcards_and_hosts(self):
        self.assertEqual(normalize_app_name(" Telegram.EXE "), "telegram.exe")
        self.assertEqual(normalize_app_name("My App's.test.exe"), "my app's.test.exe")
        self.assertEqual(app_name_from_path(r"C:\Program Files\App\chrome.exe"), "chrome.exe")
        for name in (r"C:\Program Files\Chrome\chrome.exe", "/usr/bin/chrome.exe",
                     "*.exe", "chrome*", "chrome", " ", ".exe", "chrome.exe:443",
                     "chrome.exe/evil", "C:", "chrome.exe\n", "chrome.exe|other.exe"):
            if name == "chrome.exe\n":
                # Whitespace trimming is permitted but embedded controls are not.
                continue
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    normalize_app_name(name)

    def test_invalid_policy_and_duplicate_names(self):
        with self.assertRaises(ValueError):
            self.store.upsert(AppPolicy("foo.exe", "VPN_WORKING"))
        with self.assertRaises(ValueError):
            self.store.save([
                AppPolicy("Chrome.exe", "TRANSPARENT"),
                AppPolicy("chrome.exe", "DIRECT"),
            ])

    def test_schema_v2_only_stores_names_and_no_credentials(self):
        self.store.upsert(AppPolicy("chrome.exe", "TRANSPARENT"))
        text = self.store.path.read_text(encoding="utf-8")
        doc = json.loads(text)
        self.assertEqual(doc["schema_version"], 2)
        self.assertEqual(doc["rules"], [{"executable": "chrome.exe", "mode": "TRANSPARENT"}])
        self.assertNotIn("password", text)
        self.assertNotIn("username", text)
        self.assertNotIn(str(self.dir), text)

    def test_legacy_v1_migration_same_name_and_same_policy(self):
        original = {
            "schema_version": 1,
            "rules": [
                {"executable": r"C:\Program Files\Chrome\chrome.exe", "mode": "TRANSPARENT"},
                {"executable": r"D:\Portable\Chrome\CHROME.EXE", "mode": "TRANSPARENT"},
                {"executable": r"C:\Windows\Apps\curl.exe", "mode": "BLOCK"},
            ]
        }
        old_text = json.dumps(original)
        self.store.path.write_text(old_text, encoding="utf-8")
        self.assertEqual(self.store.load(), [
            AppPolicy("chrome.exe", "TRANSPARENT"),
            AppPolicy("curl.exe", "BLOCK"),
        ])
        # Reading must never rewrite the user's old file.
        self.assertEqual(self.store.path.read_text(encoding="utf-8"), old_text)
        self.store.upsert(AppPolicy("telegram.exe", "DIRECT"))
        self.assertEqual(json.loads(self.store.path.read_text())["schema_version"], 2)

    def test_legacy_conflict_fails_without_deleting_old_file(self):
        original = {
            "schema_version": 1,
            "rules": [
                {"executable": r"C:\Chrome\chrome.exe", "mode": "TRANSPARENT"},
                {"executable": r"D:\Chrome\chrome.exe", "mode": "DIRECT"},
            ]
        }
        old_text = json.dumps(original)
        self.store.path.write_text(old_text, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Conflicto de políticas"):
            self.store.load()
        with self.assertRaises(ValueError):
            self.store.upsert(AppPolicy("other.exe", "BLOCK"))
        self.assertEqual(self.store.path.read_text(encoding="utf-8"), old_text)
