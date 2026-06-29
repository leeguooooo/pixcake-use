import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from pixcake_use import photos
from pixcake_use.environment import default_environment


def _make_project_db(root: Path) -> Path:
    """Build a minimal project.db + palette file mirroring PixCake's shape."""
    palette = root / "palette.json"
    palette.write_text(
        json.dumps(
            {
                "IsNoneEffect": False,
                "Common": {
                    "Params": [
                        {"pf": 3000, "fe": 0.78},  # Exposure +56%
                        {"pf": 3006, "fe": 0.86},  # Saturation +72%
                        {"pf": 30147, "fe": 0.5},  # neutral, unmapped
                    ]
                },
            }
        )
    )
    db = root / "project.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        create table thumbnail (
            id integer primary key, importIndex int, originalImagePath text,
            originalWidth int, originalHeight int, currentOptRecordId int,
            inRecycleBin int default 0
        );
        create table thumb_opt_record (id integer primary key, paletteJsonPath text);
        """
    )
    conn.execute(
        "insert into thumbnail values (1, 1, '/x/DSC1.ARW', 7008, 4672, 47, 0)"
    )
    conn.execute(
        "insert into thumbnail values (2, 2, '/x/DSC2.ARW', 7008, 4672, -1, 0)"
    )
    conn.execute("insert into thumb_opt_record values (47, ?)", (str(palette),))
    conn.commit()
    conn.close()
    return db


class PhotosTests(unittest.TestCase):
    def test_list_photos_reads_recipe_and_edited_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_project_db(Path(tmp))
            result = photos.list_photos(db)
            self.assertEqual([p.position for p in result], [1, 2])

            cat = result[0]
            self.assertEqual(cat.name, "DSC1")
            self.assertTrue(cat.edited)
            self.assertAlmostEqual(cat.named_params["Exposure"], 0.78)
            self.assertAlmostEqual(cat.named_params["Saturation"], 0.86)

            plain = result[1]
            self.assertFalse(plain.edited)
            self.assertEqual(plain.named_params, {})

    def test_recipe_summary_sorts_by_strength(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_project_db(Path(tmp))
            cat = photos.list_photos(db)[0]
            summary = photos.recipe_summary(cat)
            # Saturation (+72%) is stronger than Exposure (+56%) -> listed first.
            self.assertTrue(summary.startswith("Saturation+72%"))
            self.assertIn("Exposure+56%", summary)

    def test_to_dict_roundtrip_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_project_db(Path(tmp))
            d = photos.to_dict(photos.list_photos(db)[0])
            self.assertEqual(d["position"], 1)
            self.assertEqual(d["size"], [7008, 4672])
            self.assertTrue(d["edited"])

    def test_discover_project_dbs_globs_support_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "db" / "user_1" / "project_9" / "project.db"
            target.parent.mkdir(parents=True)
            target.write_text("")
            import dataclasses

            env = dataclasses.replace(default_environment(), support_dir=root)
            self.assertEqual(photos.discover_project_dbs(env), [target])


if __name__ == "__main__":
    unittest.main()
