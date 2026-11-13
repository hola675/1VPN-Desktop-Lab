# 1VPN Desktop Lab

**Versión del laboratorio:** 0.1.0 · **Fecha:** 2026-11-13  
**Estado:** investigación estática concluida sobre fuentes públicas; prototipo Windows local creado; integración directa con 1VPN y túnel VPN completo **no implementados**.

Este proyecto **no es el producto oficial de 1VPN** ni representa una conexión autorizada a su infraestructura. La investigación es sobre software público; la app creada es código original que sirve para conectar a **proxies HTTPS propios o cuyo uso hayas autorizado**.

## 1. Qué encontramos

- Extensión Chrome: `akcocjjpkmlniicdeemdceeajlmoabhg`.
- Repositorio original: https://github.com/1vpn/browser-extension
- Versión oficial más reciente comprobada: `v4.2.1`, publicada el 2026-11-03.
- Release (ZIP compilado Chrome): https://github.com/1vpn/browser-extension/releases/tag/v4.2.1
- App Android, ahora en: https://github.com/1vpn/app
- Ambos proyectos originales tienen licencia GNU GPL-3.0. Si integras o distribuyes código derivado debes cumplir la licencia y sus atribuciones.

## 2. Descargar referencia original en Windows

Desde PowerShell 7.6 (sin ejecutar contenido de terceros):

```powershell
Set-Location .\1VPN-Desktop-Lab
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\Descargar-1VPN-Oficial.ps1
```

El script consulta la última release oficial, descarga el ZIP de Chrome y el código fuente de la misma etiqueta, extrae, coteja versión del manifiesto y calcula SHA-256. Los hashes se registran localmente; para una verificación de suministro fuerte deberán cotejarse con hashes o firmas publicados independientemente por los autores.

Opcionalmente: agrega `-IncluirAndroid` para descargar la fuente Android. El comando **no instala ni ejecuta** la extensión.

## 3. Ejecutar prototipo en Windows

El equipo necesita Python 3 con Tkinter (habitualmente incluido en el instalador de Python de Windows):

```powershell
Set-Location .\desktop_prototype
pwsh -NoProfile -ExecutionPolicy Bypass -File .\Iniciar.ps1
```

Introduce **un proxy HTTPS que tengas derecho a utilizar**, puerto, usuario y contraseña si corresponden. Pulsa **INICIAR PROXY**. Sin habilitar la opción del sistema, se crea un proxy HTTP únicamente en `127.0.0.1:puerto-aleatorio`, que se comunica cifrado por TLS con el proxy remoto. Puedes configurar un navegador para usarlo.

Si marcas la opción WinINET, el programa respalda la configuración anterior del proxy de Windows para el usuario actual, aplica `127.0.0.1:puerto`, y la restaura al desconectar. También intenta recuperarla al reiniciar tras un cierre abrupto. **Prueba primero sin marcar esa opción.**

No se guarda contraseña ni se incluyen credenciales de 1VPN. Se validan certificados del proxy remoto y el listener no se expone a la LAN.

### Compilar EXE (opcional)

Si dispones de PyInstaller ya instalado, ejecuta `desktop_prototype\Compilar-EXE.ps1`. El EXE se crea solo desde Windows. No hemos compilado ni probado un ejecutable Windows en este entorno.

### Tests

```powershell
Set-Location .\desktop_prototype
py -3 -m unittest discover -s tests -v
```

## 4. Límites reales de esta versión

- **Es proxy, no VPN:** solo afecta apps que utilizan el proxy HTTP de Windows o la configuración manual; no cubre por sí mismo UDP, juegos, ICMP, DNS de sistema, ni aplicaciones que ignoren el proxy.
- **No integra API 1VPN:** no se reutilizan credenciales incluidas en fuentes públicas ni se automatizan inicios de sesión o límites de acceso.
- **No incorpora VLESS/Reality ni TUN:** eso requiere un motor confiable como Xray-core/sing-box y configuración debidamente autorizada.
- **No es un kill switch:** si el proxy local se detiene, algunas aplicaciones pueden intentar salida directa o fallar según su configuración. No se promete anonimato.
- **No sustituye pruebas de seguridad:** hay que auditar transporte, fugas DNS/WebRTC, pruebas de fallo, versiones y permisos antes de usarlo para tráfico sensible.

## 5. Siguiente iteración

1. Descargar y analizar byte-a-byte el ZIP Chrome oficial en el Windows de pruebas; comparar bundle con source del tag.
2. Validar por documentación o permiso del proveedor el uso de su backend desde un cliente Windows.
3. Diseñar interfaz nativa Tauri o Flutter para producción, separando proveedor, estado y motor de túnel.
4. Para *VPN real*, evaluar OneXray/Xray-core (GitHub 1vpn/app, derivado de OneXray) en Windows con TUN y servicio Windows; evitar copiar credenciales de la app Android.
5. Pruebas de conexión y fuga, autorestauración, firma de ejecutable, actualizaciones y artefactos verificables.

Leer `ANALISIS_TECNICO.md` y `DECISIONES.md` antes de continuar.
