# 1VPN Desktop Lab

**Versión de desarrollo: v0.4.1a (parche de autenticación) · 2026-11-13**  
**Estado:** proxy HTTP local para redirigir las solicitudes de aplicaciones compatibles hacia un **proxy HTTPS remoto autorizado**, sin usar Wintun/TUN ni modificar la configuración global de Windows.

> **Proyecto experimental independiente. No es un cliente oficial de 1VPN y no equivale a una VPN del sistema.** No incorpora servidores, tokens o credenciales del proveedor. El usuario es responsable de usar servidores y credenciales para los que tenga autorización.

## Arquitectura de la versión 0.2

```
Aplicación que soporte proxy HTTP/HTTPS
             |
             | HTTP proxy (CONNECT para sitios HTTPS)
             v
127.0.0.1:8899   <--- solo interfaz loopback; puerto ajustable
             |
             | TLS verificado; Proxy-Authorization si se proporcionó
             v
     Proxy HTTPS remoto autorizado
             |
             +------------------> Internet
```

**No se modifican:** Wintun, TUN/TAP, interfaces de red, tablas de rutas, DNS, firewall, WinINET, WinHTTP, HKCU ni el proxy global de Windows. Solo las aplicaciones configuradas explícitamente para utilizar `http://127.0.0.1:8899` envían tráfico al proxy.

## Inicio en Windows

Requisitos: Python 3 con Tkinter (incluido normalmente en la instalación para Windows). No hay dependencias externas para el prototipo.

```powershell
# Si tienes v0.1 con la casilla WinINET marcada, primero pulsa
# «DETENER Y RESTAURAR» EN LA V0.1. Cierra esa aplicación.

cd .\desktop_prototype
pwsh -NoProfile -ExecutionPolicy Bypass -File .\Iniciar.ps1
```

Rellena servidor, puerto TLS (normalmente `443`) y, si corresponde, credenciales. Define **Puerto LOCAL** en `8899` para un valor estable o en `0` para elegir uno libre. Pulsa `INICIAR PROXY`.

La pantalla indicará **«Escuchando localmente · salida sin verificar»**. Esto prueba únicamente que el puerto se abrió en la máquina. Pulsa **«COMPROBAR SALIDA»**: se abrirá un túnel CONNECT desde el puerto local hasta `api.ipify.org:443`, se verificará el TLS del destino y se leerá la IP pública observada. Esta prueba no realiza fallback a una conexión directa; si el proxy falla, la prueba también falla.

Pulsa **«COPIAR DIRECCIÓN»** para copiar `http://127.0.0.1:8899` (o el puerto elegido) y pegarlo en una aplicación compatible.

### Probarlo desde PowerShell

Con la aplicación ejecutándose y con puerto local 8899:

```powershell
curl.exe --proxy http://127.0.0.1:8899 --max-time 20 'https://api.ipify.org?format=json'
```

La IP recibida **no demuestra por sí sola que la conexión sea anónima**; contrástala con la ubicación del servidor y verifica si corresponde a la salida esperada. Si se recibe HTTP `407`, la autenticación remota ha fallado. Si se recibe `502`, revisa conectividad al remoto, TLS, hostname y puerto. Si se recibe `Connection refused`, comprueba que el listener local está iniciado y el puerto coincide.

### Aplicaciones compatibles

Configura un proxy de tipo **HTTP** (no SOCKS5) con host `127.0.0.1` y el puerto local establecido. Puedes configurar, por ejemplo, un perfil de Firefox desde sus ajustes de red. Los navegadores y procesos que no utilicen un proxy configurado **seguirán conectando directamente**. No se redirige tráfico automáticamente, no se procesan conexiones UDP ni se bloquea el tráfico externo.

### Volver al estado anterior

Pulsa **«DETENER PROXY»**. Esto cierra el servidor local. Desactiva la configuración de proxy en las aplicaciones que configuraste manualmente.

Si al migrar desde v0.1 existe un archivo `%LOCALAPPDATA%\1VPNDesktopLab\proxy_restore.json`, **v0.2 no lo modifica ni restaura automáticamente**: vuelve a v0.1 y pulsa `DETENER Y RESTAURAR`. No elimines manualmente ese archivo antes de restaurar tus preferencias de Windows.

## Pruebas

```powershell
cd .\desktop_prototype
py -3 -m unittest discover -s tests -v
```

La suite cubre validación de entrada, sustitución segura de cabeceras de autenticación, escucha exclusivamente en loopback, selección de puerto, rechazo de métodos no soportados y aislamiento del comprobador de salida. Una prueba de integración utiliza un proxy TLS **simulado localmente**, generado con OpenSSL; se omite si OpenSSL CLI no está instalado.

