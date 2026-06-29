"""Diff-semantics tests for the refactored pixcake_use.diff module.

Scope (per task): content-vs-metadata classification, added/removed
detection, and SQLite table row-count diff summarization. All fixtures
are plain in-memory snapshot dicts; nothing touches real PixCake data.
"""

from pixcake_use.diff import classify_change, diff_snapshots, summarize_sqlite_diff


def _snapshot(files):
    return {"files": files}


# --- content vs metadata separation ------------------------------------


def test_mtime_only_change_is_metadata():
    before = _snapshot({"/x/f": {"sha256": "a", "size": 10, "mtime_ns": 100}})
    after = _snapshot({"/x/f": {"sha256": "a", "size": 10, "mtime_ns": 200}})

    diff = diff_snapshots(before, after)

    entry = diff["changed"][0]
    assert entry["path"] == "/x/f"
    assert entry["kind"] == "metadata"
    assert "/x/f" in diff["metadata_only"]
    assert "/x/f" not in diff["content_changed"]
    # Only mtime_ns moved -> that is the only recorded change.
    assert set(entry["changes"]) == {"mtime_ns"}
    assert entry["changes"]["mtime_ns"] == {"before": 100, "after": 200}


def test_sha256_change_is_content():
    before = _snapshot({"/x/f": {"sha256": "a", "size": 10, "mtime_ns": 100}})
    after = _snapshot({"/x/f": {"sha256": "b", "size": 10, "mtime_ns": 100}})

    diff = diff_snapshots(before, after)

    entry = diff["changed"][0]
    assert entry["kind"] == "content"
    assert "/x/f" in diff["content_changed"]
    assert "/x/f" not in diff["metadata_only"]
    assert entry["changes"]["sha256"] == {"before": "a", "after": "b"}


def test_size_change_is_content():
    before = _snapshot({"/x/f": {"sha256": "a", "size": 10, "mtime_ns": 100}})
    after = _snapshot({"/x/f": {"sha256": "a", "size": 20, "mtime_ns": 100}})

    entry = diff_snapshots(before, after)["changed"][0]
    assert entry["kind"] == "content"
    assert entry["changes"]["size"] == {"before": 10, "after": 20}


def test_sqlite_change_is_content_even_without_hash_move():
    # sqlite summary differs while sha256/size/mtime stay equal -> still content.
    before = _snapshot(
        {
            "/x/db.db": {
                "sha256": "a",
                "size": 10,
                "mtime_ns": 100,
                "sqlite": {"schema_hash": "s", "tables": [{"name": "t", "rows": 1}]},
            }
        }
    )
    after = _snapshot(
        {
            "/x/db.db": {
                "sha256": "a",
                "size": 10,
                "mtime_ns": 100,
                "sqlite": {"schema_hash": "s", "tables": [{"name": "t", "rows": 5}]},
            }
        }
    )

    entry = diff_snapshots(before, after)["changed"][0]
    assert entry["kind"] == "content"
    assert "sqlite" in entry["changes"]


def test_classify_change_unit_metadata_vs_content():
    kind, changes = classify_change(
        {"sha256": "a", "size": 1, "mtime_ns": 1},
        {"sha256": "a", "size": 1, "mtime_ns": 2},
    )
    assert kind == "metadata"
    assert set(changes) == {"mtime_ns"}

    kind, changes = classify_change(
        {"sha256": "a", "size": 1, "mtime_ns": 1},
        {"sha256": "b", "size": 1, "mtime_ns": 1},
    )
    assert kind == "content"
    assert "sha256" in changes


def test_no_change_is_not_reported():
    rec = {"sha256": "a", "size": 10, "mtime_ns": 100}
    diff = diff_snapshots(_snapshot({"/x/f": dict(rec)}), _snapshot({"/x/f": dict(rec)}))
    assert diff["changed"] == []
    assert diff["content_changed"] == []
    assert diff["metadata_only"] == []


def test_content_entries_ordered_before_metadata():
    # Path ordering would put the metadata file first alphabetically; the
    # classifier must still surface the content change at index 0.
    before = _snapshot(
        {
            "/x/a-meta": {"sha256": "a", "size": 1, "mtime_ns": 1},
            "/x/z-content": {"sha256": "a", "size": 1, "mtime_ns": 1},
        }
    )
    after = _snapshot(
        {
            "/x/a-meta": {"sha256": "a", "size": 1, "mtime_ns": 9},
            "/x/z-content": {"sha256": "b", "size": 1, "mtime_ns": 1},
        }
    )
    changed = diff_snapshots(before, after)["changed"]
    assert changed[0]["kind"] == "content"
    assert changed[0]["path"] == "/x/z-content"
    assert changed[1]["kind"] == "metadata"


# --- added / removed detection -----------------------------------------


