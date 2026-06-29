"""Read-only photo rendering: decode the user's own RAW originals and apply an
approximate, offline reproduction of a PixCake palette recipe.

RAW decoding uses macOS ``sips`` (no third-party dependency). The grade is an
*approximation* of PixCake's look using standard image math -- it is not a
pixel-exact reproduction of PixCake's render engine, and it deliberately does
NOT touch PixCake's encrypted FXIP preview cache.

The grader requires Pillow + numpy (install the ``render`` extra). It is
imported lazily so the rest of the CLI stays dependency-free.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def decode_raw(src: Path, dst: Path, max_px: int = 1600) -> bool:
    """Decode a RAW/any-image original to a viewable JPEG via macOS sips."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["sips", "-s", "format", "jpeg", "-Z", str(max_px), str(src), "--out", str(dst)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0 and dst.exists()


def _bipolar(fe: float, scale: float) -> float:
    return (fe - 0.5) * 2.0 * scale


def render_graded(src_jpg: Path, dst_png: Path, named: dict[str, float]) -> None:
    """Apply an approximate grade from a {name: fe} recipe to a decoded JPEG.

    Raises ImportError with an actionable message if Pillow/numpy are absent.
    """
    try:
        import numpy as np
        from PIL import Image, ImageFilter
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ImportError(
            "graded previews need Pillow + numpy; install with: pip install 'pixcake-use[render]'"
        ) from exc

    x = np.asarray(Image.open(src_jpg).convert("RGB"), float) / 255.0
    luma = np.array([0.299, 0.587, 0.114])

    if "Temp" in named:
        t = _bipolar(named["Temp"], 0.25)
        x[..., 0] *= 1 + t
        x[..., 2] *= 1 - t
    if "Tint" in named:
        x[..., 1] *= 1 + _bipolar(named["Tint"], 0.20)
    if "Exposure" in named:
        x *= 2.0 ** _bipolar(named["Exposure"], 2.0)
    x = np.clip(x, 0, 1)
    if "EnhanceEditLuma" in named:  # UI 亮度/Brightness (pf 21001): gamma lift
        gamma = 1.0 - _bipolar(named["EnhanceEditLuma"], 0.5)
        x = np.clip(x ** max(gamma, 0.1), 0, 1)

    L = x @ luma

    def add_region(amount: float, mask) -> None:
        for c in range(3):
            x[..., c] = np.clip(x[..., c] + amount * mask, 0, 1)

    if "Shadows" in named:
        add_region(_bipolar(named["Shadows"], 0.30), np.clip(1 - L * 2, 0, 1))
    if "Highlights" in named:
        add_region(_bipolar(named["Highlights"], 0.30), np.clip(L * 2 - 1, 0, 1))
    if "Blacks" in named:
        add_region(_bipolar(named["Blacks"], 0.20), np.clip(1 - L * 3, 0, 1))
    if "Whites" in named:
        add_region(_bipolar(named["Whites"], 0.20), np.clip(L * 3 - 2, 0, 1))
    if "Contrast" in named:
        x = np.clip((x - 0.5) * (1 + _bipolar(named["Contrast"], 0.6)) + 0.5, 0, 1)

    L = (x @ luma)[..., None]
    sat = 1.0
    if "Saturation" in named:
        sat *= 1 + _bipolar(named["Saturation"], 1.0)
    if "Vibrance" in named:
        sat *= 1 + _bipolar(named["Vibrance"], 0.6)
    x = np.clip(L + (x - L) * sat, 0, 1)

    for key, radius in (("Clarity", 4.0), ("Texture", 1.5), ("Sharpening", 0.8)):
        if key in named and abs(named[key] - 0.5) > 1e-3:
            amount = _bipolar(named[key], 1.2 if key != "Sharpening" else 1.5)
            blur = np.asarray(
                Image.fromarray((x * 255).astype("uint8")).filter(ImageFilter.GaussianBlur(radius)),
                float,
            ) / 255.0
            x = np.clip(x + amount * (x - blur), 0, 1)

    if "Vignette" in named and abs(named["Vignette"] - 0.5) > 1e-3:  # UI 暗角 (pf 91107)
        amount = _bipolar(named["Vignette"], 0.8)
        h, w = x.shape[:2]
        yy, xx = np.ogrid[:h, :w]
        radial = np.sqrt(((yy - h / 2) / (h / 2)) ** 2 + ((xx - w / 2) / (w / 2)) ** 2)
        mask = np.clip((radial - 0.5) / 0.7, 0, 1)[..., None]
        x = np.clip(x * (1 - amount * mask), 0, 1)

    dst_png.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray((x * 255).astype("uint8")).save(dst_png)
