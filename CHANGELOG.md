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
