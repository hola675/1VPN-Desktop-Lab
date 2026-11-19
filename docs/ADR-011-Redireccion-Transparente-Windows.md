# ADR-011: Redirección transparente por aplicación en Windows

**Fecha:** 2026-11-13  
**Estado:** propuesta técnica; investigación de fuentes; no implementado ni validado sobre Windows.  
**Prioridad:** mantener Windows/Wintun intactos durante la exploración.

## Objetivo

Convertir 1VPN Desktop Lab de `proxy HTTP local configurado por aplicación` a un sistema opcional estilo **Proxifier**: seleccionar ejecutables y decidir **DIRECTO**, **PROXY** o **BLOQUEAR** sin exigir que cada aplicación acepte configuración explícita de proxy. Mantener un modo sin interceptación ni controladores.

## Investigación de repositorios

- [rookmoot/proxifier](https://github.com/rookmoot/proxifier) — Go, BSD-3-Clause; rotación de proxies para crawling y scraping. **No** intercepta procesos Windows. Último push comprobado 2018-03-16. No adoptarlo como motor de redirección.
- [wiresock/proxifyre](https://github.com/wiresock/proxifyre) — C++/C# y Windows Packet Filter/NDISAPI, AGPL-3.0. Intercepta TCP y UDP por ejecutable, motor + servicio + GUI; acepta **SOCKS5**, no el proxy **HTTP CONNECT** ofrecido por nuestro prototipo. **Principal referencia técnica**, su instalación nativa requerirá elevación, controlador compatible y revisión de licencia.
- [Microsoft WFP](https://learn.microsoft.com/en-us/windows-hardware/drivers/network/using-bind-or-connect-redirection) — vía oficial documentada de redirección ALE de conexiones. Una regla habitual de Windows Defender Firewall sirve para *permitir o bloquear*, pero **no sustituye** un motor de redirección.

## Arquitectura candidata

```text
Aplicación seleccionada (ejemplo: firefox.exe)
    |
    +-- DIRECTO --------------------------> Stack de Windows normal
    +-- BLOQUEAR -------------------------> Control de firewall (con consentimiento)
    +-- PROXY (experimental):
            |
            v
      Captura por proceso (ProxiFyre / controlador NDISAPI opcional)
            |
            v
      127.0.0.1:1080  SOCKS5 local (puente TCP; pendiente)
            |
            v
      127.0.0.1:8899  Proxy HTTP CONNECT local (laboratorio v0.2)
            |
            v
      Proxy remoto HTTPS con validación TLS
            |
            v
          Internet
```

**Incompatibilidad actual:** ProxiFyre consume SOCKS5 y nuestro listener consume HTTP. No se puede apuntar directamente `socks5ProxyEndpoint` al puerto `8899`; hay que construir un puente SOCKS5 CONNECT TCP o elegir otro motor.

### Alcance de fase 1

1. Preservar el modo manual `127.0.0.1:8899`, sin activar WinINET ni cambios de rutas, Wintun o DNS.
2. Implementar puente SOCKS5 en `127.0.0.1:1080`, **solo TCP CONNECT**; rechazo explícito a UDP ASSOCIATE/BIND.
3. Añadir configuración `PROXY|DIRECTO|BLOQUEAR` en formato JSON y simulador de políticas sin tocar filtros del sistema.
4. Validar el puente con test de bucle local y TLS; sin servidores externos.
5. En una VM Windows controlada, instalar opcionalmente los requisitos oficiales de ProxiFyre, configurar una **sola** aplicación de ensayo, excluir el proceso del motor 1VPN y el proceso del túnel/VPN previo, y validar con tráfico real.
6. Sólo entonces considerar reglas reversibles de Firewall/WFP por aplicación, con rollback y registro auditable.

### Limitaciones de seguridad

- **UDP:** el proxy HTTPS CONNECT de esta app no transporta datagramas arbitrarios. ProxiFyre soporta UDP con upstream SOCKS5 compatible, pero un puente TCP no lo habilita. Decidir explícitamente bloqueo o salida directa y comprobarlo; no prometer que UDP/QUIC está protegido.
- **DNS:** comprobar que las peticiones resuelven al otro lado del proxy cuando se usa un nombre de dominio; evaluar fugas de consultas DNS y WebRTC por separado.
- **Wintun:** no hay garantía de ausencia de conflictos si instalamos NDISAPI/WFP. En pruebas se deben cubrir Wintun apagado/encendido, reconfiguración, reconexión y recuperación tras caída.
- **Recursión:** excluir del proxificador el servicio de salida de 1VPN y el portador del túnel VPN preexistente; el filtrado recursivo puede causar un bloqueo.
- **Kill switch:** una regla genérica de bloqueo por ejecutable puede impedir también la conexión redirigida; diseñar un mecanismo específico con verificación de prioridad y rollback antes de publicitar *fail closed*.
- **Licencias:** `rookmoot/proxifier` BSD-3-Clause y `wiresock/proxifyre` AGPL-3.0; copiar e integrar código exige mantener obligaciones de licencia. Las dependencias del controlador NDISAPI tienen sus propias condiciones.
- **Privilegios:** no instalar controladores ni cambiar firewall sin aprobación expresa, respaldo y capacidad de deshacer.
- **Credenciales:** nunca comprometer usuarios/contraseñas o tokens del proveedor en git.

## Criterios mínimos de aceptación

- Ningún cambio WinINET/WinHTTP, Wintun o rutas por defecto en modo manual.
- TCP de un ejecutable seleccionado sale por proxy remoto (verificación de IP); ejecutable excluido conserva ruta original.
- Tráfico UDP no se atribuye a protección que no existe.
- Sin bucles de conexión al proxy local y sin abrir puertos en interfaces de LAN.
- Apagado, fallos y reinicios no dejan reglas huérfanas; pruebas con Wintun activo y desactivado.

## Referencias

- https://github.com/wiresock/proxifyre/blob/main/README.md
- https://github.com/wiresock/proxifyre/blob/main/docs/configuration.md
- https://github.com/rookmoot/proxifier
- https://learn.microsoft.com/en-us/windows-hardware/drivers/network/using-bind-or-connect-redirection

## Estado de implementación v0.4.2-beta — 2026-11-19

Se implementó una primera integración **por aplicación EXE** en desktop_prototype/running_apps.py, proxifyre_adapter.py y control_panel.py. La UI enumera procesos en ejecución; se guardan políticas por ruta completa, exporta configuración ProxiFyre para PROXY (TCP/IPv4) y exclusiones DIRECTO. BLOQUEAR usa el Windows Firewall preexistente mediante consentimiento. No hay driver incluido ni instalación automática: redirección transparente efectiva requiere ProxiFyre + WinpkFilter activos por separado. Requiere IP HTTPS verificada antes de generar perfil.

Ver el procedimiento detallado y limitaciones en docs/PROXIFYRE-POR-EXE-V042.md. La decisión original de preservar Windows/Wintun y evitar cambios ocultos permanece.

**Compatibilidad con Proxifier:** no activar simultáneamente el controlador de ProxiFyre y un proxificador de terceros sin pruebas aisladas. El laboratorio inicial debe usar solo un motor de captura activo, con reversión posible.

## 2026-11-19: corrección de criterio de identidad v0.4.3

Decisión explícita del usuario: las reglas deben coincidir por el **nombre del EXE** (p. ej. chrome.exe), no por su ubicación o ruta; igual que el campo Applications de Proxifier. Los perfiles ProxiFyre usan nombres; DIRECTO usa exclusiones por nombre. El bloqueo Windows Firewall no admite coincidencia global por basename mediante -Program: se conserva internamente una regla por ruta detectada y se informa de que las copias nuevas no quedan bloqueadas automáticamente. Schema v2 de política, con importación v1 segura y detección de conflictos. Consultar [guía v0.4.3](POLITICAS-POR-NOMBRE-EXE-V043.md).
