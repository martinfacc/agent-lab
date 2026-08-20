# Configurar notificaciones por Telegram

Este canal permite recibir avisos y consultar el desarrollo desde un chat
privado de Telegram. Usa long polling: el contenedor inicia conexiones salientes
a Telegram y no necesita publicar puertos adicionales.

## Datos necesarios

Al terminar vas a completar estas variables del archivo `.env`:

```env
NOTIFY_CHANNELS=telegram
NOTIFY_PROJECT_NAME=Mi proyecto
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_ALLOWED_CHAT_IDS=
TELEGRAM_COMMANDS=read-only
```

El token y el identificador del chat son secretos. No los subas a Git, no los
copies en tickets y no publiques capturas que los muestren.

## 1. Crear el bot

1. Abrí [@BotFather](https://t.me/BotFather) en Telegram.
2. Enviá `/newbot`.
3. Indicá un nombre visible, por ejemplo `Agent Lab - Proyecto Demo`.
4. Indicá un usuario terminado en `bot`, por ejemplo
   `equipo_agent_lab_bot`.
5. BotFather mostrará el token HTTP API. Guardalo temporalmente; será el valor
   de `TELEGRAM_BOT_TOKEN`.

La creación mediante BotFather y el uso del token están documentados en el
[tutorial oficial de Telegram](https://core.telegram.org/bots/tutorial).

## 2. Iniciar el chat

1. Abrí el enlace del bot que mostró BotFather.
2. Seleccioná **Start** o enviá `/start`.
3. Enviá cualquier mensaje, por ejemplo `prueba`.

Telegram exige que el usuario contacte primero al bot antes de que este pueda
enviarle mensajes privados.

## 3. Obtener el identificador del chat

En PowerShell solicitá el token sin escribirlo directamente en el comando:

```powershell
$telegramToken = Read-Host "Token de Telegram"
```

Consultá las actualizaciones recibidas:

```powershell
$updates = Invoke-RestMethod `
  "https://api.telegram.org/bot$telegramToken/getUpdates"

$updates.result | ForEach-Object {
  $_.message.chat | Select-Object id, type, username, first_name
}
```

El número de la columna `id` es `TELEGRAM_CHAT_ID`. Para un chat privado suele
ser positivo; los grupos y canales pueden usar valores negativos.

Si no aparece ningún resultado, comprobá que enviaste un mensaje al bot después
de crearlo y repetí el comando. La API oficial describe `getUpdates` en la
[referencia de Telegram Bot API](https://core.telegram.org/bots/api#getupdates).

## 4. Probar Telegram antes de configurar Docker

Reemplazá solamente el identificador del chat; el token permanece en la
variable temporal de PowerShell:

```powershell
$telegramChatId = "123456789"

Invoke-RestMethod `
  -Method Post `
  -Uri "https://api.telegram.org/bot$telegramToken/sendMessage" `
  -ContentType "application/x-www-form-urlencoded" `
  -Body @{
    chat_id = $telegramChatId
    text = "Prueba de Agent Lab"
  }
```

Deberías recibir el mensaje inmediatamente. El laboratorio utiliza este mismo
método oficial `sendMessage`.

## 5. Completar `.env`

Desde la carpeta `agent-lab`:

```powershell
notepad .env
```

Completá:

```env
NOTIFY_CHANNELS=telegram
NOTIFY_EVENTS=paused,awaiting-operator,crashed,finished
NOTIFY_PROJECT_NAME=Nombre reconocible del proyecto
NOTIFY_MONITOR_URL=http://localhost:9121
TELEGRAM_BOT_TOKEN=TOKEN_ENTREGADO_POR_BOTFATHER
TELEGRAM_CHAT_ID=123456789
TELEGRAM_ALLOWED_CHAT_IDS=123456789
TELEGRAM_COMMANDS=read-only
```

No agregues comillas alrededor de los valores.

## 6. Aplicar la configuración

```powershell
docker compose up -d --force-recreate
docker compose ps
docker compose logs --tail 50 agent-lab
```

En los logs debe aparecer:

```text
Notificaciones externas: telegram
```

El worker enviará el próximo aviso importante generado por `bmad-loop`. No
reproduce avisos anteriores al arranque.

## 7. Consultar el desarrollo desde Telegram

Con `TELEGRAM_COMMANDS=read-only` están disponibles:

```text
/estado [run_id]
/progreso [run_id]
/logs [run_id]
/runs
/ayuda
```

Si omitís `run_id`, se utiliza el run más reciente. También reconoce preguntas
simples que contengan `estado`, `progreso`, `logs`, `errores` o `qué está
haciendo`. Las respuestas son lecturas deterministas del estado local; no se
envía el texto libre a un modelo ni se habilitan herramientas mutantes.

## 8. Habilitar acciones controladas

Para permitir reanudar, detener o confirmar una story:

```env
TELEGRAM_COMMANDS=controlled
```

Comandos adicionales:

```text
/reanudar [run_id]
/detener [run_id]
/confirmar story_key
```

Ninguna acción se ejecuta inmediatamente. El bot devuelve una confirmación de
un solo uso, por ejemplo:

```text
/confirmar_resume 4821
```

El código vence después de cinco minutos y se elimina al usarlo. `/detener`
solicita una detención ordenada. Una escalación crítica no puede resolverse por
Telegram: debe revisarse desde Hermes o mediante `bmad-loop resolve`.

## Autorizar más de un chat

Separá los identificadores con comas:

```env
TELEGRAM_ALLOWED_CHAT_IDS=123456789,987654321
```

Si la variable queda vacía, solamente se autoriza `TELEGRAM_CHAT_ID`. Los
mensajes de otros chats se ignoran y se registran como intentos no autorizados.

## Usar Telegram y ntfy juntos

```env
NOTIFY_CHANNELS=telegram,ntfy
```

El mismo evento se enviará a ambos canales.

## Desactivar Telegram

Para conservar ntfy:

```env
NOTIFY_CHANNELS=ntfy
```

Para desactivar todos los canales externos:

```env
NOTIFY_CHANNELS=
```

Después recreá el contenedor.

## Problemas frecuentes

### `getUpdates` no devuelve el chat

- Abrí el chat correcto y enviá `/start` y otro mensaje.
- Confirmá que el token pertenece a ese bot.
- Si el bot ya usa un webhook en otro sistema, `getUpdates` no funcionará hasta
  retirar ese webhook.

### El mensaje de prueba devuelve `401 Unauthorized`

El token es incorrecto o fue revocado. Generá uno nuevo desde BotFather y
actualizá `.env`.

### El mensaje devuelve `400 Bad Request: chat not found`

El `TELEGRAM_CHAT_ID` no corresponde a un chat conocido por el bot o el usuario
todavía no inició la conversación.

### El canal aparece activo pero no llegan avisos

```powershell
docker compose logs --tail 100 agent-lab
```

Buscá `Notificación enviada por telegram` o
`No se pudo notificar por telegram`. El worker nunca imprime el token.

### El bot envía avisos pero no responde comandos

- Confirmá que el chat figure en `TELEGRAM_ALLOWED_CHAT_IDS` o coincida con
  `TELEGRAM_CHAT_ID`.
- Revisá que otro programa no esté consumiendo `getUpdates` con el mismo bot.
- Comprobá la auditoría en
  `OUTPUT_PATH/control/telegram-audit.jsonl`.

### Las consultas funcionan pero `/reanudar` está desactivado

El comportamiento es correcto con `TELEGRAM_COMMANDS=read-only`. Usá
`TELEGRAM_COMMANDS=controlled` y recreá el contenedor si querés habilitar
acciones confirmadas.

## Revocar el acceso

Desde BotFather podés revocar el token del bot. Después eliminá
`TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` de `.env`, vaciá
`NOTIFY_CHANNELS` y recreá el contenedor.
