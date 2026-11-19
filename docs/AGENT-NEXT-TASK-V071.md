# Agent Handoff — siguiente tarea: OneTunnel v0.7.1

Este documento es el punto de entrada para continuar después de v0.7 Qt Preview.

## Resultado esperado

Entregar una UI Qt visualmente coherente y con assets propios, sin cambiar el comportamiento de red.

No tocar algoritmos de:

- autenticación;
- selección de servidores;
- proxy de acceso;
- WFP;
- driver;
- certificación.

Si una necesidad visual exige cambiar backend, detener esa parte y abrir una tarea separada.

---

# PR 1 — Infraestructura de assets

Rama sugerida:

`feat/qt-assets-infrastructure-v071`

## Implementar

1. Crear estructura de `desktop_prototype/assets/` definida en `ASSETS-QT-V071.md`.
2. Crear recursos vectoriales placeholder originales mínimos si todavía no existen assets finales.
3. Añadir `qt_resources.qrc`.
4. Generar módulo/resources de Qt de forma reproducible en build.
5. Añadir helper para cargar SVG/iconos desde `:/...`.
6. Integrar icono de ventana/aplicación.
7. Hacer que PyInstaller incluya los recursos.
8. Añadir tests:
   - recursos obligatorios;
   - SVG seguro;
   - QRC compilable;
   - smoke PyInstaller.

## No hacer en PR 1

- no rediseñar todas las páginas;
- no cambiar NetworkEngine;
- no tocar WFP;
- no borrar Tkinter.

## Gate

CI estable + Qt PASS.

---

# PR 2 — Identidad visual

Rama sugerida:

`feat/onetunnel-brand-assets-v071`

## Generar

Siguiendo `docs/ASSETS-QT-V071.md`:

- mark;
- app icon;
- logo horizontal si aporta valor;
- navegación;
- estados.

El agente puede usar su herramienta de generación visual disponible.

## Proceso

1. Generar 3–5 variantes del mark.
2. Evaluarlas a 16/24/32/64 px.
3. Eliminar variantes que:
   - parezcan candado/escudo genérico;
   - se confundan con otra marca;
   - pierdan forma a 16 px.
4. Elegir una dirección.
5. Normalizar SVG.
6. Crear ICO multiresolución.
7. Documentar prompt final y procedencia en `assets/README.md`.
8. Integrar en Qt.

## Gate

Capturas locales a:

- 1366×768, 100%;
- 1920×1080, 125%;
- al menos una prueba 150%.

No usar screenshots como assets finales.

---

# PR 3 — Integración v0.7.1

Rama sugerida:

`feat/qt-visual-system-v071`

## Implementar

### Sidebar

- mark OneTunnel;
- iconos de:
  - Inicio;
  - Aplicaciones;
  - Servidores;
  - Cuenta;
  - Ajustes;
  - Actividad;
- estado seleccionado coherente;
- tooltips opcionales.

### Página Servidores

Crear sexta página real.

Debe mostrar:

- Automático;
- ubicaciones disponibles;
- región;
- RTT;
- estado de medición;
- seleccionado;
- última medición.

Usar `AutoSelector`; no duplicar selección en la UI.

### Inicio

Añadir:

- estado visual de conexión;
- cuenta;
- servidor;
- RTT;
- IP;
- acceso directo/proxy;
- resumen de políticas:
  - DIRECTO;
  - PROXY;
  - BLOQUEAR.

### Empty states

Integrar recursos especificados, sin texto dentro de las imágenes.

### Estados

Todos los botones asíncronos deben impedir doble ejecución mientras estén ocupados.

---

# Criterios de aceptación v0.7.1

Todos obligatorios:

- [ ] Qt abre con assets embebidos.
- [ ] No hay rutas absolutas de assets.
- [ ] EXE onefile muestra iconos correctamente.
- [ ] Página Servidores funcional.
- [ ] Inicio conserva conectar/verificar/scan.
- [ ] Aplicaciones conserva políticas/WFP.
- [ ] Cuenta conserva Premium bridge.
- [ ] Ajustes conserva proxy corporativo.
- [ ] Ninguna credencial persiste.
- [ ] No hay fallback directo nuevo.
- [ ] Stable Tkinter CI sigue PASS.
- [ ] Qt CI PASS.
- [ ] 187+ pruebas existentes siguen verdes.
- [ ] Nuevas pruebas de assets verdes.
- [ ] PR fusionado.
- [ ] rama temporal eliminada.

---

# Commits

Preferir commits pequeños:

```
feat(assets): add Qt resource pipeline
test(assets): validate safe embedded resources
feat(brand): add original OneTunnel mark and app icon
feat(qt): integrate navigation icon system
feat(qt): add Servers page
feat(qt): polish dashboard states
docs(assets): record prompts and provenance
```

No usar un único commit “redesign everything”.

---

# Después de v0.7.1

Continuar estrictamente con:

`docs/ROADMAP-QT-V071-V080.md`

Siguiente fase: **v0.7.2 — Servidores y selección visual**.
