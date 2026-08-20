# Configurar notificaciones por ntfy

ntfy permite recibir avisos en el teléfono o en un navegador mediante un tópico.
No hace falta crear un bot. Autonomous Agent Lab solamente publica mensajes; no
recibe comandos desde ntfy.

## Datos necesarios

```env
NOTIFY_CHANNELS=ntfy
NOTIFY_PROJECT_NAME=Mi proyecto
NTFY_URL=https://ntfy.sh
NTFY_TOPIC=
NTFY_TOKEN=
```

`NTFY_TOKEN` es opcional. En el servicio público sin autenticación, el nombre
del tópico funciona como secreto: debe ser largo y difícil de adivinar.

## 1. Elegir un tópico seguro

En PowerShell podés generar uno aleatorio:

```powershell
$ntfyTopic = "agent-lab-$([guid]::NewGuid().ToString('N'))"
$ntfyTopic
```

Ejemplo de formato:

```text
agent-lab-8a714f877b75463a840874f865ab72c1
```

No uses nombres previsibles como `proyecto`, `alertas` o el nombre de la
empresa. La documentación de ntfy aclara que, sin autenticación, el tópico se
comporta como una contraseña. Consultá
[Picking a topic](https://docs.ntfy.sh/publish/#picking-a-topic).

## 2. Suscribirse desde el teléfono

1. Instalá ntfy desde la tienda correspondiente o siguiendo la
   [guía oficial para teléfonos](https://docs.ntfy.sh/subscribe/phone/).
2. Abrí la aplicación.
3. Agregá una suscripción.
4. Como servidor usá `https://ntfy.sh`.
5. Pegá exactamente el tópico generado en el paso anterior.

También podés probarlo desde el navegador abriendo:

```text
https://ntfy.sh/TU_TOPICO
```

No compartas esa URL si el tópico no tiene autenticación.

## 3. Probar el tópico antes de configurar Docker

Conservando `$ntfyTopic` de PowerShell:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "https://ntfy.sh/$ntfyTopic" `
  -Headers @{
    Title = "Autonomous Agent Lab"
    Priority = "high"
    Tags = "robot,heavy_check_mark"
  } `
  -Body "Prueba de notificaciones"
```

La aplicación o la web debería mostrar el mensaje. ntfy documenta la
publicación mediante HTTP POST en
[Sending messages](https://docs.ntfy.sh/publish/).

## 4. Completar `.env`

Desde la carpeta `agent-lab`:

```powershell
notepad .env
```

Configuración para el servicio público:

```env
NOTIFY_CHANNELS=ntfy
NOTIFY_EVENTS=paused,awaiting-operator,crashed,finished
NOTIFY_PROJECT_NAME=Nombre reconocible del proyecto
NOTIFY_MONITOR_URL=http://localhost:9121
NTFY_URL=https://ntfy.sh
NTFY_TOPIC=agent-lab-TOPICO_LARGO_Y_ALEATORIO
NTFY_TOKEN=
```

No agregues comillas alrededor de los valores.

## 5. Aplicar la configuración

```powershell
docker compose up -d --force-recreate
docker compose ps
docker compose logs --tail 50 agent-lab
```

En los logs debe aparecer:

```text
Notificaciones externas: ntfy
```

El worker enviará el próximo aviso importante generado por `bmad-loop`. No
reproduce avisos anteriores al arranque.

## Servidor con autenticación

Si usás una instancia de ntfy que requiere un access token:

```env
NTFY_URL=https://ntfy.ejemplo.com
NTFY_TOPIC=agent-lab
NTFY_TOKEN=tk_TOKEN_DE_ACCESO
```

El laboratorio enviará el token mediante el encabezado `Authorization: Bearer`.
La creación y permisos del token dependen del servidor ntfy utilizado; consultá
la [documentación oficial de autenticación](https://docs.ntfy.sh/publish/#authentication).

## Usar ntfy y Telegram juntos

```env
NOTIFY_CHANNELS=telegram,ntfy
```

El mismo evento se enviará a ambos canales.

## Desactivar ntfy

Para conservar Telegram:

```env
NOTIFY_CHANNELS=telegram
```

Para desactivar todos los canales externos:

```env
NOTIFY_CHANNELS=
```

Después recreá el contenedor.

## Problemas frecuentes

### La prueba publica correctamente pero el teléfono no avisa

- Confirmá que la aplicación está suscrita al mismo servidor y tópico.
- Revisá los permisos de notificaciones y ahorro de batería del teléfono.
- Abrí la aplicación para comprobar si el mensaje llegó silenciosamente.

### El servidor devuelve `401` o `403`

El tópico necesita autenticación o `NTFY_TOKEN` es incorrecto. Revisá el token y
sus permisos de escritura.

### El canal aparece activo pero no llegan avisos

```powershell
docker compose logs --tail 100 agent-lab
```

Buscá `Notificación enviada por ntfy` o `No se pudo notificar por ntfy`.

### Se reciben avisos de personas desconocidas

El tópico es fácil de adivinar o se filtró. Generá uno nuevo, cambiá la
suscripción y actualizá `NTFY_TOPIC`.

