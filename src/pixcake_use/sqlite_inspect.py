from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .util import short_hash

DB_SUFFIXES = frozenset({".db", ".sqlite", ".sqlite3"})

_SQLITE_MASTER_SQL = (
    "select name, type, sql from sqlite_master "
    "where type in ('table', 'index', 'trigger', 'view') "
    "order by type, name"
)


def open_readonly(path: Path) -> sqlite3.Connection:
    """Open ``path`` strictly read-only. The URI is *only ever* ``mode=ro``."""
    uri = f"{path.resolve().as_uri()}?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=1.0)


def wal_sibling_state(path: Path) -> dict[str, Any]:
    wal = Path(str(path) + "-wal")
    if not wal.exists():
        return {"present": False, "size": 0, "mtime_ns": None}
    st = wal.stat()
    return {"present": True, "size": st.st_size, "mtime_ns": st.st_mtime_ns}


def _unreadable(exc: Exception, wal: dict[str, Any]) -> dict[str, Any]:
    return {
        "error": str(exc),
        "consistency": "unreadable",
        "wal": wal,
        "tables": [],
        "objects": 0,
        "schema_hash": None,
    }


def _read_summary(conn: sqlite3.Connection, wal: dict[str, Any]) -> dict[str, Any]:
    try:
        rows = conn.execute(_SQLITE_MASTER_SQL).fetchall()
    except sqlite3.Error as exc:
        return _unreadable(exc, wal)
    schema_text = "\n".join(row[2] or "" for row in rows)
    tables = []
    for name, obj_type, sql in rows:
        if obj_type != "table" or name.startswith("sqlite_"):
            continue
        entry: dict[str, Any] = {"name": name, "schema_hash": short_hash(sql or "")}
        try:
            quoted = '"' + name.replace('"', '""') + '"'
            entry["rows"] = conn.execute(f"select count(*) from {quoted}").fetchone()[0]
        except sqlite3.Error as exc:
            entry["rows"] = None
            entry["rows_error"] = str(exc)
        tables.append(entry)
    try:
        journal_mode = conn.execute("pragma journal_mode").fetchone()[0]
    except sqlite3.Error:
        journal_mode = None
    consistency = "wal-present" if (wal["present"] and wal["size"] > 0) else "ok"
    return {
        "schema_hash": short_hash(schema_text),
        "objects": len(rows),
        "tables": tables,
        "journal_mode": journal_mode,
        "wal": wal,
        "consistency": consistency,
    }


def _immutable_read(path: Path, wal: dict[str, Any]) -> dict[str, Any] | None:
    try:
        uri = f"{path.resolve().as_uri()}?immutable=1&mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=1.0)
    except sqlite3.Error:
        return None
    try:
        result = _read_summary(conn, wal)
    finally:
        conn.close()
    if result.get("consistency") == "unreadable":
        return None
    result["consistency"] = "immutable-fallback"
    result["stale"] = True
    result["note"] = "WAL ignored — counts predate uncommitted WAL frames"
    return result


def sqlite_summary(path: Path, *, immutable_fallback: bool = False) -> dict[str, Any] | None:
    if path.suffix not in DB_SUFFIXES:
        return None
    wal = wal_sibling_state(path)
    try:
        conn = open_readonly(path)
    except sqlite3.Error as exc:
        result = _unreadable(exc, wal)
    else:
        try:
            result = _read_summary(conn, wal)
        finally:
            conn.close()
    if immutable_fallback and result.get("consistency") == "unreadable":
        fallback = _immutable_read(path, wal)
        if fallback is not None:
            return fallback
    return result
