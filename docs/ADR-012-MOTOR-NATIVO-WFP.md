# ADR-012 — Motor de captura y políticas de red NATIVO de OneTunnel

**Fecha:** 2026-11-19  
**Estado:** APROBADO como arquitectura; implementación parcial v0.5.0 alpha  
**Decisión del usuario:** OneTunnel no debe depender de instalar o controlar ProxiFyre ni de usar reglas de Windows Defender Firewall para su funcionalidad principal.

## 1. Alcance final del producto

Una sola aplicación e instalador de OneTunnel para Windows 11 x64. Desde la misma interfaz, el usuario selecciona nombres de proceso como chrome.exe y elige:

- DIRECTO: tráfico de la aplicación por la conexión ordinaria de Windows.
- BLOQUEAR: OneTunnel bloquea la salida de esa aplicación directamente mediante filtros propios en WFP.
- PROXY: OneTunnel intercepta conexiones y las enruta hacia el motor Premium integrado. Sin app ProxiFyre, sin configuración proxy manual por aplicación y sin cambiar rutas globales de Windows.
- Registro por EXE: conexiones, resultado, servidor usado y pruebas de IP por el túnel (sin datos privados).

No se implementa mediante una regla global por DNS, puerto, dominio o dirección IP. El selector visible son nombres .exe normalizados y todos sus procesos (PID). Las rutas reales se obtienen internamente del sistema Windows para identificar cada binario en WFP.

## 2. API del sistema operativo vs dependencia de una app

WFP — Windows Filtering Platform — es la API de filtrado de red del propio Windows y requiere el servicio base BFE. No es necesario crear reglas de Windows Defender Firewall con PowerShell/netsh, y no se necesita ProxiFyre. Sin embargo, depender de las APIs de Windows es inevitable al filtrar tráfico en Windows.

Windows WFP permite:
- BLOQUEAR salidas TCP/UDP IPv4/IPv6 con filtros en las capas ALE_AUTH_CONNECT y condición ALE_APP_ID, administrados desde una aplicación en modo usuario.
- PROXY transparente con un controlador callout WFP firmado, registrado en ALE_CONNECT_REDIRECT; necesita acceso al destino original, redirección, detección de bucles y un relay de conexiones en modo usuario. En Windows 8+ se exigen mecanismos específicos de redirect handle y seguimiento de conexiones.
- DIRECTO por ausencia de filtro propio; prioridad/precedencia con otros filtros del sistema requiere pruebas, no se puede prometer que una regla DIRECTO anule filtros ajenos.

## 3. Implementado en v0.5.0-native-alpha (PR #15)

### Motor de bloqueo C++ propio
- Fuente: native/wfp/wfp_guard.cpp; compilación CMake mediante Windows SDK/MSVC.
- Uso de FwpmEngineOpen0 con FWPM_SESSION_FLAG_DYNAMIC; FwpmSubLayerAdd0; FwpmGetAppIdFromFileName0; FWPM_CONDITION_ALE_APP_ID, FWP_ACTION_BLOCK; ALE_AUTH_CONNECT_V4 y V6.
- Transacción WFP para instalar simultáneamente los filtros, sin reglas persistentes.
- Subproceso onetunnel-wfp-guard.exe lanzado y controlado desde OneTunnel; READY tras éxito; terminación del subproceso elimina filtros automáticamente.
- Rechaza nombres críticos/portadores; limita cantidad de rutas. No instala kernel driver. Requiere administrador al activar BLOCK, no al abrir la interfaz.
- En la GUI, BLOQUEAR solo se activa por acción y confirmación explícita. Copias futuras del mismo nombre en nuevas ubicaciones no quedan bloqueadas automáticamente hasta incluir sus rutas reales en la sesión.

### Ciclo de vida
- Backend desktop_prototype/native_wfp.py inicia nueva sesión WFP y espera confirmación, conserva la anterior si falla la nueva y detiene los filtros al cerrar OneTunnel.
- DIRECTO no crea filtros nuevos. Los filtros gestionados por OneTunnel son temporales, NO se presumen como kill switch.
- Importación de versiones anteriores: desktop_prototype/firewall_rules.py solo se utiliza para que el usuario pueda retirar las reglas antiguas que ya hubiese creado en Windows Firewall, mediante una acción explícita y reversible; nunca para aplicar reglas nuevas.
- La aplicación conserva las políticas guardadas por nombre de EXE en schema v2, independiente de la ruta.
- El motor WFP se empaqueta dentro de 1VPN-Desktop-Lab.exe desde el build Windows.

### Verificaciones de calidad
- Pruebas unitarias simulan la activación y revocación sin permisos reales.
- CI Windows compila el programa C++ y lo incluye en el EXE; smoke test del UI y arranque de PyInstaller.
- BLOQUEAR real y la convivencia con otros filtros WFP/seguridad siguen PENDIENTES de prueba en un PC de laboratorio administrado. No marcar como producción sin esas pruebas.

## 4. Fase siguiente obligatoria: redirección PROXY propia

