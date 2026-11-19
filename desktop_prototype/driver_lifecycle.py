"""Signed OneTunnel WFP driver package verification and lifecycle.

Production policy:
- no unsigned/test-signed bypass;
- no bcdedit/testsigning/Secure-Boot changes;
- verify the INF against its signed catalog before installing;
- let Windows Driver Store installation perform final package/hash validation;
- demand-start/stop the OneTunnel service through SCM APIs only.

The unsigned CI artifact is intentionally rejected by verify_package().
"""
from __future__ import annotations

from dataclasses import dataclass
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import re
import sys
import time

from native_wfp import running_as_admin

INF_NAME = "OneTunnelRedirect.inf"
CAT_NAME = "OneTunnelRedirect.cat"
SYS_NAME = "onetunnel-wfp-redirect.sys"
SERVICE_NAME = "OneTunnelWfpRedirect"
MAX_PATH = 260

SC_MANAGER_CONNECT = 0x0001
SERVICE_QUERY_STATUS = 0x0004
SERVICE_START = 0x0010
SERVICE_STOP = 0x0020
SERVICE_CONTROL_STOP = 0x00000001
SC_STATUS_PROCESS_INFO = 0
SERVICE_STOPPED = 0x00000001
SERVICE_START_PENDING = 0x00000002
SERVICE_STOP_PENDING = 0x00000003
SERVICE_RUNNING = 0x00000004
ERROR_SERVICE_ALREADY_RUNNING = 1056
ERROR_SERVICE_DOES_NOT_EXIST = 1060


class DriverLifecycleError(RuntimeError):
    pass


@dataclass(frozen=True)
class DriverPackageVerification:
    inf_path: Path
    catalog_path: Path
    driver_path: Path
    signer: str
    trusted: bool


@dataclass(frozen=True)
class DriverInstallResult:
    installed: bool
    service_started: bool
    reboot_required: bool


class _SP_INF_SIGNER_INFO_V2_W(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("CatalogFile", wintypes.WCHAR * MAX_PATH),
        ("DigitalSigner", wintypes.WCHAR * MAX_PATH),
        ("DigitalSignerVersion", wintypes.WCHAR * MAX_PATH),
        ("SignerScore", wintypes.DWORD),
    ]


class _SERVICE_STATUS(ctypes.Structure):
    _fields_ = [
        ("dwServiceType", wintypes.DWORD),
        ("dwCurrentState", wintypes.DWORD),
        ("dwControlsAccepted", wintypes.DWORD),
        ("dwWin32ExitCode", wintypes.DWORD),
        ("dwServiceSpecificExitCode", wintypes.DWORD),
        ("dwCheckPoint", wintypes.DWORD),
        ("dwWaitHint", wintypes.DWORD),
    ]


class _SERVICE_STATUS_PROCESS(ctypes.Structure):
    _fields_ = [
        ("dwServiceType", wintypes.DWORD),
        ("dwCurrentState", wintypes.DWORD),
        ("dwControlsAccepted", wintypes.DWORD),
        ("dwWin32ExitCode", wintypes.DWORD),
        ("dwServiceSpecificExitCode", wintypes.DWORD),
        ("dwCheckPoint", wintypes.DWORD),
        ("dwWaitHint", wintypes.DWORD),
        ("dwProcessId", wintypes.DWORD),
        ("dwServiceFlags", wintypes.DWORD),
    ]


def bundled_driver_package_dir() -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return root / "driver_package"


def _read_inf_strict(inf: Path) -> str:
    # INF packages are conventionally ANSI/UTF-16; ours is ASCII-only by policy.
    raw = inf.read_bytes()
    if len(raw) > 256 * 1024:
        raise DriverLifecycleError("INF de OneTunnel demasiado grande")
    if b"\x00" in raw:
        try:
            text = raw.decode("utf-16")
        except UnicodeError as error:
            raise DriverLifecycleError("INF no se puede interpretar") from error
    else:
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeError as error:
            raise DriverLifecycleError("INF no se puede interpretar") from error
    return text


