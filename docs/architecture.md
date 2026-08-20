# Arquitectura

```text
Navegador en localhost:9119
            |
          Hermes
            |
      agent-control MCP
         /          \
   bmad-loop      Prime Agent
       |              |
  Copilot CLI    Proveedor Copilot
       |
Repositorio Git privado montado

Informes y logs conservados -> OUTPUT_PATH montado
```

El contenedor también publica un monitor de solo lectura en `localhost:9121`. Lee estados persistidos, logs, procesos y Git, y los transmite al navegador mediante Server-Sent Events; no expone operaciones mutantes.

Un worker de notificaciones observa los archivos `ATTENTION` generados por
`bmad-loop` y, si se habilita desde `.env`, envía esos avisos por Telegram,
ntfy o ambos. El cursor de lectura se guarda en
`OUTPUT_PATH/control/notifications-state.json`, fuera del repositorio, para no
repetir mensajes tras recrear el contenedor. El worker no acepta comandos
remotos desde ntfy y los fallos de red nunca detienen el desarrollo. Para
Telegram, el mismo worker usa long polling y ofrece consultas de solo lectura.
Las operaciones se habilitan por separado, se restringen por chat y requieren
una confirmación temporal. Cada comando queda auditado fuera del proyecto.

La imagen es reemplazable. El proyecto y los resultados son montajes del host; las credenciales y sesiones internas usan volúmenes persistentes. El piloto administra un proyecto por contenedor.

`agent-control` forma parte de este repositorio en `components/agent-control`. El Dockerfile copia su lockfile, instala dependencias y luego copia el código. No existe una clonación remota durante el build.

`agent-control` puede identificar varias ejecuciones, pero la coordinación del alcance es manual. `bmad-loop` se mantiene en `max_parallel = 1`.

## Conocimiento operativo de Hermes

La imagen instala la skill canónica `bmad-loop-operations` de forma idempotente
en `~/.hermes/skills/agent-lab/`, fuera del repositorio montado. Contiene el
modelo estable de estados, evidencia, worktrees, seguridad y recuperación. Los
datos cambiantes de cada ejecución siempre se consultan mediante `agent-control`;
la memoria de Hermes queda reservada para preferencias y aprendizajes generales.

## Resolución de BMAD

El bootstrap utiliza dos modos mutuamente excluyentes:

1. **`project`:** existe `_bmad` sin la marca de Agent Lab. Se valida
   `_bmad/bmm/config.yaml`, se resuelven sus rutas y se comprueban las skills
   automáticas y de revisión. No se modifican sus valores.
2. **`external`:** `_bmad` no existe o lleva la marca de proyección administrada.
   Se materializa `/opt/bmad-distribution` y se aplican las rutas de `.env`.

La materialización es necesaria porque BMAD Loop 0.10 exige un `skill_tree`
relativo al proyecto y copia esa superficie a cada worktree. No es una
instalación del usuario: pertenece al runtime, tiene una marca explícita y se
excluye mediante `.git/info/exclude`.

El bootstrap escribe `/workspace/output/control/bmad-runtime.env` con el origen
y la ruta efectiva de `sprint-status.yaml`. El entrypoint lo carga antes de
iniciar Hermes, por lo que MCP y `agent-control` no dependen de `_bmad-output`.

El repositorio se monta directamente en `/workspace/project`. No existe una rama permanente del laboratorio. `bmad-loop` usa `scm.isolation = "worktree"` y `branch_per = "story"`: cada story trabaja en un checkout y una rama temporales, se integra en la rama seleccionada después de validar y luego se elimina. Los archivos operativos indispensables se excluyen localmente mediante `.git/info/exclude`, por lo que no alteran `.gitignore` ni entran en commits.

La preferencia de modelo de los subagentes se escribe en
`/home/agent/.copilot/settings.json`, dentro del volumen persistente de Copilot.
Por defecto los agentes incorporados heredan modelo, esfuerzo y contexto de la
sesión principal. No se crea `.github/copilot/settings.json` en el proyecto.

## Diagnóstico y recuperación

`lab preflight` es el gate previo a una ejecución. `doctor` diagnostica la
instalación; `preflight` responde si es seguro iniciar desarrollo.

En cada arranque, `run-recovery.py` registra runs no terminales sin motor ni
sesión tmux. La detección no modifica el desarrollo. La recuperación requiere
`lab recover <run-id>` y delega en `bmad-loop resume`, conservando el estado,
worktree y commits del run original.

`lab support-bundle` produce evidencia acotada en `/workspace/output/support`.
La selección de datos usa una lista permitida y redacta valores con apariencia
de secreto antes de escribir el ZIP.

## Política de versiones

Los argumentos de construcción fijan las versiones validadas. Copilot todavía usa la versión npm actual; antes de producción debemos fijar una versión exacta probada y registrar los digests.

`bmad-loop` se instala desde su tag oficial porque no publica paquetes en PyPI.
La imagen también fija `uv`, requerido por los renderers de BMAD 6.11. Prime se
instala mediante su instalador oficial. Ejecutá `lab doctor` después de cada
construcción o actualización.
