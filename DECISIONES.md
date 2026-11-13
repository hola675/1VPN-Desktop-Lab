# Registro de decisiones — 1VPN Desktop Lab

| ID | Fecha | Decisión | Justificación |
| --- | --- | --- | --- |
| DEC-001 | 2026-11-13 | Priorizar las fuentes oficiales GPL-3.0 frente a descompilar el paquete ofuscado. | Mayor auditabilidad y menor riesgo de atribuciones falsas. |
| DEC-002 | 2026-11-13 | Separar proxy de navegador de VPN con TUN. | No prometer un túnel global desde un script PAC. |
| DEC-003 | 2026-11-13 | No incrustar credenciales, tokens ni endpoints de infraestructura ajena en la nueva aplicación. | Evitar filtraciones, acceso no autorizado y rotura por cambios del backend. |
| DEC-004 | 2026-11-13 | Prototipo local en Python puro, sin dependencias externas. | Funciona con el Python 3 instalado en Windows y permite validar arquitectura. |
| DEC-005 | 2026-11-13 | Proxy del sistema como opción *opt-in* con respaldo y recuperación. | Reducir cambios imprevistos y respetar entornos empresariales. |
| DEC-006 | 2026-11-13 | Producción futura: Flutter/Xray-core o Tauri con engine dedicado. | Requiere análisis separado de permisos, TUN, actualizaciones y seguridad. |

## Observaciones de seguridad para QA

- Listener solo en `127.0.0.1`; TLS ascendente con CA del sistema y verificación hostname.
- Las contraseñas solo viven en la memoria del proceso, no en registro, logs ni JSON de recuperación.
- Restitución WinINET al desconectar; si el usuario cambia manualmente el proxy mientras está conectado, el código no pisa la nueva configuración.
- En cierre forzado puede quedar un proxy local inválido; al relanzar se intenta recuperar el estado anterior. Si no es posible, revisar manualmente **Configuración > Red e Internet > Proxy**.
- Primer test en máquina de laboratorio, nunca directamente en la red corporativa/proxy de producción.
| DEC-007 | 2026-11-13 | En v0.2 retirar de la interfaz la opción de cambio WinINET; no tocar Wintun ni DNS, rutas o proxy global. | El usuario prioriza tráfico selectivo a través de `127.0.0.1:puerto`, sin interferir con Wintun instalado. |
| DEC-008 | 2026-11-13 | Agregar puerto fijo configurable (8899 por defecto, 0 automático), comprobar salida por CONNECT explícito y distinguir listener de salida validada. | Evitar el falso positivo «Conectado» cuando solo hay un socket local abierto. |
| DEC-009 | 2026-11-13 | Migración conservadora desde v0.1: advertir sobre respaldos WinINET antiguos y no restaurar cambios ajenos automáticamente. | Preservar las preferencias del usuario y evitar sobrescrituras inesperadas. |
| DEC-010 | 2026-11-13 | No añadir credenciales del proveedor a repositorios públicos, aunque aparezcan en el código fuente oficial. | Evitar exposición y dependencia de credenciales ajenas y facilitar autorización explícita. |

| DEC-011 | 2026-11-13 | Adoptar como referencia técnica ProxiFyre/NDISAPI para redirección transparente opt-in por proceso; descartar `rookmoot/proxifier` como interceptor. | El proyecto rookmoot es un rotador HTTP de scraping, no un controlador de conexiones Windows. |
| DEC-012 | 2026-11-13 | Crear adaptador local SOCKS5 CONNECT -> HTTP CONNECT solo TCP, separado del motor WinINET/Wintun. | ProxiFyre consume SOCKS5 mientras que el laboratorio usa HTTP sobre TLS remoto. UDP no queda cubierto. |

### ADR-012 — Selector Free v0.4.1 (2026-11-13)

- El cliente prioriza Singapur cuando su RTT validado es comparable al mejor (+35 ms).
- Medición con TLS y CONNECT real; no usar ping como único criterio de salud.
- Catálogo público sin credenciales, filtrado por ubicaciones Free y sufijos oficiales conocidos.
- Fallback sólo antes de establecer túnel, sin salida directa y sin duplicar envíos HTTP.
- Se conserva el modo manual y la posibilidad de elegir una región fija.
- Actualizar catálogo/probar upstreams en segundo plano; no habilitar Premium sin autorización.
