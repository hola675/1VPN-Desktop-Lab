> **Actualización del backend v0.5.0-alpha:** el criterio de selección por nombre de proceso sigue vigente, pero PROXY ya no se exportará a ProxiFyre, y BLOQUEAR se gestiona con filtros nativos WFP. La guía actual está en [ADR-012](ADR-012-MOTOR-NATIVO-WFP.md).

# OneTunnel Desktop Lab v0.4.3 beta — reglas por NOMBRE de aplicación

**Decisión:** replicar la selección «Applications» de Proxifier con nombres
exactos como chrome.exe, telegram.exe, curl.exe, SIN rutas ni reglas por
destino/dominio. Se aplica por nombre a todas las instancias con igual nombre.

## Cómo usarlo

1. OneTunnel Premium: inicia el proxy y pulsa COMPROBAR SALIDA para validar
   la IP de salida HTTPS antes de exportar un perfil de captura.
2. Abre APLICACIONES / FIREWALL. El panel lista un registro por nombre de
   ejecutable y agrupa sus PID. «Ubicaciones en ejecución» indica cuántas
   carpetas distintas tienen una instancia de ese nombre.
3. Elige chrome.exe en la tabla o escribe directamente su nombre. Puedes usar
   Buscar aplicación .exe para seleccionar un fichero y obtener automáticamente
   solo su NOMBRE; no se guarda esa ruta como selector de la política.
4. Selecciona una acción:
   - PROXY (ProxiFyre TCP/IPv4): redacta una regla appNames ["chrome.exe"],
     equivalente a «Applications: chrome.exe» en Proxifier.
   - DIRECTO: añade chrome.exe a las exclusiones de ProxiFyre; como nuestro
     perfil no contiene catch-all, las aplicaciones sin PROXY ya son directas.
   - BLOQUEAR: política por nombre, aplicada mediante reglas Windows Firewall
     para TODAS las ubicaciones ejecutables de ese nombre detectadas al pulsar
     Aplicar BLOQUEO (y las elegidas manualmente desde Buscar aplicación .exe).
5. Guarda. Para PROXY/DIRECTO, exporta un BORRADOR de ProxiFyre y aplícalo
   conscientemente con su GUI (Validate, Apply & Restart) tras instalar el
   motor oficial. Para BLOQUEAR, confirma y aplica con permisos administrador.
6. Al pulsar Retirar bloqueo se quitan solo nuestras reglas gestionadas para
   las rutas registradas de ese nombre y la política pasa a DIRECTO.

Ejemplo de reglas exportadas (ilustrativo, sin token Premium):

    {
      "proxies": [{
        "appNames": ["chrome.exe", "telegram.exe"],
        "socks5ProxyEndpoint": "127.0.0.1:1080",
        "socks5Transport": "TCP",
        "supportedProtocols": ["TCP"],
        "supportedAddressFamilies": ["IPv4"]
      }],
      "excludes": ["1VPN-Desktop-Lab.exe", "ProxiFyre.exe", "curl.exe"],
      "dns": {"mode": "Direct"}
    }

La lista anterior es un fragmento parcial, no un app-config.json completo.

## Precauciones que no ocultamos

- Cualquier archivo que se llame chrome.exe, incluso si está instalado en otra
  carpeta, entra en la misma política PROXY. No se exige el mismo editor,
  firma o hash; una copia diferente con ese nombre también coincide.
- ProxiFyre appNames compara un nombre completo sin barras y sin comodines.
  Su configuración «excludes» usa una comparación más permisiva por subcadena:
  una exclusión por nombre puede dejar DIRECTO también algún programa cuyo
  nombre incluya ese mismo texto. El perfil no usa ninguna captura global.
- Windows Firewall, a diferencia de ProxiFyre, requiere rutas concretas en su
  parámetro -Program. OneTunnel deja seleccionar BLOQUEAR por NOMBRE y aplica
  reglas a todas las rutas detectadas en ese momento. Una copia futura en otra
  ubicación NO queda bloqueada automáticamente, hasta volver a aplicar
  BLOQUEAR. No es un kill switch ni un filtro universal por basename.
- Ni ProxiFyre ni WinpkFilter están integrados dentro del EXE actual.
  Sin instalar/activar ProxiFyre oficialmente, PROXY es una política
  configurada pero NO existe redirección transparente efectiva.
- El puente local solo transporta SOCKS5 CONNECT TCP/IPv4. No se declara
  bloqueo de DNS, UDP, QUIC, IPv6 o WebRTC, ni protección contra fugas.
- Nunca se redirigen ni bloquean servicios críticos o el propio motor VPN.
- No se sobrescribe configuración ProxiFyre instalada ni se instala un
  controlador sin consentimiento; Proxifier de terceros no debe capturar
  simultáneamente durante pruebas iniciales.

## Migración de políticas previas

El archivo personal sigue en LOCALAPPDATA/1VPNDesktopLab/traffic_policies.json.

- Schema v1 guardaba rutas completas; schema v2 guarda solo nombres.
- Al LEER v1, la app agrupa políticas por nombre y conserva los modos.
  No cambia el archivo existente hasta que se guarda una política.
- Si había dos rutas diferentes llamadas chrome.exe con la MISMA política, se
  unifican en una única regla «chrome.exe» al guardar.
- Si dos rutas con el mismo nombre tenían políticas DIFERENTES, la conversión
  se detiene con un mensaje de conflicto para evitar cambiar reglas a ciegas.
  Conserva el JSON original, haz una copia de seguridad y decide qué modo
  deberá aplicarse a TODO ese nombre, luego actualiza ese archivo de forma
  consciente. No se descarta información sin avisar.
- El diario de Windows Firewall (firewall_rules.json) permanece por RUTA:
  protege los bloqueos ya existentes y permite eliminarlos incluso si
  cambian las políticas de nombre.

Documentación de captura y pruebas:
[ProxiFyre por EXE v0.4.2](PROXIFYRE-POR-EXE-V042.md).

Fuente de compatibilidad ProxiFyre:
https://github.com/wiresock/proxifyre/blob/main/docs/configuration.md .
