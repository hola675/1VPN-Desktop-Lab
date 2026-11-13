# 1VPN Desktop Lab

**Versión de desarrollo: 0.3.0-alpha · 2026-11-13**  
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
