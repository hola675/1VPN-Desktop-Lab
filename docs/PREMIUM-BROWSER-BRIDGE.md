# Integración Premium con navegador (prototipo con consentimiento) — 2026-11-18

## Qué implementa

Este proyecto sigue siendo 1VPN Desktop Lab (Python/Tkinter + proxy HTTPS),
NO la aplicación Tauri/Reality. No intercepta todo el tráfico Windows.

La extensión oficial de 1VPN inicia sesión en https://1vpn.org/login/ y
consulta datos mediante POST /api/get_user_data_web/. No ofrece una interfaz
pública documentada para que una app de escritorio lea su almacenamiento
privado. Otra extensión tampoco puede leer chrome.storage.local de 1VPN.

Se incluye una extensión opcional, en browser_companion/, que requiere
consentimiento explícito. Solo funciona si la página oficial ya autenticada
permite devolver, en contexto web de primera parte, sessionAuthToken,
username, isPremium y locations. ESTO NO ESTÁ CONFIRMADO EN EL SERVIDOR REAL.
El puente falla sin extraer cookies, tokens de otra extensión, usar DevTools,
falsificar cabeceras, ni sortear respuestas HTTP 403.

## Pasos de prueba en Windows

1. Actualiza tu copia local y ejecuta el EXE nuevo de CI (Python 3.13),
   o arranca desktop_prototype/app.py desde Python.
2. Abre chrome://extensions en Chrome, o edge://extensions en Edge.
   Activa modo desarrollador y Cargar descomprimida desde browser_companion/.
3. Inicia sesión en https://1vpn.org/login/ y navega a
   https://1vpn.org/account/ con ese mismo navegador.
4. En 1VPN Desktop Lab, abre INICIAR SESIÓN 1VPN (EMAIL) y pulsa
   PREMIUM WEB (BETA). El escritorio muestra puerto local aleatorio y
   código de un único uso válido durante 5 minutos.
5. Con la pestaña oficial /account/ activa, pulsa la extensión auxiliar,
   escribe puerto y código y pulsa VINCULAR CON CONSENTIMIENTO.
6. Si la web devuelve los campos necesarios, la sesión pasa a la
   aplicación exclusivamente a través de 127.0.0.1. El escritorio
   indicará datos Premium recibidos, pero conexión sin verificar.
7. Selecciona Automático o un servidor disponible, pulsa INICIAR PROXY
   y después COMPROBAR SALIDA. Requiere salida HTTPS real por el proxy.
8. Pulsa DETENER PROXY y luego CERRAR SESIÓN cuando termines.

Si ves «la página oficial no entregó una sesión Premium transferible»,
no tienes por qué cambiar tu contraseña: el endpoint web podría no permitir
emitir una sesión desde la página. Hace falta un flujo autorizado documentado
de 1VPN. No existe fallback para leer cookies o almacenamiento ajeno.

## Seguridad

- premium_bridge.py: 127.0.0.1 únicamente, puerto efímero, código secreto
  aleatorio de 24 bytes, caducidad de 300 s, uso único.
- Origen permitido: chrome-extension:// seguido de un ID Chrome válido.
  Comprueba host local, Content-Type y tamaño máximo de 32 KiB.
- Nunca persiste tokens Premium; tampoco los copia a los campos GUI ni logs.
- No usa APIs de cookies ni permisos de almacenamiento de otras extensiones.
- El puente solo valida el formato: la conexión solo estará comprobada
  después de TLS + HTTP CONNECT y la prueba HTTPS de salida.
- Únicamente admite destinos DNS en puerto 443 procedentes de los datos
  recibidos; mientras Premium está activo, no reemplaza la lista por
  el catálogo público Free.
- La sesión Android/Xray no sirve como contraseña del proxy HTTPS.

## Pruebas y límites

Pruebas unitarias simuladas cubren consentimiento, origen, entrega única,
código inválido, token/plan/servidores incompatibles y secreto oculto.
GitHub Actions verifica sintaxis JS, genera EXE con Python 3.13, hace
un smoke test de arranque y publica ZIP de extensión complementaria.

Quedan pendientes pruebas en tu navegador real: cookie SameSite, permisos
del endpoint web, estructura de datos, certificación del túnel Premium e
integración completa con el inicio de sesión oficial.
