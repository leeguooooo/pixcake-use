from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .discovery import (
    default_targets,
    iter_files,
    pixcake_processes,
    read_app_version,
)
from .environment import Environment
from .sqlite_inspect import sqlite_summary
from .util import iso_now, sha256_file


def file_record(path: Path, base: Path | None = None) -> dict[str, Any]:
    stat = path.stat()
    record: dict[str, Any] = {
        "path": str(path),
        "relative_path": str(path.relative_to(base)) if base and path.is_relative_to(base) else None,
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "sha256": sha256_file(path),
    }
    if path.suffix == ".db-wal":
        record["wal_role"] = "wal"
    elif path.suffix == ".db-shm":
        record["wal_role"] = "shm"
    sqlite = sqlite_summary(path)
    if sqlite is not None:
        record["sqlite"] = sqlite
    return record


def build_snapshot(
    env: Environment,
    include_logs: bool = True,
    extra_paths: list[Path] | None = None,
) -> dict[str, Any]:
    targets = default_targets(env, include_logs=include_logs)
    if extra_paths:
        targets.extend(extra_paths)
    files: dict[str, dict[str, Any]] = {}
    for path in sorted(iter_files(targets, env, include_logs=include_logs), key=lambda item: str(item)):
        try:
            files[str(path)] = file_record(path)
        except (OSError, ValueError) as exc:
            files[str(path)] = {"path": str(path), "error": str(exc)}
    running = pixcake_processes()
    warnings: list[str] = []
    if running:
        warnings.append(
            "PixCake is running; snapshot counts may miss in-flight changes still in the -wal."
        )
    return {
        "created_at": iso_now(),
        "tool": "pixcake-use",
        "app_path": str(env.app_path),
        "app_version": read_app_version(env),
        "support_dir": str(env.support_dir),
        "pixcake_running": bool(running),
        "warnings": warnings,
        "files": files,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def load_snapshot(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid snapshot JSON: {path}: {exc}") from exc
