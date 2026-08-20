# Autonomous Agent Lab

Piloto portable en un único contenedor para desarrollo autónomo sobre
artefactos BMAD. Integra Hermes, `agent-control`, `bmad-loop` y GitHub Copilot
CLI. La investigación persistente con Prime Agent es opcional.

## Seguridad del piloto

- El panel web se publica únicamente en `http://localhost:9119`.
- El monitor de solo lectura se publica únicamente en `http://localhost:9121`.
- El agente trabaja sobre la rama que el usuario tenga seleccionada.
- El `push` continúa siendo una acción humana.
- Las credenciales nunca se incluyen en la imagen.
- Los informes y logs se guardan en una carpeta normal de la computadora.
- `bmad-loop` permanece en `max_parallel = 1`.
- Hermes recibe una skill base versionada para comprender estados, worktrees y recuperaciones seguras de BMAD Loop desde la primera sesión.

## Requisitos

- Docker Desktop con Compose v2.
- Un repositorio Git con los artefactos de planificación e implementación que
  usará el desarrollo. No necesita tener BMAD instalado.
- Una cuenta de GitHub con acceso al repositorio.
- Una suscripción de GitHub Copilot con Copilot CLI habilitado.
- Recomendado: 8 GB de RAM libres, 4 núcleos y 20 GB de disco libres.

## Inicio rápido

1. Copiá `.env.example` como `.env` y completá las rutas y la identidad Git.
   En Windows usá barras `/` y no agregues comillas. `RESEARCH_MODEL` sólo se
   configura si elegís `LAB_MODE=full`.
2. Creá la carpeta indicada por `OUTPUT_PATH`.
3. Construí y autenticá:

```console
docker compose build
docker compose up -d
docker compose exec -it agent-lab lab setup
```

4. Validá:

```console
docker compose exec agent-lab lab doctor
```

Antes de iniciar el primer desarrollo, ejecutá:

```console
docker compose exec agent-lab lab preflight
```

El resultado termina en `LISTO PARA DESARROLLAR` o enumera correcciones
concretas. Comprueba Git limpio, acceso al remoto, GitHub, Copilot, artefactos
BMAD, servicios locales y espacio disponible.

Abrí `http://localhost:9119`.

Para observar runs, procesos, Git y logs actualizados cada dos segundos, abrí `http://localhost:9121`. El monitor es de solo lectura y no puede iniciar, detener ni reanudar ejecuciones.

## Organización

```text
agent-lab/
├── components/agent-control/   # Control plane MCP incluido
├── docs/                       # Arquitectura, onboarding y seguridad
├── scripts/                    # Configuración, diagnóstico y arranque
├── Dockerfile
└── compose.yaml
```

El build copia `components/agent-control` directamente. No clona otro repositorio.

## Datos externos

| Ruta del host | Ruta del contenedor | Propósito |
|---|---|---|
| `PROJECT_PATH` | `/workspace/project` | Repositorio Git de trabajo |
| `OUTPUT_PATH` | `/workspace/output` | Informes, logs y estado de control |

```text
OUTPUT_PATH/
├── control/research/runs/<run-id>/
├── development/logs/
└── research/
```

El checkout indicado por `PROJECT_PATH` se monta directamente en `/workspace/project`. El laboratorio no crea una rama permanente propia. `bmad-loop` crea un worktree y una rama temporal por story, integra los commits validados en la rama seleccionada y elimina ambos al terminar.

`bmad-loop` necesita algunos archivos locales dentro del proyecto. Se excluyen mediante `.git/info/exclude`, sin modificar `.gitignore`, y nunca forman parte de los commits. El proyecto se registra como carpeta confiable de Copilot en su volumen persistente para evitar diálogos que bloquearían la ejecución autónoma.

### BMAD propio o provisto por el laboratorio

El repositorio no necesita instalar BMAD para usar el laboratorio:

- Si contiene `_bmad/bmm/config.yaml`, el arranque valida esa instalación y
  respeta sus módulos, personalizaciones y rutas de artefactos.
- Si no contiene `_bmad`, la imagen proyecta su distribución BMAD en tiempo de
  ejecución. `_bmad` y las skills proyectadas quedan excluidas localmente de Git.
- Si existe `_bmad` pero está incompleto o es inválido, el contenedor se detiene
  con el motivo concreto; nunca instala otra versión por encima.

La imagen controla internamente la versión compatible de BMAD Method. Esa versión
no forma parte de la configuración del usuario ni impone una instalación sobre el
repositorio.

El equipo sólo debe garantizar que existan los artefactos que consumirá el
desarrollo. Esto incluye `sprint-status.yaml`, las especificaciones de las
stories pendientes y los documentos de planificación que esas stories usen.
Sus ubicaciones se indican desde `.env`:

```env
BMAD_OUTPUT_DIR=docs/bmad
BMAD_PLANNING_ARTIFACTS_DIR=docs/bmad/planning
BMAD_IMPLEMENTATION_ARTIFACTS_DIR=docs/bmad/development
```

Las rutas son relativas al proyecto. Si las dos últimas quedan vacías se
derivan de `BMAD_OUTPUT_DIR`. El archivo `sprint-status.yaml` debe estar dentro
de `BMAD_IMPLEMENTATION_ARTIFACTS_DIR`. `agent-control` recibe automáticamente
esa ubicación; no asume que exista `_bmad-output`.