def test_added_and_removed_detection():
    before = _snapshot(
        {
            "/x/keep": {"sha256": "a", "size": 1, "mtime_ns": 1},
            "/x/gone": {"sha256": "a", "size": 1, "mtime_ns": 1},
        }
    )
    after = _snapshot(
        {
            "/x/keep": {"sha256": "a", "size": 1, "mtime_ns": 1},
            "/x/new": {"sha256": "a", "size": 1, "mtime_ns": 1},
        }
    )
    diff = diff_snapshots(before, after)
    assert diff["added"] == ["/x/new"]
    assert diff["removed"] == ["/x/gone"]
    # Unchanged file is neither added/removed/changed.
    assert diff["changed"] == []


def test_added_and_removed_are_sorted():
    before = _snapshot(
        {
            "/x/r2": {"sha256": "a", "size": 1, "mtime_ns": 1},
            "/x/r1": {"sha256": "a", "size": 1, "mtime_ns": 1},
        }
    )
    after = _snapshot(
        {
            "/x/a2": {"sha256": "a", "size": 1, "mtime_ns": 1},
            "/x/a1": {"sha256": "a", "size": 1, "mtime_ns": 1},
        }
    )
    diff = diff_snapshots(before, after)
    assert diff["added"] == ["/x/a1", "/x/a2"]
    assert diff["removed"] == ["/x/r1", "/x/r2"]


def test_empty_snapshots_yield_empty_diff():
    diff = diff_snapshots(_snapshot({}), _snapshot({}))
    assert diff["added"] == []
    assert diff["removed"] == []
    assert diff["changed"] == []
    assert diff["wal_changes"] == []


# --- sqlite table row-count diff summarization -------------------------


def test_summarize_sqlite_diff_row_count_delta():
    old = {"schema_hash": "s", "tables": [{"name": "palette", "rows": 3}]}
    new = {"schema_hash": "s", "tables": [{"name": "palette", "rows": 7}]}

    summary = summarize_sqlite_diff(old, new)

    # Schema unchanged -> no schema_hash key.
    assert "schema_hash" not in summary
    assert "tables" in summary
    table_delta = {t["name"]: t for t in summary["tables"]}
    assert table_delta["palette"]["before"]["rows"] == 3
    assert table_delta["palette"]["after"]["rows"] == 7


def test_summarize_sqlite_diff_row_count_surfaced_in_diff_snapshots():
    before = _snapshot(
        {
            "/x/db.db": {
                "sha256": "a",
                "size": 10,
                "mtime_ns": 100,
                "sqlite": {"schema_hash": "s", "tables": [{"name": "t", "rows": 1}]},
            }
        }
    )
    after = _snapshot(
        {
            "/x/db.db": {
                "sha256": "b",
                "size": 11,
                "mtime_ns": 200,
                "sqlite": {"schema_hash": "s", "tables": [{"name": "t", "rows": 4}]},
            }
        }
    )
    entry = diff_snapshots(before, after)["changed"][0]
    sqlite_delta = entry["changes"]["sqlite"]
    table_delta = {t["name"]: t for t in sqlite_delta["tables"]}
    assert table_delta["t"]["before"]["rows"] == 1
    assert table_delta["t"]["after"]["rows"] == 4


def test_summarize_sqlite_diff_schema_change_surfaced():
    old = {"schema_hash": "s1", "tables": []}
    new = {"schema_hash": "s2", "tables": []}
    summary = summarize_sqlite_diff(old, new)
    assert summary["schema_hash"] == {"before": "s1", "after": "s2"}


def test_summarize_sqlite_diff_added_and_removed_tables():
    old = {"schema_hash": "s", "tables": [{"name": "gone", "rows": 1}]}
    new = {"schema_hash": "s", "tables": [{"name": "fresh", "rows": 2}]}
    summary = summarize_sqlite_diff(old, new)
    table_delta = {t["name"]: t for t in summary["tables"]}
    assert table_delta["gone"]["before"]["rows"] == 1
    assert table_delta["gone"]["after"] is None
    assert table_delta["fresh"]["before"] is None
    assert table_delta["fresh"]["after"]["rows"] == 2


def test_summarize_sqlite_diff_non_dict_inputs():
    # Defensive path: a None vs dict (e.g. summary appeared/disappeared).
    summary = summarize_sqlite_diff(None, {"schema_hash": "s", "tables": []})
    assert summary == {"before": None, "after": {"schema_hash": "s", "tables": []}}


def test_summarize_sqlite_diff_identical_summary_has_no_table_delta():
    same = {"schema_hash": "s", "tables": [{"name": "t", "rows": 3}]}
    summary = summarize_sqlite_diff(dict(same), dict(same))
    assert "tables" not in summary
    assert "schema_hash" not in summary
