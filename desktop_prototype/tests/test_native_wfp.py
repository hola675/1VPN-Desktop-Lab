"""Tests for first-party native WFP guard; no Windows policy is modified."""
import io
from pathlib import Path
import tempfile
import unittest

from native_wfp import NativeWfpGuard


class FakeProcess:
    def __init__(self, count: int, *, reply="READY"):
        self.stdin = io.StringIO()
        self.stdout = io.StringIO(f"{reply} {count}\n")
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


class NativeWfpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.helper = root / "onetunnel-wfp-guard.exe"
        self.helper.write_bytes(b"MZ")
        self.one = root / "chrome.exe"
        self.two = root / "telegram.exe"
        self.one.write_bytes(b"MZ")
        self.two.write_bytes(b"MZ")
        self.launched = []
        self.processes = []

        def launcher(args, **options):
            self.launched.append(args)
            proc = FakeProcess(len(args) - 2)
            self.processes.append(proc)
            return proc

        self.guard = NativeWfpGuard(
            helper=self.helper, launcher=launcher,
            elevated=lambda: True, platform="nt",
        )
        self.addCleanup(self.guard.stop)

    def test_native_block_and_unblock_are_ephemeral(self):
        self.guard.block(str(self.one))
        self.assertEqual(list(self.guard.managed().values()), [str(self.one.resolve())])
        self.guard.block(str(self.two))
        self.assertEqual(len(self.guard.managed()), 2)
        self.assertTrue(self.processes[0].closed)
        self.assertTrue(self.guard.unblock(str(self.one)))
        self.assertEqual(list(self.guard.managed().values()), [str(self.two.resolve())])
        self.guard.stop()
        self.assertEqual(self.guard.managed(), {})
        self.assertTrue(all(proc.closed for proc in self.processes))

    def test_missing_admin_rejects_without_launching(self):
        self.guard.elevated = lambda: False
        with self.assertRaises(PermissionError):
            self.guard.block(str(self.one))
        self.assertEqual(self.launched, [])

    def test_missing_helper_rejects_without_launching(self):
        self.helper.unlink()
        with self.assertRaises(FileNotFoundError):
            self.guard.block(str(self.one))
        self.assertEqual(self.launched, [])

    def test_disallowed_process_name(self):
        blocked = self.one.parent / "lsass.exe"
        blocked.write_bytes(b"MZ")
        with self.assertRaises(ValueError):
            self.guard.block(str(blocked))
        self.assertEqual(self.launched, [])

    def test_existing_session_survives_new_helper_failure(self):
        self.guard.block(str(self.one))
        old = self.processes[0]

        def invalid_launcher(args, **_kwargs):
            proc = FakeProcess(len(args) - 2, reply="ERROR")
            self.processes.append(proc)
            return proc

        self.guard.launcher = invalid_launcher
        with self.assertRaisesRegex(RuntimeError, "No se pudo activar"):
            self.guard.block(str(self.two))
        self.assertFalse(old.closed)
        self.assertEqual(list(self.guard.managed().values()), [str(self.one.resolve())])

    def test_no_elevated_side_effect_until_explicit_apply(self):
        self.assertEqual(self.guard.managed(), {})
        self.assertEqual(self.launched, [])