La política conserva `max_parallel = 1` dentro de cada run. El aislamiento por story evita que distintas ejecuciones coordinadas por `agent-control` compartan archivos o el índice Git.

Las credenciales y sesiones se mantienen en volúmenes Docker. Recrear el contenedor no las elimina. `docker compose down -v` **sí elimina esos volúmenes**.

## Git privado

`lab setup` ejecuta `gh auth login` y `gh auth setup-git`. El contenedor configura
`core.autocrlf=input`.

Cuando una herramienta necesita abrir GitHub, el contenedor muestra una URL para abrir manualmente en el navegador de Windows. No intenta ejecutar un navegador gráfico dentro de Docker.

Si necesitás repetir una autenticación puntual:

```console
docker compose exec -it agent-lab lab login-github
docker compose exec -it agent-lab lab login-copilot
docker compose exec -it agent-lab lab login-prime
docker compose exec -it agent-lab lab setup-hermes
```

Revisá y publicá los cambios manualmente:

```console
docker compose exec agent-lab git status
docker compose exec agent-lab git push
```

## Proveedores

`LAB_PROVIDER=copilot` es el valor predeterminado para desarrollo. No hace falta
configurar Prime ni OpenCode. En modo `full`, Prime usa
`RESEARCH_PROVIDER=github-copilot` y requiere un `RESEARCH_MODEL` disponible en
la suscripción del usuario.

## Modos

El modo predeterminado es desarrollo:

```env
LAB_MODE=development
```

Registra solamente las herramientas de desarrollo y no solicita configurar Prime ni un modelo de investigación. Para habilitar todo:

```env
LAB_MODE=full
RESEARCH_MODEL=MODELO_HABILITADO
```

Después de cambiar el modo, recreá el contenedor y ejecutá `lab setup`.

Copilot CLI reutiliza la sesión de GitHub CLI, por lo que el onboarding no ejecuta un segundo OAuth con callback local. Prime y Hermes conservan sus propios mecanismos de configuración. La investigación comienza con un presupuesto conservador de 30.000 tokens.

## Operación

```console
docker compose logs -f
docker compose stop
docker compose start
docker compose exec agent-lab lab doctor
docker compose exec agent-lab lab shell
```

### Recuperar una ejecución interrumpida

Al arrancar, el laboratorio detecta runs que estaban en progreso pero perdieron
su proceso por un reinicio de Docker. Nunca los reanuda automáticamente ni crea
un run reemplazante:

```console
docker compose exec agent-lab lab runs
docker compose exec agent-lab lab recover 20260820-162654-532a
```

Un run pausado en un gate de BMAD no se clasifica como interrumpido.

### Paquete de diagnóstico

```console
docker compose exec agent-lab lab support-bundle
```

El ZIP queda bajo `OUTPUT_PATH/support/`. Incluye versiones, configuración no
sensible, validación BMAD, estado de Git, worktrees, procesos y un resumen del
run más reciente. Excluye el código fuente, `.env`, credenciales, prompts y logs
completos de las sesiones de IA.

## Notificaciones opcionales

El laboratorio puede avisar cuando un run se pausa, necesita una acción humana,
falla o termina. Telegram también permite consultar el estado y, opcionalmente,
ejecutar acciones con confirmación. Los canales están desactivados por defecto y
se habilitan solamente desde `.env`; no se agrega ningún archivo al proyecto
montado.

Telegram:

```env
NOTIFY_CHANNELS=telegram
NOTIFY_PROJECT_NAME=Mi proyecto
TELEGRAM_BOT_TOKEN=TOKEN_DEL_BOT
TELEGRAM_CHAT_ID=ID_DEL_CHAT
TELEGRAM_ALLOWED_CHAT_IDS=ID_DEL_CHAT
TELEGRAM_COMMANDS=read-only
```

Creá el bot con `@BotFather`, abrí una conversación con él y enviá `/start`
antes de usarlo. No compartas ni publiques el token.

ntfy:

```env
NOTIFY_CHANNELS=ntfy
NOTIFY_PROJECT_NAME=Mi proyecto
NTFY_URL=https://ntfy.sh
NTFY_TOPIC=un-topico-largo-y-dificil-de-adivinar
NTFY_TOKEN=
```

También podés activar ambos con `NOTIFY_CHANNELS=telegram,ntfy`. El listado
predeterminado de eventos es `paused,awaiting-operator,crashed,finished`.

Manuales completos:

- [Configurar Telegram](docs/configurar-telegram.md)
- [Configurar ntfy](docs/configurar-ntfy.md)

## Modelos de subagentes de Copilot

Los subagentes conocidos de Copilot heredan por defecto el modelo, esfuerzo y
contexto de la sesión principal:

```env
COPILOT_MODEL=gpt-5.4
COPILOT_SUBAGENT_MODEL=inherit
COPILOT_SUBAGENT_EFFORT=inherit
COPILOT_SUBAGENT_CONTEXT=inherit
```

Podés indicar otro modelo en `COPILOT_SUBAGENT_MODEL`. La configuración se
guarda en el volumen personal de Copilot, no en `.github/` ni en el repositorio.
Los cambios del `.env` se aplican al recrear el contenedor.

Consultá [Arquitectura](docs/architecture.md), [Incorporación](docs/onboarding.md) y [Seguridad](docs/security.md).
