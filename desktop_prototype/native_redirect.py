"""Capability check for OneTunnel transparent relay.

No driver is loaded and no listener is started by this module. It only locates
the bundled relay and runs its offline self-test when explicitly requested.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys


def _bundled(name: str) -> Path:
    locations = [
        Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / name,
        Path(__file__).resolve().parent.parent / "native" / "wfp" / "build" / "Release" / name,
    ]
    return next((p for p in locations if p.is_file()), locations[0])


def bundled_relay_path() -> Path:
    return _bundled("onetunnel-transparent-relay.exe")


def bundled_control_path() -> Path:
    return _bundled("onetunnel-wfp-control.exe")


@dataclass(frozen=True)
class RedirectCapability:
    relay_present: bool
    relay_self_test: bool
    callout_driver_ready: bool = False
    control_present: bool = False
    control_self_test: bool = False

    @property
    def transparent_proxy_ready(self) -> bool:
        return (
            self.relay_present
            and self.relay_self_test
            and self.control_present
            and self.control_self_test
            and self.callout_driver_ready
        )


def _self_test(executable: Path, marker: str) -> tuple[bool, bool]:
    if not executable.is_file():
        return False, False
    try:
        result = subprocess.run(
            [str(executable), "--self-test"],
            capture_output=True, text=True, timeout=5, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        return True, False
    return True, result.returncode == 0 and marker in result.stdout


def check_redirect_capability(
    path: Path | None = None,
    control_path: Path | None = None,
) -> RedirectCapability:
    relay = Path(path) if path else bundled_relay_path()
    control = Path(control_path) if control_path else bundled_control_path()
    relay_present, relay_ok = _self_test(
        relay, "PASS redirect-context/socks5 self-test"
    )
    control_present, control_ok = _self_test(
        control, "PASS WFP control-plane offline self-test"
    )
    return RedirectCapability(
        relay_present=relay_present,
        relay_self_test=relay_ok,
        callout_driver_ready=False,
        control_present=control_present,
        control_self_test=control_ok,
    )
