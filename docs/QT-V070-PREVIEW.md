# OneTunnel v0.7 — Qt / PySide6 Preview

**Estado:** preview paralelo; no reemplaza todavía a la UI estable Tkinter v0.6.1.

## Objetivo

Migrar la capa visual a PySide6/Qt manteniendo intactos los motores existentes:

- cuenta Premium;
- proxy de acceso de red;
- selección de servidores;
- HTTP CONNECT + SOCKS5 local;
- políticas por aplicación;
- bloqueo WFP nativo;
- PROXY WFP transparente;
- ciclo de vida del driver firmado.

## Arquitectura

```
PySide6 / Qt UI
    |
    +-- Inicio
    +-- Aplicaciones
    +-- Cuenta
    +-- Ajustes
    +-- Actividad
    |
    +--> NetworkEngine / AutoSelector / AccessProxy
    +--> PremiumBrowserBridge / AccountClient
    +--> PolicyStore / RunningApps
    +--> NativeWfpGuard / NativeProxySession / SignedDriverLifecycle
```

La UI Qt no importa Tkinter ni llama al frontend antiguo. Reutiliza directamente los módulos de backend.

## Funciones ya operativas en Preview

### Inicio
- CONECTAR / DESCONECTAR.
- ubicación automática / región / manual.
- cuenta activa.
- IP de salida verificada.
- medición del mejor servidor.
- estado de acceso: directo o proxy corporativo.

### Aplicaciones
- lista de procesos en ejecución;
- PID e instancias;
- guardar DIRECTO / PROXY VPN / BLOQUEAR por nombre .exe;
- aplicar/retirar BLOQUEO WFP;
- activar/detener sesión PROXY WFP para reglas guardadas.

### Cuenta
- Premium web mediante Browser Companion;
- puerto y código temporal con copia separada;
- abrir 1vpn.org/account;
- login clásico Email/2FA como alternativa;
- sesión solo en memoria.

### Ajustes
- proxy de acceso corporativo HTTP CONNECT;
- servidor manual;
- credenciales proxy 1VPN;
- puertos HTTP/SOCKS5;
- consulta del estado del callout firmado.

### Actividad
- registro seguro del frontend/backend;
- sin contraseñas/tokens.

## Build

La preview se empaqueta como:

`OneTunnel-Qt-Preview.exe`

CI publica:

`OneTunnel-v0.7-qt-preview-win-x64`

La UI estable sigue publicándose en un artefacto distinto.

## Criterio para reemplazar Tkinter

Qt no será el frontend principal hasta que se certifiquen:

1. conexión Premium real;
2. proxy corporativo real;
3. selección/medición;
4. cuenta Premium web;
5. DIRECTO/BLOQUEAR/PROXY por aplicación;
6. driver firmado;
7. certificación WFP;
8. cierre y recuperación ante fallos;
9. DPI 100/125/150/200%;
10. Windows 11 claro/oscuro y múltiples resoluciones.

## Siguiente fase v0.7.1

- iconos propios y branding;
- estados animados de conexión;
- vista de servidores con latencia;
- iconos de aplicaciones Windows;
- diálogo de driver firmado en Qt;
- certificación WFP desde Qt;
- persistencia segura de preferencias NO sensibles;
- eliminar duplicación de lógica UI mediante un AppController compartido.
