# Ingeniería inversa: autenticación de 1VPN y HTTP 403

**Fecha:** 2026-11-14. **Ámbito:** extensión pública, app Android oficial, cliente Python de 1VPN Desktop Lab. No es una especificación contractual de la API propietaria.

## Resumen del diagnóstico observado

```text
POST /api/login/?type=xray
Campos JSON: email, password
1vpn.org -> HTTP 403
Esquema de error: detail:str
Sin código numérico de API
```

**No es un fallo de sintaxis JSON confirmado.** El servidor devolvió un objeto de error con un campo `detail` de tipo texto. No se conoce el contenido del campo por el registro sanitizado. En la UI de la app Android pública, un **403 se trata como límite temporal de solicitudes**; esa interpretación es evidencia del diseño del cliente, no demostración de la causa del 403 concreto.

## 1. Flujo de navegador

Código: [extensión](https://github.com/1vpn/browser-extension) `src/pages/popup/OptionsPage.jsx`, `src/pages/background/index.js`, `src/utils/userData.js`, `tests/helpers.js`.

- El botón de entrar **abre** `https://<dominio-activo>/login/`. No realiza el POST de correo/contraseña desde la extensión.
- El test de navegador rellena un formulario web con `input[name="username"]` y `input[name="password"]` y espera navegar a `/account/`. **No extrapolar** esos nombres de formulario al JSON de la API Xray.
- La extensión obtiene datos por `POST /api/get_user_data_web/` enviando `{}` y opcionalmente la cabecera `Authorization: Token <sessionAuthToken>`. Guarda el estado de cuenta en `chrome.storage.local`.
- Para autenticación del proxy de navegador Premium utiliza `username` + `sessionAuthToken`; Free usa credenciales del proxy independientes de la cuenta. No son los campos del login.
- La versión de extensión v4.1.1 (2026-04-21) introdujo explícitamente «Switch to website-based login». [Notas oficiales](https://github.com/1vpn/browser-extension/releases/tag/v4.1.1).

La transferencia exacta de sesión desde la página web a la extensión no se puede inferir sin revisar el backend web o una sesión de pruebas controlada. No copiar cookies ni extraer tokens del navegador para emular un login.

## 2. Flujo Android / Xray

Código: [API](https://github.com/1vpn/app/blob/main/lib/onevpn/data/account_api.dart),
[transporte](https://github.com/1vpn/app/blob/main/lib/onevpn/net/api_transport.dart),
[interfaz](https://github.com/1vpn/app/blob/main/lib/onevpn/account/sign_in_page.dart),
[tests de contrato](https://github.com/1vpn/app/blob/main/test/onevpn/data/account_api_test.dart).

- `POST https://1vpn.org/api/login/?type=xray`, `Content-Type: application/json`, `Client-Type: app`, **sin Authorization**.
- JSON: `{"email":"<correo>","password":"<clave>"}` y `"token":"<código>"` opcional tras solicitar 2FA.
- Respuesta correcta: `sessionAuthToken`, `username`, `email`, `isPremium`, `locations`; posiblemente credenciales Xray `uuid`, `publicKey`, `shortId`.
- Si el backend devuelve `code=1001`, la UI Android muestra la solicitud de 2FA. Un segundo `1001` puede significar código incorrecto.
- Rechazo de API reconocido: status 4xx + objeto JSON que tenga `code` entero, `error` texto o `detail` texto. A diferencia de HTML/CAPTCHA intermedio, ese rechazo termina el recorrido de dominios sin retransmitir la contraseña.
- **La UI Android clasifica HTTP 403 como «rate limited»** y la prueba `sign_in_page_test.dart` representa un rechazo `403` con `Request was throttled.`. Es una respuesta *simulada en una prueba*, no una captura del servidor real.
- Dominios de respaldo: `1vpn.org`, `1vpn.co`, `onevpn.com`, `cloudlogcdn.com`. Los alternativos se usan para bloqueos de red/HTML, **no para eludir un rechazo auténtico de la API**.

## 3. Comparación y corrección Windows

El cliente Python ya envía el contrato Android/Xray correcto. El campo JSON **debe seguir llamándose `email`**, no `username`, a pesar de lo que use el formulario web.

El `detail:str` real queda oculto correctamente: revelar su texto completo podría divulgar datos privados. Se incorpora un clasificador local por palabras asociadas al control de frecuencia («throttled», «rate limit», «too many requests»). El clasificador solo emite un enum `rate_limit_indicated` o `unknown`; **nunca** envía el mensaje literal al diagnóstico.

- Si hay indicio textual de límite, informar `rate_limited`; no repetir ni hacer failover a otra IP o dominio para saltar controles.
- Si `detail` no coincide, mantener `forbidden`, explicar que la causa no está determinada. Un `403` por sí solo no es prueba de contraseña inválida.
- Si hay `code=1001`, mantener el flujo 2FA.
- La clasificación no resuelve restricciones de cuenta, Cloudflare/WAF, IP ni la lógica interna del backend. No falsificar user agents, cookies o cabeceras para evadir políticas.

## Verificación segura que queda por hacer

1. Esperar a que termine cualquier limitación del servicio; no probar repetidamente en intervalos breves.
2. Comprobar **manualmente** que la cuenta accede al sitio oficial `https://1vpn.org/login/` desde el navegador, sin capturar cookies.
3. Cuando proceda y de forma voluntaria, comparar un intento en Android oficial para distinguir problema de cuenta, bloqueo de red o diferencia entre clientes; no compartir credenciales.
4. En Windows actualizado realizar **un único** intento legítimo, copiar **solo** el diagnóstico sanitizado con `rejection_hint`, código API si existe y estado HTTP. No enviar el JSON completo ni `detail` literal.
5. Si persiste un rechazo genuino, consultar soporte oficial de 1VPN; el backend que aplica el límite es la fuente autoritativa de la duración y condición de desbloqueo.

Este cambio de diagnóstico no activa funciones Premium, no cambia servidores, no modifica el proxy ni las reglas de red y no captura credenciales de navegador.
