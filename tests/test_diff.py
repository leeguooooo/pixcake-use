import unittest

from pixcake_use.diff import diff_snapshots


class DiffSnapshotTests(unittest.TestCase):
    def test_diff_snapshots_detects_added_removed_and_changed(self):
        before = {
            "files": {
                "/tmp/a": {"sha256": "old", "size": 1, "mtime_ns": 1},
                "/tmp/remove": {"sha256": "x", "size": 1, "mtime_ns": 1},
            }
        }
        after = {
            "files": {
                "/tmp/a": {"sha256": "new", "size": 2, "mtime_ns": 2},
                "/tmp/add": {"sha256": "y", "size": 1, "mtime_ns": 1},
            }
        }

        diff = diff_snapshots(before, after)

        self.assertEqual(diff["added"], ["/tmp/add"])
        self.assertEqual(diff["removed"], ["/tmp/remove"])
        self.assertEqual(diff["changed"][0]["path"], "/tmp/a")
        self.assertEqual(diff["changed"][0]["changes"]["size"], {"before": 1, "after": 2})


def test_content_vs_metadata_separation():
    before = {
        "files": {
            "/tmp/meta": {"sha256": "x", "size": 1, "mtime_ns": 1},
            "/tmp/content": {"sha256": "x", "size": 1, "mtime_ns": 1},
        }
    }
    after = {
        "files": {
            "/tmp/meta": {"sha256": "x", "size": 1, "mtime_ns": 999},
            "/tmp/content": {"sha256": "y", "size": 1, "mtime_ns": 999},
        }
    }
    diff = diff_snapshots(before, after)

    by_path = {entry["path"]: entry for entry in diff["changed"]}
    assert by_path["/tmp/meta"]["kind"] == "metadata"
    assert by_path["/tmp/content"]["kind"] == "content"
    assert "/tmp/meta" in diff["metadata_only"]
    assert "/tmp/meta" not in diff["content_changed"]
    assert "/tmp/content" in diff["content_changed"]


def test_content_entries_ordered_first():
    before = {
        "files": {
            "/tmp/a-meta": {"sha256": "x", "size": 1, "mtime_ns": 1},
            "/tmp/z-content": {"sha256": "x", "size": 1, "mtime_ns": 1},
        }
    }
    after = {
        "files": {
            "/tmp/a-meta": {"sha256": "x", "size": 1, "mtime_ns": 2},
            "/tmp/z-content": {"sha256": "y", "size": 1, "mtime_ns": 1},
        }
    }
    diff = diff_snapshots(before, after)
    assert diff["changed"][0]["kind"] == "content"
    assert diff["changed"][0]["path"] == "/tmp/z-content"


def test_wal_change_surfaced():
    before = {"files": {"/tmp/project.db-wal": {"sha256": "a", "size": 1, "mtime_ns": 1}}}
    after = {"files": {"/tmp/project.db-wal": {"sha256": "b", "size": 2, "mtime_ns": 2}}}
    diff = diff_snapshots(before, after)
    wal_paths = [entry["path"] for entry in diff["wal_changes"]]
    assert "/tmp/project.db-wal" in wal_paths


def test_sqlite_consistency_surfaced():
    before = {
        "files": {
            "/tmp/p.db": {
                "sha256": "x",
                "size": 1,
                "mtime_ns": 1,
                "sqlite": {"schema_hash": "s", "tables": [], "consistency": "ok"},
            }
        }
    }
    after = {
        "files": {
            "/tmp/p.db": {
                "sha256": "x",
                "size": 1,
                "mtime_ns": 1,
                "sqlite": {"schema_hash": "s", "tables": [], "consistency": "wal-present"},
            }
        }
    }
    diff = diff_snapshots(before, after)
    entry = diff["changed"][0]
    assert entry["kind"] == "content"
    assert entry["changes"]["sqlite"]["consistency"] == {"before": "ok", "after": "wal-present"}


if __name__ == "__main__":
    unittest.main()
