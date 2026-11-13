# 1VPN Desktop Lab — Arquitectura del motor de redirección nativo

**Revisión:** 2026-11-13 · **Estado:** especificación, NO implementado.

## Producto objetivo

Una sola aplicación Windows, sin exigir que el usuario ejecute Proxifier o ProxiFyre por separado. Debe integrar una interfaz, un servicio nativo con privilegios mínimos, un proxy local TCP y un motor de reglas por proceso: **PROXY**, **DIRECTO**, **BLOQUEAR**. La compatibilidad con Wintun existente se prueba antes de habilitar cualquier captura.

### Componentes disponibles desde v0.4

1. `network_engine.py` inicia en un proceso los listeners HTTP CONNECT y SOCKS5 TCP (ambos en `127.0.0.1`). Si falla el arranque del segundo, cierra el primero.
2. `proxycore.py` comunica TLS verificado hacia un proxy HTTPS remoto compatible.
3. `traffic_policy.py` administra políticas de ejecutables y persiste sus preferencias sin contraseñas.
4. `firewall_rules.py` crea/retira **solo reglas de bloqueo saliente** por ejecutable en Windows, a solicitud del usuario, mediante cmdlets oficiales. No cambia reglas globales.
5. `control_panel.py` integra selección de procesos, políticas, bloqueo, retirada e inicio opcional con variables de entorno. **Esto último solo afecta apps que respetan esas variables.**
6. `socks5_bridge.py` implementa CONNECT TCP, no BIND ni UDP ASSOCIATE.

### Componentes necesarios para redirección real

```text
Aplicación Windows (sin soporte proxy)
      │
      ▼
Servicio del sistema, motor de políticas y asociación PID/ruta
      │
      ├── DIRECTO ──────► red normal
      ├── BLOQUEAR ─────► WFP/Firewall (regla por aplicación)
      └── PROXY ────────► callout WFP ALE_CONNECT_REDIRECT
                                     │
                                     ▼
                          Proxy nativo local (recupera destino real)
                                     │
                                     ▼
                            SOCKS5 TCP / HTTP CONNECT
                                     │
                                     ▼
                         Proxy HTTPS remoto autenticado
```

La redirección ALE_CONNECT_REDIRECT requiere un **callout driver** y un servicio que obtenga correctamente la conexión original y etiquete los sockets de salida. No basta una API de firewall en espacio de usuario. Para capturar UDP se necesita soporte independiente de datagramas y un protocolo remoto apropiado. En caso de destinos no admitidos se debe decidir explícitamente entre bloquear/directo, sin alegar un *kill switch* que todavía no existe.

## Alternativas evaluadas

| Alternativa | Uso previsto | Coste/limitación |
| --- | --- | --- |
| Microsoft WFP + callout propio | **Objetivo** de motor nativo original con integración de firewall y proceso | Desarrollo WDK/C++, revisión de seguridad, firma del driver, instalador y pruebas de compatibilidad |
| NDISAPI / Windows Packet Filter | Referencia técnica y posible POC si su licencia lo permite | El SDK de usuario no incluye el derecho de redistribuir el driver comercial; no mezclar licencias |
| wiresock/ProxiFyre (AGPL-3.0) | Referencia de reglas y pruebas TCP/UDP; **no copiado ni incluido** | Su motor no es una biblioteca lista para vincular sin trabajo; obligaciones AGPL y driver externo |
| rookmoot/proxifier (BSD-3-Clause) | Selección/rotación de upstreams | No intercepta tráfico de procesos Windows |

## Seguridad, mínimos de aceptación antes de instalar un driver

- Un único paquete Windows firmado con desinstalador y restauración; la instalación de un driver necesita administrador y aprobación explícita.
- No recurrencia: excluir los sockets del propio motor y de otros transportes (`xray.exe`, portador Wintun o VPN anterior), sin capturar la conexión necesaria para transportar el proxy.
- Reglas por ruta completa, no coincidencia aproximada en nombre que pueda afectar otro proceso.
- Recuperar dirección original de cada conexión (IP, puerto, familia) sin fuga por DNS/IPv6.
- Ensayos con Chrome, Telegram, VS Code y apps propias en VM: TCP, UDP, reinicio, suspensión, pérdida de conexión, desconexión y Wintun ya activo.
- Sin filtro global por defecto, con modo diagnóstico y rollback medible.
- Protección frente a fallos abierta/cerrada configurable y descrita, no silenciosa.
- Sin certificados de confianza falsos, sin desactivar TLS, sin credenciales en logs/GitHub.
- Auditoría de las condiciones de redistribución y firma del driver antes de publicar `.exe`.

## Hitos definidos

1. **v0.4**: motor HTTP/SOCKS5 integrado, políticas persistentes, bloqueo nativo por ejecutable y tests. **Implementado en Python**.
2. **v0.5**: servicio Windows separado del UI, IPC autenticado y reversible, supervisión y diagnósticos de permisos. Pendiente.
3. **v0.6**: laboratorio WFP callout `CONNECT_REDIRECT`, una aplicación TCP y recuperación del destino. Pendiente, requiere Windows WDK y firma de desarrollo.
4. **v0.7**: políticas de redirección + reglas de firewall coordinadas, DNS/IPv6 y coexistencia Wintun. Pendiente.
5. **v1.0**: instalador firmado, pruebas de fugas TCP/UDP, fallo seguro y rollback. Pendiente.

### Fuentes oficiales

- Microsoft WFP: https://learn.microsoft.com/en-us/windows-hardware/drivers/network/using-bind-or-connect-redirection
- Microsoft ALE: https://learn.microsoft.com/en-us/windows/win32/fwp/ale-layers
- Windows Packet Filter y licencia: https://www.ntkernel.com/windows-packet-filter/
- ProxiFyre: https://github.com/wiresock/proxifyre
