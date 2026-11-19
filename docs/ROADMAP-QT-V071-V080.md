# Roadmap OneTunnel Qt — v0.7.1 a v0.8

**Base:** v0.7 Qt Preview en `main`  
**Objetivo de producto:** aplicación Windows visualmente premium, sencilla en uso diario y con backend de red/WFP complejo aislado detrás de controladores.

---

## Principios de ejecución

1. Cada versión debe quedar usable por sí sola.
2. No mezclar una gran refactorización visual con cambios profundos del dataplane en el mismo PR.
3. Qt sigue siendo Preview hasta completar el Gate A.
4. Tkinter no se elimina hasta completar el Gate B.
5. Assets se producen según `docs/ASSETS-QT-V071.md`.
6. Cada fase requiere CI verde y prueba manual Windows.

---

# v0.7.1 — Visual System + navegación completa

## Objetivo

Convertir el Qt Preview en una interfaz coherente de producto sin cambiar la arquitectura de red.

## Tareas

### A. Sistema visual

- Crear `desktop_prototype/assets/`.
- Integrar logo, app icon e iconos de navegación.
- Añadir `qt_resources.qrc` o un cargador de assets equivalente.
- Sustituir símbolos Unicode de estado por iconos/indicadores consistentes.
- Definir tokens únicos en `qt_theme.py`:
  - color;
  - spacing;
  - radius;
  - typography;
  - shadows/borders;
  - states.

### B. Navegación

Añadir página **Servidores**:

`Inicio · Aplicaciones · Servidores · Cuenta · Ajustes · Actividad`

### C. Inicio

- gran estado Conectado/Desconectado/Verificando/Error;
- ubicación activa;
- RTT;
- IP verificada;
- cuenta;
- proxy corporativo;
- resumen de reglas por aplicación;
- CTA principal único.

### D. Estados

Toda vista debe soportar:

- vacío;
- cargando;
- éxito;
- advertencia;
- error;
- deshabilitado.

### E. DPI/responsive

Probar al menos:

- 100%;
- 125%;
- 150%;
- 200%.

Resoluciones mínimas:

- 1366×768;
- 1920×1080.

No fijar geometrías que corten controles.

## Aceptación v0.7.1

- Qt abre con todos los assets embebidos;
- no depende de rutas absolutas;
- no hay iconos faltantes en EXE PyInstaller;
- página Servidores existe;
- ninguna función de v0.7 se pierde;
- CI estable + Qt PASS.

---

# v0.7.2 — Servidores y selección visual

## Objetivo

Hacer visible y comprensible la selección automática.

## Tareas

- lista/tarjetas de ubicaciones;
- RTT medido;
- estado saludable/no disponible;
- servidor elegido;
- “Automático” explicado visualmente;
- refresco manual;
- indicador de última medición;
- preservar preferencia Singapur dentro del margen existente;
- mostrar Premium/Free sin revelar credenciales.

No cambiar algoritmo sin pruebas específicas de `AutoSelector`.

## Aceptación

- el usuario entiende por qué un servidor fue elegido;
- scan no bloquea UI;
- cancelación/cierre seguros;
- errores no fuerzan salida directa.

---

# v0.7.3 — Aplicaciones premium

## Objetivo

Lograr experiencia tipo Proxifier, pero propia y centrada en procesos.

## Tareas

- extraer icono real del ejecutable en Windows;
- tabla/lista con:
  - icono;
  - app;
  - PID/instancias;
  - política;
  - estado WFP;
- selector rápido:
  - DIRECTO;
  - PROXY VPN;
  - BLOQUEAR;
- filtro/búsqueda;
- mostrar apps sin regla;
- agrupación por nombre .exe;
- feedback de regla aplicada;
- resolver rutas internamente, nunca pedir ruta al usuario para uso normal.

## Aceptación

- cambiar política requiere como máximo dos acciones;
- no se confunde nombre con ruta;
- estado visual coincide con PolicyStore/WFP real;
- no se afirma PROXY activo si el driver/callout no lo está.

---

# v0.7.4 — Cuenta y onboarding Premium

## Objetivo

Reducir pasos de vinculación.

## Tareas

- card de cuenta;
- estado Premium/Free;
- Browser Companion explicado por pasos;
- puerto y código con botones separados;
- temporizador visual de expiración;
- éxito → cerrar pairing automáticamente;
- error → mensaje accionable;
- login Email/2FA permanece secundario;
- logout limpia sesión en memoria.

## Aceptación

- no mostrar token;
- no leer cookies/storage privado;
- pairing sigue siendo one-time + loopback;
- ningún secreto entra en logs.

---

# v0.7.5 — Proxy de red y perfiles

## Objetivo

Mejorar operación en redes corporativas.

