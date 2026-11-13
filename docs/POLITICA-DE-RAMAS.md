# Política de ramas y entregas — 1VPN Desktop Lab

**Vigencia:** 2026-11-13 · **Rama estable:** `main`

## Regla acordada

1. Cada tarea de desarrollo se realiza en una rama **temporal** (por ejemplo, `feature/motor-transparente` o `fix/... `); no se hacen cambios experimentales directamente en `main`.
2. Ejecutar pruebas automáticas y revisión de seguridad antes de integrar cambios; para funcionalidades que tocan red, firewall o drivers, la validación Windows es obligatoria.
3. Crear Pull Request con destino `main`, revisar y fusionar.
4. Tras la fusión, borrar la rama temporal (si tiene todo su historial incorporado). El flujo `.github/workflows/cleanup-merged-branches.yml` automatiza la limpieza después de actualizar `main`.
5. Al finalizar una tarea, comprobar que **solo queda `main`**.

## Protección contra pérdida de trabajo

- El mantenimiento **no elimina ramas con commits sin integrar en `main`**. Una rama pendiente necesita revisión, fusión o decisión explícita antes de su eliminación.
- El flujo comprueba `git merge-base --is-ancestor` para evitar borrar cambios que no se hayan fusionado.
- No modificar el proxy de Windows, Wintun, rutas, DNS o el firewall como parte de estas tareas de higiene.
- Si el GitHub Actions Token carece de `contents:write`, revisar el fallo y eliminar manualmente las ramas fusionadas. No usar `force push`.

## Verificación

```powershell
git fetch --prune origin
git branch -r
gh pr list --state open
```

Cuando el job no pueda ejecutar la eliminación, y **solo después de confirmar que la rama fue fusionada**:

```powershell
git push origin --delete feature/local-proxy-v0.2
git fetch --prune origin
git branch -r
```

El repositorio opera sobre `main`; las ramas de trabajo existen únicamente mientras se desarrolla una tarea activa.
