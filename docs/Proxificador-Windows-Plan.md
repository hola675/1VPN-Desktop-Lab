# 1VPN Desktop Lab — Proxificador transparente Windows (ADR-011)

**Versión:** 0.3.0-alpha | **Fecha:** 2026-11-13 | **Estado:** diseño aprobado para prototipo; sin despliegue de drivers ni firewall.

## Qué repositorio usar

- `rookmoot/proxifier` (BSD-3-Clause): proxy rotator de Go para scraping. No intercepta procesos Windows; solo referencia para selección dinámica de upstreams. Último push consultado: 2018-03-16.
- `wiresock/proxifyre` (AGPL-3.0): proxificador real Windows por proceso, TCP/UDP vía Windows Packet Filter (NDISAPI), servicio y GUI. Referencia de motor de redirección, configuración JSON por ejecutable y exclusiones. Necesita driver/elevación; no se instala automáticamente.
- Microsoft WFP: alternativa futura para redirección ALE con callout, requiere desarrollo/revisión de driver. Windows Defender Firewall permite/bloquea pero NO redirige por sí solo.

## Arquitectura optativa

```
app elegida (ej. curl.exe) [modo PROXY]
       |
       v
ProxiFyre/NDISAPI (driver externo, SOLO con permiso, en VM primero)
       |
       v
127.0.0.1:1080 SOCKS5/TCP  <-- puente nuevo original socks5_bridge.py
       |
       v
127.0.0.1:8899 HTTP CONNECT <-- app 1VPN Desktop Lab v0.2
       |
       v
Proxy HTTPS remoto TLS (host, puerto y credenciales autorizadas)
       |
       v
Internet
```

`DIRECTO` no se intercepta; `BLOQUEAR` requiere una política apropiada de Windows Firewall/WFP que aún NO está implementada. Ni este puente ni el firewall por sí solos capturan procesos Windows.

## Qué está implementado

- `desktop_prototype/socks5_bridge.py`: listener SOCKS5 en loopback, protocolo RFC 1928: NO AUTH (solo localhost), CONNECT TCP con nombres de dominio, IPv4 e IPv6 destino, traducción a HTTP CONNECT, respuestas de error explícitas y cierre reversible.
- **No UDP/BIND ni autenticación SOCKS local**; esto es deliberado: el upstream HTTP CONNECT actual no encapsula UDP.
- Cinco pruebas locales nuevas para handshake, TCP, rechazo de UDP, error 407, y loopback; la prueba TLS original del proxy HTTP se mantiene.

## Secuencia de laboratorio Windows SIN instalar controlador

1. Abrir el cliente de v0.2 y poner puerto local fijo `8899` sin tocar WinINET.
2. Comprobar salida en UI. Este paso distingue socket local levantado de conexión real hacia el servidor remoto.
3. En otra PowerShell: `py -3 .\desktop_prototype\socks5_bridge.py --http-port 8899 --port 1080`.
4. Comprobar SOLO el SOCKS5 mediante `curl.exe --socks5-hostname 127.0.0.1:1080 https://api.ipify.org` (requiere que el upstream funcione y que se tenga acceso autorizado).
5. Inspeccionar que ambos puertos escuchan únicamente en `127.0.0.1`, y no en `0.0.0.0`.
6. Para terminar, Ctrl+C al puente y luego detener el cliente HTTP.

## ProxiFyre solo tras test del puente

- Usar su interfaz propia en una máquina Windows de pruebas, con driver oficial verificado, comprobando hashes y licencia AGPL-3.0.
- Como caso mínimo seleccionar **solo** `curl.exe` y `socks5ProxyEndpoint = 127.0.0.1:1080`, `supportedProtocols = ["TCP"]`, `supportedAddressFamilies = ["IPv4"]`.
- Excluir el ejecutable de 1VPN Desktop Lab, el de ProxiFyre y los procesos portadores de otros túneles/VPN que puedan causar bucles. No usar catch-all hasta completar QA.
- Un proceso capturado que utilice UDP/QUIC podría fallar o escapar de esta ruta. **No prometer kill switch** ni protección DNS/UDP sin pruebas dedicadas.
- Windows Packet Filter es independiente de Wintun pero ambos operan sobre el stack de red; la convivencia NO está garantizada hasta probar con Wintun activo, inactivo, al reconectar, al detener el proxy y tras reinicios.
- Revisar con especial atención el conflicto por drivers/filtros, fallo abierto/cerrado, DNS/WebRTC, recursión y tráfico del motor proxy.

## No automatizar aún

No instalar NDISAPI, ProxiFyre, servicios ni reglas Firewall en esta fase. No grabar credenciales en un repositorio. Las reglas futuras deberán ser reversibles, aplicadas bajo consentimiento, con backups y lista de exclusiones. Si el puente falla, no suponer que el tráfico se bloquea: comprobar el comportamiento real de ProxiFyre y Windows.

## Referencias comprobadas

- https://github.com/rookmoot/proxifier
- https://github.com/wiresock/proxifyre
- https://github.com/wiresock/proxifyre/blob/main/docs/configuration.md
- https://learn.microsoft.com/en-us/windows-hardware/drivers/network/using-bind-or-connect-redirection
