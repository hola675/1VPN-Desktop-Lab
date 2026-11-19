# ADR-013 — Callout WFP propio para PROXY transparente

**Fecha:** 2026-11-19  
**Estado:** implementación y compilación WDK en curso; NO desplegado.

## Decisión

OneTunnel usará tres componentes propios: la app de escritorio/políticas, el relay transparente de usuario y un callout kernel WFP en ALE_CONNECT_REDIRECT V4/V6. No se utilizarán ProxiFyre, NDISAPI ni reglas nuevas de Windows Defender Firewall para PROXY.

El selector visible sigue siendo el nombre del proceso (por ejemplo chrome.exe). Internamente, Windows WFP identifica aplicaciones por ALE_APP_ID, por lo que el futuro control plane resolverá las rutas actuales de ese nombre y añadirá filtros exactos.

## Contrato

native/wfp/redirect_contract.h define OneTunnelRedirectConfig (magic, versión, puerto y PID del relay) y OneTunnelRedirectContext (familia, puerto y dirección originales). La configuración llegará al callout como FWPM_GENERAL_CONTEXT; el management callout deberá usar FWPM_CALLOUT_FLAG_USES_PROVIDER_CONTEXT.

## Algoritmo del driver

1. Solo procesa TCP en ALE_CONNECT_REDIRECT V4/V6.
2. Valida provider context, relay PID/puerto y derechos de clasificación.
3. Consulta FwpsQueryConnectionRedirectState0 para evitar bucles; si el flujo ya fue redirigido, no lo vuelve a capturar.
4. Obtiene FWPS_CONNECT_REQUEST0 escribible.
5. Copia el destino original al localRedirectContext.
6. Sustituye el destino por loopback y el puerto del relay.
7. Establece localRedirectHandle y localRedirectTargetPID.
8. Aplica FwpsApplyModifiedLayerData0.
9. Si un flujo ya seleccionado como PROXY no puede redirigirse, se bloquea en vez de caer silenciosamente a DIRECTO.

El driver registra callouts, pero NO crea filtros ni decide aplicaciones por sí mismo. Esa responsabilidad queda en modo usuario.

## Build y despliegue

El proyecto native/driver/OneTunnelRedirect.vcxproj usa WDK/SDK NuGet 10.0.28000.2526, siguiendo el mecanismo CI oficial de Microsoft. GitHub Actions solo compila Release x64 y guarda un .sys marcado UNSIGNED-CI. No ejecuta sc create/start, pnputil ni carga el driver.

Un .sys sin firma de CI NO es distribuible. Windows 11 de producción requerirá firma válida y pruebas de driver.

## Fase siguiente — control plane

El siguiente componente abrirá una sesión BFE dinámica, iniciará el relay, añadirá provider/sublayer/provider-context/callouts y filtros por ALE_APP_ID + TCP, mantendrá exclusiones del propio motor y actualizará rutas cuando aparezcan nuevas instancias del mismo nombre EXE. Solo después de una prueba real de IP sin parámetros --proxy se podrá mostrar PROXY como activo.

## Pendientes

- Driver todavía no firmado, instalado ni cargado.
- UDP/QUIC, DNS/DoH/WebRTC y protección contra fugas siguen pendientes.
- No existe kill switch global.
- Compatibilidad con EDR, antivirus y otros callouts WFP requiere VM/PC de laboratorio.

## Referencias

- Microsoft: Using Bind or Connect Redirection.
- Microsoft: FwpsRedirectHandleCreate0, FwpsQueryConnectionRedirectState0 y FwpsAcquireWritableLayerDataPointer0.
- Microsoft Windows-driver-samples / WFPSampler.
- Microsoft WDK NuGet para CI.
