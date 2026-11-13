"""Firewall Windows para ejecutables explícitos y consentimiento local del usuario.

Usa cmdlets nativos de Windows. NO redirige tráfico: solamente bloquea una app.
Nunca toca la política predeterminada, grupos ajenos, Wintun, DNS o rutas.
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

from traffic_policy import executable_key, normalize_executable

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
        exe = normalize_executable(executable)
        if executable_key(exe) == executable_key(sys.executable):
            raise ValueError("No se puede bloquear el ejecutable del propio motor")
        system32 = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "System32")
        if os.path.normcase(exe).startswith(os.path.normcase(system32) + os.sep):
            raise ValueError("No se permiten bloqueos de ejecutables del sistema")
        name = rule_name(exe)
        self._require_admin()  # No registrar intenciones si faltan privilegios.
        managed = self._load()
        if name in managed and executable_key(managed[name]) != executable_key(exe):
            raise RuntimeError("Colisión de nombre de regla")
        display = f"1VPN Desktop Lab | Bloquear {Path(exe).name} [{name[-8:]}]"
        script = (
            f"$existing = Get-NetFirewallRule -Name {psquote(name)} -ErrorAction SilentlyContinue; "
            "if ($existing) { "
            f"if ($existing.Group -ne {psquote(RULE_GROUP)}) "
            "{ throw 'La regla pertenece a un grupo externo' }; "
            "$program = (Get-NetFirewallApplicationFilter -AssociatedNetFirewallRule $existing).Program; "
            f"if ($program -ine {psquote(exe)}) "
            "{ throw 'El programa existente no coincide' } "
            "} else { "
            f"New-NetFirewallRule -Name {psquote(name)} -DisplayName {psquote(display)} "
            f"-Group {psquote(RULE_GROUP)} -Direction Outbound -Action Block "
            f"-Program {psquote(exe)} -Enabled True -Profile Any | Out-Null "
            "}"
        )
        # Diario antes de la ejecución: conserva la capacidad de recuperación tras caída.
        # Si el comando falla, puede haber quedado una regla creada parcialmente;
        # unblock() podrá retirarla con validación del grupo.
        managed[name] = exe
        self._save(managed)
        self._execute(script)
        return name

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
