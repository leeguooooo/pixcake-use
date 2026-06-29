from __future__ import annotations

import argparse
import dataclasses
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from .diff import diff_snapshots, print_diff, summarize_sqlite_diff
from .discovery import (
    candidate_paths,
    iter_default_databases,
    pixcake_processes,
    read_app_version,
)
from .environment import Environment, default_environment
from .params import collect_params, maybe_json
from .photo_render import decode_raw, render_graded
from .photos import discover_project_dbs, list_photos, recipe_summary, to_dict
from .snapshot import build_snapshot, load_snapshot, write_json
from .sqlite_inspect import open_readonly, sqlite_summary, wal_sibling_state
from .writeops import apply_recipe_to_current_record, apply_recipe_to_row

# Backward-compatible re-exports: historical imports such as
# `from pixcake_use.cli import diff_snapshots` keep working.
__all__ = [
    "diff_snapshots",
    "print_diff",
    "summarize_sqlite_diff",
    "build_snapshot",
    "load_snapshot",
    "sqlite_summary",
    "collect_params",
    "maybe_json",
    "Environment",
    "default_environment",
    "build_parser",
    "main",
]

_RUNNING_WARNING = (
    "WARNING: PixCake is running. Snapshots/row counts may miss in-flight "
    "changes still in the -wal. Quit PixCake before snapshot/watch for a "
    "consistent read."
)


def command_doctor(args: argparse.Namespace, env: Environment) -> int:
    print(f"PixCake app: {env.app_path}")
    print(f"Installed: {env.app_path.exists()}")
    print(f"Version: {read_app_version(env) or 'unknown'}")
    print(f"Support dir: {env.support_dir}")
    print("")
    for item in candidate_paths(env):
        status = "ok" if item.exists else "missing"
        print(f"{status:7} {item.kind:12} {item.path}")
    print("")
    processes = pixcake_processes()
    print(f"Running processes: {len(processes)}")
    for process in processes:
        print(f"  {process}")
    if shutil.which("sqlite3"):
        print("sqlite3: available")
    else:
        print("sqlite3: not found, Python sqlite3 is still used internally")
    if processes:
        print(_RUNNING_WARNING, file=sys.stderr)
    return 0


def command_snapshot(args: argparse.Namespace, env: Environment) -> int:
    snapshot = build_snapshot(
        env,
        include_logs=not args.no_logs,
        extra_paths=[Path(p).expanduser() for p in args.path],
    )
    output_dir = Path(args.output_dir)
    name = args.name or datetime.now().strftime("%Y%m%d-%H%M%S")
    output_path = output_dir / f"{name}.json"
    write_json(output_path, snapshot)
    print(f"Wrote {output_path.resolve()}")
    print(f"Files: {len(snapshot['files'])}")
    if snapshot.get("pixcake_running"):
        print(_RUNNING_WARNING, file=sys.stderr)
    return 0


def command_diff(args: argparse.Namespace, env: Environment) -> int:
    try:
        before = load_snapshot(Path(args.before))
        after = load_snapshot(Path(args.after))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    diff = diff_snapshots(before, after)
    print_diff(diff, json_output=args.json)
    return 0


def command_watch(args: argparse.Namespace, env: Environment) -> int:
    import time

    output_dir = Path(args.output_dir)
    name = args.name or datetime.now().strftime("%Y%m%d-%H%M%S")
    extra = [Path(p).expanduser() for p in args.path]
    print("Taking baseline snapshot...")
    before = build_snapshot(env, include_logs=not args.no_logs, extra_paths=extra)
    if before.get("pixcake_running"):
        print(_RUNNING_WARNING, file=sys.stderr)
    print(f"Watching for {args.seconds} seconds. Perform the PixCake UI action now.")
    deadline = time.monotonic() + args.seconds
    while time.monotonic() < deadline:
        remaining = int(deadline - time.monotonic())
        print(f"\rRemaining: {remaining:3d}s", end="", flush=True)
        time.sleep(1)
    print("\nTaking final snapshot...")
    after = build_snapshot(env, include_logs=not args.no_logs, extra_paths=extra)
    if after.get("pixcake_running"):
        print(_RUNNING_WARNING, file=sys.stderr)
    before_path = output_dir / f"{name}-before.json"
    after_path = output_dir / f"{name}-after.json"
    diff_path = output_dir / f"{name}-diff.json"
    write_json(before_path, before)
    write_json(after_path, after)
    diff = diff_snapshots(before, after)
    write_json(diff_path, diff)
    print(f"Wrote {before_path.resolve()}")
    print(f"Wrote {after_path.resolve()}")
    print(f"Wrote {diff_path.resolve()}")
    print_diff(diff, json_output=False)
    return 0


