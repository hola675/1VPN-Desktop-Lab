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
