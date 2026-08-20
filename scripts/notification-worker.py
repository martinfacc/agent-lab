#!/usr/bin/env python3
"""Envía avisos importantes de bmad-loop a canales externos opcionales."""

from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


PROJECT = Path(os.environ.get("AGENT_CONTROL_PROJECT_PATH", "/workspace/project"))
RUNS_DIR = PROJECT / ".bmad-loop" / "runs"
STATE_PATH = Path(
    os.environ.get(
        "NOTIFY_STATE_PATH", "/workspace/output/control/notifications-state.json"
    )
)
POLL_SECONDS = 2
ATTENTION_LINE = re.compile(r"^\[[^]]+\]\s+([^:]+):\s*(.*)$", re.DOTALL)
SUPPORTED_CHANNELS = {"telegram", "ntfy"}
DEFAULT_EVENTS = {"paused", "awaiting-operator", "crashed", "finished"}
AUDIT_PATH = Path("/workspace/output/control/telegram-audit.jsonl")
ENGINE_LOG_DIR = Path("/workspace/output/development/logs")
CONFIRMATION_TTL_SECONDS = 300


def csv_values(name: str, defaults: set[str] | None = None) -> set[str]:
    raw = os.environ.get(name, "")
    if not raw.strip():
        return set(defaults or ())
    return {value.strip().lower() for value in raw.split(",") if value.strip()}


def classify(title: str) -> str:
    normalized = title.lower()
    if "awaiting operator" in normalized:
        return "awaiting-operator"
    if "paused" in normalized or "gated" in normalized or "escalat" in normalized:
        return "paused"
    if "crash" in normalized or "failed" in normalized or "error" in normalized:
        return "crashed"
    if "finished" in normalized or "completed" in normalized:
        return "finished"
    return "other"


def load_state() -> dict[str, object]:
    try:
        value = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def load_offsets() -> dict[str, int]:
    offsets = load_state().get("offsets", {})
    if not isinstance(offsets, dict):
        return {}
    return {
        str(path): int(offset)
        for path, offset in offsets.items()
        if isinstance(path, str) and isinstance(offset, int) and offset >= 0
    }


def save_state(offsets: dict[str, int], telegram_update_id: int) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {"offsets": offsets, "telegram_update_id": telegram_update_id},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    temporary.replace(STATE_PATH)


def post(url: str, body: bytes, headers: dict[str, str]) -> None:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=10) as response:
        if not 200 <= response.status < 300:
            raise RuntimeError(f"HTTP {response.status}")


def send_telegram(text: str, chat_id: str | None = None) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    target_chat = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not target_chat:
        raise ValueError("faltan TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID")
    body = urllib.parse.urlencode(
        {"chat_id": target_chat, "text": text[:4096], "disable_web_page_preview": "true"}
    ).encode()
    post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        body,
        {"Content-Type": "application/x-www-form-urlencoded"},
    )