def _validate_package_layout(package_dir: str | Path) -> tuple[Path, Path, Path]:
    root = Path(package_dir).expanduser().resolve()
    if not root.is_dir():
        raise DriverLifecycleError("No existe la carpeta del paquete WFP firmado")
    inf = (root / INF_NAME).resolve()
    cat = (root / CAT_NAME).resolve()
    sys_file = (root / SYS_NAME).resolve()
    for path in (inf, cat, sys_file):
        if path.parent != root or not path.is_file():
            raise DriverLifecycleError(f"Falta archivo obligatorio del paquete: {path.name}")
        if path.stat().st_size <= 0:
            raise DriverLifecycleError(f"Archivo vacío en paquete: {path.name}")
    return inf, cat, sys_file


def _validate_inf_policy(inf: Path) -> None:
    text = _read_inf_strict(inf)
    required = (
        r"(?im)^\s*CatalogFile\s*=\s*OneTunnelRedirect\.cat\s*$",
        r"(?im)^\s*Class\s*=\s*WFPCALLOUTS\s*$",
        r"(?im)^\s*PnpLockdown\s*=\s*1\s*$",
        r"(?im)^\s*OneTunnelRedirect\.CopyFiles\s*=\s*13\s*$",
        r"(?im)^\s*StartType\s*=\s*3\s*$",
        r"(?im)^\s*ServiceBinary\s*=\s*%13%\\onetunnel-wfp-redirect\.sys\s*$",
        r"(?im)^\s*ServiceName\s*=\s*\"OneTunnelWfpRedirect\"\s*$",
    )
    for pattern in required:
        if not re.search(pattern, text):
            raise DriverLifecycleError(
                "El INF no cumple el contrato de paquete aislado/demand-start de OneTunnel"
            )
    forbidden = (
        "[DefaultUninstall",
        "StartType      = 0",
        "TestSigning",
        "bcdedit",
        "ProxiFyre",
        "New-NetFirewallRule",
    )
    for value in forbidden:
        if value.casefold() in text.casefold():
            raise DriverLifecycleError(f"INF contiene directiva prohibida: {value}")


def _native_verify_inf(inf_path: Path) -> tuple[str, Path]:
    if os.name != "nt":
        raise OSError("La verificación de firma del driver solo funciona en Windows")
    setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
    verify = setupapi.SetupVerifyInfFileW
    verify.argtypes = [
        wintypes.LPCWSTR,
        ctypes.c_void_p,
        ctypes.POINTER(_SP_INF_SIGNER_INFO_V2_W),
    ]
    verify.restype = wintypes.BOOL

    info = _SP_INF_SIGNER_INFO_V2_W()
    info.cbSize = ctypes.sizeof(info)
    ctypes.set_last_error(0)
    ok = verify(str(inf_path), None, ctypes.byref(info))
    if not ok:
        error = ctypes.get_last_error()
        raise DriverLifecycleError(
            "Windows no confía en la firma/catálogo del paquete WFP "
            f"(SetupVerifyInfFileW={error})."
        )
    signer = str(info.DigitalSigner).strip()
    catalog = Path(str(info.CatalogFile)).expanduser()
    if not signer or not str(catalog):
        raise DriverLifecycleError("Windows no devolvió un firmante/catálogo válido")
    return signer, catalog


def verify_package(
    package_dir: str | Path,
    *,
    native_verifier=_native_verify_inf,
) -> DriverPackageVerification:
    """Require our exact package layout + a catalog signature trusted by Windows."""
    inf, cat, sys_file = _validate_package_layout(package_dir)
    _validate_inf_policy(inf)
    signer, verified_catalog = native_verifier(inf)
    if verified_catalog.name.casefold() != CAT_NAME.casefold():
        raise DriverLifecycleError("El catálogo verificado no es el esperado por OneTunnel")
    # SetupVerifyInfFile authenticates INF+catalog. DiInstallDriver remains the
    # final authority that validates every package member hash before staging.
    return DriverPackageVerification(
        inf_path=inf,
        catalog_path=cat,
        driver_path=sys_file,
        signer=signer,
        trusted=True,
    )


