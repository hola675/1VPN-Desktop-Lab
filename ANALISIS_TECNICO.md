# 1VPN – Informe técnico de arquitectura (revisión 1)

Fecha: 2026-11-13 · Fuente: código abierto publicado en GitHub por 1vpn.

## Fuentes verificadas

- https://github.com/1vpn/browser-extension
- https://github.com/1vpn/browser-extension/releases/tag/v4.2.1
- https://github.com/1vpn/app
- https://1vpn.org/terms-of-service/
- https://github.com/1vpn/browser-extension/blob/main/LICENSE

El código del repositorio `main` y el contenido de la release **pueden diferir**; la comparación paquete-vs-fuente queda pendiente hasta ejecutar el descargador y revisar el resultado.

## Mapa estático del flujo

```
[Usuario selecciona región]
     |
     v
[Popup.jsx: connect()]
     |
     v
[manageProxy.js: obtiene locations + currentLocation]
     |
     +--> Chrome: chrome.proxy.settings.set() / PAC
     |          devuelve «HTTPS host:443» (orden aleatorio)
     |          y excepciones DIRECT para dominios determinados
     |
     +--> Firefox: browser.proxy.onRequest -> HTTPS proxy
     |
     v
[background/index.js: webRequest.onAuthRequired]
     |
     +--> Cuenta Premium: sessionAuthToken del almacenamiento
     +--> Nivel gratuito: credenciales referenciadas en constants.js
     |
     v
[Proxy HTTPS autenticado] ---> [Internet]
```

### Archivos clave comprobados

| Ruta | Comportamiento observado |
| --- | --- |
| `src/pages/background/index.js` | Registro de autenticación del proxy; reintento en inicio del navegador; refresh de token cada seis horas; gestión de conflicto y opciones de privacidad. |
| `src/utils/manageProxy.js` | PAC, con `HTTPS hostname:port`; selección de ubicaciones; lista de dominios directos; conexión/desconexión. |
| `src/utils/apiFetch.js` | Solicitudes HTTPS a API, timeout de 10 segundos y fallback entre hosts alternativos; 401 se entrega al llamador. |
| `src/utils/userData.js` | Consulta `get_user_data_web`, normaliza catálogo y reconecta cuando cambia el plan. |
| `src/utils/freeLocations.js` | Catálogo de regiones gratuitas y ubicaciones Premium; puede estar obsoleto frente a backend. |
| `src/manifest/base.json` | MV3, permisos `proxy`, `webRequest`, `storage`, `alarms`, `scripting`, etc. |
| `scripts/fetchFreeServers.js` | Durante build lee un endpoint de catálogo de proxies para regenerar datos de regiones libres. |

### Lo que no demuestra el análisis

- No prueba que el servicio acepte clientes de escritorio de terceros.
- No prueba que servidores actuales estén operativos ni que sus certificados correspondan a nombres indicados en código.
- No prueba que usar el proxy WinINET equivalga a un túnel VPN de todo Windows.
- No incluye tráfico capturado, credenciales privadas ni ejecuciones sobre la infraestructura de 1VPN.

## Arquitectura recomendada

```
[Windows UI / cuenta / regiones]
             |
    [Gestor de conexión y política]
             |
     +-------+--------+
     |                |
 [Proxy HTTP local] [Engine VPN/TUN, etapa 2]
     |                |
 [TLS -> proxy       [Xray-core o sing-box]
  HTTPS autorizado]      |
     |                 [Rutas y DNS del sistema]
 [Apps que usan proxy]        |
     +-------------------------+
                      [Salida de red autorizada]
```

Para producto Windows profesional se recomienda usar componentes probados, implementar **kill switch**, DNS/IPv6, control de fugas, recuperación de estado, permisos del servicio Windows, pruebas de red, auditoría de dependencias y firma del software. El prototipo adjunto solo cubre la rama «proxy HTTP local».

## Revisión de Android

El repositorio `1vpn/app` es un fork GPL-3.0 de OneXray escrito en Flutter. Su documentación indica motor libXray/Xray-core, y define credenciales VLESS/Reality de las regiones gratuitas mediante variables de compilación **no incluidas** en el código. No se ha identificado un proyecto Windows listo para compilar en ese repositorio: no hay árbol `windows/` en la revisión consultada. Ser multiplataforma en Flutter no implica automáticamente soporte Windows operativo.

## Licencia y límites

El código original está disponible bajo GPL-3.0; si lo combinas en una obra derivada distribuida, debes cumplir condiciones de GPL-3.0. El laboratorio aporta código independiente y no incorpora módulos originales. Las condiciones de servicio prohíben vender o revender el servicio sin permiso. La licencia sobre el código no concede automáticamente permiso para acceder ilimitadamente a la infraestructura del proveedor. Consulta asesoría legal antes de distribuir un cliente compatible con marcas o backend de terceros.

## Verificación del prototipo en este entorno

| Ensayo | Resultado |
| --- | --- |
| Compilación sintáctica de módulos Python | PASS |
| 5 pruebas unitarias (validez de servidor, cabeceras, listener solo-loopback) | PASS |
| Integración local con proxy ascendente HTTPS simulado, certificado TLS verificado y solicitud CONNECT | PASS |
| Remisión de cabecera Basic del usuario proporcionado en prueba aislada | PASS |
| Compilación Windows `.exe` | NO EJECUTADA (entorno de desarrollo Linux) |
| Cambio de proxy WinINET / restauración en Windows | NO EJECUTADO (requiere máquina Windows de pruebas) |
| Descarga de paquete oficial en este entorno | NO COMPLETADA (restricción de red de descarga). Script preparado para Windows. |
| Conexión a servidores de 1VPN | NO INTENTADA (se requiere validar uso autorizado). |

No se enviaron credenciales ni peticiones a los servidores de 1VPN durante las pruebas de integración.

## Nota de evolución — 0.2.0 (2026-11-13)

A petición del usuario, la aplicación de escritorio funciona **solo con proxy HTTP local** y no invoca `windows_proxy.py` ni modifica el registro. El módulo `windows_proxy.py` queda documentado únicamente como artefacto histórico de v0.1; se excluye de la entrega del repositorio v0.2 para reducir el riesgo de uso accidental. La interfaz nueva abre un puerto local explícito (predeterminado `8899`) y deja al usuario configurar las aplicaciones seleccionadas.

El botón **Comprobar salida** prueba la ruta HTTP CONNECT -> proxy remoto HTTPS/TLS -> HTTPS `api.ipify.org` usando el proxy local, sin conexión directa de respaldo. Un listener local activo **no acredita** una salida remota válida. Las pruebas de integración locales no sustituyen una prueba autorizada con el proveedor.
