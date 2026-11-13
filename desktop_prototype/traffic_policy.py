"""Políticas de aplicaciones: persistencia sin credenciales y sin cambios al sistema."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import tempfile

# TRANSPARENT es un estado de diseño no aplicable con el motor actual.
MODES = ("MANUAL_PROXY", "DIRECT", "BLOCK", "TRANSPARENT")


def default_state_file() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "1VPNDesktopLab"
    return root / "traffic_policies.json"


def normalize_executable(path: str) -> str:
    if not isinstance(path, str) or not path.strip():
        raise ValueError("Indica la ruta del ejecutable")
    p = Path(path.strip().strip('"')).expanduser()
    if not p.is_absolute() or p.suffix.lower() != ".exe":
        raise ValueError("Se requiere una ruta absoluta a un archivo .exe")
    if not p.is_file():
        raise ValueError("El archivo .exe no existe")
    return str(p.resolve())


def executable_key(path: str) -> str:
    """Comparación coherente para rutas de ejecutables (alias/variantes de mayúsculas)."""
    p = Path(path.strip().strip('"')).expanduser()
    return os.path.normcase(os.path.normpath(str(p.resolve(strict=False)))).casefold()


@dataclass(frozen=True)
class AppPolicy:
    executable: str
    mode: str

    def validated(self, require_existing: bool = True) -> "AppPolicy":
        if self.mode not in MODES:
            raise ValueError("Política desconocida")
        path = normalize_executable(self.executable) if require_existing else self.executable
        return AppPolicy(path, self.mode)


class PolicyStore:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else default_state_file()

    def load(self) -> list[AppPolicy]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if data.get("schema_version") != 1 or not isinstance(data.get("rules"), list):
            raise ValueError("Archivo de políticas no compatible")
        # Nunca ejecutar reglas al cargar; es solo una lista de preferencias.
        return [AppPolicy(str(r["executable"]), str(r["mode"])).validated(False) for r in data["rules"]]

    def save(self, rules: list[AppPolicy]):
        validated = [r.validated(False) for r in rules]
        paths = [executable_key(r.executable) for r in validated]
        if len(paths) != len(set(paths)):
            raise ValueError("Hay aplicaciones duplicadas")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Nunca persistir datos del proxy remoto ni contraseñas.
        payload = {"schema_version": 1, "rules": [asdict(r) for r in validated]}
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), prefix=".policy-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def upsert(self, rule: AppPolicy):
        rule = rule.validated()
        rules = [r for r in self.load() if executable_key(r.executable) != executable_key(rule.executable)]
        rules.append(rule)
        self.save(rules)

    def delete(self, executable: str):
        rules = [r for r in self.load() if executable_key(r.executable) != executable_key(executable)]
        self.save(rules)
