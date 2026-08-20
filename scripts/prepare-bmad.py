#!/usr/bin/env python3
"""Valida BMAD del proyecto o proyecta una distribución externa administrada."""

from __future__ import annotations

import json
import os
import shutil
import shlex
import sys
from pathlib import Path, PurePosixPath

import yaml


PROJECT = Path(os.environ.get("AGENT_CONTROL_PROJECT_PATH", "/workspace/project")).resolve()
DISTRIBUTION = Path(os.environ.get("BMAD_DISTRIBUTION_DIR", "/opt/bmad-distribution"))
RUNTIME_ENV = Path(
    os.environ.get("BMAD_RUNTIME_ENV", "/workspace/output/control/bmad-runtime.env")
)
MANAGED_MARKER = ".agent-lab-managed.json"
REQUIRED_SKILL_GROUPS = (
    ("bmad-build-auto", "bmad-dev-auto"),
    ("bmad-review-adversarial-general",),
    ("bmad-review-edge-case-hunter",),
)


class BmadPreparationError(RuntimeError):
    pass


def project_relative(name: str, value: str) -> str:
    normalized = value.strip().replace("\\", "/").rstrip("/")
    path = PurePosixPath(normalized)
    if (
        not normalized
        or path.is_absolute()
        or len(path.parts) == 0
        or any(part in ("", ".", "..") for part in path.parts)
        or (len(normalized) >= 2 and normalized[1] == ":")
    ):
        raise BmadPreparationError(
            f"{name} debe ser una ruta relativa al proyecto y no puede contener '..': {value!r}"
        )
    return path.as_posix()


def environment_value(name: str, default: str) -> str:
    return os.getenv(name, "").strip() or default


def configured_paths() -> tuple[str, str, str]:
    output = project_relative("BMAD_OUTPUT_DIR", environment_value("BMAD_OUTPUT_DIR", "_bmad-output"))
    planning = project_relative(
        "BMAD_PLANNING_ARTIFACTS_DIR",
        environment_value("BMAD_PLANNING_ARTIFACTS_DIR", f"{output}/planning-artifacts"),
    )
    implementation = project_relative(
        "BMAD_IMPLEMENTATION_ARTIFACTS_DIR",
        environment_value(
            "BMAD_IMPLEMENTATION_ARTIFACTS_DIR",
            f"{output}/implementation-artifacts",
        ),
    )
    return output, planning, implementation


def managed_skill_names(marker: Path) -> list[str]:
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return []
    names = data.get("skills", []) if isinstance(data, dict) else []
    return [name for name in names if isinstance(name, str) and name.startswith("bmad-")]


def validate_distribution() -> tuple[Path, Path]:
    bmad_source = DISTRIBUTION / "_bmad"
    skills_source = DISTRIBUTION / ".agents" / "skills"
    if not (bmad_source / "bmm" / "config.yaml").is_file():
        raise BmadPreparationError(
            f"La distribución BMAD externa es inválida: falta {bmad_source / 'bmm/config.yaml'}"
        )
    if not skills_source.is_dir():
        raise BmadPreparationError(
            f"La distribución BMAD externa es inválida: falta {skills_source}"
        )
    return bmad_source, skills_source


def materialize_external() -> None:
    bmad_source, skills_source = validate_distribution()
    bmad_target = PROJECT / "_bmad"
    skills_target = PROJECT / ".agents" / "skills"
    marker = bmad_target / MANAGED_MARKER

    if bmad_target.exists():
        if not marker.is_file():
            raise BmadPreparationError(
                "Existe _bmad pero no es una proyección administrada. "
                "Se rechazó reemplazar la instalación del repositorio."
            )
        for name in managed_skill_names(marker):
            shutil.rmtree(skills_target / name, ignore_errors=True)
        shutil.rmtree(bmad_target)

    shutil.copytree(bmad_source, bmad_target)
    skills_target.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for source in sorted(skills_source.iterdir()):
        if not source.is_dir():
            continue
        destination = skills_target / source.name
        if destination.exists():
            raise BmadPreparationError(
                f"No se puede proyectar BMAD: la skill {destination} ya existe y no es administrada."
            )
        shutil.copytree(source, destination)
        copied.append(source.name)

    output, planning, implementation = configured_paths()
    config_path = bmad_target / "bmm" / "config.yaml"
    document = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(document, dict):
        raise BmadPreparationError(f"Configuración BMAD inválida: {config_path}")
    document.update(
        {
            "planning_artifacts": f"{{project-root}}/{planning}",
            "implementation_artifacts": f"{{project-root}}/{implementation}",
            "output_folder": f"{{project-root}}/{output}",
            "communication_language": environment_value("BMAD_COMMUNICATION_LANGUAGE", "spanish"),
            "document_output_language": environment_value("BMAD_DOCUMENT_LANGUAGE", "spanish"),
            "user_name": environment_value(
                "BMAD_USER_NAME", environment_value("GIT_USER_NAME", "Usuario")
            ),
            "project_name": environment_value("BMAD_PROJECT_NAME", PROJECT.name),
        }
    )
    config_path.write_text(
        yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    marker.write_text(
        json.dumps({"schema": 1, "source": str(DISTRIBUTION), "skills": copied}, indent=2),
        encoding="utf-8",
    )


def validate_project_bmad() -> tuple[Path, Path, Path]:
    try:
        from bmad_loop.bmadconfig import BmadConfigError, load_paths
    except ImportError as error:
        raise BmadPreparationError("bmad-loop no está disponible en el contenedor") from error

    try:
        paths = load_paths(PROJECT)
    except BmadConfigError as error:
        raise BmadPreparationError(f"La instalación BMAD del repositorio es inválida: {error}") from error

    skills = PROJECT / ".agents" / "skills"
    missing = [" o ".join(group) for group in REQUIRED_SKILL_GROUPS if not any((skills / name / "SKILL.md").is_file() for name in group)]
    if missing:
        raise BmadPreparationError(
            "La instalación BMAD no contiene las skills requeridas: " + ", ".join(missing)
        )
    return paths.output_folder, paths.planning_artifacts, paths.implementation_artifacts


def write_runtime_environment(origin: str, implementation: Path) -> None:
    try:
        sprint = implementation.joinpath("sprint-status.yaml").resolve().relative_to(PROJECT)
        sprint_value = sprint.as_posix()
    except ValueError:
        sprint_value = str(implementation / "sprint-status.yaml")
    RUNTIME_ENV.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_ENV.write_text(
        f"export BMAD_ORIGIN={shlex.quote(origin)}\n"
        f"export BMAD_SPRINT_STATUS_PATH={shlex.quote(sprint_value)}\n",
        encoding="utf-8",
    )


def main() -> int:
    marker = PROJECT / "_bmad" / MANAGED_MARKER
    if not (PROJECT / "_bmad").exists() or marker.is_file():
        materialize_external()
        origin = "external"
    else:
        origin = "project"

    _, _, implementation = validate_project_bmad()
    write_runtime_environment(origin, implementation)
    print(
        "BMAD válido: "
        + ("instalación del repositorio" if origin == "project" else "distribución externa")
    )
    print(f"Artefactos de implementación: {implementation}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BmadPreparationError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
