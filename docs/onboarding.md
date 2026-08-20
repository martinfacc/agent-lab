# Incorporación de integrantes

1. Habilitá en Docker Desktop el acceso a `PROJECT_PATH` y `OUTPUT_PATH`.
2. Confirmá que la organización permita GitHub Copilot CLI.
3. Copiá `.env.example` como `.env`; nunca lo subas a Git.
   Conservá `LAB_MODE=development` si solo necesitás desarrollo. Usá `LAB_MODE=full` y definí `RESEARCH_MODEL` para incluir Prime.
   Si querés avisos remotos, completá Telegram o ntfy y agregá el canal en
   `NOTIFY_CHANNELS`. Si queda vacío, no se realiza ninguna conexión externa.
4. Ejecutá `docker compose build` y `docker compose up -d`.
5. Ejecutá `docker compose exec -it agent-lab lab setup` desde PowerShell.
6. Completá los accesos de GitHub, Copilot, Prime y Hermes con tu propia cuenta.
   En Hermes elegí `GitHub Copilot`, luego `GitHub Copilot` (no ACP) y finalmente un modelo disponible, recomendado `claude-sonnet-5`.
7. Ejecutá `docker compose up -d` y `docker compose exec agent-lab lab doctor`.
8. Ejecutá `docker compose exec agent-lab lab preflight` y confirmá que finalice con `LISTO PARA DESARROLLAR`.

Si Docker se reinició durante un desarrollo, usá `lab runs` para detectar el
run interrumpido y `lab recover <run-id>` para reanudar exactamente ese run. El
laboratorio nunca toma esa decisión automáticamente.

Para pedir asistencia, generá `lab support-bundle`. El archivo queda en la
carpeta de salida y no incluye el repositorio ni las credenciales.

El laboratorio usa como destino la rama seleccionada en `PROJECT_PATH` y no crea una rama permanente. Durante el desarrollo, `bmad-loop` crea worktrees y ramas temporales por story y los elimina después de integrarlos. Los archivos locales requeridos se excluyen mediante `.git/info/exclude` y no se versionan. El proyecto se agrega automáticamente a `trustedFolders` de Copilot porque es el alcance elegido por el usuario; no se confía en ninguna otra ruta del host.

No hace falta instalar BMAD en el repositorio. Si ya existe `_bmad`, el
laboratorio lo valida y respeta. Si no existe, usa la distribución incluida en
Docker. En este segundo caso, `BMAD_OUTPUT_DIR` y las rutas opcionales de
planificación e implementación se configuran en `.env` antes de iniciar.

Las credenciales no se incluyen en la imagen. Copilot CLI reutiliza la autenticación de GitHub CLI y el onboarding valida el acceso con una consulta breve; no abre un segundo callback OAuth.

Si la empresa intercepta TLS, instalá su certificado mediante una imagen derivada controlada. No deshabilites la verificación TLS.
