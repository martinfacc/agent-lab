"""Compatibilidad acotada para renders BMAD sobre bind mounts de Docker Desktop."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any


_original_rename = os.rename


def _is_bmad_render_directory(source: Any, destination: Any) -> bool:
    try:
        source_path = Path(os.fsdecode(source))
        destination_path = Path(os.fsdecode(destination))
    except (TypeError, ValueError):
        return False
    marker = f"{os.sep}_bmad{os.sep}render{os.sep}"
    return (
        source_path.is_dir()
        and marker in f"{source_path}{os.sep}"
        and marker in f"{destination_path}{os.sep}"
    )


def _rename_with_bmad_fallback(
    source: Any,
    destination: Any,
    *args: Any,
    **kwargs: Any,
) -> None:
    try:
        _original_rename(source, destination, *args, **kwargs)
    except PermissionError:
        if args or kwargs or not _is_bmad_render_directory(source, destination):
            raise
        # Docker Desktop para Windows puede rechazar el rename atómico de un
        # directorio no vacío en un bind mount. BMAD verifica el manifiesto y
        # max_parallel=1 evita publicaciones concurrentes dentro del run.
        shutil.copytree(source, destination)


os.rename = _rename_with_bmad_fallback
