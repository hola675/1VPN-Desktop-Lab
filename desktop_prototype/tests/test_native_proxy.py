"""Transactional supervisor tests. No driver, WFP filter or socket is touched."""
import io
from pathlib import Path
import tempfile
import unittest

from native_proxy import NativeProxySession


class FakeProcess:
    _next_pid = 5000

    def __init__(self, stdout_text):
        type(self)._next_pid += 1
        self.pid = type(self)._next_pid
        self.stdout = io.StringIO(stdout_text)
        self.stdin = io.StringIO()
        self.closed = False

    def poll(self):
        return 0 if self.closed else None

    def wait(self, timeout=None):
        self.closed = True
        return 0

    def terminate(self):
        self.closed = True

    def kill(self):
        self.closed = True


class NativeProxySessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.relay = root / "onetunnel-transparent-relay.exe"
        self.control = root / "onetunnel-wfp-control.exe"
        self.app = root / "chrome.exe"
        for path in (self.relay, self.control, self.app):
            path.write_bytes(b"MZ")
        self.calls = []
        self.processes = []

    def launcher_ok(self, args, **_kwargs):
        self.calls.append(args)
        if args[0] == str(self.relay):
            proc = FakeProcess("READY 51234 1080\n")
        else:
            proc = FakeProcess("READY 1\n")
        self.processes.append(proc)
        return proc

    def test_transactional_start_and_stop(self):
        session = NativeProxySession(
            self.relay, self.control, self.launcher_ok, platform="nt"
        )
        result = session.start([str(self.app)], 1080)
        self.assertTrue(session.active())
        self.assertEqual(result["relay_port"], 51234)
        self.assertEqual(session.relay_port, 51234)
        self.assertEqual(session.apps, (str(self.app.resolve()),))
        self.assertEqual(self.calls[0][1:], [
            "--listen-port", "0", "--socks-port", "1080"
        ])
        self.assertIn("--relay-pid", self.calls[1])
        self.assertIn("--relay-port", self.calls[1])
        self.assertIn("--app", self.calls[1])
        session.stop()
        self.assertFalse(session.active())
        self.assertTrue(all(p.closed for p in self.processes))

    def test_missing_callout_control_failure_stops_relay_and_leaves_no_session(self):
        def launcher(args, **_kwargs):
            self.calls.append(args)
            if args[0] == str(self.relay):
                proc = FakeProcess("READY 51234 1080\n")
            else:
                proc = FakeProcess("")
                proc.closed = True
            self.processes.append(proc)
            return proc

        session = NativeProxySession(
            self.relay, self.control, launcher, platform="nt"
        )
        with self.assertRaisesRegex(RuntimeError, "callout WFP"):
            session.start([str(self.app)], 1080)
        self.assertFalse(session.active())
        self.assertTrue(self.processes[0].closed)

    def test_rejects_bad_port_before_launch(self):
        session = NativeProxySession(
            self.relay, self.control, self.launcher_ok, platform="nt"
        )
        for port in (0, 65536, True, "1080"):
            with self.subTest(port=port):
                with self.assertRaises(ValueError):
                    session.start([str(self.app)], port)
        self.assertEqual(self.calls, [])

    def test_rejects_missing_or_empty_apps_before_launch(self):
        session = NativeProxySession(
            self.relay, self.control, self.launcher_ok, platform="nt"
        )
        with self.assertRaises(ValueError):
            session.start([], 1080)
        with self.assertRaises(ValueError):
            session.start([str(self.app.parent / "missing.exe")], 1080)
        self.assertEqual(self.calls, [])

    def test_non_windows_rejects_without_launch(self):
        session = NativeProxySession(
            self.relay, self.control, self.launcher_ok, platform="posix"
        )
        with self.assertRaises(OSError):
            session.start([str(self.app)], 1080)
        self.assertEqual(self.calls, [])
