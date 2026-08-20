---
name: bmad-loop-operations
description: Conocimiento operativo base para iniciar, observar, explicar y recuperar ejecuciones de desarrollo BMAD Loop mediante agent-control sin poner en riesgo trabajo preservado.
---

# Operaciones de BMAD Loop

Usá esta skill al iniciar, supervisar, diagnosticar, reanudar, detener o explicar
un desarrollo gestionado por BMAD Loop.

## Modelo mental

- Hermes conversa y coordina mediante `agent-control`; no implementa stories.
- BMAD Loop mantiene el estado del run y orquesta a Copilot como adaptador.
- El checkout principal es la rama destino. Cada story trabaja en un worktree y
  rama temporales que BMAD integra y elimina después de validar.
- MCP, monitor y notificaciones pueden estar vivos aunque BMAD o Copilot no lo estén.

Consultá [references/states-and-evidence.md](references/states-and-evidence.md)
para interpretar estados y [references/safe-recovery.md](references/safe-recovery.md)
antes de resolver un bloqueo.

## Flujo obligatorio

1. Identificá el `run_id` exacto con `dev_runs`.
2. Consultá `dev_status` para ese run: estado, story, fase, intento y pausa.
3. Para diagnosticar, corroborá `dev_log`, procesos, journal y Git.
4. Explicá en español claro qué ocurre y qué debe hacer el usuario.
5. Mutá el run solamente cuando el usuario lo solicite o apruebe.
6. Después de actuar, verificá otra vez estado y evidencia real.

## Reglas de seguridad

- Nunca ejecutes BMAD Loop como `root`; usá el usuario `agent`.
- No reinicies ni reconstruyas el contenedor para resolver un run.
- No borres manualmente worktrees, ramas, runs, commits o refs preservadas.
- No uses `reset --hard`, `clean` ni descarte de cambios como recuperación automática.
- No edites estado, journal o sprint-status para forzar un resultado.
- No introduzcas archivos operativos en commits del proyecto.
- No inicies otro run para el mismo alcance hasta reconciliar el existente.
- No avances una story si una anterior sigue pendiente, escalada o sin commit verificado.
- Preservá el trabajo antes de reparar; ante una decisión funcional, preguntá.

## Comunicación

Informá estado, story/fase, causa en lenguaje simple, trabajo preservado y una
acción segura. Las trazas son evidencia secundaria. No declares una story
terminada sin commit integrado y validaciones comprobadas.

## Memoria

La memoria de Hermes conserva preferencias estables y aprendizajes generales.
No memorices estados, PID, run IDs, ramas, stories actuales o errores transitorios:
consultalos nuevamente mediante `agent-control`.