def send_ntfy(title: str, text: str, event: str) -> None:
    base_url = os.environ.get("NTFY_URL", "https://ntfy.sh").strip().rstrip("/")
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        raise ValueError("falta NTFY_TOPIC")
    # Los headers HTTP no transportan Unicode de forma consistente. El cuerpo
    # sigue siendo UTF-8; el título se translitera para evitar caracteres rotos.
    safe_title = (
        unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    )
    headers = {
        "Content-Type": "text/plain; charset=utf-8",
        "Title": safe_title,
        "Priority": "high" if event in {"paused", "crashed", "awaiting-operator"} else "default",
        "Tags": "robot," + ("warning" if event != "finished" else "heavy_check_mark"),
    }
    token = os.environ.get("NTFY_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    post(f"{base_url}/{urllib.parse.quote(topic, safe='')}", text.encode(), headers)


def story_from(title: str, message: str) -> str | None:
    match = re.search(r"\b(\d+-\d+-[a-z0-9-]+)\b", f"{title} {message}", re.I)
    return match.group(1) if match else None


def friendly_notification(run_id: str, title: str, message: str) -> tuple[str, str]:
    normalized = f"{title}\n{message}".lower()
    story = story_from(title, message)
    story_line = f"\nStory: {story}" if story else ""

    if "worktree open failed" in normalized:
        heading = "No se pudo iniciar una story"
        body = (
            "BMAD no pudo preparar el espacio de trabajo temporal de Git. "
            "La story no comenzó y requiere una revisión técnica."
            f"{story_line}\n\nQué hacer: abrí Hermes y pedí revisar el run {run_id}. "
            "No borres ramas ni worktrees manualmente."
        )
    elif "critical escalation" in normalized:
        reason = "El agente encontró una condición que no puede resolver de forma segura."
        if "missing previous-story continuity decision" in normalized:
            reason = "La story anterior todavía no está finalizada y BMAD necesita decidir cómo continuar."
        elif "metadata not writable" in normalized or "worktree not clean" in normalized:
            reason = "Git tiene cambios o permisos que impiden continuar de forma segura."
        heading = "El desarrollo necesita atención"
        body = (
            f"{reason}{story_line}\n\nQué hacer: abrí Hermes y pedí revisar y resolver "
            f"la escalación del run {run_id}. No lo reanudes sin resolver la causa."
        )
    elif "uncommitted work could not be auto-preserved" in normalized:
        heading = "Hay cambios que necesitan revisión"
        body = (
            "BMAD encontró cambios sin commit y evitó descartarlos automáticamente. "
            f"El trabajo sigue preservado.{story_line}\n\nQué hacer: abrí Hermes y pedí "
            f"recuperar los cambios del run {run_id}. No uses reset --hard."
        )
    elif "story awaiting operator" in normalized:
        heading = "Una story espera una acción tuya"
        body = (
            f"El agente terminó todo lo que podía hacer.{story_line}\n\n"
            "Qué hacer: revisá en Hermes las acciones pendientes y, cuando estén listas, "
            "confirmá la story."
        )
    elif "story deferred" in normalized:
        heading = "Una story quedó pendiente"
        body = (
            "BMAD no pudo completar esta story y conservó el trabajo disponible."
            f"{story_line}\n\nQué hacer: abrí Hermes y pedí revisar por qué fue diferida "
            f"en el run {run_id}."
        )
    elif "epic" in normalized and "boundary" in normalized:
        heading = "La épica terminó y el desarrollo está pausado"
        body = (
            "BMAD llegó al punto de revisión entre épicas.\n\nQué hacer: revisá los "
            f"resultados y reanudá el run {run_id} cuando quieras continuar."
        )
    elif "run finished" in normalized:
        summary = re.search(
            r"(\d+) done,\s*(\d+) deferred,\s*(\d+) escalated", message, re.I
        )
        done, deferred, escalated = (
            (int(summary.group(1)), int(summary.group(2)), int(summary.group(3)))
            if summary
            else (0, 0, 0)
        )
        if deferred or escalated:
            heading = "La ejecución terminó con tareas pendientes"
            action = "Qué hacer: abrí Hermes y pedí revisar las stories pendientes."
        elif done:
            heading = "La ejecución terminó correctamente"
            action = "No necesitás hacer nada. Podés revisar el resultado cuando quieras."
        else:
            heading = "La ejecución terminó sin completar stories"
            action = "Qué hacer: abrí Hermes y pedí revisar por qué no hubo avances."
        body = (
            f"Completadas: {done}\nPendientes: {deferred}\n"
            f"Con escalación: {escalated}\n\n{action}"
        )
    elif "stopped gracefully" in normalized:
        heading = "El desarrollo se detuvo de forma ordenada"
        body = f"El trabajo actual quedó preservado.\n\nQué hacer: reanudá el run {run_id} cuando quieras continuar."
    else:
        heading = "El desarrollo necesita atención"
        body = (
            f"BMAD registró un evento que requiere revisión.{story_line}\n\n"
            f"Qué hacer: abrí Hermes y consultá el estado del run {run_id}."
        )
    return heading, body


def format_message(run_id: str, title: str, message: str) -> tuple[str, str]:
    project_name = os.environ.get("NOTIFY_PROJECT_NAME", "Autonomous Agent Lab").strip()
    monitor_url = os.environ.get("NOTIFY_MONITOR_URL", "http://localhost:9121").strip()
    friendly_title, friendly_body = friendly_notification(run_id, title, message)
    heading = f"{project_name} - {friendly_title}"
    body = f"Run: {run_id}\n\n{friendly_body}"
    if monitor_url:
        location = "Monitor en la PC" if "localhost" in monitor_url else "Monitor"
        body += f"\n\n{location}: {monitor_url}"
    return heading, body


def dispatch(run_id: str, title: str, message: str) -> None:
    channels = csv_values("NOTIFY_CHANNELS") & SUPPORTED_CHANNELS
    event = classify(title)
    if not channels or event not in csv_values("NOTIFY_EVENTS", DEFAULT_EVENTS):
        return
    heading, body = format_message(run_id, title, message)
    for channel in sorted(channels):
        try:
            if channel == "telegram":
                send_telegram(f"{heading}\n\n{body}")
            elif channel == "ntfy":
                send_ntfy(heading, body, event)
            print(f"Notificación enviada por {channel}: {event}", flush=True)
        except ValueError as error:
            print(f"No se pudo notificar por {channel}: {error}", flush=True)
        except (OSError, RuntimeError, urllib.error.URLError) as error:
            # No imprimir URLs: Telegram incluye el token del bot en la ruta.
            print(
                f"No se pudo notificar por {channel}: {type(error).__name__}",
                flush=True,
            )


def run_status(state: dict[str, object], run_dir: Path) -> str:
    if state.get("paused_reason"):
        return "paused"
    for value in ("crashed", "stopped", "finished"):
        if state.get(value):
            return value
    try:
        pid = int((run_dir / "engine.pid").read_text(encoding="utf-8").strip())
        command = (Path("/proc") / str(pid) / "cmdline").read_bytes()
        return "running" if b"bmad-loop" in command else "interrupted"
    except (OSError, ValueError):
        return "interrupted"


def runs() -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    if not RUNS_DIR.is_dir():
        return result
    for path in RUNS_DIR.glob("*/state.json"):
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(state, dict):
            continue
        state["run_id"] = str(state.get("run_id", path.parent.name))
        state["status"] = run_status(state, path.parent)
        state["_updated_at"] = path.stat().st_mtime
        result.append(state)
    return sorted(result, key=lambda item: float(item["_updated_at"]), reverse=True)


def select_run(run_id: str | None = None) -> dict[str, object] | None:
    available = runs()
    if not run_id:
        return available[0] if available else None
    return next((run for run in available if run.get("run_id") == run_id), None)


def task_list(state: dict[str, object]) -> list[dict[str, object]]:
    raw = state.get("tasks", {})
    values = raw.values() if isinstance(raw, dict) else raw if isinstance(raw, list) else []
    return [task for task in values if isinstance(task, dict)]


def current_task(state: dict[str, object]) -> dict[str, object] | None:
    tasks = task_list(state)
    return next(
        (task for task in tasks if str(task.get("phase", "")).endswith("running")),
        tasks[-1] if tasks else None,
    )


def format_status(state: dict[str, object]) -> str:
    task = current_task(state)
    lines = [
        f"Run: {state.get('run_id')}",
        f"Estado: {state.get('status')}",
        f"Épica: {state.get('current_epic', '—')}",
    ]
    if task:
        lines.extend(
            [
                f"Story: {task.get('story_key', '—')}",
                f"Fase: {task.get('phase', '—')}",
            ]
        )
    if state.get("paused_stage"):
        lines.append(f"Pausa: {state.get('paused_stage')}")
    if state.get("paused_reason"):
        lines.append(f"Motivo: {state.get('paused_reason')}")
    return "\n".join(lines)


def format_progress(state: dict[str, object]) -> str:
    counts: dict[str, int] = {}
    for task in task_list(state):
        phase = str(task.get("phase", "unknown"))
        counts[phase] = counts.get(phase, 0) + 1
    lines = [f"Progreso · {state.get('run_id')}"]
    lines.extend(f"{phase}: {count}" for phase, count in sorted(counts.items()))
    return "\n".join(lines) if counts else "Todavía no hay tareas registradas."


def format_runs() -> str:
    available = runs()[:8]
    if not available:
        return "No hay runs registrados."
    return "Últimos runs:\n" + "\n".join(
        f"{run.get('run_id')} · {run.get('status')}" for run in available
    )


def format_logs(state: dict[str, object], count: int = 12) -> str:
    run_id = str(state.get("run_id"))
    log_dir = RUNS_DIR / run_id / "logs"
    candidates = sorted(
        log_dir.glob("*.log") if log_dir.is_dir() else [],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return f"No hay logs disponibles para {run_id}."
    try:
        lines = candidates[0].read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return f"No se pudo leer el log de {run_id}."
    tail = "\n".join(lines[-max(1, min(count, 30)) :])
    return f"Log · {run_id}\n{candidates[0].name}\n\n{tail}"[-4000:]


def audit(chat_id: str, command: str, result: str) -> None:
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "chat_id": chat_id,
        "command": command,
        "result": result,
    }
    with AUDIT_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def allowed_chats() -> set[str]:
    configured = os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS", "").strip()
    if not configured:
        configured = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    return {value.strip() for value in configured.split(",") if value.strip()}


def telegram_api(method: str, values: dict[str, str]) -> dict[str, object]:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise ValueError("falta TELEGRAM_BOT_TOKEN")
    body = urllib.parse.urlencode(values).encode()
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not isinstance(result, dict) or not result.get("ok"):
        raise RuntimeError("Telegram rechazó la solicitud")
    return result


def start_resume(run_id: str) -> None:
    ENGINE_LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = ENGINE_LOG_DIR / f"bmad-telegram-resume-{int(time.time())}.log"
    with log_path.open("ab") as log:
        subprocess.Popen(
            ["bmad-loop", "resume", run_id],
            cwd=PROJECT,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )


def execute_action(action: str, target: str) -> str:
    if action == "resume":
        state = select_run(target)
        if not state:
            return "No encontré ese run."
        if state.get("paused_stage") == "escalation":
            return "Ese run requiere resolver una escalación desde Hermes o con bmad-loop resolve."
        start_resume(target)
        return f"Reanudación iniciada para {target}."
    if action == "stop":
        result = subprocess.run(
            ["bmad-loop", "stop", target, "--graceful"],
            cwd=PROJECT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return (
            f"Detención ordenada solicitada para {target}."
            if result.returncode == 0
            else f"No se pudo detener {target}: {(result.stderr or result.stdout).strip()}"
        )
    result = subprocess.run(
        ["bmad-loop", "confirm", target, "--yes"],
        cwd=PROJECT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    return (
        f"Story confirmada: {target}."
        if result.returncode == 0
        else f"No se pudo confirmar {target}: {(result.stderr or result.stdout).strip()}"
    )


HELP = """Comandos disponibles:
/estado [run_id]
/progreso [run_id]
/logs [run_id]
/runs
/ayuda

En modo controlled:
/reanudar [run_id]
/detener [run_id]
/confirmar <story_key>"""


def handle_command(
    chat_id: str, text: str, pending: dict[str, dict[str, object]]
) -> str:
    words = text.strip().split()
    command = words[0].split("@", 1)[0].lower() if words else ""
    argument = words[1] if len(words) > 1 else None
    natural = text.strip().lower()
    if not command.startswith("/"):
        if "log" in natural or "error" in natural:
            command = "/logs"
        elif "progreso" in natural:
            command = "/progreso"
        elif "estado" in natural or "haciendo" in natural:
            command = "/estado"
        else:
            return HELP
    if command in {"/start", "/ayuda", "/help"}:
        return HELP
    if command == "/runs":
        return format_runs()
    if command in {"/estado", "/progreso", "/logs"}:
        state = select_run(argument)
        if not state:
            return "No encontré ejecuciones registradas."
        if command == "/estado":
            return format_status(state)
        if command == "/progreso":
            return format_progress(state)
        return format_logs(state)
    if command.startswith("/confirmar_"):
        confirmation = pending.get(chat_id)
        if not confirmation or time.time() > float(confirmation["expires"]):
            pending.pop(chat_id, None)
            return "La confirmación venció o no existe."
        expected = f"/confirmar_{confirmation['action']}"
        if command != expected or argument != confirmation["code"]:
            return "El código de confirmación no coincide."
        pending.pop(chat_id, None)
        return execute_action(str(confirmation["action"]), str(confirmation["target"]))
    if command not in {"/reanudar", "/detener", "/confirmar"}:
        return HELP
    if os.environ.get("TELEGRAM_COMMANDS", "read-only").strip().lower() != "controlled":
        return "Las acciones están desactivadas. Configurá TELEGRAM_COMMANDS=controlled."
    action = {"/reanudar": "resume", "/detener": "stop", "/confirmar": "story"}[command]
    if action == "story":
        if not argument:
            return "Indicá la story: /confirmar story_key"
        target = argument
    else:
        state = select_run(argument)
        if not state:
            return "No encontré ese run."
        target = str(state.get("run_id"))
    code = f"{secrets.randbelow(10000):04d}"
    pending[chat_id] = {
        "action": action,
        "target": target,
        "code": code,
        "expires": time.time() + CONFIRMATION_TTL_SECONDS,
    }
    verb = {"resume": "reanudar", "stop": "detener", "story": "confirmar"}[action]
    return f"Confirmá {verb} {target} con:\n/confirmar_{action} {code}\n\nVence en 5 minutos."


def poll_telegram(
    update_id: int, pending: dict[str, dict[str, object]]
) -> int:
    if "telegram" not in csv_values("NOTIFY_CHANNELS"):
        return update_id
    try:
        response = telegram_api(
            "getUpdates",
            {
                "offset": str(update_id + 1),
                "timeout": "1",
                "allowed_updates": json.dumps(["message"]),
            },
        )
    except (OSError, ValueError, RuntimeError, urllib.error.URLError):
        return update_id
    updates = response.get("result", [])
    if not isinstance(updates, list):
        return update_id
    for update in updates:
        if not isinstance(update, dict):
            continue
        update_id = max(update_id, int(update.get("update_id", update_id)))
        message = update.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("text"), str):
            continue
        chat = message.get("chat")
        if not isinstance(chat, dict):
            continue
        chat_id = str(chat.get("id", ""))
        command = str(message["text"])
        command_name = command.split()[0] if command.split() else "(vacío)"
        if chat_id not in allowed_chats():
            audit(chat_id, command_name, "unauthorized")
            continue
        response_text = handle_command(chat_id, command, pending)
        try:
            send_telegram(response_text, chat_id)
            audit(chat_id, command_name, "ok")
        except (OSError, ValueError, RuntimeError, urllib.error.URLError):
            audit(chat_id, command_name, "send-failed")
    return update_id


def process_file(path: Path, offsets: dict[str, int], initialize: bool) -> None:
    key = str(path)
    try:
        size = path.stat().st_size
        if key not in offsets and initialize:
            offsets[key] = size
            return
        offset = offsets.get(key, 0)
        if offset > size:
            offset = 0
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            handle.seek(offset)
            content = handle.read()
            offsets[key] = handle.tell()
    except OSError:
        return
    if not content:
        return
    run_id = path.parent.name
    current: tuple[str, list[str]] | None = None
    for raw_line in content.splitlines():
        match = ATTENTION_LINE.match(raw_line)
        if match:
            if current:
                dispatch(run_id, current[0], "\n".join(current[1]))
            current = (match.group(1), [match.group(2)])
        elif current:
            current[1].append(raw_line)
    if current:
        dispatch(run_id, current[0], "\n".join(current[1]))


def run() -> None:
    channels = csv_values("NOTIFY_CHANNELS")
    unknown = channels - SUPPORTED_CHANNELS
    if unknown:
        print(f"Canales de notificación ignorados: {', '.join(sorted(unknown))}", flush=True)
    persisted = load_state()
    offsets = load_offsets()
    try:
        telegram_update_id = int(persisted.get("telegram_update_id", 0))
    except (TypeError, ValueError):
        telegram_update_id = 0
    pending: dict[str, dict[str, object]] = {}
    first_scan = not STATE_PATH.exists()
    print(
        "Notificaciones externas: "
        + (", ".join(sorted(channels & SUPPORTED_CHANNELS)) or "desactivadas"),
        flush=True,
    )
    while True:
        if RUNS_DIR.is_dir():
            for path in RUNS_DIR.glob("*/ATTENTION"):
                process_file(path, offsets, first_scan)
        telegram_update_id = poll_telegram(telegram_update_id, pending)
        save_state(offsets, telegram_update_id)
        first_scan = False
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    run()
