import json
import os
import re
import subprocess
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


PROJECT = Path(os.environ.get("AGENT_CONTROL_PROJECT_PATH", "/workspace/project"))
LOG_DIR = Path(os.environ.get("AGENT_CONTROL_LOG_DIR", "/workspace/output/development/logs"))
RUNS_DIR = PROJECT / ".bmad-loop" / "runs"
HTML_PATH = Path("/usr/local/lib/agent-lab/monitor.html")
MAX_LOG_LINES = 250
ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def engine_is_alive(run_dir: Path) -> bool:
    try:
        pid = int((run_dir / "engine.pid").read_text(encoding="utf-8").split()[0])
        command = (Path("/proc") / str(pid) / "cmdline").read_bytes().replace(b"\0", b" ")
        return b"bmad-loop" in command
    except (OSError, ValueError):
        return False


def tmux_session_is_alive(run_id: str) -> bool:
    command = ["tmux", "has-session", "-t", f"bmad-loop-{run_id}"]
    if os.geteuid() == 0:
        command = ["runuser", "--user", "agent", "--", *command]
    try:
        return subprocess.run(
            command, capture_output=True, timeout=3, check=False
        ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def status_name(state: dict[str, Any], run_dir: Path) -> str:
    if state.get("paused_reason"):
        return "paused"
    if state.get("crashed"):
        return "crashed"
    if state.get("stopped"):
        return "stopped"
    if state.get("finished"):
        return "finished"
    run_id = str(state.get("run_id", run_dir.name))
    if engine_is_alive(run_dir) or tmux_session_is_alive(run_id):
        return "running"
    return "interrupted"


def normalize_tasks(raw_tasks: Any) -> list[dict[str, Any]]:
    if isinstance(raw_tasks, dict):
        tasks = list(raw_tasks.values())
    elif isinstance(raw_tasks, list):
        tasks = raw_tasks
    else:
        return []
    return [task for task in tasks if isinstance(task, dict)]


def load_runs() -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    if not RUNS_DIR.is_dir():
        return runs
    for state_path in RUNS_DIR.glob("*/state.json"):
        state = read_json(state_path)
        if not state:
            continue
        tasks = normalize_tasks(state.get("tasks"))
        current = next(
            (task for task in tasks if str(task.get("phase", "")).endswith("running")),
            None,
        )
        counts: dict[str, int] = {}
        for task in tasks:
            phase = str(task.get("phase", "unknown"))
            counts[phase] = counts.get(phase, 0) + 1
        runs.append(
            {
                "run_id": state.get("run_id", state_path.parent.name),
                "status": status_name(state, state_path.parent),
                "recoverable": status_name(state, state_path.parent) == "interrupted",
                "started_at": state.get("started_at"),
                "current_epic": state.get("current_epic"),
                "paused_stage": state.get("paused_stage"),
                "paused_reason": state.get("paused_reason"),
                "current_task": current,
                "task_counts": counts,
                "task_count": len(tasks),
                "updated_at": state_path.stat().st_mtime,
            }
        )
    runs.sort(key=lambda run: float(run["updated_at"]), reverse=True)
    return runs


def process_list() -> list[dict[str, str]]:
    try:
        result = subprocess.run(
            ["ps", "-eo", "pid=,etimes=,stat=,comm=,args="],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    processes: list[dict[str, str]] = []
    needles = ("bmad-loop", "copilot", "tmux", "tsx")
    for line in result.stdout.splitlines():
        if not any(needle in line.lower() for needle in needles):
            continue
        parts = line.strip().split(maxsplit=4)
        if len(parts) < 5 or "monitor-server.py" in parts[4]:
            continue
        processes.append(
            {
                "pid": parts[0],
                "seconds": parts[1],
                "state": parts[2],
                "command": parts[3],
                "args": parts[4],
            }
        )
    return processes


def terminal_list() -> list[dict[str, str]]:
    tmux = ["tmux"]
    if os.geteuid() == 0:
        tmux = ["runuser", "--user", "agent", "--", "tmux"]
    try:
        result = subprocess.run(
            [*tmux, "list-panes", "-a", "-F", "#{pane_id}\t#{session_name}\t#{pane_current_command}"],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    terminals: list[dict[str, str]] = []
    for line in result.stdout.splitlines()[:6]:
        parts = line.split("\t", maxsplit=2)
        if len(parts) != 3:
            continue
        try:
            capture = subprocess.run(
                [*tmux, "capture-pane", "-p", "-S", "-120", "-t", parts[0]],
                check=True,
                capture_output=True,
                text=True,
                timeout=3,
            ).stdout.rstrip()
        except (OSError, subprocess.SubprocessError):
            capture = ""
        terminals.append(
            {"pane": parts[0], "session": parts[1], "command": parts[2], "output": capture}
        )
    return terminals


def tail(path: Path, limit: int) -> list[str]:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            lines = handle.readlines()
        cleaned: list[str] = []
        for line in lines[-limit:]:
            value = ANSI_ESCAPE.sub("", line).replace("\r", "").rstrip("\n")
            if value or not cleaned or cleaned[-1]:
                cleaned.append(value)
        return cleaned
    except OSError:
        return []


def journal_lines(run_id: str | None, limit: int = 100) -> list[str]:
    if not run_id:
        return []
    path = RUNS_DIR / run_id / "journal.jsonl"
    try:
        raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]
    except OSError:
        return []
    lines: list[str] = []
    for raw in raw_lines:
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        timestamp = time.strftime("%H:%M:%S", time.localtime(float(event.get("ts", 0))))
        kind = str(event.get("kind", "evento"))
        details = [
            event.get("story_key"),
            event.get("task_id"),
            event.get("status"),
            event.get("action"),
            event.get("reason"),
        ]
        summary = " · ".join(str(value) for value in details if value not in (None, ""))
        lines.append(f"{timestamp}  {kind}{'  ' + summary if summary else ''}")
    return lines


def latest_logs(run_id: str | None) -> dict[str, Any]:
    candidates: list[Path] = []
    if LOG_DIR.is_dir():
        candidates.extend(LOG_DIR.glob("*.log"))
    candidates = [path for path in candidates if path.is_file()]
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    # El log más reciente corresponde al lanzamiento actual. Incluir también el
    # anterior mezcla errores de intentos fallidos con el estado del run activo.
    selected = candidates[:1]
    lines = journal_lines(run_id)
    for path in reversed(selected):
        lines.append(f"── {path.name} ──")
        lines.extend(tail(path, 60))
    return {"files": [str(path) for path in selected], "lines": lines[-MAX_LOG_LINES:]}


def git_status() -> dict[str, Any]:
    try:
        branch = subprocess.run(
            ["git", "--no-optional-locks", "-C", str(PROJECT), "branch", "--show-current"],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        ).stdout.strip()
        changes = subprocess.run(
            ["git", "--no-optional-locks", "-C", str(PROJECT), "status", "--short"],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        ).stdout.splitlines()
        commit = subprocess.run(
            ["git", "--no-optional-locks", "-C", str(PROJECT), "log", "-1", "--format=%h %s"],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        ).stdout.strip()
        return {"branch": branch, "changes": changes, "commit": commit}
    except (OSError, subprocess.SubprocessError):
        return {"branch": "", "changes": [], "commit": ""}


def snapshot() -> dict[str, Any]:
    runs = load_runs()
    latest = runs[0] if runs else None
    return {
        "timestamp": time.time(),
        "runs": runs,
        "latest": latest,
        "processes": process_list(),
        "terminals": terminal_list(),
        "logs": latest_logs(str(latest["run_id"]) if latest else None),
        "git": git_status(),
    }


class Handler(BaseHTTPRequestHandler):
    def send_bytes(self, body: bytes, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/" or self.path == "/index.html":
            self.send_bytes(HTML_PATH.read_bytes(), "text/html; charset=utf-8")
            return
        if self.path == "/api/snapshot":
            body = json.dumps(snapshot(), ensure_ascii=False).encode("utf-8")
            self.send_bytes(body, "application/json; charset=utf-8")
            return
        if self.path == "/api/events":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            try:
                while True:
                    payload = json.dumps(snapshot(), ensure_ascii=False)
                    self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    time.sleep(2)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
        self.send_bytes(b"Not found", "text/plain; charset=utf-8", HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: Any) -> None:
        return


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", 9121), Handler)
    server.serve_forever()