def command_schema(args: argparse.Namespace, env: Environment) -> int:
    db_path = Path(args.database).expanduser()
    summary = sqlite_summary(db_path, immutable_fallback=args.immutable_fallback)
    if summary is None:
        print(f"Not a supported SQLite path: {db_path}", file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_tables(args: argparse.Namespace, env: Environment) -> int:
    needle = args.filter.lower() if args.filter else None
    rows = []
    for db_path in sorted(iter_default_databases(env), key=lambda item: str(item)):
        summary = sqlite_summary(db_path, immutable_fallback=args.immutable_fallback)
        if not isinstance(summary, dict) or summary.get("error"):
            continue
        for table in summary.get("tables", []):
            name = table["name"]
            if needle and needle not in name.lower() and needle not in str(db_path).lower():
                continue
            rows.append(
                {
                    "database": str(db_path),
                    "table": name,
                    "rows": table.get("rows"),
                    "schema_hash": table.get("schema_hash"),
                }
            )
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    for row in rows:
        print(f"{row['rows']!s:>8} {row['table']:<32} {row['database']}")
    return 0


def command_rows(args: argparse.Namespace, env: Environment) -> int:
    db_path = Path(args.database).expanduser()
    table = args.table.replace('"', '""')
    limit = max(1, min(args.limit, 200))
    try:
        conn = open_readonly(db_path)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        print(f"Failed to open database: {exc}", file=sys.stderr)
        return 2
    try:
        try:
            result = conn.execute(f'select * from "{table}" limit ?', (limit,)).fetchall()
        except sqlite3.Error as exc:
            print(f"Failed to query table: {exc}", file=sys.stderr)
            return 2
        payload = [dict(row) for row in result]
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str))
        return 0
    finally:
        conn.close()


def command_params(args: argparse.Namespace, env: Environment) -> int:
    db_path = Path(args.database).expanduser()
    table = args.table.replace('"', '""')
    column = args.column.replace('"', '""')
    try:
        conn = open_readonly(db_path)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        print(f"Failed to open database: {exc}", file=sys.stderr)
        return 2
    try:
        try:
            row = conn.execute(f'select * from "{table}" where id = ? limit 1', (args.id,)).fetchone()
        except sqlite3.Error as exc:
            print(f"Failed to query table: {exc}", file=sys.stderr)
            return 2
        if row is None:
            print(f"No row with id={args.id}", file=sys.stderr)
            return 1
        columns = row.keys() if column == "*" else [column]
        payload = []
        for item_column in columns:
            if item_column not in row.keys():
                continue
            for param in collect_params(row[item_column], f"{table}.{item_column}"):
                param["column"] = item_column
                payload.append(param)
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        for param in payload:
            value = param.get("value")
            if isinstance(value, list):
                value = f"list[{len(value)}]"
            name = param.get("name") or ""
            print(
                f"{param.get('pf')!s:>6} {param.get('value_type', ''):<2} "
                f"{str(value):<12} {name:<24} {param['path']}"
            )
        return 0
    finally:
        conn.close()


