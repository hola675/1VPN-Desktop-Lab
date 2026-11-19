"""Offline tests of exact process names, ProxiFyre and native Windows PID enumeration."""
import json
import os
from pathlib import Path
import tempfile
import unittest

from proxifyre_adapter import (
    EXCLUDED_CARRIERS,
    build_proxifyre_draft,
    describe_proxifyre_draft,
    save_proxifyre_draft,
)
from running_apps import list_running_apps
from traffic_policy import AppPolicy


class TestPerExecutableRouting(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.chrome = self.folder / "chrome.exe"
        self.code = self.folder / "code.exe"
        self.blocked = self.folder / "blocked.exe"
        for path in (self.chrome, self.code, self.blocked):
            path.write_bytes(b"MZTEST")
        self.policies = [
            AppPolicy("chrome.exe", "TRANSPARENT"),
            AppPolicy("code.exe", "DIRECT"),
            AppPolicy("blocked.exe", "BLOCK"),
        ]

    def test_proxy_by_executable_and_direct_exclusion(self):
        config = build_proxifyre_draft(self.policies, 1080)
        route = config["proxies"][0]
        self.assertEqual(route["appNames"], ["chrome.exe"])
        self.assertIn("code.exe", config["excludes"])
        self.assertNotIn("blocked.exe", config["excludes"])
        self.assertEqual(route["socks5ProxyEndpoint"], "127.0.0.1:1080")
        self.assertEqual(route["supportedProtocols"], ["TCP"])
        self.assertEqual(route["supportedAddressFamilies"], ["IPv4"])
        self.assertEqual(config["dns"], {"mode": "Direct"})
        self.assertTrue(config["bypassLan"])
        self.assertEqual(len(config["proxies"]), 1)
        self.assertNotIn("", route["appNames"])
        self.assertNotIn(str(self.chrome), json.dumps(config))
        self.assertIn("1VPN-Desktop-Lab.exe", config["excludes"])
        self.assertIn("DNS: DIRECTO", describe_proxifyre_draft(config))

    def test_firewall_block_conflict_uses_basename_not_path(self):
        with self.assertRaisesRegex(ValueError, "BLOQUEO"):
            build_proxifyre_draft(
                [AppPolicy("chrome.exe", "TRANSPARENT")],
                1080, managed_firewall_programs=[str(self.chrome)],
            )

    def test_only_explicit_proxy_policies_are_intercepted(self):
        with self.assertRaisesRegex(ValueError, "TRANSPARENTE"):
            build_proxifyre_draft(
                [AppPolicy("code.exe", "DIRECT"), AppPolicy("blocked.exe", "BLOCK")],
                1080,
            )

    def test_rejects_system_process_as_proxy_target(self):
        with self.assertRaisesRegex(ValueError, "proceso esencial"):
            build_proxifyre_draft(
                [AppPolicy("lsass.exe", "TRANSPARENT")], 1080,
            )

    def test_rejects_duplicate_and_bad_port(self):
        with self.assertRaisesRegex(ValueError, "duplicados"):
            build_proxifyre_draft([
                AppPolicy("Chrome.exe", "TRANSPARENT"),
                AppPolicy("chrome.exe", "DIRECT"),
            ], 1080)
        for bad_port in (0, -1, 65536, True, "1080"):
            with self.subTest(bad_port=bad_port):
                with self.assertRaises(ValueError):
                    build_proxifyre_draft(self.policies, bad_port)

    def test_export_only_non_active_json_and_no_overwrite(self):
        config = build_proxifyre_draft(self.policies, 1080)
        output = self.folder / "profile.json"
        saved = save_proxifyre_draft(output, config)
        self.assertEqual(saved, output)
        doc = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(doc, config)
        self.assertNotIn("sessionAuthToken", output.read_text(encoding="utf-8"))
        with self.assertRaises(FileExistsError):
            save_proxifyre_draft(output, config)
        with self.assertRaisesRegex(ValueError, "app-config.json"):
            save_proxifyre_draft(self.folder / "app-config.json", config)

    def test_running_list_groups_by_name_across_folders(self):
        portable = self.folder / "portable"
        portable.mkdir()
        other = portable / "chrome.exe"
        other.write_bytes(b"MZTEST")
        apps = list_running_apps(lambda: [
            (10, str(self.chrome)), (20, str(other)),
            (30, str(self.code)),
            (31, str(self.folder / "missing.exe")),
            (0, str(self.code)), (44, "relative.exe"),
        ])
        self.assertEqual(len(apps), 2)
        by_name = {app.name: app for app in apps}
        self.assertEqual(by_name["chrome.exe"].pids, (10, 20))
        self.assertEqual(len(by_name["chrome.exe"].paths), 2)
        self.assertEqual(by_name["code.exe"].pids, (30,))
        self.assertEqual([app.name for app in apps], ["chrome.exe", "code.exe"])

    def test_native_windows_process_discovery_is_read_only(self):
        if os.name != "nt":
            self.skipTest("La API Win32 no existe fuera de Windows")
        entries = list_running_apps()
        self.assertIsInstance(entries, list)
        self.assertTrue(all(app.name.endswith(".exe") for app in entries))
        self.assertTrue(all(all(pid > 0 for pid in app.pids) for app in entries))

    def test_running_list_does_not_access_real_processes_with_source(self):
        self.assertEqual(list_running_apps(lambda: ()), [])
        if os.name != "nt":
            self.assertEqual(list_running_apps(), [])
