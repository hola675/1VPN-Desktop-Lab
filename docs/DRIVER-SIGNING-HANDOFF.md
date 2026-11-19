# Handoff de firma del driver OneTunnel WFP

**Fecha:** 2026-11-19
**Estado:** el código/INF/paquete se compilan y validan en CI; falta firma Microsoft y prueba real de kernel.

## Objetivo

Convertir `OneTunnel-WFP-Package-UNSIGNED-CI` en un paquete confiable por Windows 11 y luego integrarlo dentro del mismo EXE de OneTunnel. No se almacenan certificados privados ni secretos en Git.

## Qué produce CI

El workflow Windows:

- compila `onetunnel-wfp-redirect.sys` con WDK;
- valida `OneTunnelRedirect.inf` con `InfVerif /w`;
- genera `OneTunnelRedirect.cat` con `Inf2Cat`;
- publica `OneTunnel-WFP-Package-UNSIGNED-CI`;
- NO firma, instala ni carga el driver.

El catálogo de CI es estructuralmente válido pero no confiable para kernel-mode. OneTunnel debe rechazarlo mediante `SetupVerifyInfFileW`.

## Firma Microsoft

Para Windows 10/11 x64, un driver kernel nuevo necesita una firma aceptada por Microsoft Hardware Dev Center. El proceso requiere una organización registrada y al menos un certificado EV asociado al dashboard.

Hay dos rutas que deben mantenerse separadas:

1. **Pruebas/laboratorio — attestation signing:** sirve para Windows Desktop de prueba sin HLK, pero Microsoft la documenta actualmente como opción para escenarios de testing. No equivale a certificación Windows ni es el camino para publicación retail en Windows Update.
2. **Producción/distribución — WHCP/HLK:** ejecutar las pruebas HLK aplicables y enviar la submission al Hardware Dev Center para obtener el paquete de producción/certificación correspondiente.

No introducir `bcdedit testsigning`, `nointegritychecks`, desactivación de Secure Boot ni certificados de prueba en la rama principal.

## Material sensible

- El certificado EV/PFX, PIN, token hardware y credenciales de Partner Center NO pertenecen al repositorio.
- `.gitignore` excluye `.pfx`, `.p12`, `.pvk` y `native/driver/signed-package/`.
- Una build que solo integra un paquete ya firmado por Microsoft no necesita conocer la clave privada EV.

## Integrar el paquete firmado en OneTunnel

Cuando Partner Center devuelva el paquete firmado, coloca en una carpeta local exactamente:

- `OneTunnelRedirect.inf`
- `OneTunnelRedirect.cat`
- `onetunnel-wfp-redirect.sys`

No renombres ni modifiques esos archivos después de la firma.

Desde PowerShell normal de desarrollo/release:

```powershell
$env:ONETUNNEL_SIGNED_DRIVER_DIR = 'D:\Firmado\OneTunnelDriver'
cd D:\Proyectos\1VPN-Desktop-Lab\desktop_prototype
.\Compilar-EXE.ps1
```

El script:

1. ejecuta las pruebas;
2. compila guard/relay/control user-mode;
3. llama `driver_lifecycle.verify_package()` sobre la carpeta firmada;
4. `SetupVerifyInfFileW` debe confirmar que Windows confía en el catálogo exacto;
5. si falla, la compilación se detiene antes de PyInstaller;
6. si pasa, PyInstaller incorpora INF/CAT/SYS bajo `driver_package` dentro del EXE.

Una build sin `ONETUNNEL_SIGNED_DRIVER_DIR` continúa siendo válida para desarrollo, pero no incluye paquete kernel y no puede instalar PROXY WFP por sí sola.

## Comportamiento en ejecución

En una release con paquete firmado integrado:

- el panel detecta automáticamente `driver_package`;
- NO lo instala al arrancar;
- el usuario puede pulsar VERIFICAR FIRMA;
- INSTALAR MOTOR vuelve a verificar firma y exige administrador;
- Windows instala el primitive driver en Driver Store;
- el callout queda demand-start;
- ACTIVAR PROXY WFP solo crea filtros después de comprobar que el driver/callout está realmente registrado.

El botón ELEGIR PAQUETE FIRMADO se conserva para desarrollo/recuperación, pero no es requisito de una release integrada.

## Gate antes de llamarlo funcional

Después de obtener paquete firmado:

1. VM Windows 11 x64 con snapshot;
2. verificar firma desde OneTunnel;
3. instalar y confirmar servicio `OneTunnelWfpRedirect` RUNNING;
4. seleccionar una sola app de prueba como PROXY;
5. activar Premium y COMPROBAR SALIDA;
6. activar PROXY WFP;
7. desde la app seleccionada, sin `--proxy` ni variables HTTP_PROXY, comprobar IP pública;
8. confirmar que una app DIRECTO conserva la salida normal;
9. probar DETENER PROXY y cierre abrupto;
10. probar desinstalación/reinicio;
11. solo después probar varias aplicaciones.

UDP/QUIC/DNS/DoH/WebRTC y kill switch siguen fuera de este gate; no afirmar protección total.

## Referencias Microsoft

- Driver Code Signing Requirements
- Driver Signing Options
- Attestation Sign Windows Drivers
- Kernel-Mode Code Signing Requirements
- Creating a Primitive Driver
- SetupVerifyInfFileW
- DiInstallDriverW / DiUninstallDriverW
