# Protocolo local/remoto de agentes y diagnóstico de HTTP 403 — v0.4.1c

**Propósito:** una sola rama permanente: `main`. Ramas temporales solo mientras contienen trabajo activo. En ningún caso perder commits sin integrar.

## Hallazgo confirmado

El cliente de cuenta en `desktop_prototype/account_auth.py` usa el contrato **Android/Xray** del repositorio oficial:

- `POST https://1vpn.org/api/login/?type=xray` (respaldo solo sobre dominios aprobados).
- Cabeceras: `Content-Type: application/json`, `Client-Type: app`, `Accept: application/json`.
- JSON en el cuerpo: claves `email` (correo), `password` (contraseña literal), y `token` **solo cuando se aporta 2FA**.
- La contraseña de la cuenta no se envía como la clave del proxy HTTPS, que es otro sistema.

Una respuesta HTTP 403 **no demuestra una contraseña incorrecta**. Se necesita clasificar la forma del JSON de respuesta: `code` numérico, `error`/`detail` tipo texto y si existe `code=1001` para solicitar 2FA. Los valores literales del cuerpo **no se guardan ni se comparten**. Ante un 403 genuino se muestra `forbidden`, no `rejected` como si se conociera la causa precisa. Un 429 genuino se informa como `rate_limited`.

## Reparto de archivos y exclusión mutua

| Responsable | Archivos principales | Prohibido modificar en paralelo |
|---|---|---|
| Agentes locales Kilo/VS Code | `desktop_prototype/account_panel.py`, UX responsive y pruebas de GUI nuevas | `account_auth.py`, `tests/test_account_auth.py` mientras está activa la revisión remota |
| Revisor remoto ChatGPT | `desktop_prototype/account_auth.py`, `tests/test_account_auth.py`, este documento | `account_panel.py` mientras el agente local construye la interfaz |

Cada agente usa una rama temporal diferente. No hacer `push --force`, no trabajar directamente en `main`, no eliminar ramas que tengan commits exclusivos. No lanzar scripts que cambien Wintun, rutas, firewall, DNS, proxy WinINET o credenciales.

## Entrada al trabajo local (PowerShell 7)

```powershell
cd D:\Proyectos\1VPN-Desktop-Lab
git status --short
git fetch --prune origin
git switch main
git pull --ff-only origin main
git switch -c work/auth-403-visual-local
```

Si `git status` no está limpio, detener el cambio de rama y crear un commit o respaldo antes. El agente local no debe modificar los archivos que el revisor remoto está tocando.

## Tareas exactas para el agente local

1. Validar con captura o ejecución real en Windows el formulario de 640×540 y mínimo 570×500, fuentes/DPI al 100/125/150%, tabulación, foco y scroll de diagnósticos.
2. Mostrar en el registro los eventos ya recibidos por `AccountPanel._show_diagnostic`. El módulo remoto emitirá `POST JSON: email, password, token(2FA)` (sin valores) y `HTTP 403 · JSON code:int, detail:str · código API N` cuando corresponda.
3. Añadir opción explícita de **copiar informe sanitizado** que copie exclusivamente marcas de tiempo, host permitido, HTTP, código numérico y tipos de campos. No copiar contenido arbitrario de la API, ni valores de `email`, `password`, `token`, `sessionAuthToken`.
4. Probar localmente contra transportes simulados: respuesta 403 genuina, 403 HTML, 401, 429, 1001 2FA, timeout TLS y 200 con sesión falsa. Ninguna prueba real necesita credenciales.
5. **No** automatizar reintentos frente a 403/429 y no deshabilitar TLS/certificados. Evitar registrar mensajes literales de error que podrían contener datos personales.

## Pruebas y entrega local

```powershell
cd D:\Proyectos\1VPN-Desktop-Lab\desktop_prototype
py -3 -m unittest discover -s tests -v
py -3 -m compileall -q .
cd ..
git diff --check
git status --short
git add desktop_prototype/account_panel.py desktop_prototype/tests/test_account_panel.py
git diff --cached --stat
git commit -m "fix(auth-ui): mostrar diagnóstico 403 seguro y validar disposición"
git push -u origin work/auth-403-visual-local
```

Ajustar las rutas del `git add` a los archivos creados realmente. No agregar secretos ni logs reales. **No hacer merge automático antes de que se valide la CI.**

## Sincronización tras cada entrega

1. El revisor abre PR desde la rama que termina a `main`; ejecuta CI Windows y revisión de cambios sensibles; fusiona cuando pase.
2. El workflow `cleanup-merged-branches.yml` elimina ramas cuyo **commit** ya es ancestro de `main`; el agente local hace `git fetch --prune origin`.
3. Si el agente local tiene trabajo sin fusionar al mismo tiempo, terminar el commit local y luego:
   ```powershell
   git fetch origin
   git switch work/auth-403-visual-local
   git rebase origin/main
   git push --force-with-lease origin work/auth-403-visual-local
   ```
   `--force-with-lease` solo si no hay otros autores trabajando en esa misma rama temporal; de lo contrario, integrar `main` mediante `git merge origin/main`.
4. Tras la fusión del PR local y su limpieza en GitHub:
   ```powershell
   git switch main
   git pull --ff-only origin main
   git fetch --prune origin
   git branch -d work/auth-403-visual-local
   git branch -a
   ```
5. Una rama divergente con commits exclusivos, por ejemplo `work/enforce-app-policies`, **no se elimina** sin revisión explícita y preservación de esos commits; dejar solo `main` requiere integrar o archivar conscientemente ese trabajo.

## Diagnóstico seguro a entregar al revisor

```text
Ambiente: Windows 11 / Python (versión)
Método: POST
Ruta: /api/login/?type=xray
Claves enviadas: email:str, password:str, token:str (si hubo 2FA)
Respuesta: HTTP 403
Esquema JSON: code:int, error:str, detail:str (lo que realmente se reciba)
Código API: 1001 / otro entero / ausente
Resultado: forbidden / two_factor_required / rejected / unavailable
```

No compartir capturas de cuerpos JSON originales, credenciales, URL con parámetros privados, headers `Authorization`, cookies, tokens ni logs con correo. Si se requiere inspección local extraordinaria del mensaje literal del servidor, mantenerla fuera de GitHub/ChatGPT y redaccionar manualmente cualquier dato personal antes de compartir conclusiones.

## Referencias técnicas

- Android API: https://github.com/1vpn/app/blob/main/lib/onevpn/data/account_api.dart
- Transporte: https://github.com/1vpn/app/blob/main/lib/onevpn/net/api_transport.dart
- Política de ramas: `docs/POLITICA-DE-RAMAS.md`