def _native_install(inf: Path) -> bool:
    newdev = ctypes.WinDLL("newdev", use_last_error=True)
    install = newdev.DiInstallDriverW
    install.argtypes = [
        wintypes.HWND, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.POINTER(wintypes.BOOL),
    ]
    install.restype = wintypes.BOOL
    reboot = wintypes.BOOL(False)
    ctypes.set_last_error(0)
    if not install(None, str(inf), 0, ctypes.byref(reboot)):
        raise DriverLifecycleError(
            f"Windows rechazó la instalación del paquete ({ctypes.get_last_error()})"
        )
    return bool(reboot.value)


def _native_uninstall(inf: Path) -> bool:
    newdev = ctypes.WinDLL("newdev", use_last_error=True)
    uninstall = newdev.DiUninstallDriverW
    uninstall.argtypes = [
        wintypes.HWND, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.POINTER(wintypes.BOOL),
    ]
    uninstall.restype = wintypes.BOOL
    reboot = wintypes.BOOL(False)
    ctypes.set_last_error(0)
    if not uninstall(None, str(inf), 0, ctypes.byref(reboot)):
        raise DriverLifecycleError(
            f"Windows rechazó la desinstalación del paquete ({ctypes.get_last_error()})"
        )
    return bool(reboot.value)


class _ServiceManager:
    def __init__(self):
        if os.name != "nt":
            raise OSError("SCM solo está disponible en Windows")
        self.api = ctypes.WinDLL("advapi32", use_last_error=True)
        self.api.OpenSCManagerW.argtypes = [
            wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD
        ]
        self.api.OpenSCManagerW.restype = wintypes.HANDLE
        self.api.OpenServiceW.argtypes = [
            wintypes.HANDLE, wintypes.LPCWSTR, wintypes.DWORD
        ]
        self.api.OpenServiceW.restype = wintypes.HANDLE
        self.api.CloseServiceHandle.argtypes = [wintypes.HANDLE]
        self.api.CloseServiceHandle.restype = wintypes.BOOL
        self.api.StartServiceW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD,
            ctypes.POINTER(wintypes.LPCWSTR),
        ]
        self.api.StartServiceW.restype = wintypes.BOOL
        self.api.ControlService.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(_SERVICE_STATUS)
        ]
        self.api.ControlService.restype = wintypes.BOOL
        self.api.QueryServiceStatusEx.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.BYTE),
            wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
        ]
        self.api.QueryServiceStatusEx.restype = wintypes.BOOL

    def _open(self):
        scm = self.api.OpenSCManagerW(None, None, SC_MANAGER_CONNECT)
        if not scm:
            raise DriverLifecycleError(
                f"No se pudo abrir Service Control Manager ({ctypes.get_last_error()})"
            )
        service = self.api.OpenServiceW(
            scm, SERVICE_NAME,
            SERVICE_QUERY_STATUS | SERVICE_START | SERVICE_STOP,
        )
        if not service:
            error = ctypes.get_last_error()
            self.api.CloseServiceHandle(scm)
            if error == ERROR_SERVICE_DOES_NOT_EXIST:
                raise DriverLifecycleError("El servicio WFP de OneTunnel no está instalado")
            raise DriverLifecycleError(f"No se pudo abrir el servicio WFP ({error})")
        return scm, service

    def _state(self, service) -> int:
        status = _SERVICE_STATUS_PROCESS()
        needed = wintypes.DWORD()
        if not self.api.QueryServiceStatusEx(
            service, SC_STATUS_PROCESS_INFO,
            ctypes.cast(ctypes.byref(status), ctypes.POINTER(wintypes.BYTE)),
            ctypes.sizeof(status), ctypes.byref(needed),
        ):
            raise DriverLifecycleError(
                f"No se pudo consultar el servicio WFP ({ctypes.get_last_error()})"
            )
        return int(status.dwCurrentState)

    def state(self) -> int:
        scm, service = self._open()
        try:
            return self._state(service)
        finally:
            self.api.CloseServiceHandle(service)
            self.api.CloseServiceHandle(scm)

    def start(self, timeout: float = 10.0) -> None:
        scm, service = self._open()
        try:
            state = self._state(service)
            if state == SERVICE_RUNNING:
                return
            ctypes.set_last_error(0)
            if not self.api.StartServiceW(service, 0, None):
                error = ctypes.get_last_error()
                if error != ERROR_SERVICE_ALREADY_RUNNING:
                    raise DriverLifecycleError(
                        f"No se pudo arrancar el callout WFP ({error})"
                    )
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                state = self._state(service)
                if state == SERVICE_RUNNING:
                    return
                if state not in (SERVICE_START_PENDING, SERVICE_STOP_PENDING):
                    break
                time.sleep(0.1)
            raise DriverLifecycleError("El callout WFP no alcanzó estado RUNNING")
        finally:
            self.api.CloseServiceHandle(service)
            self.api.CloseServiceHandle(scm)

    def stop(self, timeout: float = 10.0) -> None:
        scm, service = self._open()
        try:
            state = self._state(service)
            if state == SERVICE_STOPPED:
                return
            status = _SERVICE_STATUS()
            ctypes.set_last_error(0)
            if not self.api.ControlService(
                service, SERVICE_CONTROL_STOP, ctypes.byref(status)
            ):
                raise DriverLifecycleError(
                    f"No se pudo detener el callout WFP ({ctypes.get_last_error()})"
                )
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if self._state(service) == SERVICE_STOPPED:
                    return
                time.sleep(0.1)
            raise DriverLifecycleError("El callout WFP no alcanzó estado STOPPED")
        finally:
            self.api.CloseServiceHandle(service)
            self.api.CloseServiceHandle(scm)


