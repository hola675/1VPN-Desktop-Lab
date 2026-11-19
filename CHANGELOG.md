## v0.5.0-native-alpha — motor WFP propio (2026-11-19)

- Cambio arquitectónico autorizado por el usuario: no depender de ProxiFyre ni de reglas Windows Defender Firewall para funcionalidades nuevas.
- Se añadió helper C++ propio onetunnel-wfp-guard: filtros WFP dinámicos para BLOQUEAR por ruta interna de aplicación con interfaces IPv4+IPv6 ALE_AUTH_CONNECT; cierre del helper revierte el filtro.
- Integración Python: ciclo de vida supervisado, comprobación admin, handshake acotado, reemplazo de sesiones y reversión por fallo; empaquetado en EXE.
- UI: DIRECTO, BLOQUEAR nativo y PROXY pendiente de callout firmado. Los botones ProxiFyre se retiraron; solo queda limpieza de reglas de firewall heredadas como función de migración.
- CI verifica suite Python y compilación nativa Windows SDK/MSVC. No se ejecutan filtros en CI, y el bloqueo real necesita prueba con administrador en Windows.
- **Pendiente para PROXY real:** driver callout ALE_CONNECT_REDIRECT firmado + relay destino-original→SOCKS5 CONNECT, política de DNS/UDP/IPv6 y test de fugas. No hay kill switch.

## v0.4.3 beta — Reglas por nombre de EXE, como Proxifier (2026-11-19)

- Políticas PROXY / DIRECTO / BLOQUEAR identificadas únicamente por basename exacto (chrome.exe), sin exigir rutas ni destino IP; schema de políticas v2.
- Migración segura de antiguas políticas v1 por ruta; conflictos por nombres iguales/modos distintos detienen la migración sin sobrescribir el archivo.
- Tabla de procesos agrupa PID y todas las instalaciones del mismo nombre; el buscador .exe introduce solo el nombre.
- Exportación ProxiFyre con appNames y excludes por nombre, no rutas.
- BLOQUEAR aplica reglas Windows Firewall a las rutas detectadas del nombre con confirmación y administrador; no cubre nuevas rutas automáticamente.
- Pruebas de migración, coincidencia, varios directorios, aplicación y retirada de bloqueos con firewall simulado. ProxiFyre sigue siendo externo.

## v0.4.2 beta — aplicaciones EXE y adaptación ProxiFyre (2026-11-19)

- Descubrimiento de aplicaciones Windows en ejecución mediante API Win32 en solo lectura, con PID, ruta completa y política; actualización en el panel cada 10 segundos.
- Selección por ejecutable de PROXY, DIRECTO o BLOQUEAR. No se usan dominios/IP para elegir políticas.
- Exportador de configuración compatible con ProxiFyre, con PROXY por EXE y exclusiones DIRECTO; validación de puerto SOCKS5 y prohibición de catch-all, procesos críticos y bucles.
- Requiere salida HTTPS realmente verificada antes de generar borrador; no instala NDIS ni modifica servicios automáticamente.
- Firewall saliente bloquea únicamente ejecutables seleccionados tras confirmación y privilegios; reglas reversibles.
- Tests offline; documentación de instalación externa, límites DNS/UDP/IPv6 y obligaciones AGPL-3.0.
- **Pendiente:** instalar/activar ProxiFyre por separado y certificar redirección real en Windows, sin afirmar kill switch o protección total.

## Premium Browser Bridge — compatibilidad de cuenta localizada (2026-11-18)

- El complemento reconoce las páginas de cuenta oficiales bajo rutas de idioma, incluida /es/account/, sin exigir volver a iniciar sesión.
- Comprobación de origen https://1vpn.org y ruta de cuenta exacta; rechazo de dominios similares y páginas distintas.
- Pruebas automáticas JavaScript añadidas a CI; no se ha modificado el manejo de cookies, contraseñas o tokens.

## Premium Web Beta — Copiado independiente de emparejamiento (2026-11-18)

