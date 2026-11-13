"""Control reversible de proxy WinINET para el usuario Windows actual.

No modifica WinHTTP, rutas, firewall, DNS ni controladores VPN.
Solo cambia HKCU para aplicaciones que adoptan el proxy de Windows.
"""
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import sys

KEY = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
NAMES = ("ProxyEnable", "ProxyServer", "ProxyOverride", "AutoConfigURL")


def _winreg():
    if sys.platform != "win32":
        raise RuntimeError("El cambio de proxy del sistema requiere Windows")
    import winreg
    return winreg


def _state_file() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "1VPNDesktopLab"
    base.mkdir(parents=True, exist_ok=True)
    return base / "proxy_restore.json"


def _notify_wininet() -> None:
    dll = ctypes.WinDLL("wininet", use_last_error=True)
    for option in (39, 37):  # SETTINGS_CHANGED, REFRESH
        dll.InternetSetOptionW(None, option, None, 0)


def _read_current() -> dict:
    wr = _winreg()
    out = {}
    with wr.OpenKey(wr.HKEY_CURRENT_USER, KEY, 0, wr.KEY_READ) as key:
        for name in NAMES:
            try:
                value, typ = wr.QueryValueEx(key, name)
                out[name] = {"present": True, "value": value, "type": typ}
            except FileNotFoundError:
                out[name] = {"present": False}
    return out


def _restore_values(values: dict) -> None:
    wr = _winreg()
    with wr.OpenKey(wr.HKEY_CURRENT_USER, KEY, 0, wr.KEY_SET_VALUE) as key:
        for name in NAMES:
            previous = values[name]
            if previous["present"]:
                wr.SetValueEx(key, name, 0, previous["type"], previous["value"])
            else:
                try:
                    wr.DeleteValue(key, name)
                except FileNotFoundError:
                    pass
    _notify_wininet()


class WindowsProxy:
    def __init__(self):
        self.path = _state_file()
        self.active = False

    def activate(self, local_port: int) -> None:
        wr = _winreg()
        if not (1 <= local_port <= 65535):
            raise ValueError("Puerto local inválido")
        if self.path.exists():
            raise RuntimeError("Existe una copia pendiente de restauración del proxy. Primero recupérala.")
        before = _read_current()
        proxy = f"127.0.0.1:{local_port}"
        record = {"before": before, "installed_proxy": proxy}
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(record, indent=2), encoding="utf-8")
        tmp.replace(self.path)
        try:
            with wr.OpenKey(wr.HKEY_CURRENT_USER, KEY, 0, wr.KEY_SET_VALUE) as key:
                wr.SetValueEx(key, "ProxyEnable", 0, wr.REG_DWORD, 1)
                wr.SetValueEx(key, "ProxyServer", 0, wr.REG_SZ, proxy)
                wr.SetValueEx(key, "ProxyOverride", 0, wr.REG_SZ, "<local>;localhost;127.*")
                try:
                    wr.DeleteValue(key, "AutoConfigURL")
                except FileNotFoundError:
                    pass
            _notify_wininet()
            self.active = True
        except Exception:
            _restore_values(before)
            self.path.unlink(missing_ok=True)
            raise

    def restore(self) -> bool:
        if not self.path.exists():
            self.active = False
            return False
        record = json.loads(self.path.read_text(encoding="utf-8"))
        current = _read_current()
        installed = record["installed_proxy"]
        # Evita borrar cambios ajenos realizados después de conectar.
        current_server = current["ProxyServer"].get("value")
        if current_server != installed:
            raise RuntimeError("El proxy de Windows cambió externamente; no se sobrescribirá.")
        _restore_values(record["before"])
        self.path.unlink(missing_ok=True)
        self.active = False
        return True

    def recover_stale(self) -> bool:
        return self.restore()
