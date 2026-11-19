# ADR-014 — Ciclo de vida del driver firmado de OneTunnel

**Fecha:** 2026-11-19  
**Estado:** implementación en PR #18; paquete de CI permanece SIN FIRMAR  
**Objetivo:** instalar/cargar el callout WFP desde OneTunnel sin ProxiFyre, sin Windows Firewall y sin desactivar las protecciones de firma de Windows.

## Decisiones

1. El callout es un primitive driver x64 para Windows 10 1903+/Windows 11.
2. El paquete usa DefaultInstall.NTamd64, DIRID 13 (Driver Store), PnpLockdown=1, clase WFPCALLOUTS y StartType=3 (demand start).
3. No hay DefaultUninstall; la retirada del paquete se realiza con DiUninstallDriverW.
4. La instalación se realiza con DiInstallDriverW, después de una verificación previa de firma.
5. El driver nunca se instala automáticamente al abrir OneTunnel.
6. No existe bypass de firma, testsigning, nointegritychecks, modificación de Secure Boot ni instalación del .sys unsigned de CI.

## Verificación de paquete

driver_lifecycle.py requiere exactamente OneTunnelRedirect.inf, OneTunnelRedirect.cat y onetunnel-wfp-redirect.sys.

Antes de cambiar el sistema:

1. SetupVerifyInfFileW verifica el INF utilizando el catálogo asociado.
2. Debe devolver un firmante y el catálogo exacto dentro del paquete seleccionado.
3. Si Windows no confía en el catálogo, la operación termina.
4. DiInstallDriverW actúa como validación final del paquete y sus miembros antes de ingresarlo al Driver Store.

El catálogo producido por Inf2Cat en CI es deliberadamente UNSIGNED; por diseño debe ser rechazado en un Windows normal.

## Instalación y arranque

La acción INSTALAR MOTOR verifica firma, exige administrador, llama DiInstallDriverW y arranca OneTunnelWfpRedirect solo si Windows no solicita reinicio. Si el servicio no arranca, OneTunnel intenta retirar el paquete para evitar una instalación a medias.

INICIAR DRIVER y DETENER DRIVER usan APIs SCM (OpenSCManager, OpenService, StartService, ControlService), nunca sc.exe.

OneTunnel registra si esta instancia inició el servicio. Al cerrar elimina primero sesión PROXY/BFE, luego filtros BLOCK efímeros, después detiene el callout solo si es propiedad de esta instancia y finalmente detiene el transporte Premium. Un servicio preexistente RUNNING no se detiene automáticamente.

## Activación PROXY

ACTIVAR PROXY WFP requiere simultáneamente:

- transporte Premium HTTP/SOCKS5 activo;
- COMPROBAR SALIDA aprobado;
- una o más políticas PROXY (WFP nativo firmado);
- rutas actuales de esos nombres .exe resueltas;
- ausencia de conflicto con BLOCK;
- driver firmado instalado y RUNNING;
- relay y control plane empaquetados.

Secuencia: driver demand-start si corresponde → relay en puerto loopback efímero → control plane con PID/puerto/rutas → comprobación de callouts registrados → filtros dinámicos ALE_APP_ID + TCP. Si cualquier paso falla, se revierte la sesión y no se declara PROXY activo.

No existe fallback silencioso DIRECTO para una aplicación que ya coincidió con un filtro PROXY.

## Desactivación y desinstalación

DETENER PROXY WFP cierra primero el control plane (BFE retira filtros), luego el relay y, si OneTunnel inició el driver solo para esa sesión, detiene el servicio.

DESINSTALAR no se permite con una sesión PROXY activa; vuelve a verificar el paquete firmado, detiene el servicio, llama DiUninstallDriverW e informa si Windows solicita reinicio.

## CI y firma

CI compila el .sys con WDK/SDK NuGet fijado, valida el INF moderno con InfVerif /w, genera catálogo mediante Inf2Cat y publica OneTunnel-WFP-Package-UNSIGNED-CI. CI nunca instala/carga el driver ni incorpora el paquete unsigned al EXE de usuario.

El paquete unsigned sirve exclusivamente para validar reproducibilidad y estructura; la distribución estable necesita un catálogo firmado mediante un proceso de firma autorizado para kernel-mode Windows 11.

## Gate de producción

1. Obtener firma de kernel aceptada por Windows 11.
2. Validar SetupVerifyInfFileW en un PC limpio.
3. Instalar en VM/snapshot y comprobar RUNNING.
4. Activar PROXY para una app sin --proxy ni variables manuales.
5. Confirmar IP VPN y DIRECTO por separado.
6. Detener OneTunnel y comprobar retirada de filtros.
7. Probar actualización, desinstalación y reinicio.
8. Auditar convivencia con antivirus/EDR/otros callouts WFP.
9. Resolver UDP/QUIC/DNS/IPv6 antes de afirmar protección total o kill switch.

## Referencias Microsoft

- Creating a Primitive Driver
- DiInstallDriverW / DiUninstallDriverW
- SetupVerifyInfFileW
- Driver package signing / catalog files
- InfVerif e Inf2Cat
- WFP callout driver installation
