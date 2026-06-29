from __future__ import annotations

import json
from typing import Any

_WAL_SUFFIXES = (".db-wal", ".db-shm")
_FLAGGED_CONSISTENCY = {"unreadable", "wal-present"}


def _is_wal(path: str) -> bool:
    return path.endswith(_WAL_SUFFIXES)


def summarize_sqlite_diff(old: Any, new: Any) -> dict[str, Any]:
    if not isinstance(old, dict) or not isinstance(new, dict):
        return {"before": old, "after": new}
    result: dict[str, Any] = {}
    if old.get("schema_hash") != new.get("schema_hash"):
        result["schema_hash"] = {"before": old.get("schema_hash"), "after": new.get("schema_hash")}
    old_tables = {table.get("name"): table for table in old.get("tables", [])}
    new_tables = {table.get("name"): table for table in new.get("tables", [])}
    table_changes = []
    for name in sorted(set(old_tables) | set(new_tables)):
        if old_tables.get(name) != new_tables.get(name):
            table_changes.append(
                {"name": name, "before": old_tables.get(name), "after": new_tables.get(name)}
            )
    if table_changes:
        result["tables"] = table_changes
    old_c = old.get("consistency")
    new_c = new.get("consistency")
    if old_c != new_c or old_c in _FLAGGED_CONSISTENCY or new_c in _FLAGGED_CONSISTENCY:
        result["consistency"] = {"before": old_c, "after": new_c}
    return result


def classify_change(old: dict[str, Any], new: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    changes: dict[str, Any] = {}
    for key in ("size", "mtime_ns", "sha256"):
        if old.get(key) != new.get(key):
            changes[key] = {"before": old.get(key), "after": new.get(key)}
    if old.get("sqlite") != new.get("sqlite"):
        changes["sqlite"] = summarize_sqlite_diff(old.get("sqlite"), new.get("sqlite"))
    content = any(k in changes for k in ("size", "sha256", "sqlite"))
    kind = "content" if content else "metadata"
    return kind, changes


def diff_snapshots(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_files = before.get("files", {})
    after_files = after.get("files", {})
    before_paths = set(before_files)
    after_paths = set(after_files)
    added = sorted(after_paths - before_paths)
    removed = sorted(before_paths - after_paths)

    content_entries: list[dict[str, Any]] = []
    metadata_entries: list[dict[str, Any]] = []
    for path in sorted(before_paths & after_paths):
        kind, changes = classify_change(before_files[path], after_files[path])
        if not changes:
            continue
        entry = {"path": path, "kind": kind, "changes": changes}
        if kind == "content":
            content_entries.append(entry)
        else:
            metadata_entries.append(entry)

    # Content entries first (sorted by path), then metadata-only (sorted by path).
    changed = content_entries + metadata_entries
    content_changed = [entry["path"] for entry in content_entries]
    metadata_only = [entry["path"] for entry in metadata_entries]

    wal_changes: list[dict[str, Any]] = []
    for path in added:
        if _is_wal(path):
            wal_changes.append({"path": path, "kind": "added", "changes": {}})
    for path in removed:
        if _is_wal(path):
            wal_changes.append({"path": path, "kind": "removed", "changes": {}})
    for entry in changed:
        if _is_wal(entry["path"]):
            wal_changes.append(entry)

    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "content_changed": content_changed,
        "metadata_only": metadata_only,
        "wal_changes": wal_changes,
    }


def print_diff(diff: dict[str, Any], json_output: bool = False) -> None:
    if json_output:
        print(json.dumps(diff, ensure_ascii=False, indent=2, sort_keys=True))
        return

    wal_changes = diff.get("wal_changes", [])
    print(f"WAL/-shm changes: {len(wal_changes)}")
    for item in wal_changes:
        print(f"  ! {item['path']} (live DB content moved)")

    print(f"Added: {len(diff['added'])}")
    for path in diff["added"]:
        print(f"  + {path}")

    print(f"Removed: {len(diff['removed'])}")
    for path in diff["removed"]:
        print(f"  - {path}")

    content = [entry for entry in diff["changed"] if entry.get("kind") == "content"]
    print(f"Content changes: {len(content)}")
    for item in content:
        print(f"  * {item['path']}")
        changes = item["changes"]
        if "size" in changes:
            print(f"    size: {changes['size']['before']} -> {changes['size']['after']}")
        if "sha256" in changes:
            print("    content: sha256 changed")
        if "sqlite" in changes:
            sqlite = changes["sqlite"]
            if "consistency" in sqlite:
                consistency = sqlite["consistency"]
                print(
                    f"    sqlite consistency: {consistency.get('before')} -> {consistency.get('after')}"
                )
            if "schema_hash" in sqlite:
                print("    sqlite schema changed")
            for table in sqlite.get("tables", [])[:20]:
                before = table.get("before") or {}
                after = table.get("after") or {}
                before_rows = before.get("rows")
                after_rows = after.get("rows")
                if before_rows != after_rows:
                    print(f"    table {table['name']}: rows {before_rows} -> {after_rows}")

    metadata = [entry for entry in diff["changed"] if entry.get("kind") != "content"]
    print(f"Metadata-only (mtime): {len(metadata)}")
    for item in metadata:
        print(f"  ~ {item['path']}")
