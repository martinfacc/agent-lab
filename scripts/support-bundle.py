#!/usr/bin/env python3
import json
import os
import re
import subprocess
import time
import zipfile
from pathlib import Path


PROJECT = Path(os.environ.get("AGENT_CONTROL_PROJECT_PATH", "/workspace/project"))
OUTPUT = Path("/workspace/output")
RUNS = PROJECT / ".bmad-loop" / "runs"
SENSITIVE = re.compile(
    r"(?i)(token|secret|password|passwd|authorization|api[_-]?key)(\s*[:=]\s*)([^\s\"']+)"
)


def sanitize(value: str) -> str:
    value = SENSITIVE.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTADO]", value)
    for secret_name in (
        "TELEGRAM_BOT_TOKEN", "NTFY_TOKEN", "OPENCODE_API_KEY", "GITHUB_TOKEN", "GH_TOKEN"
    ):
        secret = os.environ.get(secret_name, "")
        if secret:
            value = value.replace(secret, "[REDACTADO]")
    return value


def command(args: list[str], timeout: int = 20) -> str:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
        return sanitize(f"$ {' '.join(args)}\n{result.stdout}{result.stderr}")
    except (OSError, subprocess.SubprocessError) as error:
        return f"No se pudo ejecutar {' '.join(args)}: {error}\n"


def latest_run() -> Path | None:
    states = list(RUNS.glob("*/state.json")) if RUNS.is_dir() else []
    return max(states, key=lambda path: path.stat().st_mtime).parent if states else None


def journal_summary(path: Path) -> str:
    allowed = ("ts", "kind", "story_key", "task_id", "status", "action", "reason", "stage")
    summaries: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-200:]:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            summaries.append(json.dumps({key: event[key] for key in allowed if key in event}, ensure_ascii=False))
    return "\n".join(summaries)


def main() -> int:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    destination = OUTPUT / "support" / f"agent-lab-support-{stamp}.zip"
    destination.parent.mkdir(parents=True, exist_ok=True)
    allowed_env = (
        "LAB_MODE", "LAB_PROVIDER", "TZ", "BMAD_OUTPUT_DIR",
        "BMAD_PLANNING_ARTIFACTS_DIR", "BMAD_IMPLEMENTATION_ARTIFACTS_DIR",
        "RESEARCH_PROVIDER", "NOTIFY_CHANNELS", "NOTIFY_EVENTS",
    )
    configuration = {name: os.environ.get(name, "") for name in allowed_env}
    evidence = {
        "versions.txt": command(["bash", "-c", "lab --help >/dev/null; node --version; npm --version; hermes --version; bmad-loop --version; copilot --version"]),
        "git.txt": command(["git", "--no-optional-locks", "-C", str(PROJECT), "status", "--short", "--branch"])
        + command(["git", "--no-optional-locks", "-C", str(PROJECT), "log", "-10", "--oneline", "--decorate"])
        + command(["git", "--no-optional-locks", "-C", str(PROJECT), "worktree", "list", "--porcelain"]),
        "processes.txt": command(["ps", "-eo", "pid,ppid,user,etime,stat,comm,args"]),
        "disk.txt": command(["df", "-h", str(PROJECT), str(OUTPUT)]),
        "configuration.json": json.dumps(configuration, ensure_ascii=False, indent=2),
        "recovery.txt": command(["python3", "/usr/local/lib/agent-lab/run-recovery.py", "scan"]),
        "bmad-validation.txt": command(["bmad-loop", "validate", "--project", str(PROJECT)]),
    }
    current = latest_run()
    if current:
        for name in ("state.json", "journal.jsonl", "ATTENTION"):
            path = current / name
            if path.is_file():
                content = (
                    journal_summary(path)
                    if name == "journal.jsonl"
                    else path.read_text(encoding="utf-8", errors="replace")
                )
                evidence[f"latest-run/{name}"] = sanitize(content)
    manifest = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "latest_run_id": current.name if current else None,
        "privacy": "No incluye código fuente, credenciales, .env ni logs completos de sesiones IA.",
    }
    evidence["manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in evidence.items():
            archive.writestr(name, sanitize(content))
    print(f"Paquete de diagnóstico generado: {destination}")
    print("No contiene código fuente, .env, credenciales ni logs completos de la IA.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
