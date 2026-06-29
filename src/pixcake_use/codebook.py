"""Mapping from PixCake palette ``pf`` ids to human parameter names.

Provenance of the ``BASIC`` tone/colour ids
--------------------------------------------
Most ``BASIC`` ids are **confirmed** not by guessing but by PixCake's own data:
the app writes a ``"name":"X"`` field next to the ``pf`` inside each preset's
nested ``StrParams`` JSON (found in 5/8 preset rows of
``presets_config_detail.paletteCfg`` in the live project db). That is an
app-generated ``pf -> name`` annotation, i.e. static ground truth, not a
hand-authored recipe. Confidence tiers below:

* ``confirmed`` -- PixCake itself writes ``"name"`` next to the ``pf`` in
  StrParams. No slider pass needed; the app's own annotation is the proof.
* ``high`` -- appears in ``Common.Params`` with live ``fe`` values and the
  English label exists in the app binary's ``__cstring`` table, but **no**
  ``name`` field is ever attached. The name comes from the binary string +
  hand-authored recipe, NOT from app preset data. Verify with one slider pass.
* ``unknown`` -- appears in ``Common.Params`` with live ``fe`` but no name
  anywhere (db / binary / Qt resources). NOT given a real label here.

``fe`` is 0..1, 0.5 == neutral. ``ae`` carries a tone-curve point array.

Note on ``pf`` binding: the numeric ``pf`` ids are NOT loaded as code
immediates in the binary (disasm does not yield the binding), and the named
entries are config/preset driven. The static proof for the named basics is the
``pf -> name`` annotation persisted into preset records, not binary constants.

Detail / effects sliders -- confirmed EMPIRICALLY (watch/diff)
-------------------------------------------------------------
Moving each named UI slider on one photo and diffing the palette proved:
Texture=44799, Clarity=3022, Sharpening=90016 (UI 锐化), Dehaze=90152 (UI 祛雾,
app "RemoveFog"), Grain=8200 (UI 颗粒), Vignette=91107 (UI 暗角,
"LensManualVignetting"). This DISPROVED the old hand-recipe guess that
90074/90075 were Texture/Clarity -- those two stay unidentified
(``UNKNOWN_COMMON_PF``).

Still unidentified
------------------
* 90073 / 90074 / 90075 / 90076 / 90077 / 90078 -- appear in Common.Params with
  live fe but no name anywhere; not the detail sliders above. Tracked in
  ``UNKNOWN_COMMON_PF``, deliberately NOT given guessed names.
* 3009 -- carries ``ie`` (integer enum), observed always 8. Believed a mode
  flag, not a continuous tone slider; excluded from ``BASIC``. Tracked in
  ``MODE_FLAG_PF``.

Brightness / 亮度
-----------------
The UI 亮度/Brightness slider writes **pf 21001** (confirmed empirically: moving
it changed 21001). 21001's app StrParams name is ``EnhanceEditLuma``, so the
codebook key stays "EnhanceEditLuma" but it IS the Brightness control. There is
no SEPARATE Brightness pf. 3000 remains ``Exposure`` (distinct from 亮度).

Canonical app labels vs. codebook keys
--------------------------------------
A few codebook keys are abbreviations of the app's canonical StrParams label
(kept short, and kept stable because ``photo_render`` keys grades by these
strings). Differences, for the record: 3007 app=``Temperature`` (key ``Temp``),
90069/90070/90071 app=``CurveRed/CurveGreen/CurveBlue`` (keys ``CurveR/G/B``).
Lookup is by ``pf`` so the abbreviation is functionally irrelevant.

HSL block (91170-91193) -- DO NOT TOUCH
---------------------------------------
Recovered read-only from the binary's ``__cstring`` table (an ``HSLTunner``
family) and confirmed empirically via the watch/diff method: maxing the Red
Hue/Saturation/Luminance sliders moved the three consecutive ids
91170/91171/91172, proving a **colour-major** layout (each colour owns a
consecutive [Hue, Saturation, Luminance] triplet). The StrParams ``name``
fields independently corroborate this for the first two colours
(91170 ``HSLTunnerRedHue`` ... 91173 ``HSLTunnerOrangeHue`` ...); 91176+ collapse
to a generic "HSLTunner" so the watch/diff mapping remains the authority there.

    id = 91170 + colour_index * 3 + attr_index
    colours: Red Orange Yellow Green Aqua Blue Purple Magenta
    attrs:   Hue(0) Saturation(1) Luminance(2)
"""

from __future__ import annotations

