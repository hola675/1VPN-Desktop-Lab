# OneTunnel v0.6.1 — Proxy de acceso de la red

**Fecha:** 2026-11-19  
**Objetivo:** permitir que OneTunnel se conecte a 1VPN desde redes que obligan a salir mediante un proxy corporativo HTTP CONNECT.

## Flujo

Sin proxy de red:

```
OneTunnel -> servidor 1VPN -> túnel Premium -> Internet
```

Con proxy de red activado:

```
OneTunnel -> proxy corporativo HTTP CONNECT -> servidor 1VPN -> túnel Premium -> Internet
```

El proxy de acceso es distinto del proxy local que OneTunnel expone en 127.0.0.1 y distinto de las credenciales Premium de 1VPN.

## Configuración

En **AVANZADO** aparece:

- **Usar proxy de la red para conectar a 1VPN**
- Host / IP
- Puerto
- Usuario opcional
- Clave opcional

Autenticación soportada inicialmente:

- sin autenticación;
- HTTP Basic.

No se implementan todavía NTLM, Negotiate/Kerberos o PAC/WPAD.

## Seguridad y comportamiento

- La clave del proxy de red vive únicamente en memoria.
- No se guarda en archivos ni aparece en logs.
- Al pulsar CONECTAR se realiza un único preflight CONNECT al servidor 1VPN elegido.
- Si el proxy devuelve 407, OneTunnel informa error de autenticación.
- Si el proxy devuelve otro error, OneTunnel no inicia el motor.
- **No existe fallback directo** cuando esta opción está activada.
- El selector de servidores mide los endpoints 1VPN atravesando el mismo proxy configurado.
- OneTunnel no modifica WinINET, WinHTTP, Wintun ni el proxy global de Windows.
- Mientras la VPN está activa, los campos del proxy de red quedan bloqueados para evitar que la UI muestre una configuración diferente de la que realmente está en uso.

## Ejemplo

Para una red con proxy:

```
Host / IP: 172.16.21.197
Puerto:    3132
Usuario:   (vacío si no requiere)
Clave:     (vacío si no requiere)
```

Activar la casilla y pulsar **CONECTAR**.

## Diagnóstico

Si falla:

- HTTP 407: revisar usuario/clave o método de autenticación requerido.
- HTTP 403: el proxy de red bloqueó CONNECT al destino.
- Timeout: el proxy no responde o no es alcanzable.
- TLS posterior: CONNECT funcionó, pero no se pudo completar TLS con el servidor 1VPN.

La aplicación registra solo la etapa y el tipo de error, nunca la contraseña.

## Limitaciones actuales

La v0.6.1 cubre proxy HTTP CONNECT explícito. No detecta automáticamente proxy del sistema, PAC/WPAD, NTLM o Kerberos. Esas variantes deben añadirse como modos separados para no mezclar credenciales o degradar el comportamiento fail-closed.
