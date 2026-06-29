import sqlite3
import tempfile
import unittest
from pathlib import Path

from pixcake_use.diff import summarize_sqlite_diff
from pixcake_use.sqlite_inspect import (
    open_readonly,
    sqlite_summary,
    wal_sibling_state,
)


def _make_plain_db(path: Path, rows: int = 3) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("create table widgets (id integer primary key, name text)")
        conn.execute("create table gadgets (id integer primary key)")
        conn.execute("create index idx_widgets_name on widgets(name)")
        for i in range(rows):
            conn.execute("insert into widgets (name) values (?)", (f"w{i}",))
        conn.commit()
    finally:
        conn.close()


def _make_wal_db(path: Path, rows: int = 5) -> sqlite3.Connection:
    """Create a WAL-mode db and return an *open* connection holding committed
    frames so a non-empty -wal sits next to the file (closing can checkpoint
    and truncate it)."""
    conn = sqlite3.connect(str(path))
    conn.execute("pragma journal_mode=wal")
    conn.execute("create table items (id integer primary key, val text)")
    conn.commit()
    for i in range(rows):
        conn.execute("insert into items (val) values (?)", (f"v{i}",))
    conn.commit()
    return conn


class SqliteSummaryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_non_db_suffix_returns_none(self):
        p = self.tmp / "notes.txt"
        p.write_text("hello")
        self.assertIsNone(sqlite_summary(p))

    def test_plain_db_summary(self):
        p = self.tmp / "plain.db"
        _make_plain_db(p, rows=3)
        summary = sqlite_summary(p)
        self.assertIsNotNone(summary)
        self.assertEqual(summary["consistency"], "ok")
        self.assertFalse(summary["wal"]["present"])

        tables = {t["name"]: t for t in summary["tables"]}
        # Only user tables; no sqlite_* internal tables leak in.
        self.assertEqual(set(tables), {"widgets", "gadgets"})
        self.assertEqual(tables["widgets"]["rows"], 3)
        self.assertEqual(tables["gadgets"]["rows"], 0)

        # objects counts sqlite_master rows (2 tables + 1 index).
        self.assertGreaterEqual(summary["objects"], 3)
        self.assertIsInstance(summary["schema_hash"], str)
        self.assertTrue(summary["schema_hash"])

    def test_schema_hash_stable_across_calls(self):
        p = self.tmp / "stable.db"
        _make_plain_db(p, rows=2)
        first = sqlite_summary(p)["schema_hash"]
        second = sqlite_summary(p)["schema_hash"]
        self.assertEqual(first, second)

    def test_read_only_does_not_modify_file(self):
        p = self.tmp / "ro.db"
        _make_plain_db(p, rows=4)
        before = p.stat()
        sqlite_summary(p)
        sqlite_summary(p)
        after = p.stat()
        self.assertEqual(before.st_size, after.st_size)
        self.assertEqual(before.st_mtime_ns, after.st_mtime_ns)

    def test_open_readonly_uri_is_mode_ro(self):
        captured = {}
        real_connect = sqlite3.connect

        def spy(database, *args, **kwargs):
            captured["uri"] = database
            return real_connect(database, *args, **kwargs)

        p = self.tmp / "spy.db"
        _make_plain_db(p, rows=1)
        sqlite3.connect = spy
        try:
            conn = open_readonly(p)
            conn.close()
        finally:
            sqlite3.connect = real_connect
        self.assertIn("mode=ro", captured["uri"])
        self.assertNotIn("mode=rw", captured["uri"])
        self.assertNotIn("immutable=1", captured["uri"])

    def test_summary_only_ever_uses_mode_ro(self):
        captured = []
        real_connect = sqlite3.connect

        def spy(database, *args, **kwargs):
            captured.append(database)
            return real_connect(database, *args, **kwargs)

        p = self.tmp / "spy2.db"
        _make_plain_db(p, rows=1)
        sqlite3.connect = spy
        try:
            sqlite_summary(p)
        finally:
            sqlite3.connect = real_connect
        self.assertTrue(captured)
        self.assertTrue(all("mode=ro" in uri for uri in captured))
        self.assertTrue(all("mode=rw" not in uri for uri in captured))
        self.assertTrue(all("immutable=1" not in uri for uri in captured))

    def test_read_only_connection_cannot_write(self):
        p = self.tmp / "rw_blocked.db"
        _make_plain_db(p, rows=1)
        conn = open_readonly(p)
        try:
            with self.assertRaises(sqlite3.OperationalError):
                conn.execute("insert into widgets (name) values ('x')")
                conn.commit()
        finally:
            conn.close()

    def test_wal_mode_db_summarized_without_checkpoint(self):
        p = self.tmp / "wal.db"
        conn = _make_wal_db(p, rows=5)
        try:
            wal_path = Path(str(p) + "-wal")
            self.assertTrue(wal_path.exists())
            self.assertGreater(wal_path.stat().st_size, 0)
            wal_size_before = wal_path.stat().st_size

            summary = sqlite_summary(p)
            self.assertIsNotNone(summary)
            self.assertEqual(summary["journal_mode"], "wal")
            self.assertTrue(summary["wal"]["present"])
            self.assertGreater(summary["wal"]["size"], 0)
            self.assertEqual(summary["consistency"], "wal-present")

            # Rows reflect committed data read THROUGH the WAL (not via immutable).
            tables = {t["name"]: t for t in summary["tables"]}
            self.assertEqual(tables["items"]["rows"], 5)

            # Summary must not checkpoint/truncate the -wal.
            self.assertTrue(wal_path.exists())
            self.assertGreaterEqual(wal_path.stat().st_size, wal_size_before)
        finally:
            conn.close()

    def test_unreadable_db_marked_no_fabricated_counts(self):
        p = self.tmp / "garbage.db"
        p.write_bytes(b"this is not a sqlite database at all" * 4)
        summary = sqlite_summary(p)
        self.assertIsNotNone(summary)
        self.assertEqual(summary["consistency"], "unreadable")
        self.assertIn("error", summary)
        self.assertTrue(summary["error"])
        self.assertEqual(summary["tables"], [])
        self.assertEqual(summary["objects"], 0)
        self.assertIsNone(summary["schema_hash"])


class WalSiblingStateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_absent(self):
        p = self.tmp / "x.db"
        p.write_bytes(b"")
        state = wal_sibling_state(p)
        self.assertFalse(state["present"])
        self.assertEqual(state["size"], 0)
        self.assertIsNone(state["mtime_ns"])

    def test_present(self):
        p = self.tmp / "y.db"
        p.write_bytes(b"")
        wal = Path(str(p) + "-wal")
        wal.write_bytes(b"\x00" * 128)
        state = wal_sibling_state(p)
        self.assertTrue(state["present"])
        self.assertEqual(state["size"], 128)
        self.assertIsInstance(state["mtime_ns"], int)


class SummarizeSqliteDiffTests(unittest.TestCase):
    def test_row_count_change_produces_table_delta(self):
        old = {
            "schema_hash": "s",
            "consistency": "ok",
            "tables": [{"name": "t", "schema_hash": "h", "rows": 1}],
        }
        new = {
            "schema_hash": "s",
            "consistency": "ok",
            "tables": [{"name": "t", "schema_hash": "h", "rows": 5}],
        }
        result = summarize_sqlite_diff(old, new)
        self.assertIn("tables", result)
        self.assertNotIn("schema_hash", result)
        delta = result["tables"][0]
        self.assertEqual(delta["name"], "t")
        self.assertEqual(delta["before"]["rows"], 1)
        self.assertEqual(delta["after"]["rows"], 5)

    def test_schema_change_produces_schema_hash(self):
        old = {"schema_hash": "a", "consistency": "ok", "tables": []}
        new = {"schema_hash": "b", "consistency": "ok", "tables": []}
        result = summarize_sqlite_diff(old, new)
        self.assertEqual(result["schema_hash"], {"before": "a", "after": "b"})

    def test_consistency_transition_surfaced(self):
        old = {"schema_hash": "s", "consistency": "ok", "tables": []}
        new = {"schema_hash": "s", "consistency": "wal-present", "tables": []}
        result = summarize_sqlite_diff(old, new)
        self.assertEqual(result["consistency"], {"before": "ok", "after": "wal-present"})

    def test_unreadable_consistency_always_flagged(self):
        old = {"schema_hash": None, "consistency": "unreadable", "tables": []}
        new = {"schema_hash": None, "consistency": "unreadable", "tables": []}
        result = summarize_sqlite_diff(old, new)
        self.assertIn("consistency", result)

    def test_non_dict_inputs(self):
        result = summarize_sqlite_diff(None, {"consistency": "ok"})
        self.assertEqual(result, {"before": None, "after": {"consistency": "ok"}})


if __name__ == "__main__":
    unittest.main()
