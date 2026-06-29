from __future__ import annotations

import os
import plistlib
import subprocess
from pathlib import Path
from typing import Iterable

from .environment import CandidatePath, Environment


def read_app_version(env: Environment) -> str | None:
    info_plist = env.app_path / "Contents/Info.plist"
    if not info_plist.exists():
        return None
    try:
        with info_plist.open("rb") as handle:
            data = plistlib.load(handle)
    except Exception:
        return None
    version = data.get("CFBundleShortVersionString")
    build = data.get("CFBundleVersion")
    if version and build:
        return f"{version} ({build})"
    return version or build


def pixcake_processes() -> list[str]:
    try:
        result = subprocess.run(
            ["ps", "ax", "-o", "pid=", "-o", "command="],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return []
    lines = []
    for line in result.stdout.splitlines():
        normalized = line.lower()
        if "pixcake" in normalized and "pixcake_use" not in normalized:
            value = line.strip()
            if len(value) > 180:
                value = value[:177] + "..."
            lines.append(value)
    return lines


def candidate_paths(env: Environment) -> list[CandidatePath]:
    support = env.support_dir
    paths = [
        CandidatePath(env.app_path, "app", env.app_path.exists()),
        CandidatePath(support, "support", support.exists()),
        CandidatePath(support / "project", "projects", (support / "project").exists()),
        CandidatePath(support / "db", "databases", (support / "db").exists()),
        CandidatePath(support / "hotkey", "hotkeys", (support / "hotkey").exists()),
        CandidatePath(support / "logs", "logs", (support / "logs").exists()),
    ]
    paths.extend(CandidatePath(path, "preference", path.exists()) for path in env.preferences)
    return paths


def iter_files(paths: Iterable[Path], env: Environment, include_logs: bool = True) -> Iterable[Path]:
    seen: set[Path] = set()
    for root in paths:
        if not root.exists():
            continue
        if root.is_file():
            resolved = root.resolve()
            if resolved not in seen:
                seen.add(resolved)
                yield root
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [
                name
                for name in dirnames
                if name not in env.skip_dir_names and (include_logs or name != "logs")
            ]
            for filename in filenames:
                path = Path(dirpath) / filename
                resolved = path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                yield path


def default_targets(env: Environment, include_logs: bool = True) -> list[Path]:
    targets = [path for path in env.include_dirs if include_logs or path.name != "logs"]
    targets.extend(env.include_files)
    return targets


def iter_default_databases(env: Environment, include_logs: bool = False) -> Iterable[Path]:
    for path in iter_files(default_targets(env, include_logs=include_logs), env, include_logs=include_logs):
        if path.suffix in env.db_suffixes:
            yield path
