# Seguridad y limitaciones del piloto

- El puerto 9119 se publica únicamente en el loopback del host. Dentro del contenedor, Hermes también escucha en loopback y un proxy interno une ambos extremos. No cambies el bind de Compose para exponerlo a la red.
- El puerto 9121 del monitor también se limita al loopback. Aunque es de solo lectura, puede mostrar código, comandos, rutas y logs sensibles; no lo publiques en la red sin autenticación.
- El proyecto se monta con escritura. Trabajá sobre un repositorio limpio y con un remoto recuperable.
- Los futuros documentos de entrada deberán usar un montaje separado de solo lectura.
- Guardá los secretos en los almacenes interactivos, en el `.env` excluido de Git o en Docker secrets. `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `NTFY_TOPIC` y `NTFY_TOKEN` deben considerarse sensibles.
- Los avisos externos pueden contener nombres de stories, errores y acciones pendientes. Habilitalos únicamente en chats o tópicos privados. Para ntfy sin autenticación usá un tópico largo e imposible de adivinar.
- El `push` automático, `force push`, borrado de ramas y limpieza destructiva quedan fuera del piloto.
- Revisá los logs antes de compartirlos por si contienen información sensible.
- El paquete de soporte no incluye `.env`, código fuente, credenciales, prompts ni logs completos de sesiones IA. Aun así, revisalo antes de compartirlo fuera del equipo.
- La detección de runs interrumpidos es pasiva; reanudar requiere seleccionar explícitamente un `run-id`.
- `docker compose down -v` elimina credenciales y sesiones, pero no las carpetas montadas del host.
- ntfy es únicamente saliente. Telegram recibe comandos mediante long polling,
  restringe el acceso con `TELEGRAM_ALLOWED_CHAT_IDS` y registra cada intento en
  `OUTPUT_PATH/control/telegram-audit.jsonl`. Las acciones mutantes están
  desactivadas salvo que `TELEGRAM_COMMANDS=controlled`, y aun así requieren un
  código temporal de confirmación. No uses un grupo público como chat autorizado.
