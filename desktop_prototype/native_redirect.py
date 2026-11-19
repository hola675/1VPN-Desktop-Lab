"""Capability check for OneTunnel transparent relay.

No driver is loaded and no listener is started by this module. It only locates
the bundled relay and runs its offline self-test when explicitly requested.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys


def bundled_relay_path() -> Path:
    name = "onetunnel-transparent-relay.exe"
    locations = [
        Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / name,
        Path(__file__).resolve().parent.parent / "native" / "wfp" / "build" / "Release" / name,
    ]
    return next((p for p in locations if p.is_file()), locations[0])


@dataclass(frozen=True)
class RedirectCapability:
    relay_present: bool
    relay_self_test: bool
    callout_driver_ready: bool = False

    @property
    def transparent_proxy_ready(self) -> bool:
        return self.relay_present and self.relay_self_test and self.callout_driver_ready


def check_redirect_capability(path: Path | None = None) -> RedirectCapability:
    relay = Path(path) if path else bundled_relay_path()
    if not relay.is_file():
        return RedirectCapability(False, False, False)
    try:
        result = subprocess.run(
            [str(relay), "--self-test"],
            capture_output=True, text=True, timeout=5, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        return RedirectCapability(True, False, False)
    return RedirectCapability(
        relay_present=True,
        relay_self_test=result.returncode == 0
        and "PASS redirect-context/socks5 self-test" in result.stdout,
        callout_driver_ready=False,
    )