## Tareas

- perfiles locales NO sensibles:
  - “Directo”;
  - “Oficina”;
  - “Manual”;
- detectar configuración pública de proxy Windows como sugerencia, sin aplicarla automáticamente;
- botón **Probar proxy**;
- mostrar:
  - proxy alcanzable;
  - CONNECT permitido;
  - TLS 1VPN correcto;
- mantener password solo en memoria;
- preparar abstracción para futuros métodos:
  - None;
  - Basic;
  - NTLM;
  - Negotiate/Kerberos.

No implementar NTLM/Kerberos dentro del mismo PR salvo tests y contrato separados.

## Aceptación

- fail-closed preservado;
- no modifica proxy global Windows;
- no persiste password.

---

# v0.7.6 — Driver y certificación Qt

## Objetivo

Migrar a Qt todas las operaciones avanzadas de WFP todavía dependientes de la UI anterior.

## Tareas

- estado del servicio;
- seleccionar paquete firmado;
- verificar paquete;
- instalar;
- iniciar;
- detener;
- desinstalar;
- certificación transparente NO_PROXY;
- resultado PASS/FAIL detallado;
- mostrar claramente cuando el artefacto es UNSIGNED-CI y rechazarlo.

## Aceptación

- ningún auto-install;
- requiere elevación donde corresponda;
- rollback seguro;
- paquete unsigned no puede atravesar el gate.

---

# v0.7.7 — Controller compartido

## Objetivo

Eliminar lógica duplicada entre Tkinter y Qt antes de retirar Tkinter.

## Estructura propuesta

```
desktop_prototype/
  controllers/
    app_controller.py
    account_controller.py
    applications_controller.py
    server_controller.py
    driver_controller.py
```

La UI recibe estados y emite intenciones.

No mover toda la aplicación en un único PR.

## Aceptación

- widgets Qt no construyen directamente reglas de negocio;
- tests de controller sin GUI;
- backend actual sigue reutilizado.

---

# Gate A — Qt candidato principal

Para declarar Qt “candidato principal” deben pasar en Windows real:

- Premium web;
- conexión y egress;
- proxy corporativo;
- scan;
- DIRECTO;
- BLOQUEAR;
- PROXY WFP con driver firmado;
- certificación NO_PROXY;
- cierre limpio;
- recuperación tras error;
- DPI 100/125/150/200;
- EXE empaquetado;
- 30 min de uso sin crash.

Hasta entonces se siguen publicando ambos EXE.

---

# v0.7.8 — Preferencias y calidad

## Tareas

Persistir solo preferencias no sensibles:

- última ubicación;
- tamaño/posición ventana;
- tema;
- proxy habilitado + host/puerto/usuario si se decide explícitamente;
- nunca password/token/2FA.

Añadir:

- accesibilidad por teclado;
- focus visible;
- tooltips;
- textos consistentes;
- pruebas de resize;
- crash-safe shutdown.

---

# Gate B — Sustitución de Tkinter

Solo después de Gate A + v0.7.8:

1. hacer Qt el ejecutable principal;
2. mantener Tkinter una versión como fallback;
3. marcar Tkinter deprecated;
4. retirar Tkinter en un PR independiente;
5. eliminar Tcl/Tk de packaging solo cuando CI Qt y producción sean estables.

---

# v0.8 — Release Candidate Windows

## Objetivo

Convertir el laboratorio en un cliente instalable mantenible.

## Requisitos

- Qt como UI única;
- identidad visual completa;
- instalador Windows;
- actualización/versionado;
- driver firmado válido;
- WFP certificado funcionalmente;
- logs seguros exportables;
- recuperación/reparación;
- documentación usuario;
- política de privacidad;
- licencia/NOTICE de dependencias;
- SBOM/revisión de paquetes;
- pruebas de instalación/upgrade/uninstall;
- regresión de red.

## No declarar v0.8 estable si falta

- firma válida del driver;
- pruebas reales PROXY por aplicación;
- validación DNS/UDP/QUIC/IPv6 según alcance final;
- comportamiento definido ante caída del túnel.

---

# Orden de trabajo recomendado para el agente

```
v0.7.1 Assets + visual system
       ↓
v0.7.2 Servidores
       ↓
v0.7.3 Aplicaciones
       ↓
v0.7.4 Cuenta
       ↓
v0.7.5 Proxy corporativo
       ↓
v0.7.6 Driver/certificación
       ↓
v0.7.7 Controllers
       ↓
Gate A
       ↓
v0.7.8 Calidad/preferencias
       ↓
Gate B
       ↓
v0.8 RC
```

Cada bloque debe ser un PR pequeño o una secuencia de PRs pequeños. No crear una “mega rama v0.8”.
