# pixcake-use

Local PixCake probing CLI. The MVP is intentionally read-only: it locates PixCake data, snapshots files and SQLite databases, and diffs snapshots after a manual UI action such as saving a new preset.

## Quick Start

```bash
cd /Users/leo/github.com/pixcake-use
python3 -m pixcake_use doctor
python3 -m pixcake_use snapshot --name before
# In PixCake: change exactly one parameter, then save a preset or sync to the selected image.
python3 -m pixcake_use snapshot --name after
python3 -m pixcake_use diff snapshots/before.json snapshots/after.json
```

For a timed capture while you perform a UI action:

```bash
python3 -m pixcake_use watch --seconds 30 --name exposure-plus
```

Find likely preset/config tables:

```bash
python3 -m pixcake_use tables --filter preset
```

Extract parameter IDs and values from a PixCake config row:

```bash
python3 -m pixcake_use params \
  "$HOME/Library/Application Support/PixCake-qt_pro/db/user_<id>/project_<id>/project.db" \
  presets_config_detail \
  --id 2
```

Apply a recipe to one PixCake config row:

```bash
python3 -m pixcake_use apply-recipe \
  "$HOME/Library/Application Support/PixCake-qt_pro/db/user_<id>/project_<id>/project.db" \
  presets_config_detail \
  --id 1 \
  --recipe recipes/low-key-cat-publish.json
```

Apply a recipe to the thumbnail's active PixCake edit record:

```bash
python3 -m pixcake_use apply-current-record \
  "$HOME/Library/Application Support/PixCake-qt_pro/db/user_<id>/project_<id>/project.db" \
  --thumbnail-id 1 \
  --recipe recipes/low-key-cat-publish.json
```

List photos, decode RAW previews, and render an approximate graded preview:

```bash
# List every photo (grid position, id, edited?, recipe summary) across discovered projects
python3 -m pixcake_use photos

# Decode RAW originals to viewable JPEGs, and render an offline approximation
# of each photo's current grade (needs the render extra: pip install 'pixcake-use[render]')
python3 -m pixcake_use photos --extract photo-previews --graded
```

RAW decoding uses macOS `sips` (no dependency). `--graded` reproduces the look with standard image math via Pillow/numpy — it is an approximation, not a pixel-exact copy of PixCake's render engine, and it does **not** read PixCake's encrypted `FXIP` preview cache.

## Current Scope

- Finds `/Applications/pixcake.app`.
- Finds PixCake support, project, database, log, and preference paths.
- Creates deterministic JSON snapshots.
- Summarizes changed files.
- Inspects SQLite schemas and table row counts without writing to PixCake data.
- Extracts nested `pf` parameter records from `paletteCfg` / `beautifyCfg` JSON columns.
- Applies explicit `pf` recipe updates to a selected config row with automatic SQLite-family backups.
- Applies recipes to `thumbnail.currentOptRecordId` and its `paletteJsonPath`, which is the active edit path used by PixCake preview/export.
- Lists photos with their current recipe, decodes RAW originals via `sips`, and renders an approximate offline grade (optional `render` extra).

## Quiescing for accurate diffs

Quit PixCake (or at least stop editing) before running `snapshot` / `watch`. SQLite databases run in WAL mode, so a live PixCake writer keeps uncommitted edits in the `*.db-wal` sidecar file. A read-only probe sees only committed frames: if PixCake is running with a non-empty `-wal`, the reported row counts reflect the **last commit**, not the unsaved edit you just made.

`doctor`, `snapshot`, and `watch` print a warning to stderr when a PixCake process is detected. The diff output flags the same condition two ways:

- `consistency: wal-present` on a SQLite summary means a non-empty `-wal` was present at read time, so the counts may be stale.
- `wal_changes` lists any changed `*.db-wal` / `*.db-shm` siblings first — a WAL hash change is the strongest signal that the live database content moved.

For a clean diff: quit PixCake, perform the action, reopen, then snapshot. The probe never checkpoints or writes to live PixCake data.

## Safety Boundary

This project targets local automation for your own account and your own images. It does not bypass login, paid features, quotas, signatures, or service-side checks.
