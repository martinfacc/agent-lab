# Estados y evidencia

| Estado o fase | Significado | Acción habitual |
| --- | --- | --- |
| `in-progress` | El run declara actividad | Corroborar motor, adaptador y log reciente |
| `paused` / `epic-boundary` | Pausa deliberada entre epics | Esperar aprobación para reanudar |
| `paused` / `escalation` | Bloqueo no resuelto por el worker | Clasificar decisión humana o reparación operativa |
| `deferred` | La story no continuó en este intento | Revisar motivo, orden y trabajo preservado |
| `finished` | El orquestador cerró el run | Verificar tareas, commits e integración |
| `crashed` | Fallo terminal registrado | Preservar evidencia antes de reintentar |

El estado persistido es una afirmación, no prueba de actividad. Para declarar un
run saludable deben coincidir `dev_status`, PID del motor, proceso real del
adaptador, journal/log reciente y story/fase. Un MCP sano o un tmux con shell
inactivo no prueban que Copilot esté trabajando.

Una story solo está terminada cuando existe resultado terminal, commit de
implementación, validación o revisión registrada e integración en la rama destino.
