# AGENTS.md — OneTunnel Desktop

Este archivo define cómo debe trabajar cualquier agente de código en este repositorio.

## Estado base

- Rama estable: `main`.
- UI estable de respaldo: Tkinter v0.6.1.
- UI objetivo: PySide6/Qt, actualmente v0.7 Preview.
- Motor vigente: componentes propios OneTunnel + Windows Filtering Platform (WFP).
- No reintroducir dependencias operativas de Proxifier, ProxiFyre o Windows Defender Firewall.
- El driver kernel de CI es UNSIGNED y nunca debe instalarse ni cargarse en un Windows de producción.
- El paquete firmado futuro debe seguir el contrato de `docs/DRIVER-SIGNING-HANDOFF.md`.

## Regla principal

**Simple por fuera, completo por dentro.**

La UI debe mostrar primero tareas del usuario y esconder detalles técnicos en Ajustes/Diagnóstico.

No duplicar lógica de red dentro de widgets Qt. La UI llama a controladores/backend; el backend decide estado y errores.

## Flujo obligatorio de trabajo

1. Sincronizar `main`.
2. Crear rama temporal fresca: `feat/...`, `fix/...` o `docs/...`.
3. Implementar cambios pequeños y verificables.
4. Añadir/actualizar pruebas.
5. Ejecutar CI Windows.
6. Abrir PR a `main`.
7. No fusionar con checks rojos.
8. Fusionar sin force-push.
9. Confirmar CI post-merge.
10. Eliminar la rama temporal después de confirmar que todos sus commits están en `main`.

Consultar también `docs/POLITICA-DE-RAMAS.md`.

## Arquitectura que no debe romperse

### Frontend

`desktop_prototype/qt_app.py`

Debe evolucionar hacia una capa de presentación. La lógica compartida debe extraerse gradualmente a controladores/modelos para reducir duplicación con `app.py`.

### Backend existente

Reutilizar, no reescribir sin necesidad:

- `network_engine.py`
- `proxycore.py`
- `access_proxy.py`
- `server_selector.py`
- `server_catalog.py`
- `premium_bridge.py`
- `account_auth.py`
- `traffic_policy.py`
- `running_apps.py`
- `native_wfp.py`
- `native_proxy.py`
- `native_certification.py`
- `driver_lifecycle.py`

### Motor nativo

`native/wfp/` y `native/driver/`.

No debilitar:

- verificación de firma;
- rechazo del paquete unsigned;
- fail-closed del proxy de acceso;
- aislamiento loopback;
- validación de nombres/rutas de ejecutables;
- limpieza transaccional de filtros/sesiones.

## Seguridad

Nunca:

- guardar contraseñas, tokens Premium, códigos 2FA o pairing en Git;
- escribirlos en logs;
- mostrar tokens completos en UI;
- hacer fallback directo cuando el proxy de acceso está activado;
- instalar automáticamente el driver al iniciar la aplicación;
- desactivar Secure Boot, integridad de código o firma de drivers;
- extraer cookies o storage privado de otra extensión/navegador;
- habilitar reglas globales de firewall para “hacer que funcione”.

## Objetivo de UI Qt

Navegación estable:

1. Inicio
2. Aplicaciones
3. Servidores
4. Cuenta
5. Ajustes
6. Actividad

La página **Servidores** debe añadirse en v0.7.1.

### Inicio

Debe responder sin abrir Ajustes:

- ¿estoy conectado?
- ¿está verificada la salida?
- ¿qué ubicación/servidor uso?
- ¿qué cuenta está activa?
- ¿la red es directa o usa proxy corporativo?
- ¿cuántas aplicaciones están en DIRECTO / PROXY / BLOQUEAR?

### Aplicaciones

El usuario trabaja por **nombre .exe**, no por ruta.

Las rutas completas solo se resuelven internamente para WFP.

### Ajustes

Contiene detalles avanzados:

- proxy de acceso HTTP CONNECT;
- host manual;
- puertos;
- driver firmado;
- diagnóstico/certificación;
- opciones de laboratorio.

## Assets

Seguir `docs/ASSETS-QT-V071.md`.

Reglas:

- generar solo identidad visual original de OneTunnel;
- no copiar logos, iconos o ilustraciones de otras VPN;
- mantener fuentes editables/prompts cuando el generador lo permita;
- preferir SVG para iconos propios y PNG/WebP para ilustraciones;
- crear ICO multiresolución para Windows;
- no incrustar secretos, URLs internas ni datos reales de cuentas en imágenes;
- no añadir archivos enormes sin necesidad.

## Gate de pruebas

Antes de un PR de UI/Qt:

```powershell
cd desktop_prototype
py -3.13 -m unittest discover -s tests -v
$env:QT_QPA_PLATFORM='offscreen'
py -3.13 -c "from PySide6.QtWidgets import QApplication; from qt_app import OneTunnelQt; a=QApplication([]); w=OneTunnelQt(); assert w.isWindow(); w.close()"
```

Además debe pasar GitHub Actions completo:

- `test-and-package`;
- `Qt v0.7 Preview`.

## Definición de terminado

Una tarea no está terminada solo porque “se ve bien”.

Debe cumplir:

- código;
- pruebas;
- documentación;
- estado vacío/cargando/error/éxito;
- DPI y resize razonables;
- accesibilidad básica;
- ningún secreto expuesto;
- CI verde;
- PR fusionado;
- rama limpia.

## Prioridad actual

Ejecutar `docs/ROADMAP-QT-V071-V080.md` en orden.

No saltar a eliminar Tkinter hasta que el roadmap marque el gate de sustitución como cumplido.
