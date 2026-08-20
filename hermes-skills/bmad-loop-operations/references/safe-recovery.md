# Recuperación segura

1. Confirmá el `run_id`, estado y logs mediante `agent-control`.
2. Verificá motor, adaptador, journal, Git, worktrees y refs preservadas.
3. Separá decisiones funcionales de fallas operativas.
4. Aplicá la reparación mínima soportada y volvé a verificar.

## Casos frecuentes

- **No se encuentra una story:** confirmá su clave y estado en el
  `sprint-status.yaml` configurado, y luego verificá el artefacto de
  implementación correspondiente. No interpretes la story como una carpeta o
  como una spec independiente y no cambies la fuente del run.
- **Skills ausentes:** restauralas desde la instalación de BMAD Loop dentro del
  contenedor, nunca desde otro proyecto ni mediante un commit al producto.
- **Confianza de Copilot:** confiá solo en el proyecto y worktrees del run.
- **`in-progress` sin worker:** tratá el estado como inconsistente y confirmá PID
  y journal antes de usar controles soportados.
- **Error de worktree:** preservá refs y revisá limpieza, permisos y registros;
  no borres directorios manualmente.
- **Límite de epic:** no es un error; requiere aprobación antes de `dev_resume`.

No uses una resolución automática cuando hay requisitos ambiguos o una decisión
del producto. Presentá opciones al usuario y esperá su elección.
