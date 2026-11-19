"""CI gate: the locally generated Inf2Cat package must remain untrusted."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop_prototype"))

from driver_lifecycle import DriverLifecycleError, verify_package

if len(sys.argv) != 2:
    raise SystemExit("usage: assert_unsigned_driver_rejected.py <package-dir>")

package = Path(sys.argv[1]).resolve()
try:
    verify_package(package)
except DriverLifecycleError as error:
    print(f"PASS: Windows rechazo el paquete unsigned: {type(error).__name__}")
    raise SystemExit(0)
except Exception as error:
    raise SystemExit(
        f"ERROR: fallo inesperado verificando paquete unsigned: {type(error).__name__}"
    ) from error

raise SystemExit("ERROR: el paquete UNSIGNED-CI fue aceptado como confiable")
