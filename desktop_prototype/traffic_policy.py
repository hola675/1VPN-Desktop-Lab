"""Políticas por NOMBRE DE PROCESO .exe (estilo Proxifier), no por ruta.

Schema v2. v1 con rutas se lee y convierte en memoria sin modificar el archivo
hasta que la persona guarde otra política. Un conflicto entre rutas antiguas
que comparten nombre pero tenían acciones diferentes exige resolución manual.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import tempfile

MODES = ("MANUAL_PROXY", "DIRECT", "BLOCK", "TRANSPARENT")
SCHEMA_VERSION = 2


def default_state_file() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "1VPNDesktopLab"
    return root / "traffic_policies.json"


def normalize_executable(path: str) -> str:
    """Resolve a REAL file path. Used internally by Windows Firewall only."""
    if not isinstance(path, str) or not path.strip():
        raise ValueError("Indica la ruta del ejecutable")
    p = Path(path.strip().strip('"')).expanduser()
    if not p.is_absolute() or p.suffix.lower() != ".exe":
        raise ValueError("Se requiere una ruta absoluta a un archivo .exe")
    if not p.is_file():
        raise ValueError("El archivo .exe no existe")
    return str(p.resolve())


def executable_key(path: str) -> str:
    """Canonical full-path comparison for firewall journaling, not app policy."""
    p = Path(path.strip().strip('"')).expanduser()
    return os.path.normcase(os.path.normpath(str(p.resolve(strict=False)))).casefold()


def normalize_app_name(raw: str) -> str:
    """Validate a literal executable basename; no wildcard, path or host rule."""
    if not isinstance(raw, str):
        raise ValueError("Indica el nombre de una aplicación .exe")
    name = raw.strip()
    if (not 5 <= len(name) <= 255
            or name[0] in (" ", ".")
            or name[-1] in (" ", ".")
            or not name.casefold().endswith(".exe")
            or any(char in name for char in '\\/:*?"<>|')
            or any(ord(char) < 32 or ord(char) == 127 for char in name)):
        raise ValueError("Introduce solo el nombre del programa (ejemplo: chrome.exe), sin ruta ni comodines")
    return name.casefold()


def app_name_from_path(path: str) -> str:
    """Get the EXE basename from Windows or POSIX-style full paths."""
    if not isinstance(path, str):
        raise ValueError("Ruta de ejecutable inválida")
    return normalize_app_name(path.replace("\\", "/").rsplit("/", 1)[-1])


@dataclass(frozen=True)
class AppPolicy:
    # Kept as 'executable' for backwards-compatible callers; v2 stores a name.
    executable: str
    mode: str

    def validated(self, require_existing: bool = True) -> "AppPolicy":
        if self.mode not in MODES:
            raise ValueError("Política desconocida")
        return AppPolicy(normalize_app_name(self.executable), self.mode)


class PolicyStore:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else default_state_file()

    def load(self) -> list[AppPolicy]:
        if not self.path.exists():
            return []
        doc = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict) or doc.get("schema_version") not in (1, SCHEMA_VERSION):
            raise ValueError("Archivo de políticas no compatible")
        raw_rules = doc.get("rules")
        if not isinstance(raw_rules, list):
            raise ValueError("Lista de políticas no válida")

        old_format = doc["schema_version"] == 1
        names: dict[str, AppPolicy] = {}
        for item in raw_rules:
            if not isinstance(item, dict):
                raise ValueError("Política de aplicación no válida")
            raw = item.get("executable")
            if not isinstance(raw, str):
                raise ValueError("Nombre/ruta de política no válido")
            name = app_name_from_path(raw) if old_format else normalize_app_name(raw)
            policy = AppPolicy(name, item.get("mode")).validated()
            previous = names.get(name)
            if previous is not None and (not old_format or previous.mode != policy.mode):
                raise ValueError(
                    f"Conflicto de políticas para {name}: varias rutas anteriores "
                    "con acciones diferentes o entradas duplicadas. Resuélvelo "
                    "en una copia de seguridad antes de actualizar las reglas."
                )
            names[name] = policy
        return list(names.values())

    def save(self, rules: list[AppPolicy]):
        validated = [r.validated() for r in rules]
        names = [r.executable for r in validated]
        if len(names) != len(set(names)):
            raise ValueError("Hay nombres de aplicaciones duplicados")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema_version": SCHEMA_VERSION, "rules": [asdict(r) for r in validated]}
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
        rules = [r for r in self.load() if r.executable != rule.executable]
        rules.append(rule)
        self.save(rules)

    def delete(self, executable: str):
        name = normalize_app_name(executable)
        self.save([r for r in self.load() if r.executable != name])