class SignedDriverLifecycle:
    """Explicit privileged lifecycle. Never auto-installs on app startup."""

    def __init__(
        self,
        *,
        verifier=verify_package,
        installer=_native_install,
        uninstaller=_native_uninstall,
        service_factory=_ServiceManager,
        admin_check=running_as_admin,
    ):
        self.verifier = verifier
        self.installer = installer
        self.uninstaller = uninstaller
        self.service_factory = service_factory
        self.admin_check = admin_check

    def verify(self, package_dir: str | Path) -> DriverPackageVerification:
        return self.verifier(package_dir)

    def install(self, package_dir: str | Path) -> DriverInstallResult:
        verification = self.verifier(package_dir)
        if not self.admin_check():
            raise PermissionError("Instalar el motor WFP firmado requiere administrador")
        reboot = self.installer(verification.inf_path)
        if reboot:
            return DriverInstallResult(True, False, True)
        service = self.service_factory()
        service.start()
        return DriverInstallResult(True, True, False)

    def start(self) -> None:
        if not self.admin_check():
            raise PermissionError("Arrancar el motor WFP requiere administrador")
        self.service_factory().start()

    def stop(self) -> None:
        if not self.admin_check():
            raise PermissionError("Detener el motor WFP requiere administrador")
        self.service_factory().stop()

    def uninstall(self, package_dir: str | Path) -> DriverInstallResult:
        verification = self.verifier(package_dir)
        if not self.admin_check():
            raise PermissionError("Desinstalar el motor WFP requiere administrador")
        service = self.service_factory()
        try:
            service.stop()
        except DriverLifecycleError as error:
            if "no está instalado" not in str(error):
                raise
        reboot = self.uninstaller(verification.inf_path)
        return DriverInstallResult(False, False, reboot)