def command_apply_recipe(args: argparse.Namespace, env: Environment) -> int:
    db_path = Path(args.database).expanduser()
    recipe_path = Path(args.recipe).expanduser()
    try:
        recipe = json.loads(recipe_path.read_text())
        return apply_recipe_to_row(
            db_path,
            args.table,
            args.id,
            recipe,
            backup_dir=Path(args.backup_dir),
            no_backup=args.no_backup,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2


def command_apply_current_record(args: argparse.Namespace, env: Environment) -> int:
    db_path = Path(args.database).expanduser()
    recipe_path = Path(args.recipe).expanduser()
    try:
        recipe = json.loads(recipe_path.read_text())
        return apply_recipe_to_current_record(
            db_path,
            args.thumbnail_id,
            recipe,
            recipe_path.stem,
            backup_dir=Path(args.backup_dir),
            no_backup=args.no_backup,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2


def command_photos(args: argparse.Namespace, env: Environment) -> int:
    if args.database:
        dbs = [Path(args.database).expanduser()]
    else:
        dbs = discover_project_dbs(env)
    if not dbs:
        print("No PixCake project databases found.", file=sys.stderr)
        return 1

    extract_dir: Path | None = None
    if args.extract or args.graded:
        extract_dir = Path(args.extract) if args.extract else Path("photo-previews")

    all_photos = []
    for db in dbs:
        try:
            all_photos.extend(list_photos(db))
        except Exception as exc:  # noqa: BLE001 - report and continue across dbs
            print(f"Skipping {db}: {exc}", file=sys.stderr)

    if args.json:
        payload = [to_dict(p) for p in all_photos]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"{'pos':>3} {'id':>3} {'edited':6} {'name':<14} {'size':>11}  recipe")
        for p in all_photos:
            mark = "yes" if p.edited else "-"
            size = f"{p.width}x{p.height}"
            print(f"{p.position:>3} {p.thumbnail_id:>3} {mark:6} {p.name:<14} {size:>11}  {recipe_summary(p)}")

    if extract_dir is not None:
        print(f"\nExtracting previews to {extract_dir.resolve()} ...")
        for p in all_photos:
            src = Path(p.original_path).expanduser()
            if not src.exists():
                print(f"  {p.name}: original missing ({src})", file=sys.stderr)
                continue
            jpg = extract_dir / f"{p.position:02d}_{p.name}.jpg"
            if not decode_raw(src, jpg, max_px=args.max_px):
                print(f"  {p.name}: sips decode failed", file=sys.stderr)
                continue
            line = f"  {p.name}: {jpg.name}"
            if args.graded and p.named_params:
                graded = extract_dir / f"{p.position:02d}_{p.name}_graded.png"
                try:
                    render_graded(jpg, graded, p.named_params)
                    line += f" + {graded.name}"
                except ImportError as exc:
                    print(str(exc), file=sys.stderr)
                    return 2
            print(line)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pixcake-use", description="PixCake local probing CLI")
    parser.add_argument("--app-path", help=argparse.SUPPRESS)
    parser.add_argument("--support-dir", help=argparse.SUPPRESS)
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="Show detected PixCake paths and runtime state")
    doctor.set_defaults(func=command_doctor)

    snapshot = subparsers.add_parser("snapshot", help="Write a JSON snapshot of PixCake local data")
    snapshot.add_argument("--name", help="Snapshot file name without .json")
    snapshot.add_argument("--output-dir", default="snapshots")
    snapshot.add_argument("--no-logs", action="store_true", help="Skip log files")
    snapshot.add_argument("--path", action="append", default=[], help="Extra file or directory to include")
    snapshot.set_defaults(func=command_snapshot)

    diff = subparsers.add_parser("diff", help="Diff two snapshot JSON files")
    diff.add_argument("before")
    diff.add_argument("after")
    diff.add_argument("--json", action="store_true", help="Print full JSON diff")
    diff.set_defaults(func=command_diff)

    watch = subparsers.add_parser("watch", help="Take before/after snapshots around a manual PixCake action")
    watch.add_argument("--seconds", type=int, default=30)
    watch.add_argument("--name", help="Output file prefix")
    watch.add_argument("--output-dir", default="snapshots")
    watch.add_argument("--no-logs", action="store_true", help="Skip log files")
    watch.add_argument("--path", action="append", default=[], help="Extra file or directory to include")
    watch.set_defaults(func=command_watch)

    schema = subparsers.add_parser("schema", help="Inspect a PixCake SQLite database")
    schema.add_argument("database")
    schema.add_argument(
        "--immutable-fallback",
        action="store_true",
        help="If the DB is unreadable, retry read-only with immutable=1 (WAL ignored, counts may be stale)",
    )
    schema.set_defaults(func=command_schema)

    tables = subparsers.add_parser("tables", help="List tables across detected PixCake SQLite databases")
    tables.add_argument("--filter", help="Filter by table or database path substring")
    tables.add_argument("--json", action="store_true", help="Print JSON rows")
    tables.add_argument(
        "--immutable-fallback",
        action="store_true",
        help="If a DB is unreadable, retry read-only with immutable=1 (WAL ignored, counts may be stale)",
    )
    tables.set_defaults(func=command_tables)

    rows = subparsers.add_parser("rows", help="Dump a few rows from a SQLite table as JSON")
    rows.add_argument("database")
    rows.add_argument("table")
    rows.add_argument("--limit", type=int, default=20)
    rows.set_defaults(func=command_rows)

    params = subparsers.add_parser("params", help="Extract PixCake pf parameters from a JSON config column")
    params.add_argument("database")
    params.add_argument("table")
    params.add_argument("--id", type=int, required=True, help="Row id to inspect")
    params.add_argument("--column", default="paletteCfg", help="JSON column to parse, or * for all columns")
    params.add_argument("--json", action="store_true", help="Print JSON rows")
    params.set_defaults(func=command_params)

    apply_recipe = subparsers.add_parser("apply-recipe", help="Apply pf parameter updates to a config row")
    apply_recipe.add_argument("database")
    apply_recipe.add_argument("table")
    apply_recipe.add_argument("--id", type=int, required=True, help="Row id to update")
    apply_recipe.add_argument("--recipe", required=True, help="Recipe JSON file")
    apply_recipe.add_argument("--backup-dir", default="backups", help="Directory for database backups")
    apply_recipe.add_argument("--no-backup", action="store_true", help="Do not copy db/-wal/-shm before writing")
    apply_recipe.set_defaults(func=command_apply_recipe)

    apply_current = subparsers.add_parser(
        "apply-current-record",
        help="Apply a recipe to thumbnail.currentOptRecordId and its paletteJsonPath file",
    )
    apply_current.add_argument("database")
    apply_current.add_argument("--thumbnail-id", type=int, required=True, help="Thumbnail id to update")
    apply_current.add_argument("--recipe", required=True, help="Recipe JSON file")
    apply_current.add_argument("--backup-dir", default="backups", help="Directory for database and palette backups")
    apply_current.add_argument(
        "--no-backup", action="store_true", help="Do not copy db/-wal/-shm/palette before writing"
    )
    apply_current.set_defaults(func=command_apply_current_record)

    photos = subparsers.add_parser(
        "photos",
        help="List PixCake photos, decode RAW previews, and render approximate graded previews",
    )
    photos.add_argument("database", nargs="?", help="project.db (default: auto-discover under support dir)")
    photos.add_argument("--extract", metavar="DIR", help="Decode RAW originals to viewable JPEGs in DIR")
    photos.add_argument(
        "--graded",
        action="store_true",
        help="Also render an approximate graded preview from each photo's recipe (needs render extra)",
    )
    photos.add_argument("--max-px", type=int, default=1600, help="Longest edge for decoded previews")
    photos.add_argument("--json", action="store_true", help="Print JSON")
    photos.set_defaults(func=command_photos)
    return parser


def _resolve_env(args: argparse.Namespace) -> Environment:
    env = default_environment()
    changes: dict[str, Path] = {}
    if getattr(args, "app_path", None):
        changes["app_path"] = Path(args.app_path).expanduser()
    if getattr(args, "support_dir", None):
        changes["support_dir"] = Path(args.support_dir).expanduser()
    if changes:
        env = dataclasses.replace(env, **changes)
    return env


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    env = _resolve_env(args)
    return args.func(args, env)