- Separados **Puerto local** y **Código temporal** en campos seleccionables, con botones individuales **COPIAR PUERTO** y **COPIAR CÓDIGO**.
- Cada acción reemplaza el portapapeles solo con el campo solicitado, con confirmación sin revelar el código en el diagnóstico.
- Añadidas pruebas para copiado exacto e indisponibilidad del portapapeles; sin cambios al protocolo Premium ni a credenciales.

## Premium Browser Bridge — fase beta (2026-11-18)

- Puente local 127.0.0.1 de emparejamiento explícito y temporal, sin lectura de cookies ni tokens de la extensión ajena.
- Extensión auxiliar Chrome MV3 para intentar obtener sesión desde la página oficial autenticada; la compatibilidad real del endpoint está pendiente.
- Proxy HTTPS usa solo credenciales Premium de la sesión web emparejada, nunca tokens Xray, y preserva lista de servidores autorizados.
- Pruebas de puente y verificación de arranque EXE en CI Windows Python 3.13; extensión distribuida como artefacto separado.
- Estado: integración beta no certificada frente a cuenta Premium real; no afirmar conexión hasta comprobar salida HTTPS.

# Historial de cambios — 1VPN Desktop Lab

## v0.4.1c — 2026-11-15

- Confirmado contrato de cuenta Android/Xray: POST HTTPS JSON con `email`, `password` y `token` solo para 2FA; cabecera `Client-Type: app`.
- Para HTTP 403 se registran únicamente tipos de campos de error y código numérico API (si existe); no se muestra el cuerpo JSON literal ni información personal.
- HTTP 403 con rechazo estructurado clasificado como acceso denegado sin afirmar que la contraseña esté mal; 429 detiene el intento incluso con respuesta HTML, sin reenviar credenciales a respaldos; código 1001 solicita 2FA.
- Pruebas de privacidad y clasificación; CI Windows, pruebas y compilación EXE verificadas en el PR #6.
- Guía de coordinación de agentes locales/remotos: `docs/PROTOCOLO-AGENTES-Y-AUTH-403.md`.
- Pendiente diagnóstico real del contenido semántico del rechazo y prueba visual de la interfaz en Windows.

## v0.4.1b — 2026-11-15

- Registro visible por etapas del inicio de sesión de cuenta: host oficial, estado HTTP, categoría de respuesta, tipo de error de transporte y resultado.
- El registro omite correo, contraseña, 2FA, cuerpo de respuesta y texto de excepciones; campo 2FA enmascarado.
- Suite local: 58 pruebas, 2 omitidas; sin autenticación real contra 1VPN.

## v0.4.1a — 2026-11-13

- Formulario de cuenta 1VPN con correo electrónico y contraseña, POST HTTPS JSON al endpoint de inicio de sesión Xray y soporte para 2FA.
- Separación explícita entre credenciales de cuenta y autenticación del proxy HTTPS; no se intenta usar la contraseña de cuenta como contraseña de proxy.
- Respuesta de plan Free/Premium y token en memoria, sin persistir contraseñas ni datos confidenciales.
- Errores de red, credenciales rechazadas y segundo factor diferenciados.
- Pruebas unitarias de credenciales y manejo seguro (56 pruebas locales OK).
- Sin cambio de redirección, Wintun, DNS, rutas o firewall. No se probó un login real.


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

## v0.4.1-dev — 2026-11-13

- Catálogo Free con actualización pública HTTPS, validación de hosts y respaldo estático.
- Selección automática por RTT TLS+CONNECT con preferencia inicial Singapur (+35 ms).
- Fallback de conexiones CONNECT nuevas, máximo cuatro upstreams y enfriamiento de errores.
- Selector de región y botón de medición en la interfaz v0.4.1.
- 43 pruebas locales OK, incluida integración TLS CONNECT con recuperación tras fallo del primer servidor.
- Sin autenticación Premium, servicio Windows ni driver de redirección transparente (pendientes).
