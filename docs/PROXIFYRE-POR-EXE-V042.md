# OneTunnel Desktop Lab v0.4.2 beta — PROXY/DIRECTO/BLOQUEAR por ejecutable

**Estado:** descubrimiento de procesos y políticas por archivo .exe implementados. La captura NDIS requiere ProxiFyre y Windows Packet Filter instalados externamente. Guardar PROXY no activa el filtro por sí solo.

## Funcionamiento

- **PROXY:** una regla por ruta absoluta .exe en ProxiFyre, aplicada a todas las instancias/PID de ese ejecutable. Conexiones TCP/IPv4 redirigidas por ProxiFyre + NDISAPI a SOCKS5 local 127.0.0.1:1080, que atraviesa nuestro puente HTTP CONNECT 127.0.0.1:8899 hacia el proxy HTTPS Premium.
- **DIRECTO:** el .exe se excluye expresamente en ProxiFyre. Tráfico normal de Windows.
- **BLOQUEAR:** Windows Defender Firewall, regla saliente exclusivamente para la ruta .exe, aplicada únicamente con confirmación y elevación administrativa. Se puede retirar sin afectar reglas ajenas.
- **Sin política:** no se intercepta.
- Los dominios, direcciones IP y servidores VPN no deciden qué ejecutable se captura.

## Funciones implementadas

1. **APLICACIONES / FIREWALL:** lista de aplicaciones que están en ejecución con nombre, PID(s), ruta .exe y política guardada; refresco manual y cada diez segundos.
2. Selecciona una fila para cargar la ruta real de su ejecutable; elige PROXY, DIRECTO o BLOQUEAR y pulsa **Guardar política**.
3. **Aplicar BLOQUEO** y **Retirar bloqueo** usan reglas Windows Firewall propias, con confirmación explícita, sin tocar política predeterminada ni Wintun.
4. **COMPROBAR SALIDA** en pantalla principal debe verificar IP pública a través del proxy antes de preparar la captura.
5. **PREPARAR PERFIL PROXIFYRE (TCP)** muestra las aplicaciones elegidas y exporta un borrador JSON; no contiene secretos Premium, no sobrescribe la configuración instalada.
6. El borrador contiene appNames con las rutas seleccionadas como PROXY, excludes con los programas DIRECTO y portadores OneTunnel/ProxiFyre/Xray, socks5ProxyEndpoint local, supportedProtocols TCP, supportedAddressFamilies IPv4, dns Direct, bypassLan true.
7. **DIAGNÓSTICO DRIVER/SERVICIO** consulta en modo solo lectura ProxiFyreService y NDISRD.

## Prueba de redirección REAL en Windows

1. Activa OneTunnel Premium y pulsa **COMPROBAR SALIDA** hasta obtener IP pública verificada. Un puerto local abierto no es suficiente.
2. En **APLICACIONES / FIREWALL**, elige una aplicación de prueba .exe en ejecución, guarda PROXY; elige otra como DIRECTO. No uses programas críticos del sistema.
3. Prepara y guarda el borrador ProxiFyre; comprueba cada ruta y puerto.
4. Instala por separado ProxiFyre desde https://github.com/wiresock/proxifyre/releases/latest . Para Windows x64 usa el instalador x64 y verifica su SHA-256 publicada. El instalador oficial gestiona Windows Packet Filter y dependencias cuando corresponda. Requiere permisos administrativos y puede afectar al stack de red: prueba primero en máquina virtual o con plan de recuperación.
5. En la GUI oficial ProxiFyre, crea reglas de enrutamiento por los ejecutables seleccionados; configura SOCKS5 127.0.0.1:1080, transporte TCP, protocolo TCP, familia IPv4 y excepciones del borrador. **No reemplaces directamente** su app-config.json, que podría tener reglas de otras aplicaciones.
6. Pulsa **Validate** y después **Apply & Restart** en ProxiFyre. Confirma estado Running y logs reales de esa aplicación.
7. Prueba el proceso elegido sin configurar variables HTTP_PROXY ni pasarle el parámetro --proxy: verifica su IP de salida y compara con el acceso directo. Validar curl usando --proxy solo prueba el listener, no la redirección transparente.
8. Prueba el proceso DIRECTO y el proceso BLOQUEAR; retira reglas de prueba después. Al detener OneTunnel o ProxiFyre, comprueba específicamente si existe fuga directa; no hay kill switch certificado.

## Limitaciones

- **UDP/QUIC no protegido** por nuestro SOCKS5 porque solo implementa CONNECT TCP. ProxiFyre soporta UDP con proxies adecuados, pero nuestro upstream actual no. No habilitar UDP en este perfil.
- **DNS Direct** en este perfil; puede haber fugas DNS. DoH, WebRTC, IPv6, fragmentación y aplicaciones sin dueño atribuible requieren auditoría. No declarar protección total ni un kill switch.
- **bypassLan true:** las redes privadas siguen directas.
- **Sin catch-all:** nunca incluir una regla de aplicación vacía. No capturar OneTunnel, ProxiFyre, Xray, Python ni procesos críticos.
- Firewall BLOCK y PROXY sobre un mismo .exe pueden interferir. Retira las reglas de bloqueo antes de proxificar; no hay bloqueo a nivel WFP integrado.
- El adaptador local es código propio. ProxiFyre es AGPL-3.0 y NDISAPI requiere controlador WinpkFilter: revisar licencias antes de incorporar binarios o redistribuirlos.
- No se instalan drivers, no se cambia la configuración de Windows, no se inicia el servicio ProxiFyre desde esta versión beta.

## Fuentes

- https://github.com/wiresock/proxifyre
- https://github.com/wiresock/proxifyre/blob/main/docs/configuration.md
- https://github.com/wiresock/proxifyre/blob/main/docs/gui.md
- https://github.com/wiresock/ndisapi
- https://learn.microsoft.com/en-us/windows/win32/api/psapi/nf-psapi-enumprocesses

**Pendiente obligatorio:** certificar en Windows la captura efectiva del .exe elegido, excepción DIRECTO, bloqueo reversible, DNS/UDP y recuperación ante fallos antes de llamar al producto VPN con redirección transparente completa.
