# agent-control

Control plane MCP para desarrollo autónomo mediante BMAD/`bmad-loop` e investigación persistente mediante Prime Agent.

Esta copia forma parte del monorepo demostrativo `agent-lab`. El contenedor la instala directamente durante el build.

## Desarrollo local

```bash
npm ci
npm run check
npm start
```

`AGENT_CONTROL_PROJECT_PATH` es obligatorio y apunta al proyecto BMAD administrado. Las demás variables están documentadas en `.env.example`.

Las ejecuciones no se serializan globalmente. `dev_runs` lista sus identificadores; `dev_status` y `dev_log` aceptan un `run_id` opcional. La persona operadora debe evitar alcances superpuestos.
