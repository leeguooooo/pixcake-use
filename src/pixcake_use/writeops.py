"""Write operations against the user's *own* local PixCake config DB.

This is the only module that opens a *writable* SQLite connection or writes
to a palette JSON file. Every other module is strictly read-only. Isolating
the writes here keeps the read/write boundary auditable. These commands stay
inside the README safety boundary: they edit the user's own local config and
do not bypass login, paid features, quotas, or signatures.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


def backup_sqlite_family(db_path: Path, backup_dir: Path) -> list[Path]:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    copied = []
    for suffix in ("", "-wal", "-shm"):
        src = Path(str(db_path) + suffix)
        if not src.exists():
            continue
        dest = backup_dir / f"{db_path.stem}-{stamp}{db_path.suffix}{suffix}"
        shutil.copy2(src, dest)
        copied.append(dest)
    return copied


def backup_file(path: Path, backup_dir: Path) -> Path | None:
    if not path.exists():
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = backup_dir / f"{path.name}-{stamp}.bak"
    shutil.copy2(path, dest)
    return dest


def recipe_param_updates(recipe: dict[str, Any]) -> dict[int, dict[str, Any]]:
    raw_params = recipe.get("params")
    if not isinstance(raw_params, list):
        raise ValueError("recipe must contain a params list")
    updates: dict[int, dict[str, Any]] = {}
    for item in raw_params:
        if not isinstance(item, dict) or "pf" not in item:
            raise ValueError("each recipe param must be an object with pf")
        pf = int(item["pf"])
        value_keys = [key for key in ("fe", "ie", "se", "ae") if key in item]
        if len(value_keys) != 1:
            raise ValueError(f"param {pf} must contain exactly one of fe/ie/se/ae")
        key = value_keys[0]
        updates[pf] = {"pf": pf, key: item[key]}
    return updates


def apply_updates_to_palette(palette: dict[str, Any], updates: dict[int, dict[str, Any]]) -> dict[str, Any]:
    palette = dict(palette)
    palette["IsNoneEffect"] = False
    common = palette.setdefault("Common", {})
    if not isinstance(common, dict):
        raise ValueError("paletteCfg.Common is not an object")
    common["Visible"] = True
    params = common.setdefault("Params", [])
    if not isinstance(params, list):
        raise ValueError("paletteCfg.Common.Params is not a list")

    by_pf: dict[int, dict[str, Any]] = {}
    for param in params:
        if isinstance(param, dict) and "pf" in param:
            by_pf[int(param["pf"])] = param

    for pf, update in updates.items():
        if pf in by_pf:
            target = by_pf[pf]
            for key in ("fe", "ie", "se", "ae"):
                target.pop(key, None)
            target.update(update)
        else:
            params.append(update)
    return palette


def current_opt_record(conn: sqlite3.Connection, thumbnail_id: int) -> sqlite3.Row:
    row = conn.execute(
        "select currentOptRecordId from thumbnail where id = ? limit 1",
        (thumbnail_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"thumbnail id {thumbnail_id} not found")
    record_id = row["currentOptRecordId"]
    record = conn.execute(
        "select * from thumb_opt_record where id = ? limit 1",
        (record_id,),
    ).fetchone()
    if record is None:
        raise ValueError(f"current opt record id {record_id} not found")
    return record


def apply_recipe_to_row(
    db_path: Path,
    table_arg: str,
    row_id: int,
    recipe: dict[str, Any],
    *,
    backup_dir: Path,
    no_backup: bool,
) -> int:
    updates = recipe_param_updates(recipe)
    table = table_arg.replace('"', '""')
    copied: list[Path] = []
    if not no_backup:
        copied = backup_sqlite_family(db_path, backup_dir)

    conn = sqlite3.connect(str(db_path), timeout=3.0)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(f'select * from "{table}" where id = ? limit 1', (row_id,)).fetchone()
        if row is None:
            print(f"No row with id={row_id}", file=sys.stderr)
            return 1
        palette = json.loads(row["paletteCfg"])
        updated_palette = apply_updates_to_palette(palette, updates)
        updated_text = json.dumps(updated_palette, ensure_ascii=False, separators=(",", ":"))
        now_ms = int(time.time() * 1000)
        conn.execute(
            f'update "{table}" set paletteCfg = ?, update_time = ? where id = ?',
            (updated_text, now_ms, row_id),
        )
        conn.commit()
    finally:
        conn.close()

    print(f"Updated {db_path} table={table_arg} id={row_id}")
    print(f"Applied params: {', '.join(str(pf) for pf in sorted(updates))}")
    if copied:
        print("Backups:")
        for path in copied:
            print(f"  {path}")
    return 0


def apply_recipe_to_current_record(
    db_path: Path,
    thumbnail_id: int,
    recipe: dict[str, Any],
    recipe_label: str,
    *,
    backup_dir: Path,
    no_backup: bool,
) -> int:
    updates = recipe_param_updates(recipe)

    copied: list[Path] = []
    palette_backup: Path | None = None
    if not no_backup:
        copied = backup_sqlite_family(db_path, backup_dir)

    conn = sqlite3.connect(str(db_path), timeout=3.0)
    try:
        conn.row_factory = sqlite3.Row
        record = current_opt_record(conn, thumbnail_id)
        record_id = record["id"]
        palette_path = Path(record["paletteJsonPath"])
        if not palette_path.exists():
            raise FileNotFoundError(f"paletteJsonPath does not exist: {palette_path}")
        if not no_backup:
            palette_backup = backup_file(palette_path, backup_dir)

        palette = json.loads(palette_path.read_text())
        updated_palette = apply_updates_to_palette(palette, updates)
        palette_path.write_text(json.dumps(updated_palette, ensure_ascii=False, separators=(",", ":")))

        now_ms = int(time.time() * 1000)
        label = recipe.get("description") or recipe_label
        opt_json = json.dumps({"labName": f"pixcake-use: {label}"}, ensure_ascii=False, separators=(",", ":"))
        conn.execute(
            "update thumb_opt_record set optJson = ?, created_time = ? where id = ?",
            (opt_json, now_ms, record_id),
        )
        conn.execute(
            "update thumbnail set optStatus = 1, isOnlyFreeEffectOnUI = 0, update_time = ? where id = ?",
            (now_ms, thumbnail_id),
        )
        conn.commit()
    finally:
        conn.close()

    print(f"Updated current opt record for thumbnail={thumbnail_id}")
    print(f"Record id: {record_id}")
    print(f"Palette file: {palette_path}")
    print(f"Applied params: {', '.join(str(pf) for pf in sorted(updates))}")
    if copied or palette_backup:
        print("Backups:")
        for path in copied:
            print(f"  {path}")
        if palette_backup:
            print(f"  {palette_backup}")
    return 0