**Pruebas realizadas el 2026-11-13:** 15/15 OK en el entorno de desarrollo, incluida la integración TLS/CONNECT. **Sin pruebas verificadas todavía contra los servidores públicos de 1VPN ni ejecución de v0.2 en Windows.**

## Origen del estudio y licencias

- Fuente de la extensión: <https://github.com/1vpn/browser-extension>
- Versión oficial analizada: v4.2.1 (2026-11-03)
- Fuente de la aplicación 1VPN/OneXray: <https://github.com/1vpn/app>
- Los repositorios oficiales anteriores anuncian **GPL-3.0**. Si incorporas su código, cumple sus términos y conserva atribuciones. El código de ejemplo de este laboratorio no incluye copias de ese código.
- Descarga estática de archivos de referencia: `scripts/Descargar-1VPN-Oficial.ps1`, sin ejecutar contenido descargado.

## Seguridad y límites

- No exponemos el proxy en la red local: el socket escucha exclusivamente en `127.0.0.1`.
- **Cualquier proceso local del equipo puede conectar al puerto**. No existe autenticación local ni aislamiento por proceso. Evita usarlo como protección ante malware local.
- No persistimos contraseñas en archivos y no guardamos destinos de navegación en logs. La memoria del proceso no está protegida frente a otros procesos privilegiados.
- La conexión al proxy remoto usa TLS con verificación de certificado y hostname; los destinos HTTPS negocian su propio TLS extremo a extremo dentro del CONNECT.
- No hay protección tipo *kill switch*: si una aplicación decide no usar proxy, puede salir directamente.
- No se verifica aún el uso permitido de la infraestructura de 1VPN por aplicaciones no oficiales. No automatizamos autenticaciones restringidas ni eludimos planes premium.

## Estructura

```
desktop_prototype/
  app.py                 # UI Windows local-only
  proxycore.py           # Relay CONNECT / HTTP proxy => proxy HTTPS TLS
  connection_check.py    # Comprobación HTTPS exclusivamente por proxy local
  Iniciar.ps1            # Ejecución Windows
  Compilar-EXE.ps1       # Compilación opcional en Windows
  tests/                 # Pruebas unitarias e integración local
scripts/
  Descargar-1VPN-Oficial.ps1
ANALISIS_TECNICO.md
DECISIONES.md
```

## Próximo hito

Conectar el catálogo de servidores permitidos, diagnóstico de fallos por región, métricas de conexiones activas y empaquetado Windows; siempre conservar el modo local-only. Una futura integración de TUN/Wintun se tratará en **otro módulo, sin activarse por defecto**.


## 6. Proxificación TCP por aplicación (experimental, v0.3-alpha)

**No se instala controlador ni se cambian rutas, WinINET, Wintun o reglas de firewall.**

El puente SOCKS5/TCP permite usar 1VPN Desktop Lab como backend de un proxificador
Windows compatible con SOCKS5. Conecta el puerto SOCKS5 local `127.0.0.1:1080`
al proxy HTTP CONNECT que la app levanta en `127.0.0.1:8899`.

Con la app principal v0.2 ya conectada y puerto 8899:

```powershell
py -3 .\desktop_prototype\socks5_bridge.py --http-port 8899 --port 1080
# Prueba del protocolo SOCKS5, SIN instalar driver:
curl.exe --socks5-hostname 127.0.0.1:1080 https://api.ipify.org
```

El adaptador **solo** soporta SOCKS5 `CONNECT` TCP, no UDP, QUIC, BIND,
redirección automática de procesos ni kill switch. No lo confundas con una VPN.
Consulta `docs/Proxificador-Windows-Plan.md` y
`docs/proxifyre-lab-example.json` antes de probar ProxiFyre por separado.
La configuración de ejemplo es de laboratorio: **no se aplica automáticamente**.

## v0.4.1 — Selección automática de servidores Free (2026-11-13)

El panel principal incorpora un selector de **Automático · Singapur preferido**, Singapur,
Ámsterdam, Los Ángeles y **Servidor manual**. No se graban usuarios ni contraseñas.