No basta cambiar el destino de la conexión al puerto SOCKS5 1080: SOCKS5 necesita negociación y conocer el host/puerto original. El motor requiere:

1. **Callout kernel WFP firmado** (Windows Driver Kit, C/C++ o KMDF): registrar FWPS_LAYER_ALE_CONNECT_REDIRECT_V4/V6, decidir por programa, obtener contexto original, asociar redirect handle y evitar redirigir el mismo socket repetidamente.
2. **Servicio local de políticas** (proceso OneTunnel): comunicarle al controlador las reglas por nombre de EXE y el puerto de redirección, con ACL y versionado; no enviar tokens al kernel.
3. **Transparent relay de usuario**: aceptar sockets redirigidos, recuperar destino original mediante contexto fiable del driver y construir SOCKS5 CONNECT al proxy local 127.0.0.1:1080; devolver errores cerrando el flujo sin convertirlo silenciosamente en conexión DIRECTO.
4. **Política del portador**: excluir OneTunnel y conexiones propias del túnel para evitar recursión, introducir rollback por caída y supervisar el estado.
5. **Protección de tráfico no soportado**: UDP, DNS, DoH, QUIC, IPv6, WFP ALE_RECV_ACCEPT y WebRTC requieren plan propio de filtrado y validación; no declarar FULL VPN/kill switch hasta implementarlo.
6. **Firma y distribución**: instalador para registrar de forma segura un controlador firmado por Microsoft (attestation/WHQL según producto) y un servicio; desinstalación y recuperación de red en máquina de prueba.

### Estados exigidos en la UI
- DIRECTO: disponible.
- BLOQUEAR: motor nativo WFP disponible con aprobación administrativa; comprobar filtros realmente activados.
- PROXY: PENDIENTE hasta que el callout WFP firmado y el relay estén validados. Es una preferencia guardable, NO una captura activa.
- CAÍDA/FALLO: no declarar conexión VPN protegida ni kill switch automáticamente.

## 5. Revisión de referencia, no importación de código

- ProxiFyre (AGPL-3.0) y Windows Packet Filter/NDISAPI sirven para estudio arquitectónico, no se compilan, cargan o redistribuyen ni son dependencia del programa nativo.
- Microsoft WFP es la referencia normativa de la implementación propia.
- IDA/Ghidra pueden servir para analizar binarios propios o APIs documentadas, pero no hacen falta para reconstruir el funcionamiento de proyectos con fuente pública.
- La implementación actual del puente 1VPN Premium/SOCKS5 existente sigue intacta.

## 6. Condiciones de aceptación restantes

- VM o equipo de laboratorio con respaldo. Bloquear y desbloquear una aplicación de prueba sin cortar Internet de otras aplicaciones.
- Confirmar que WFP AUTH_CONNECT V4/V6 filtra exactamente la aplicación elegida y que matar el helper elimina todos sus filtros. Comprobar errores de permisos y conflictos con EDR/VPN/Proxifier.
- Verificar las transiciones DIRECTO↔BLOQUEAR, dos nombres EXE simultáneos y caída inesperada.
- Más adelante certificar PROXY por aplicación sin configurar proxy manual, incluyendo loop prevention, destino original, salida IP, UDP/DNS y fail closed cuando sea aplicable.

## Fuentes Microsoft
- https://learn.microsoft.com/en-us/windows/win32/api/fwpmu/nf-fwpmu-fwpmengineopen0
- https://learn.microsoft.com/en-us/windows/win32/api/fwpmu/nf-fwpmu-fwpmgetappidfromfilename0
- https://learn.microsoft.com/en-us/windows-hardware/drivers/network/using-bind-or-connect-redirection
- https://learn.microsoft.com/en-us/windows-hardware/drivers/dashboard/driver-signing-offerings

## 7. Avance v0.5.1 — relay transparente de usuario

Se implementó el dataplane de usuario previo al driver: `native/wfp/transparent_relay.cpp`. El relay escucha exclusivamente en loopback (IPv4 e IPv6), exige que el socket aceptado exponga `SIO_QUERY_WFP_CONNECTION_REDIRECT_CONTEXT` y `SIO_QUERY_WFP_CONNECTION_REDIRECT_RECORDS`, valida nuestro ABI versionado y transfiere los redirect records al socket que conecta con el SOCKS5 local. A continuación negocia SOCKS5 CONNECT con el destino original y bombea el flujo TCP en ambas direcciones.

El contexto propio contiene magic, versión, familia, puerto original y 16 bytes de dirección. El futuro callout deberá llenar exactamente ese contexto en `localRedirectContext`, establecer `localRedirectHandle` y `localRedirectTargetPID`, además de consultar el estado de redirección para evitar bucles. El relay no acepta tráfico si faltan records/contexto; esto evita convertir el puerto de relay en un proxy abierto.

CI puede compilar y ejecutar `--self-test` sin instalar filtros. El self-test valida la construcción SOCKS5 IPv4/IPv6, pero no sustituye una prueba con un socket realmente redirigido por WFP. PROXY sigue PENDIENTE hasta implementar y firmar el callout kernel.
