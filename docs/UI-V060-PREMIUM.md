# OneTunnel v0.6 — Premium UI

**Fecha:** 2026-11-19  
**Objetivo:** “simple por fuera, completo por dentro”.

La v0.6 no sustituye el motor v0.5.5; reorganiza la experiencia alrededor de tareas del usuario y mantiene Premium, WFP, driver firmado, relay, certificación y políticas por aplicación por debajo.

## Principios

1. La pantalla principal responde primero: ¿estoy conectado?, ¿qué cuenta uso?, ¿qué ubicación?, ¿qué IP de salida?, ¿qué servidor?
2. Los detalles técnicos no desaparecen: se mueven a **Avanzado** y **Actividad**.
3. La ventana de aplicaciones separa:
   - **Aplicaciones**: DIRECTO / PROXY VPN / BLOQUEAR.
   - **Motor WFP**: sesión PROXY, driver, instalación, firma y compatibilidad.
   - **Diagnóstico**: certificación transparente y limpieza de reglas heredadas.
4. La cuenta prioriza **Premium web**; Email/2FA y diagnóstico quedan como alternativas.
5. Estados visuales deben representar el motor real. “Conectado” no sustituye la verificación de salida.
6. No se agregan dependencias ProxiFyre/Windows Firewall ni se cambia la arquitectura nativa.

## Inicio

La primera pantalla contiene:

- OneTunnel + versión.
- Estado de conexión.
- Botón CONECTAR / DESCONECTAR.
- Ubicación.
- Resumen de cuenta.
- Tarjetas SALIDA, SERVIDOR y MOTOR.
- Acciones APLICACIONES, VERIFICAR SALIDA, ELEGIR MEJOR SERVIDOR.
- AVANZADO: servidor manual, credenciales proxy, puertos locales y copiar proxy local.
- ACTIVIDAD: registro seguro.

La IP verificada aparece directamente en la tarjeta SALIDA.

## Aplicaciones

La tarea primaria se centra en nombres .exe:

- DIRECTO.
- PROXY VPN.
- BLOQUEAR.
- Guardar política.
- Lista de apps en ejecución.
- Reglas guardadas.

El usuario no necesita ver instalación de driver para cambiar una política. El ciclo del motor vive en otra pestaña.

## Cuenta

Orden de pestañas:

1. Premium web.
2. Email / 2FA.
3. Diagnóstico.

Premium web explica consentimiento y privacidad antes de abrir el bridge.

## Estilo

- Fondo oscuro azul profundo.
- Superficies escalonadas con borde discreto.
- Acento cyan.
- Verde para éxito.
- Ámbar para advertencia.
- Rojo para acciones destructivas.
- Segoe UI y Consolas solo para datos técnicos.
- Botones y tablas reutilizan ui_theme.py.

## Validación

CI debe:

- compilar todos los módulos;
- ejecutar suite completa;
- abrir la pantalla principal;
- verificar que Avanzado y Actividad arrancan ocultos;
- abrir Aplicaciones;
- abrir Cuenta;
- compilar WFP user-mode, probe y callout;
- empaquetar EXE;
- smoke test del EXE.

## Fuera de alcance

La v0.6 no convierte por sí sola el paquete kernel unsigned en instalable, no añade UDP/DNS/QUIC/IPv6 ni cambia los gates de firma/certificación del motor.