- Catálogo incluido: 16 proxies HTTPS/443 de las tres regiones Free del código público
  [1VPN/browser-extension](https://github.com/1vpn/browser-extension/blob/main/src/utils/freeLocations.js)
  (referencia v4.2.1). En cada arranque automático intenta actualizarse usando
  `https://1vpn.org/api/get_proxy_servers/` (consulta HTTPS pública, sin autenticación).
  Si no responde o el JSON no cumple la validación, se conserva el catálogo incluido.
  Sólo se aceptan hosts de los dominios presentes en el catálogo público y ubicaciones
  Free reconocidas; el catálogo Premium no se habilita sin derechos de cuenta.
- **Medición real:** cada candidato hace conexión TCP + negociación TLS con certificado
  verificado + `CONNECT api.ipify.org:443`. RTT refleja el tiempo de esa operación,
  no un ping ICMP ni ancho de banda. Los intentos de medición corren en segundo plano,
  sin interrumpir los listeners locales.
- **Preferencia por Singapur:** gana el servidor de menor RTT, excepto cuando un
  servidor de Singapur está a no más de 35 ms del más rápido: en ese caso se
  prefiere Singapur. Seleccionar una región fija sólo prueba esa región.
- **Fallback:** para una conexión TCP CONNECT nueva que falle antes de establecerse,
  intenta hasta cuatro upstreams de su lista clasificada. Un servidor rechazado se
  evita temporalmente 45 s y las próximas conexiones seleccionan otro. Si todos
  fallan, devuelve error (sin desviar el tráfico a una conexión directa). No
  reintenta tráfico cuyo túnel ya está establecido ni reenvía HTTP POST dos veces.
- Botón **MEDIR SERVIDORES** para volver a medir; se informa qué host/región fue
  seleccionado y cuántos candidatos pasaron. **COMPROBAR SALIDA** sigue confirmando
  la IP pública a través del proxy local.
- Los puertos HTTP/SOCKS5 siguen limitados a `127.0.0.1`; no hay captura
  transparente, UDP ni cambios a Wintun, DNS, WinINET o rutas de Windows.

**Inicio Windows:** `py -3 .\desktop_prototype\app.py` desde la raíz del repositorio.
Para seleccionar Manual, elige *Servidor manual* e introduce el hostname.
En modo automático sólo necesitas las credenciales del proxy remoto que
te correspondan legítimamente: no están incluidas en la aplicación.

**Límites de las pruebas:** la suite local usa servidores TLS efímeros y mocks;
no realiza conexiones con la infraestructura real de 1VPN. La validación de
la latencia real, región elegida y continuidad debe completarse en Windows.


## v0.4.1a — Inicio de sesión de CUENTA separado del PROXY (2026-11-13)

Esta revisión corrige la confusión entre **cuenta 1VPN** y **credenciales del proxy HTTPS**:

- El botón **INICIAR SESIÓN 1VPN (EMAIL)** abre el formulario de la cuenta.
- El campo **Correo electrónico** se envía como clave JSON `email` y la **contraseña exacta** (no se recorta ni modifica) como `password`. Si la API solicita 2FA, se envía el campo adicional `token` con el código introducido. El endpoint de cuenta es `POST https://1vpn.org/api/login/?type=xray` y se usan los dominios alternativos documentados por la app oficial cuando el principal no es alcanzable. Encabezado `Client-Type: app`. TLS se valida normalmente y **no se siguen redirecciones**.
- Al responder la API con `sessionAuthToken` e `isPremium` se muestra la cuenta y el tipo de plan. **La sesión solo permanece en memoria** durante la ejecución; la aplicación no guarda la clave ni el token en disco y no los registra en logs.
- Los campos de la pantalla principal ahora dicen **Usuario del PROXY** y **Clave del PROXY**. Son diferentes del correo y contraseña de la cuenta. El proxy web oficial de cuentas Premium usa `username` más `sessionAuthToken`, no la contraseña de inicio de sesión; el token de tipo Xray de la app Android **no se incorpora automáticamente al proxy HTTPS de navegador** porque esa compatibilidad no se ha validado.
- El login no cambia Wintun, firewall, rutas, servidores Free ni la configuración de los puertos HTTP/SOCKS5. En caso de fallo de red no se informa falsamente de una contraseña incorrecta.
- Pruebas locales con respuestas simuladas: comprobar la forma exacta del POST, rechazo de email no válido, 2FA, plan Free/Premium, dominio oficial, privacidad de tokens y manejo de errores. **No se ha probado con credenciales reales de una cuenta.**

### Ejecución

```powershell
cd D:\Proyectos\1VPN-Desktop-Lab
git switch main
git pull --ff-only origin main
py -3 .\desktop_prototype\app.py
```

Pulsa **INICIAR SESIÓN 1VPN (EMAIL)** para validar la cuenta. No copies la contraseña de la cuenta en el campo **Clave del PROXY**: esa clave autentica un servicio diferente. El inicio de sesión de cuenta por sí solo no habilita acceso Premium a los proxies de navegador; esa integración debe validarse por separado.