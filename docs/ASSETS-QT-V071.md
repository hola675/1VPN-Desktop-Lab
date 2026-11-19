# Assets OneTunnel Qt v0.7.1 — especificación para agente

Este documento es el contrato para generar e integrar los recursos visuales de OneTunnel.

## Dirección de marca

Conceptos:

- túnel seguro;
- conexión;
- flujo;
- privacidad;
- precisión técnica;
- Windows moderno.

Evitar clichés:

- escudo genérico como único símbolo;
- candado enorme;
- globo terráqueo típico de VPN;
- estética hacker/neón;
- copiar identidades de Proton VPN, NordVPN, Mullvad, Surfshark, Cloudflare u otras marcas.

Personalidad:

**técnica, limpia, confiable, compacta y premium.**

Paleta base existente:

- fondo: `#07111f`;
- superficie: `#0d1a2b`;
- superficie 2: `#12243a`;
- cyan: `#54d7f4`;
- éxito: `#55d6ad`;
- warning: `#f4b860`;
- danger: `#ff7182`;
- texto: `#f4f8ff`.

No generar texto dentro de iconos salvo el wordmark específico.

---

## Estructura de archivos

Crear:

```
desktop_prototype/assets/
  brand/
    onetunnel-mark.svg
    onetunnel-wordmark.svg
    onetunnel-logo-horizontal.svg
    onetunnel-app.ico
    onetunnel-app-256.png
  nav/
    home.svg
    applications.svg
    servers.svg
    account.svg
    settings.svg
    activity.svg
  states/
    connected.svg
    disconnected.svg
    checking.svg
    warning.svg
    blocked.svg
    direct.svg
    proxy.svg
  servers/
    location-pin.svg
    latency.svg
    auto-select.svg
  empty/
    no-apps.svg
    no-servers.svg
    no-account.svg
  README.md
```

No usar nombres con espacios.

---

## 1. Marca

### onetunnel-mark.svg

Formato:

- SVG;
- viewBox cuadrado;
- sin fuentes;
- máximo 3 colores;
- legible a 16×16;
- fondo transparente.

Idea visual preferida:

un corredor/túnel formado por dos trazos que convergen y una línea central/flujo; debe sugerir tránsito protegido sin parecer un candado.

### Prompt base para generador

> Create an original minimal vector brand mark for a Windows privacy/network application named OneTunnel. Abstract tunnel or corridor made from two geometric rails converging into a protected data path, subtle sense of forward flow, precise technical geometry, premium modern software identity, dark-mode first, cyan accent, no shield, no padlock, no globe, no letters, no gradients required, flat vector, transparent background, must remain recognizable at 16px.

El agente debe generar varias opciones, comparar legibilidad a 16/24/32 px y elegir una sola dirección.

### Wordmark

Texto:

`OneTunnel`

Recomendación:

- no depender de una fuente redistribuida dentro del SVG final;
- convertir a paths si el flujo utilizado lo permite y la licencia es válida;
- alternativa preferida: renderizar el nombre con Segoe UI desde Qt y usar solo el mark como asset.

---

## 2. App icon Windows

Generar PNG maestro 1024×1024 o SVG maestro.

Exportar:

- 16×16;
- 20×20;
- 24×24;
- 32×32;
- 40×40;
- 48×48;
- 64×64;
- 128×128;
- 256×256.

Crear `onetunnel-app.ico` multiresolución.

Criterios:

- silueta clara;
- margen interno 10–14%;
- no usar detalle fino;
- funcionar sobre taskbar clara y oscura;
- no depender de transparencia demasiado tenue.

---

## 3. Navegación

Todos los iconos:

- SVG;
- 20×20 viewBox recomendado;
- stroke coherente;
- currentColor o color sustituible por Qt;
- sin sombras;
- máximo 2 px stroke visual.

Semántica:

- home: dashboard/casa abstracta simple;
- applications: ventana/app grid;
- servers: nodos/servidor/location;
- account: usuario;
- settings: sliders, preferible a engranaje genérico si encaja;
- activity: pulso/log.

No mezclar iconos filled y outline.

---

## 4. Estados de tráfico

Necesarios:

- `direct.svg`: ruta abierta/neutra;
- `proxy.svg`: flujo atravesando túnel;
- `blocked.svg`: corte/barrera;
- `connected.svg`: punto/ruta confirmada;
- `checking.svg`: recurso estático que Qt pueda animar;
- `warning.svg`: advertencia.

Color debe venir preferentemente del estado QSS; no hornear todos los colores en el SVG.

---

## 5. Empty states

Ilustraciones pequeñas, no hero art.

Tamaño de diseño aproximado:

- 320×180 SVG/PNG.

Casos:

- no applications;
- no servers measured;
- no Premium account.

Estilo:

- geométrico;
- 2–4 colores;
- bajo contraste;
- no personajes;
- no fotografías;
- no textos incrustados.

El texto explicativo se renderiza en Qt para traducción/accesibilidad.

---

## 6. Assets de aplicaciones Windows

No generar iconos para Chrome, Telegram, VS Code, etc.

El agente debe extraer en runtime el icono del ejecutable instalado mediante APIs Windows/Qt y cachearlo localmente.

Reglas:

- usar el icono del EXE real;
- no descargar logos de Internet;
- fallback a `applications.svg`;
- cache por ruta/hash o timestamp;
- no bloquear UI durante extracción masiva.

---

## 7. Integración Qt

Preferencia:

`qt_resources.qrc` + recursos `:/...`.

Ejemplo conceptual:

```
:/brand/onetunnel-mark.svg
:/nav/home.svg
:/states/proxy.svg
```

Objetivos:

- PyInstaller no depende de rutas de desarrollo;
- assets disponibles en onefile;
- tests validan existencia;
- no leer desde Internet.

El agente puede usar `pyside6-rcc` o una estrategia equivalente documentada.

---

## 8. Generación reproducible

Por cada asset generado con IA, guardar en `desktop_prototype/assets/README.md`:

- nombre del archivo;
- propósito;
- prompt final;
- fecha;
- herramienta/modelo usado, si está disponible;
- transformaciones manuales posteriores;
- confirmación de que no se copió una marca de terceros.

No es necesario guardar borradores descartados en Git.

---

## 9. Validación automática

Añadir tests para comprobar:

- archivos obligatorios presentes;
- SVG parseable;
- sin referencias HTTP/HTTPS dentro de SVG;
- sin scripts;
- sin imágenes externas embebidas;
- tamaño razonable;
- ICO contiene tamaños mínimos requeridos;
- QRC compila;
- PyInstaller incluye assets.

---

## 10. Checklist visual

Antes de aceptar una dirección:

- [ ] marca legible a 16 px;
- [ ] app icon reconocible en taskbar;
- [ ] funciona en fondo claro;
- [ ] funciona en fondo oscuro;
- [ ] iconografía consistente;
- [ ] no parece otra VPN conocida;
- [ ] no contiene texto rasterizado innecesario;
- [ ] no hay assets con copyright dudoso;
- [ ] navegación se entiende sin tooltip;
- [ ] empty states no dominan la UI;
- [ ] EXE empaquetado no pierde recursos.

---

## Entrega recomendada del agente

PR 1: infraestructura de recursos + tests + placeholders vectoriales simples.

PR 2: marca/app icon final.

PR 3: navegación/estados/empty states + integración completa.

Esto facilita revisar diseño sin mezclarlo con cambios de networking.
