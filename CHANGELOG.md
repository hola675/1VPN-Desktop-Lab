# Historial de cambios — 1VPN Desktop Lab

## v0.4.0-dev — 2026-11-13

- Motor HTTP CONNECT + SOCKS5 TCP combinado en un único proceso, arranque transaccional y puertos configurables.
- Nueva GUI integrada para políticas por ejecutable, bloqueo saliente específico y recuperación de reglas gestionadas.
- Reglas Firewall por identificador determinista y grupo propio, sin afectar configuración global, previa confirmación del usuario.
- Preferencias persistidas sin credenciales; modo transparente marcado como pendiente de driver.
- Pruebas: 27 PASS local; CI Windows para verificar empaquetado EXE no firmado.
- Documentado diseño futuro de captura WFP y obligaciones de licencias.

## v0.3.0-alpha — 2026-11-13

- Adaptador SOCKS5 CONNECT TCP a proxy HTTP local, separadamente ejecutable.
- Pruebas de negociación, destinos IPv4/DNS y rechazo UDP/BIND.

## v0.2.0 — 2026-11-13

- Puerto HTTP local configurable, verificación independiente de IP pública y TLS.
- Sin cambios del proxy global de Windows.

## v0.1.0 — 2026-11-13

- Investigación estática de extensión oficial 1VPN y primer proxy TLS local en Windows.