# Confirmed/high-confidence tone + colour parameters (fe is 0..1, 0.5 == neutral).
# Names are stable lookup keys; see BASIC_CONFIDENCE for the evidence tier.
BASIC: dict[int, str] = {
    3000: "Exposure",          # confirmed (app "name":"Exposure")
    3002: "Contrast",          # confirmed
    3003: "Highlights",        # confirmed (not permuted with Shadows)
    3004: "Shadows",           # confirmed
    3006: "Saturation",        # confirmed
    3007: "Temp",              # confirmed; app canonical = "Temperature"
    3008: "Tint",              # confirmed
    3020: "Whites",            # confirmed (distinct range from Highlights)
    3021: "Blacks",            # confirmed
    21001: "EnhanceEditLuma",  # confirmed; this IS the UI 亮度/Brightness slider
    90014: "Vibrance",         # confirmed
    90069: "CurveR",           # confirmed; app canonical = "CurveRed" (carries ae)
    90070: "CurveG",           # confirmed; app canonical = "CurveGreen" (carries ae)
    90071: "CurveB",           # confirmed; app canonical = "CurveBlue" (carries ae)
    # Detail / effects sliders -- confirmed EMPIRICALLY (watch/diff: moved the
    # named UI slider on one photo, saw exactly which pf changed). These are the
    # real Texture/Clarity ids; the old hand-recipe guess of 90074/90075 was
    # WRONG (those are now in UNKNOWN_COMMON_PF).
    44799: "Texture",          # confirmed-empirical (UI 纹理)
    3022: "Clarity",           # confirmed-empirical (UI 清晰度)
    90016: "Sharpening",       # confirmed-empirical (UI 锐化; app "SharpeningAmount")
    90152: "Dehaze",           # confirmed-empirical (UI 祛雾; app "RemoveFog")
    8200: "Grain",             # confirmed-empirical (UI 颗粒; app "GrainAmount")
    91107: "Vignette",         # confirmed-empirical (UI 暗角; app "LensManualVignetting")
}

# Evidence tier per BASIC id. "confirmed" == app-written StrParams "name" field;
# "high" == Common.Params live fe + binary string, but never a name field.
BASIC_CONFIDENCE: dict[int, str] = {
    3000: "confirmed",
    3002: "confirmed",
    3003: "confirmed",
    3004: "confirmed",
    3006: "confirmed",
    3007: "confirmed",
    3008: "confirmed",
    3020: "confirmed",
    3021: "confirmed",
    21001: "confirmed",
    90014: "confirmed",
    90069: "confirmed",
    90070: "confirmed",
    90071: "confirmed",
    44799: "confirmed",   # empirical
    3022: "confirmed",    # empirical
    90016: "confirmed",   # empirical
    90152: "confirmed",   # empirical
    8200: "confirmed",    # empirical
    91107: "confirmed",   # empirical
}

# Ids that appear in Common.Params with live fe but have NO name anywhere
# (db / binary / Qt resources). Deliberately unnamed. 90074/90075 are here
# because the empirical slider pass proved Texture/Clarity are 44799/3022, NOT
# these -- so 90074/90075 remain unidentified preset params.
UNKNOWN_COMMON_PF: tuple[int, ...] = (90073, 90074, 90075, 90076, 90077, 90078)

# Mode/enum flag (carries ``ie``, observed always 8): believed NOT a tone
# slider. Excluded from BASIC pending one confirming pass.
MODE_FLAG_PF: tuple[int, ...] = (3009,)

# BASIC ids whose name is NOT app-name-confirmed -- still need one watch/diff
# slider pass. (The "confirmed" tier does not appear here: the app's own name
# field is its static proof.)
PROVISIONAL_BASIC_PF: tuple[int, ...] = tuple(
    pf for pf, tier in BASIC_CONFIDENCE.items() if tier != "confirmed"
)

# HSL colour bands, in the confirmed order. Each colour owns a consecutive
# [Hue, Saturation, Luminance] triplet (colour-major). DO NOT TOUCH.
HSL_COLORS = ("Red", "Orange", "Yellow", "Green", "Aqua", "Blue", "Purple", "Magenta")
HSL_ATTRS = ("Hue", "Saturation", "Luminance")
HSL_BLOCK = range(91170, 91194)  # 24 consecutive ids


def _hsl_color_major() -> dict[int, str]:
    """Confirmed layout: [Red H,S,L][Orange H,S,L]...[Magenta H,S,L]."""
    out: dict[int, str] = {}
    base = HSL_BLOCK.start
    for ci, color in enumerate(HSL_COLORS):
        for ai, attr in enumerate(HSL_ATTRS):
            out[base + ci * len(HSL_ATTRS) + ai] = f"HSL.{color}.{attr}"
    return out


HSL: dict[int, str] = _hsl_color_major()
CODEBOOK: dict[int, str] = {**BASIC, **HSL}


def name_for(pf: int) -> str | None:
    """Return the human name for a pf id, or None if unknown/unmapped.

    Unknown (90073/90076/90077/90078), mode-flag (3009) and any unmapped id all
    return None -- we never return a guessed label.
    """
    return CODEBOOK.get(pf)


def confidence_for(pf: int) -> str | None:
    """Evidence tier for a BASIC pf id: "confirmed", "high", or None.

    None for HSL ids (their authority is the watch/diff mapping, not StrParams)
    and for unmapped ids.
    """
    return BASIC_CONFIDENCE.get(pf)
