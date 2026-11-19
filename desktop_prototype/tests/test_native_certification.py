"""Offline tests for the explicit WFP transparent-PROXY certification transaction."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

from native_certification import (
    CertificationResult,
    _parse_probe_output,
    certify_transparent_proxy,
)


class FakeProxy:
    def __init__(self, active=False):
        self._active = active
        self.starts = []
        self.stops = 0

    def active(self):
        return self._active

    def start(self, paths, socks5_port):
        self.starts.append((tuple(paths), socks5_port))
        self._active = True
        return {"relay_port": 10900, "application_paths": tuple(paths)}

    def stop(self):
        self.stops += 1
        self._active = False


class FakeDriver:
    def __init__(self, running=True):
        self.running = running

    def service_running(self):
        return self.running


class NativeCertificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.probe = Path(self.temp.name) / "onetunnel-egress-probe.exe"
        self.probe.write_bytes(b"MZFAKE")
        self.calls = []

    def runner(self, args, **kwargs):
        self.calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, "PASS 203.0.113.9\n", "")

    def test_success_uses_temporary_proxy_and_always_stops(self):
        proxy = FakeProxy()
        result = certify_transparent_proxy(
            native_proxy=proxy,
            driver_lifecycle=FakeDriver(),
            socks5_port=1080,
            expected_ip="203.0.113.9",
            probe_path=self.probe,
            runner=self.runner,
            platform="nt",
        )
        self.assertEqual(
            result, CertificationResult("203.0.113.9", "203.0.113.9", True)
        )
        self.assertEqual(proxy.starts, [((str(self.probe),), 1080)])
        self.assertEqual(proxy.stops, 1)
        args, kwargs = self.calls[0]
        self.assertEqual(args, [str(self.probe)])
        self.assertFalse(kwargs["check"])
        self.assertEqual(kwargs["timeout"], 25)
        for key in (
            "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
            "http_proxy", "https_proxy", "all_proxy", "no_proxy",
        ):
            self.assertNotIn(key, kwargs["env"])

    def test_ip_mismatch_is_not_certified_and_filters_are_removed(self):
        proxy = FakeProxy()

        def wrong(args, **kwargs):
            return subprocess.CompletedProcess(args, 0, "PASS 198.51.100.7\n", "")

        with self.assertRaisesRegex(RuntimeError, "no coincide"):
            certify_transparent_proxy(
                native_proxy=proxy,
                driver_lifecycle=FakeDriver(),
                socks5_port=1080,
                expected_ip="203.0.113.9",
                probe_path=self.probe,
                runner=wrong,
                platform="nt",
            )
        self.assertEqual(proxy.stops, 1)
        self.assertFalse(proxy.active())

    def test_probe_failure_is_fail_closed_and_filters_are_removed(self):
        proxy = FakeProxy()

        def failed(args, **kwargs):
            return subprocess.CompletedProcess(args, 18, "", "")

        with self.assertRaisesRegex(RuntimeError, "código 18"):
            certify_transparent_proxy(
                native_proxy=proxy,
                driver_lifecycle=FakeDriver(),
                socks5_port=1080,
                expected_ip="203.0.113.9",
                probe_path=self.probe,
                runner=failed,
                platform="nt",
            )
        self.assertEqual(proxy.stops, 1)

    def test_existing_proxy_session_is_never_interrupted(self):
        proxy = FakeProxy(active=True)
        with self.assertRaisesRegex(RuntimeError, "Detén primero"):
            certify_transparent_proxy(
                native_proxy=proxy,
                driver_lifecycle=FakeDriver(),
                socks5_port=1080,
                expected_ip="203.0.113.9",
                probe_path=self.probe,
                runner=self.runner,
                platform="nt",
            )
        self.assertEqual(proxy.starts, [])
        self.assertEqual(proxy.stops, 0)

    def test_driver_must_already_be_running(self):
        proxy = FakeProxy()
        with self.assertRaisesRegex(RuntimeError, "no está RUNNING"):
            certify_transparent_proxy(
                native_proxy=proxy,
                driver_lifecycle=FakeDriver(False),
                socks5_port=1080,
                expected_ip="203.0.113.9",
                probe_path=self.probe,
                runner=self.runner,
                platform="nt",
            )
        self.assertEqual(proxy.starts, [])

    def test_missing_probe_and_bad_inputs_stop_before_filters(self):
        proxy = FakeProxy()
        with self.assertRaises(FileNotFoundError):
            certify_transparent_proxy(
                native_proxy=proxy,
                driver_lifecycle=FakeDriver(),
                socks5_port=1080,
                expected_ip="203.0.113.9",
                probe_path=self.probe.with_name("missing.exe"),
                runner=self.runner,
                platform="nt",
            )
        with self.assertRaises(ValueError):
            certify_transparent_proxy(
                native_proxy=proxy,
                driver_lifecycle=FakeDriver(),
                socks5_port=0,
                expected_ip="203.0.113.9",
                probe_path=self.probe,
                runner=self.runner,
                platform="nt",
            )
        with self.assertRaises(ValueError):
            certify_transparent_proxy(
                native_proxy=proxy,
                driver_lifecycle=FakeDriver(),
                socks5_port=1080,
                expected_ip="not-an-ip",
                probe_path=self.probe,
                runner=self.runner,
                platform="nt",
            )
        self.assertEqual(proxy.starts, [])

    def test_probe_parser_rejects_non_pass_or_non_ip(self):
        self.assertEqual(_parse_probe_output("PASS 2001:db8::1\n"), "2001:db8::1")
        for output in ("", "ERROR 203.0.113.9", "PASS not-an-ip"):
            with self.subTest(output=output):
                with self.assertRaises(RuntimeError):
                    _parse_probe_output(output)

    def test_non_windows_is_rejected(self):
        with self.assertRaises(OSError):
            certify_transparent_proxy(
                native_proxy=FakeProxy(),
                driver_lifecycle=FakeDriver(),
                socks5_port=1080,
                expected_ip="203.0.113.9",
                probe_path=self.probe,
                runner=self.runner,
                platform="posix",
            )
