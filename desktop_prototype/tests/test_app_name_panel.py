"""Panel integration: one process name covers multiple paths for firewall blocking.

Fake native WFP guard prevents modifying the system in this test.
"""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from control_panel import TrafficControlPanel
from running_apps import RunningApp
from traffic_policy import AppPolicy, PolicyStore


class FakeNativeGuard:
    def __init__(self):
        self.paths = ()
        self.calls = []

    def managed(self):
        return {str(i): p for i, p in enumerate(self.paths)}

    def apply_paths(self, paths):
        self.paths = tuple(sorted(set(paths)))
        self.calls.append(self.paths)
        return self.managed()


class FakeInfo:
    def __init__(self):
        self.text = ""

    def configure(self, **values):
        self.text = values.get("text", "")


class TestAppNamePanel(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        folder = Path(self.temp.name)
        a = folder / "one"
        b = folder / "two"
        a.mkdir()
        b.mkdir()
        self.paths = (str(a / "chrome.exe"), str(b / "CHROME.EXE"))
        for path in self.paths:
            Path(path).write_bytes(b"MZTEST")
        self.manager = FakeNativeGuard()
        self.store = PolicyStore(folder / "policies.json")
        # Tests business behavior without creating Tk windows.
        self.panel = TrafficControlPanel.__new__(TrafficControlPanel)
        self.panel.guard = self.manager
        self.panel.store = self.store
        self.panel._browsed_paths = {}
        self.panel._selected = lambda: "chrome.exe"
        self.panel.refresh = lambda: None
        self.panel.win = object()
        self.panel.info = FakeInfo()

    def test_selected_name_finds_both_installation_paths(self):
        apps = [RunningApp("chrome.exe", (10, 20), self.paths)]
        with patch("control_panel.list_running_apps", return_value=apps):
            self.assertEqual(set(self.panel._known_paths_for("chrome.exe")), set(self.paths))

    def test_block_by_name_applies_each_detected_path_and_unblocks_all(self):
        apps = [RunningApp("chrome.exe", (10, 20), self.paths)]
        with (patch("control_panel.list_running_apps", return_value=apps),
              patch("control_panel.messagebox.askyesno", return_value=True)):
            self.panel.block()
            self.assertEqual(set(self.manager.calls[-1]), set(self.paths))
            self.assertEqual(self.store.load(), [AppPolicy("chrome.exe", "BLOCK")])
            self.assertEqual(len(self.manager.managed()), 2)
            self.panel.unblock()
            self.assertEqual(self.manager.managed(), {})
            self.assertEqual(self.store.load(), [AppPolicy("chrome.exe", "DIRECT")])

    def test_no_detected_paths_refuses_to_claim_block(self):
        with (patch("control_panel.list_running_apps", return_value=[]),
              patch("control_panel.messagebox.showerror") as error):
            self.panel.block()
            self.assertTrue(error.called)
            self.assertEqual(self.manager.calls, [])
            self.assertEqual(self.store.load(), [])
