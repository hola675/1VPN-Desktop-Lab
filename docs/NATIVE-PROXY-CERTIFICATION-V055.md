# v0.5.5 alpha — Certificación de PROXY WFP nativo

**Fecha:** 2026-11-19  
**Estado:** implementado en software; requiere paquete kernel firmado, driver RUNNING y prueba real en Windows de laboratorio.

## Objetivo

Demostrar que OneTunnel redirige tráfico de una aplicación por debajo de la capa de configuración proxy de la aplicación, sin ProxiFyre, sin variables HTTP_PROXY/HTTPS_PROXY y sin argumentos --proxy.

La prueba usa un ejecutable propio:

- native/wfp/egress_probe.cpp
- artefacto: onetunnel-egress-probe.exe

El probe usa WinHTTP con WINHTTP_ACCESS_TYPE_NO_PROXY y una petición HTTPS a api.ipify.org. La conexión solo puede coincidir con la IP Premium esperada si el callout WFP + relay + SOCKS5 + upstream Premium funcionan correctamente.

## Condiciones previas

1. OneTunnel Premium conectado.
2. COMPROBAR SALIDA debe haber obtenido una IP pública válida mediante el proxy Premium integrado.
3. Paquete kernel firmado por Microsoft verificado por OneTunnel.
4. Driver OneTunnelWfpRedirect instalado y en estado RUNNING.
5. Ninguna otra sesión PROXY WFP de OneTunnel activa.
6. Ejecutar OneTunnel con permisos suficientes para crear los filtros dinámicos BFE de la sesión.
7. Proxifier/ProxiFyre y otros motores de redirección de prueba deben estar detenidos durante la primera certificación.

No se desactiva Secure Boot, integridad de código, antivirus ni otras protecciones.

## Secuencia desde la interfaz

1. Inicia OneTunnel Premium.
2. Pulsa COMPROBAR SALIDA y conserva la IP mostrada.
3. Abre APLICACIONES / FIREWALL.
4. Verifica/instala/inicia el paquete WFP firmado si procede.
5. Confirma ESTADO MOTOR y que el callout está RUNNING.
6. Asegúrate de que PROXY WFP normal esté detenido.
7. Pulsa CERTIFICAR PROXY (LAB).
8. OneTunnel pedirá confirmación explícita e indicará la IP Premium esperada.
9. Solo después de confirmar:
   - crea una sesión PROXY WFP dinámica dirigida únicamente a onetunnel-egress-probe.exe;
   - inicia el relay transparente;
   - el probe hace una petición HTTPS con WinHTTP NO_PROXY;
   - OneTunnel compara la IP recibida con la IP Premium previamente verificada;
   - retira siempre la sesión/filtros temporales al finalizar.
10. Si las IP coinciden, la interfaz muestra CERTIFICACIÓN PASS.

## Qué demuestra un PASS

Un PASS demuestra para ese ensayo:

- el callout WFP firmado está registrado/cargado;
- BFE aceptó los filtros dinámicos;
- la conexión TCP HTTPS del probe fue seleccionada por aplicación;
- la redirección local conservó el destino original;
- el relay recibió contexto WFP válido;
- el relay negoció SOCKS5 CONNECT con 127.0.0.1;
- el motor Premium alcanzó Internet;
- la IP observada coincide con la salida Premium verificada;
- la aplicación de prueba no usó una configuración proxy explícita.

## Qué NO demuestra

No certifica todavía:

- UDP;
- QUIC/HTTP3;
- consultas DNS clásicas;
- DoH de aplicaciones;
- WebRTC;
- tráfico IPv6 completo de todos los procesos;
- servicios Windows sin ruta de proceso visible;
- procesos que cambian de ejecutable/ubicación después de aplicar reglas;
- kill switch global;
- recuperación ante todas las caídas posibles;
- convivencia con EDR/antivirus/VPN/callouts WFP de terceros.

## Fallos esperados y comportamiento

- Driver no RUNNING: no se inicia la prueba.
- IP Premium no verificada: no se inicia la prueba.
- Sesión PROXY normal activa: la certificación se niega a interrumpirla.
- Probe ausente: no se añaden filtros.
- BFE/control plane rechaza la sesión: no hay fallback a DIRECTO.
- Petición HTTPS falla: resultado FAIL y filtros retirados.
- IP diferente de la esperada: resultado FAIL; no se considera PROXY certificado.
- Excepción inesperada después de activar filtros: finally detiene NativeProxySession.

## Gate antes de producción

Tras PASS del probe, probar una aplicación real seleccionada por el usuario, por ejemplo chrome.exe:

1. PROXY WFP activo para esa app.
2. Sin variables de entorno proxy.
3. Sin proxy del sistema configurado para forzar la app.
4. Verificar IP desde la aplicación.
5. Cerrar relay/control y verificar fail-closed de los flujos seleccionados.
6. Repetir con DIRECTO y BLOQUEAR.
7. Repetir tras reinicio.
8. Auditar DNS, UDP, IPv6 y QUIC.

Solo después de esos pasos se puede avanzar hacia una política de protección completa.
