import unittest

from pixcake_use import codebook


class CodebookTests(unittest.TestCase):
    def test_basic_names_confirmed(self):
        self.assertEqual(codebook.name_for(3000), "Exposure")
        self.assertEqual(codebook.name_for(3006), "Saturation")
        self.assertEqual(codebook.name_for(90014), "Vibrance")

    def test_confirmed_tier_ids_have_app_name_proof(self):
        # These carry an app-written StrParams "name" field -> tier "confirmed".
        for pf in (3000, 3002, 3003, 3004, 3006, 3007, 3008, 3020, 3021,
                   21001, 90014, 90069, 90070, 90071):
            self.assertEqual(codebook.confidence_for(pf), "confirmed", pf)
            self.assertIsNotNone(codebook.name_for(pf), pf)

    def test_detail_sliders_confirmed_empirically(self):
        # watch/diff: moved each named UI slider on one photo, saw which pf changed.
        self.assertEqual(codebook.name_for(44799), "Texture")
        self.assertEqual(codebook.name_for(3022), "Clarity")
        self.assertEqual(codebook.name_for(90016), "Sharpening")
        self.assertEqual(codebook.name_for(90152), "Dehaze")
        self.assertEqual(codebook.name_for(8200), "Grain")
        self.assertEqual(codebook.name_for(91107), "Vignette")
        for pf in (44799, 3022, 90016, 90152, 8200, 91107):
            self.assertEqual(codebook.confidence_for(pf), "confirmed", pf)

    def test_old_texture_clarity_guess_demoted(self):
        # 90074/90075 were a WRONG hand-recipe guess; now unidentified.
        for pf in (90074, 90075):
            self.assertIn(pf, codebook.UNKNOWN_COMMON_PF)
            self.assertIsNone(codebook.name_for(pf), pf)

    def test_all_basic_are_confirmed_now(self):
        self.assertEqual(codebook.PROVISIONAL_BASIC_PF, ())

    def test_unknown_common_ids_are_not_falsely_named(self):
        # Appear in Common.Params but have no name anywhere -> stay None.
        for pf in (90073, 90074, 90075, 90076, 90077, 90078):
            self.assertIn(pf, codebook.UNKNOWN_COMMON_PF)
            self.assertIsNone(codebook.name_for(pf), pf)

    def test_mode_flag_excluded_from_basic(self):
        self.assertIn(3009, codebook.MODE_FLAG_PF)
        self.assertNotIn(3009, codebook.BASIC)
        self.assertIsNone(codebook.name_for(3009))

    def test_brightness_is_21001(self):
        # UI 亮度/Brightness slider writes pf 21001 (key kept as EnhanceEditLuma).
        self.assertEqual(codebook.name_for(21001), "EnhanceEditLuma")
        self.assertNotIn("Brightness", codebook.CODEBOOK.values())

    def test_hsl_block_is_24_consecutive(self):
        self.assertEqual(len(codebook.HSL), 24)
        self.assertEqual(sorted(codebook.HSL), list(range(91170, 91194)))

    def test_hsl_color_major_binding_confirmed(self):
        # Empirically confirmed: Red owns the first consecutive H,S,L triplet.
        self.assertEqual(codebook.HSL_COLORS[0], "Red")
        self.assertEqual(codebook.HSL_COLORS[-1], "Magenta")
        self.assertEqual(codebook.name_for(91170), "HSL.Red.Hue")
        self.assertEqual(codebook.name_for(91171), "HSL.Red.Saturation")
        self.assertEqual(codebook.name_for(91172), "HSL.Red.Luminance")
        # color-major: next colour (Orange) starts at +3
        self.assertEqual(codebook.name_for(91173), "HSL.Orange.Hue")
        self.assertEqual(codebook.name_for(91193), "HSL.Magenta.Luminance")

    def test_hsl_ids_have_no_basic_confidence_tier(self):
        # HSL authority is watch/diff, not StrParams name -> no BASIC tier.
        self.assertIsNone(codebook.confidence_for(91170))

    def test_unknown_pf_returns_none(self):
        self.assertIsNone(codebook.name_for(999999))


if __name__ == "__main__":
    unittest.main()
