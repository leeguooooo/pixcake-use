"""Read-only enumeration of PixCake photos and their current edit recipe.

Bridges the project database (``thumbnail`` + ``thumb_opt_record`` + the palette
JSON files) into a simple per-photo view so the CLI can identify, locate and
preview photos without opening PixCake.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .codebook import name_for
from .environment import Environment
from .sqlite_inspect import open_readonly


@dataclass
class Photo:
    project_db: Path
    thumbnail_id: int
    position: int  # grid order (importIndex)
    original_path: str
    width: int
    height: int
    edited: bool
    palette_path: Path | None
    named_params: dict[str, float] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return Path(self.original_path).stem or f"thumb{self.thumbnail_id}"


def discover_project_dbs(env: Environment) -> list[Path]:
    """Find every user project.db under the support dir's db/ tree."""
    root = env.support_dir / "db"
    return sorted(root.glob("user_*/project_*/project.db"))


def _palette_named_params(palette_path: Path) -> tuple[bool, dict[str, float]]:
    """Return (edited, {name: fe}) for non-neutral params in a palette file."""
    try:
        data = json.loads(palette_path.read_text())
    except (OSError, ValueError):
        return False, {}
    params = data.get("Common", {}).get("Params", [])
    named: dict[str, float] = {}
    non_neutral = False
    for p in params:
        if "fe" not in p:
            continue
        fe = p["fe"]
        if abs(fe - 0.5) > 1e-6:
            non_neutral = True
        name = name_for(p["pf"])
        if name:
            named[name] = fe
    edited = (not data.get("IsNoneEffect", True)) and non_neutral
    return edited, named


def list_photos(project_db: Path) -> list[Photo]:
    conn = open_readonly(project_db)
    conn.row_factory = __import__("sqlite3").Row
    photos: list[Photo] = []
    try:
        rows = conn.execute(
            "select id, importIndex, originalImagePath, originalWidth, originalHeight, "
            "currentOptRecordId from thumbnail where inRecycleBin = 0 "
            "order by importIndex, id"
        ).fetchall()
        for row in rows:
            palette_path: Path | None = None
            opt_id = row["currentOptRecordId"]
            if opt_id is not None and opt_id >= 0:
                rec = conn.execute(
                    "select paletteJsonPath from thumb_opt_record where id = ? limit 1",
                    (opt_id,),
                ).fetchone()
                if rec and rec["paletteJsonPath"]:
                    palette_path = Path(rec["paletteJsonPath"])
            edited, named = (False, {})
            if palette_path and palette_path.exists():
                edited, named = _palette_named_params(palette_path)
            photos.append(
                Photo(
                    project_db=project_db,
                    thumbnail_id=row["id"],
                    position=row["importIndex"],
                    original_path=row["originalImagePath"] or "",
                    width=row["originalWidth"] or 0,
                    height=row["originalHeight"] or 0,
                    edited=edited,
                    palette_path=palette_path,
                    named_params=named,
                )
            )
    finally:
        conn.close()
    return photos


def recipe_summary(photo: Photo, limit: int = 6) -> str:
    """One-line human summary of the photo's non-neutral named params."""
    if not photo.named_params:
        return "(no recognized edits)" if not photo.edited else "(edited; params unmapped)"
    items = sorted(photo.named_params.items(), key=lambda kv: -abs(kv[1] - 0.5))
    parts = []
    for name, fe in items[:limit]:
        sign = "+" if fe >= 0.5 else ""
        parts.append(f"{name}{sign}{(fe - 0.5) * 200:.0f}%")
    extra = "" if len(items) <= limit else f" +{len(items) - limit} more"
    return ", ".join(parts) + extra


def to_dict(photo: Photo) -> dict[str, Any]:
    return {
        "position": photo.position,
        "thumbnail_id": photo.thumbnail_id,
        "name": photo.name,
        "original_path": photo.original_path,
        "size": [photo.width, photo.height],
        "edited": photo.edited,
        "palette_path": str(photo.palette_path) if photo.palette_path else None,
        "named_params": photo.named_params,
        "project_db": str(photo.project_db),
    }
