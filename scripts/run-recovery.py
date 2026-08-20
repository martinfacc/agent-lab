#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


PROJECT = Path(os.environ.get("AGENT_CONTROL_PROJECT_PATH", "/workspace/project"))
RUNS_DIR = PROJECT / ".bmad-loop" / "runs"
CONTROL_DIR = Path(os.environ.get("AGENT_CONTROL_DATA_DIR", "/workspace/output/control"))
RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$")


def read_state(run_dir: Path) -> dict[str, Any] | None:
    try:
        value = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def engine_alive(run_dir: Path) -> bool:
    try:
        pid = int((run_dir / "engine.pid").read_text(encoding="utf-8").split()[0])
        command = (Path("/proc") / str(pid) / "cmdline").read_bytes().replace(b"\0", b" ")
        return b"bmad-loop" in command
    except (OSError, ValueError, IndexError):
        return False


def tmux_alive(run_id: str) -> bool:
    try:
        return subprocess.run(
            ["tmux", "has-session", "-t", f"bmad-loop-{run_id}"],
            capture_output=True,
            check=False,
            timeout=3,
        ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def is_terminal(state: dict[str, Any]) -> bool:
    return any(bool(state.get(key)) for key in ("finished", "stopped", "crashed"))


def orphaned_runs() -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if not RUNS_DIR.is_dir():
        return found
    for run_dir in RUNS_DIR.iterdir():
        if not run_dir.is_dir():
            continue
        state = read_state(run_dir)
        if not state or is_terminal(state) or state.get("paused_reason"):
            continue
        run_id = str(state.get("run_id", run_dir.name))
        if engine_alive(run_dir) or tmux_alive(run_id):
            continue
        tasks = state.get("tasks")
        task_list = list(tasks.values()) if isinstance(tasks, dict) else tasks
        task_list = task_list if isinstance(task_list, list) else []
        current = next(
            (task for task in reversed(task_list) if isinstance(task, dict)), {}
        )
        found.append(
            {
                "run_id": run_id,
                "status": "interrupted",
                "story_key": current.get("story_key"),
                "phase": current.get("phase"),
                "updated_at": (run_dir / "state.json").stat().st_mtime,
                "recoverable": True,
            }
        )
    return sorted(found, key=lambda item: float(item["updated_at"]), reverse=True)


def write_snapshot(runs: list[dict[str, Any]]) -> None:
    CONTROL_DIR.mkdir(parents=True, exist_ok=True)
    target = CONTROL_DIR / "orphaned-runs.json"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"generated_at": time.time(), "runs": runs}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(target)


def recover(run_id: str) -> int:
    if not RUN_ID.fullmatch(run_id):
        print("Run ID inválido.", file=sys.stderr)
        return 2
    candidates = {item["run_id"]: item for item in orphaned_runs()}
    if run_id not in candidates:
        print("El run no está interrumpido o ya no necesita recuperación.", file=sys.stderr)
        return 1
    log_dir = CONTROL_DIR / "recovery-logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"resume-{run_id}-{int(time.time())}.log"
    with log_path.open("ab") as log:
        subprocess.Popen(
            ["bmad-loop", "resume", "--project", str(PROJECT), run_id],
            cwd=PROJECT,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    print(f"Reanudación solicitada para {run_id}.")
    print(f"Log de recuperación: {log_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Detecta y recupera runs interrumpidos.")
    subcommands = parser.add_subparsers(dest="command", required=True)
    scan = subcommands.add_parser("scan")
    scan.add_argument("--json", action="store_true")
    scan.add_argument("--write", action="store_true")
    resume = subcommands.add_parser("recover")
    resume.add_argument("run_id")
    args = parser.parse_args()
    if args.command == "recover":
        return recover(args.run_id)
    runs = orphaned_runs()
    if args.write:
        write_snapshot(runs)
    if args.json:
        print(json.dumps(runs, ensure_ascii=False))
    elif not runs:
        print("No hay runs interrumpidos recuperables.")
    else:
        print("Runs interrumpidos recuperables:")
        for item in runs:
            detail = " · ".join(
                value for value in (str(item["story_key"] or ""), str(item["phase"] or "")) if value
            )
            print(f"  {item['run_id']}{' · ' + detail if detail else ''}")
        print("Reanudá uno explícitamente con: lab recover <run-id>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
