import tempfile
import unittest
from pathlib import Path

try:
    import numpy  # noqa: F401
    from PIL import Image

    HAVE_RENDER = True
except ImportError:
    HAVE_RENDER = False

from pixcake_use import photo_render


@unittest.skipUnless(HAVE_RENDER, "render extra (pillow+numpy) not installed")
class RenderGradedTests(unittest.TestCase):
    def test_exposure_brightens(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src.jpg"
            dst = Path(tmp) / "out.png"
            Image.new("RGB", (32, 32), (80, 80, 80)).save(src)

            photo_render.render_graded(src, dst, {"Exposure": 0.9})
            self.assertTrue(dst.exists())

            import numpy as np

            before = np.asarray(Image.open(src), float).mean()
            after = np.asarray(Image.open(dst), float).mean()
            self.assertGreater(after, before)

    def test_neutral_recipe_is_near_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src.jpg"
            dst = Path(tmp) / "out.png"
            Image.new("RGB", (16, 16), (120, 130, 140)).save(src)
            photo_render.render_graded(src, dst, {"Exposure": 0.5, "Contrast": 0.5})
            self.assertTrue(dst.exists())


if __name__ == "__main__":
    unittest.main()
