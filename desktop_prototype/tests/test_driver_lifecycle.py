"""Signed driver lifecycle tests; all privileged Windows operations are mocked."""
from pathlib import Path
import shutil
import tempfile
import unittest

from driver_lifecycle import (
    DriverInstallResult,
    DriverLifecycleError,
    DriverPackageVerification,
    SignedDriverLifecycle,
    bundled_driver_package_candidate,
    verify_package,
)

ROOT = Path(__file__).resolve().parents[2]
SOURCE_INF = ROOT / "native" / "driver" / "OneTunnelRedirect.inf"


class FakeService:
    def __init__(self, events, state):
        self.events = events
        self.shared = state

    def state(self):
        return 4 if self.shared["running"] else 1

    def start(self):
        if not self.shared["running"]:
            self.events.append("start")
            self.shared["running"] = True

    def stop(self):
        if self.shared["running"]:
            self.events.append("stop")
            self.shared["running"] = False


class DriverPackageVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copy2(SOURCE_INF, self.root / "OneTunnelRedirect.inf")
        (self.root / "OneTunnelRedirect.cat").write_bytes(b"FAKE-CATALOG")
        (self.root / "onetunnel-wfp-redirect.sys").write_bytes(b"MZFAKE")

    def test_verified_layout_accepts_only_expected_catalog(self):
        def fake_native(inf):
            self.assertEqual(inf, (self.root / "OneTunnelRedirect.inf").resolve())
            return (
                "Microsoft Test Signer",
                (self.root / "OneTunnelRedirect.cat").resolve(),
            )

        result = verify_package(self.root, native_verifier=fake_native)
        self.assertTrue(result.trusted)
        self.assertEqual(result.signer, "Microsoft Test Signer")
        self.assertEqual(result.catalog_path.name, "OneTunnelRedirect.cat")

    def test_unsigned_or_untrusted_package_stops_before_install(self):
        def reject(_inf):
            raise DriverLifecycleError("Windows no confía en la firma")

        with self.assertRaisesRegex(DriverLifecycleError, "no confía"):
            verify_package(self.root, native_verifier=reject)

    def test_catalog_with_right_name_but_wrong_directory_is_rejected(self):
        other = self.root / "other"
        other.mkdir()
        wrong = other / "OneTunnelRedirect.cat"
        wrong.write_bytes(b"OTHER")

        with self.assertRaisesRegex(DriverLifecycleError, "fuera del paquete"):
            verify_package(
                self.root,
                native_verifier=lambda _inf: ("Signer", wrong),
            )

    def test_wrong_catalog_identity_is_rejected(self):
        def wrong(_inf):
            return "Signer", self.root / "Other.cat"

        with self.assertRaisesRegex(DriverLifecycleError, "catálogo verificado"):
            verify_package(self.root, native_verifier=wrong)

    def test_missing_member_is_rejected_before_signature_call(self):
        (self.root / "onetunnel-wfp-redirect.sys").unlink()
        calls = []
        with self.assertRaisesRegex(DriverLifecycleError, "Falta archivo"):
            verify_package(
                self.root,
                native_verifier=lambda p: calls.append(p),
            )
        self.assertEqual(calls, [])

    def test_legacy_or_boot_inf_is_rejected(self):
        inf = (self.root / "OneTunnelRedirect.inf")
        text = inf.read_text(encoding="utf-8")
        inf.write_text(
            text.replace("StartType      = 3", "StartType      = 0"),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(DriverLifecycleError, "contrato|prohibida"):
            verify_package(
                self.root,
                native_verifier=lambda _p: (
                    "Signer", self.root / "OneTunnelRedirect.cat"
                ),
            )


class BundledDriverPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_incomplete_embedded_package_is_not_selected(self):
        from unittest.mock import patch

        (self.root / "OneTunnelRedirect.inf").write_text("x", encoding="utf-8")
        with patch("driver_lifecycle.bundled_driver_package_dir", return_value=self.root):
            self.assertIsNone(bundled_driver_package_candidate())

    def test_complete_embedded_package_is_selected_but_not_auto_verified(self):
        from unittest.mock import patch

        for name in (
            "OneTunnelRedirect.inf",
            "OneTunnelRedirect.cat",
            "onetunnel-wfp-redirect.sys",
        ):
            (self.root / name).write_bytes(b"x")
        with patch("driver_lifecycle.bundled_driver_package_dir", return_value=self.root):
            self.assertEqual(bundled_driver_package_candidate(), self.root)


class DriverLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.inf = Path(r"C:\signed\OneTunnelRedirect.inf")
        self.verification = DriverPackageVerification(
            self.inf,
            Path(r"C:\signed\OneTunnelRedirect.cat"),
            Path(r"C:\signed\onetunnel-wfp-redirect.sys"),
            "Trusted Signer",
            True,
        )

    def lifecycle(self, *, reboot=False, verify_error=None, admin=True, running=False):
        service_state = {"running": running}

        def verifier(_directory):
            self.events.append("verify")
            if verify_error:
                raise verify_error
            return self.verification

        def installer(inf):
            self.events.append(("install", inf))
            return reboot

        def uninstaller(inf):
            self.events.append(("uninstall", inf))
            return reboot

        return SignedDriverLifecycle(
            verifier=verifier,
            installer=installer,
            uninstaller=uninstaller,
            service_factory=lambda: FakeService(self.events, service_state),
            admin_check=lambda: admin,
        )

    def test_install_verifies_before_any_privileged_change(self):
        lifecycle = self.lifecycle()
        result = lifecycle.install("ignored")
        self.assertEqual(
            self.events,
            ["verify", ("install", self.inf), "start"],
        )
        self.assertEqual(result, DriverInstallResult(True, True, False))

    def test_signature_failure_prevents_install_and_service_start(self):
        lifecycle = self.lifecycle(
            verify_error=DriverLifecycleError("unsigned")
        )
        with self.assertRaisesRegex(DriverLifecycleError, "unsigned"):
            lifecycle.install("ignored")
        self.assertEqual(self.events, ["verify"])

    def test_start_failure_rolls_back_installed_package(self):
        lifecycle = self.lifecycle()

        class FailingService:
            def start(_self):
                self.events.append("start")
                raise DriverLifecycleError("start failed")

        lifecycle.service_factory = lambda: FailingService()
        with self.assertRaisesRegex(DriverLifecycleError, "revirtió"):
            lifecycle.install("ignored")
        self.assertEqual(
            self.events,
            ["verify", ("install", self.inf), "start", ("uninstall", self.inf)],
        )

    def test_start_and_rollback_failure_reports_half_configured_state(self):
        lifecycle = self.lifecycle()

        class FailingService:
            def start(_self):
                raise DriverLifecycleError("start failed")

        lifecycle.service_factory = lambda: FailingService()
        lifecycle.uninstaller = lambda _inf: (_ for _ in ()).throw(
            DriverLifecycleError("rollback failed")
        )
        with self.assertRaisesRegex(DriverLifecycleError, "reversión.*falló"):
            lifecycle.install("ignored")

    def test_reboot_required_does_not_start_driver_immediately(self):
        lifecycle = self.lifecycle(reboot=True)
        result = lifecycle.install("ignored")
        self.assertEqual(self.events, ["verify", ("install", self.inf)])
        self.assertEqual(result, DriverInstallResult(True, False, True))

    def test_admin_gate_happens_after_signature_preflight_before_install(self):
        lifecycle = self.lifecycle(admin=False)
        with self.assertRaises(PermissionError):
            lifecycle.install("ignored")
        self.assertEqual(self.events, ["verify"])

    def test_uninstall_stops_service_before_driver_store_removal(self):
        lifecycle = self.lifecycle(running=True)
        result = lifecycle.uninstall("ignored")
        self.assertEqual(
            self.events,
            ["verify", "stop", ("uninstall", self.inf)],
        )
        self.assertEqual(result, DriverInstallResult(False, False, False))

    def test_start_and_stop_are_explicit_admin_operations(self):
        lifecycle = self.lifecycle()
        lifecycle.start()
        self.assertTrue(lifecycle.started_by_this_instance)
        lifecycle.stop()
        self.assertFalse(lifecycle.started_by_this_instance)
        self.assertEqual(self.events, ["start", "stop"])

    def test_preexisting_running_service_is_not_owned_or_stopped_on_cleanup(self):
        lifecycle = self.lifecycle(running=True)
        lifecycle.start()
        self.assertFalse(lifecycle.started_by_this_instance)
        self.assertFalse(lifecycle.stop_if_owned())
        self.assertEqual(self.events, [])

    def test_owned_service_is_stopped_by_cleanup(self):
        lifecycle = self.lifecycle()
        lifecycle.start()
        self.assertTrue(lifecycle.stop_if_owned())
        self.assertFalse(lifecycle.started_by_this_instance)
        self.assertEqual(self.events, ["start", "stop"])

    def test_no_unsigned_bypass_language_in_runtime(self):
        source = (ROOT / "desktop_prototype" / "driver_lifecycle.py").read_text(
            encoding="utf-8"
        ).casefold()
        for forbidden in (
            "bcdedit /set testsigning on",
            "nointegritychecks",
            "disable secure boot",
            "allow_unsigned=true",
        ):
            self.assertNotIn(forbidden, source)
