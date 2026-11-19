"""Compatibilidad de retirada para reglas antiguas de Windows Firewall.

Desde v0.5 OneTunnel NO crea nuevas reglas de Windows Defender Firewall.
Este módulo existe únicamente para leer el diario legado y retirar, con
consentimiento, reglas creadas por versiones v0.4.x. El backend nuevo usa WFP.
"""
from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Callable

from traffic_policy import executable_key

RULE_GROUP = "1VPN Desktop Lab"


def rule_name(executable: str) -> str:
    # Identificador determinista y propio. No se permite borrado por patrón.
    key = executable_key(executable).encode("utf-8")
    return "OneVPNLab-Block-" + hashlib.sha256(key).hexdigest()[:20]


def psquote(value: str) -> str:
    """Escapar datos como una única cadena literal en PowerShell."""
    return "'" + value.replace("'", "''") + "'"


def encoded_powershell(script: str) -> list[str]:
    code = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    return ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", code]


def admin_mode() -> bool:
    if sys.platform != "win32":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def journal_default() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "1VPNDesktopLab"
    return base / "firewall_rules.json"


class FirewallManager:
    def __init__(self, journal: Path | None = None,
                 runner: Callable[[list[str]], object] | None = None,
                 elevated: Callable[[], bool] = admin_mode):
        self.journal = Path(journal) if journal is not None else journal_default()
        self.runner = runner or self._run
        self.elevated = elevated

    @staticmethod
    def _run(argv: list[str]):
        return subprocess.run(argv, text=True, capture_output=True, timeout=30, check=False)

    def _load(self) -> dict[str, str]:
        if not self.journal.exists():
            return {}
        doc = json.loads(self.journal.read_text(encoding="utf-8"))
        if doc.get("schema_version") != 1:
            raise ValueError("Archivo de reglas de firewall no compatible")
        return dict(doc.get("managed", {}))

    def _save(self, values: dict[str, str]):
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        body = {"schema_version": 1, "managed": values}
        fd, tmp = tempfile.mkstemp(prefix=".firewall-", suffix=".json", dir=str(self.journal.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(body, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.journal)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def managed(self) -> dict[str, str]:
        return self._load()

    def _require_admin(self):
        if not self.elevated():
            raise PermissionError("Ejecuta esta aplicación como administrador para editar sus reglas de firewall")

    def _execute(self, script: str):
        self._require_admin()
        result = self.runner(encoded_powershell("$ErrorActionPreference='Stop'; " + script))
        if result.returncode:
            # Evitar propagar salida arbitraria de Windows a logs que se puedan publicar.
            raise RuntimeError(f"PowerShell no pudo aplicar la regla (código {result.returncode})")

    def block(self, executable: str) -> str:
        raise RuntimeError(
            "Función heredada deshabilitada: OneTunnel v0.5 no crea reglas "
            "de Windows Firewall. Usa el motor WFP nativo."
        )

    def unblock(self, executable: str) -> bool:
        name = rule_name(executable)
        managed = self._load()
        if name not in managed:
            return False
        # El nombre está bajo nuestro prefijo y aparece en el diario: no tocar reglas ajenas.
        script = (
            f"$rule = Get-NetFirewallRule -Name {psquote(name)} -ErrorAction SilentlyContinue; "
            "if ($rule) { "
            f"if ($rule.Group -ne {psquote(RULE_GROUP)}) "
            "{ throw 'El grupo de la regla no coincide' }; "
            f"Remove-NetFirewallRule -Name {psquote(name)} "
            "}"
        )
        self._execute(script)
        del managed[name]
        self._save(managed)
        return True
