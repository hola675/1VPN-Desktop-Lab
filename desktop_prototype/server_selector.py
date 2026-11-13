"""Selector de upstreams con pruebas reales TLS+CONNECT y fallback TCP.

Las mediciones no usan ping ICMP ni rutas directas: cada prueba abre TLS al
proxy remoto y exige HTTP 200 de CONNECT. No guarda credenciales en disco.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import socket
import ssl
import threading
import time
from typing import Callable

from proxycore import Upstream, _inject_proxy_auth, _recv_header
from server_catalog import ServerEndpoint, snapshot_catalogue

PROBE_AUTHORITY = "api.ipify.org:443"
DEFAULT_TIMEOUT = 4.0
COOLDOWN_SECONDS = 45.0
PREFERENCE_MARGIN_MS = 35.0
MAX_PROBES = 18
MAX_CONNECT_ATTEMPTS = 4


@dataclass(frozen=True)
class ProbeResult:
    endpoint: ServerEndpoint
    ok: bool
    rtt_ms: float | None = None
    reason: str = ""


def probe_endpoint(endpoint: ServerEndpoint, username: str = "", password: str = "", timeout: float = DEFAULT_TIMEOUT) -> ProbeResult:
    """Mide conexión TCP+TLS+CONNECT desde este PC. No crea tráfico directo al destino."""
    start = time.perf_counter()
    try:
        upstream = Upstream(endpoint.hostname, endpoint.port, username, password).validated()
        with socket.create_connection((upstream.host, upstream.port), timeout=timeout) as raw:
            context = ssl.create_default_context()
            with context.wrap_socket(raw, server_hostname=upstream.host) as remote:
                remote.settimeout(timeout)
                header = f"CONNECT {PROBE_AUTHORITY} HTTP/1.1\r\nHost: {PROBE_AUTHORITY}\r\n\r\n".encode("ascii")
                remote.sendall(_inject_proxy_auth(header, upstream))
                response, _ = _recv_header(remote)
                words = response.split(b"\r\n", 1)[0].split(b" ", 2)
                if len(words) < 2 or words[1] != b"200":
                    status = words[1].decode("ascii", "replace") if len(words) > 1 else "?"
                    return ProbeResult(endpoint, False, reason=f"HTTP {status}")
                return ProbeResult(endpoint, True, round((time.perf_counter() - start) * 1000, 1))
    except (OSError, ssl.SSLError, TimeoutError, ValueError) as exc:
        # Sólo se registra el tipo, nunca mensajes que contengan credenciales o URLs.
        return ProbeResult(endpoint, False, reason=type(exc).__name__)


class AutoSelector:
    """Preferencia inicial Singapur; mejor RTT gana salvo diferencia <= 35 ms.

    Un fallo de establecimiento pone el endpoint en enfriamiento y cambia
    inmediatamente el candidato preferido; nunca pasa a conexión directa.
    """

    def __init__(self, endpoints: tuple[ServerEndpoint, ...] | None = None,
                 username: str = "", password: str = "", region: str = "auto",
                 preferred: str = "sgp", probe: Callable[..., ProbeResult] = probe_endpoint):
        if region not in ("auto", "sgp", "ams", "lax"):
            raise ValueError("Región desconocida")
        self._lock = threading.RLock()
        self._endpoints = tuple(endpoints if endpoints is not None else snapshot_catalogue())
        if not self._endpoints:
            raise ValueError("Catálogo vacío")
        self.username, self.password = username, password
        self.region, self.preferred = region, preferred
        self._probe = probe
        self._results: dict[ServerEndpoint, ProbeResult] = {}
        self._disabled_until: dict[ServerEndpoint, float] = {}
        self._selected: ServerEndpoint | None = None
        self._scanning = False
        self._last_scan = 0.0

    def set_catalogue(self, endpoints: tuple[ServerEndpoint, ...]) -> None:
        if not endpoints:
            raise ValueError("No se puede instalar un catálogo vacío")
        with self._lock:
            self._endpoints = tuple(endpoints)
            self._results = {k: v for k, v in self._results.items() if k in endpoints}
            self._disabled_until = {k: v for k, v in self._disabled_until.items() if k in endpoints}
            self._selected = None

    def _eligible(self) -> tuple[ServerEndpoint, ...]:
        return tuple(e for e in self._endpoints if self.region == "auto" or e.region == self.region)

    def _ordered_locked(self) -> list[ServerEndpoint]:
        now = time.monotonic()
        eligible = list(self._eligible())
        healthy = [e for e in eligible if self._disabled_until.get(e, 0) <= now]
        # Si todo ha fallado, vuelve a intentar la lista sin derivar tráfico directamente.
        if not healthy:
            healthy = eligible
        measured = sorted((e for e in healthy if self._results.get(e) and self._results[e].ok),
                          key=lambda e: self._results[e].rtt_ms or float("inf"))
        if self.region == "auto" and measured:
            fastest = self._results[measured[0]].rtt_ms or 0
            preferred = [e for e in measured if e.region == self.preferred and
                         (self._results[e].rtt_ms or 0) <= fastest + PREFERENCE_MARGIN_MS]
            if preferred:
                winner = preferred[0]
                measured.remove(winner)
                measured.insert(0, winner)
        elif not measured:
            healthy.sort(key=lambda e: (e.region != self.preferred, e.hostname))
        remainder = sorted((e for e in healthy if e not in measured),
                           key=lambda e: (e.region != self.preferred, e.hostname))
        return measured + remainder

    def candidates(self) -> tuple[Upstream, ...]:
        with self._lock:
            ordered = self._ordered_locked()
            self._selected = ordered[0] if ordered else None
            # Antes de la primera medición real, probar también otra región
            # dentro del límite de 4 intentos: no agotar todos en Singapur.
            if self.region == "auto" and not any(r.ok for r in self._results.values()) and ordered:
                own = [e for e in ordered if e.region == ordered[0].region]
                other = [e for e in ordered if e.region != ordered[0].region]
                ordered = own[:2] + other[:MAX_CONNECT_ATTEMPTS - min(2, len(own))] + own[2:]
            return tuple(Upstream(e.hostname, e.port, self.username, self.password) for e in ordered[:MAX_CONNECT_ATTEMPTS])

    def mark_failure(self, upstream: Upstream, reason: str = "") -> None:
        endpoint = next((e for e in self._endpoints if e.hostname == upstream.host and e.port == upstream.port), None)
        if endpoint is None:
            return
        with self._lock:
            self._disabled_until[endpoint] = time.monotonic() + COOLDOWN_SECONDS
            self._results[endpoint] = ProbeResult(endpoint, False, reason=reason[:35])
            self._selected = None

    def mark_success(self, upstream: Upstream) -> None:
        endpoint = next((e for e in self._endpoints if e.hostname == upstream.host and e.port == upstream.port), None)
        if endpoint is None:
            return
        with self._lock:
            self._disabled_until.pop(endpoint, None)
            self._selected = endpoint

    def scan(self, workers: int = 6, timeout: float = DEFAULT_TIMEOUT) -> list[ProbeResult]:
        with self._lock:
            if self._scanning:
                return list(self._results.values())
            self._scanning = True
            endpoints = self._eligible()[:MAX_PROBES]
        results: list[ProbeResult] = []
        try:
            with ThreadPoolExecutor(max_workers=min(max(workers, 1), 8), thread_name_prefix="proxy-probe") as pool:
                futures = {pool.submit(self._probe, e, self.username, self.password, timeout): e for e in endpoints}
                for future in as_completed(futures):
                    endpoint = futures[future]
                    try:
                        results.append(future.result())
                    except Exception as exc:
                        results.append(ProbeResult(endpoint, False, reason=type(exc).__name__))
            with self._lock:
                for result in results:
                    self._results[result.endpoint] = result
                    if result.ok:
                        self._disabled_until.pop(result.endpoint, None)
                    else:
                        self._disabled_until[result.endpoint] = time.monotonic() + COOLDOWN_SECONDS
                self._last_scan = time.monotonic()
                self._selected = None
            return results
        finally:
            with self._lock:
                self._scanning = False

    def summary(self) -> dict[str, object]:
        with self._lock:
            ordered = self._ordered_locked()
            active = self._selected or (ordered[0] if ordered else None)
            best = self._results.get(active) if active else None
            return {"host": active.hostname if active else None,
                    "region": active.region if active else None,
                    "rtt_ms": best.rtt_ms if best and best.ok else None,
                    "ok": sum(1 for v in self._results.values() if v.ok),
                    "tested": len(self._results),
                    "last_scan": self._last_scan}
