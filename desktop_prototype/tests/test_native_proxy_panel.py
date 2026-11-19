"""UI orchestration tests for signed-driver native PROXY; no WFP changes occur."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from control_panel import TrafficControlPanel
from running_apps import RunningApp
from traffic_policy import AppPolicy, PolicyStore


class FakeEndpoints:
    socks5_port = 1080


class FakeInfo:
    def __init__(self):
        self.text = ""

    def configure(self, **values):
        self.text = values.get("text", "")


class FakeGuard:
    def managed(self):
        return {}


class FakeLifecycle:
    def __init__(self, running=False, events=None):
        self.running = running
        self.events = events if events is not None else []

    def service_running(self):
        self.events.append("service_running")
        return self.running

    def start(self):
        self.events.append("driver_start")
        self.running = True

    def stop(self):
        self.events.append("driver_stop")
        self.running = False


class FakeProxy:
    def __init__(self, events=None, fail=False):
        self.events = events if events is not None else []
        self.running = False
        self.fail = fail

    def active(self):
        return self.running

    def start(self, paths, port):
        self.events.append(("proxy_start", tuple(paths), port))
        if self.fail:
            raise RuntimeError("control plane failed")
        self.running = True
        return {"application_paths": tuple(paths), "relay_port": 53000}

    def stop(self):
        self.events.append("proxy_stop")
        self.running = False


class NativeProxyPanelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.chrome = root / "chrome.exe"
        self.chrome.write_bytes(b"MZTEST")
        self.store = PolicyStore(root / "policies.json")
        self.store.save([AppPolicy("chrome.exe", "TRANSPARENT")])

    def panel(self, lifecycle, proxy, verified=True):
        panel = TrafficControlPanel.__new__(TrafficControlPanel)
        panel.store = self.store
        panel.guard = FakeGuard()
        panel.native_proxy = proxy
        panel.driver_lifecycle = lifecycle
        panel._browsed_paths = {}
        panel._driver_started_for_proxy = False
        panel.endpoint_getter = lambda: FakeEndpoints()
        panel.verified_getter = lambda: verified
        panel.info = FakeInfo()
        panel.win = object()
        return panel

    def running_apps(self):
        return [RunningApp("chrome.exe", (101, 202), (str(self.chrome),))]

    def test_unverified_premium_egress_prevents_driver_or_proxy_start(self):
        events = []
        panel = self.panel(
            FakeLifecycle(False, events), FakeProxy(events), verified=False
        )
        with (
            patch("control_panel.list_running_apps", return_value=self.running_apps()),
            patch("control_panel.messagebox.showerror") as error,
        ):
            panel.activate_native_proxy()
        self.assertTrue(error.called)
        self.assertEqual(events, [])

    def test_stopped_driver_is_started_then_proxy_session(self):
        events = []
        lifecycle = FakeLifecycle(False, events)
        proxy = FakeProxy(events)
        panel = self.panel(lifecycle, proxy)
        with (
            patch("control_panel.list_running_apps", return_value=self.running_apps()),
            patch("control_panel.messagebox.askyesno", return_value=True),
        ):
            panel.activate_native_proxy()
        self.assertEqual(events[:2], ["service_running", "driver_start"])
        self.assertEqual(events[2][0], "proxy_start")
        self.assertEqual(events[2][2], 1080)
        self.assertTrue(panel._driver_started_for_proxy)
        self.assertTrue(proxy.active())

    def test_existing_driver_is_not_owned_or_stopped_by_proxy_session(self):
        events = []
        lifecycle = FakeLifecycle(True, events)
        proxy = FakeProxy(events)
        panel = self.panel(lifecycle, proxy)
        with patch(
            "control_panel.list_running_apps", return_value=self.running_apps()
        ):
            panel.activate_native_proxy()
            panel.stop_native_proxy()
        self.assertNotIn("driver_start", events)
        self.assertNotIn("driver_stop", events)
        self.assertIn("proxy_stop", events)

    def test_control_failure_rolls_back_driver_started_for_proxy(self):
        events = []
        lifecycle = FakeLifecycle(False, events)
        proxy = FakeProxy(events, fail=True)
        panel = self.panel(lifecycle, proxy)
        with (
            patch("control_panel.list_running_apps", return_value=self.running_apps()),
            patch("control_panel.messagebox.askyesno", return_value=True),
            patch("control_panel.messagebox.showerror") as error,
        ):
            panel.activate_native_proxy()
        self.assertTrue(error.called)
        self.assertEqual(events[0:2], ["service_running", "driver_start"])
        self.assertEqual(events[2][0], "proxy_start")
        self.assertEqual(events[3], "driver_stop")
        self.assertFalse(panel._driver_started_for_proxy)

    def test_stop_order_is_filters_first_then_owned_driver(self):
        events = []
        lifecycle = FakeLifecycle(True, events)
        proxy = FakeProxy(events)
        proxy.running = True
        panel = self.panel(lifecycle, proxy)
        panel._driver_started_for_proxy = True
        panel.stop_native_proxy()
        self.assertEqual(events, ["proxy_stop", "driver_stop"])
        self.assertFalse(panel._driver_started_for_proxy)
