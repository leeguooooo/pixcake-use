from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CandidatePath:
    path: Path
    kind: str
    exists: bool


@dataclass(frozen=True)
class Environment:
    app_path: Path
    support_dir: Path
    preferences: tuple[Path, ...]
    output_dir: Path = Path("snapshots")
    skip_dir_names: frozenset[str] = frozenset(
        {"Banner", "QtWebEngine", "sentry", "preview_mem", "export_mem", "material"}
    )
    db_suffixes: frozenset[str] = frozenset({".db", ".sqlite", ".sqlite3"})

    @property
    def include_dirs(self) -> list[Path]:
        return [self.support_dir / n for n in ("project", "db", "hotkey", "logs")]

    @property
    def include_files(self) -> list[Path]:
        return [
            self.support_dir / "externalapi.json",
            self.support_dir / "reportcache.db",
            *self.preferences,
        ]


def default_environment() -> Environment:
    home = Path.home()
    return Environment(
        app_path=Path("/Applications/pixcake.app"),
        support_dir=home / "Library/Application Support/PixCake-qt_pro",
        preferences=(
            home / "Library/Preferences/com.xiangtian.pixcakepc.plist",
            home / "Library/Preferences/com.truesight.PixCakeInstaller.plist",
        ),
    )
