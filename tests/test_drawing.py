import unittest

from cybermint_hud.drawing import (
    chamfer_card_polygon,
    compute_meter_segments,
    hex_to_rgba,
)


class DrawingTests(unittest.TestCase):
    def test_hex_to_rgba_conversions(self):
        # Full red
        r, g, b, a = hex_to_rgba("#ff0000", 1.0)
        self.assertAlmostEqual(r, 1.0)
        self.assertAlmostEqual(g, 0.0)
        self.assertAlmostEqual(b, 0.0)
        self.assertAlmostEqual(a, 1.0)

        # Cyan
        r, g, b, a = hex_to_rgba("#00f0ff", 0.8)
        self.assertAlmostEqual(r, 0.0)
        self.assertAlmostEqual(g, 240 / 255.0)
        self.assertAlmostEqual(b, 1.0)
        self.assertAlmostEqual(a, 0.8)

        # Invalid fallback
        r, g, b, a = hex_to_rgba("not-a-hex", 0.5)
        self.assertEqual((r, g, b, a), (0.0, 0.0, 0.0, 0.5))

    def test_chamfer_polygon_structure(self):
        pts = chamfer_card_polygon(200.0, 100.0, cut_top_right=14.0, cut_bottom_left=8.0)
        self.assertEqual(len(pts), 6)
        # Top-left
        self.assertEqual(pts[0], (0.0, 0.0))
        # Top-right chamfer start
        self.assertEqual(pts[1], (200.0 - 14.0, 0.0))
        # Top-right chamfer end
        self.assertEqual(pts[2], (200.0, 14.0))
        # Bottom-right
        self.assertEqual(pts[3], (200.0, 100.0))
        # Bottom-left chamfer start
        self.assertEqual(pts[4], (8.0, 100.0))
        # Bottom-left chamfer end
        self.assertEqual(pts[5], (0.0, 100.0 - 8.0))

    def test_meter_segments_empty_and_full(self):
        # Empty fraction 0.0
        empty_segs = compute_meter_segments(100.0, 10.0, fraction=0.0)
        self.assertTrue(len(empty_segs) > 0)
        self.assertFalse(any(s["filled"] for s in empty_segs))

        # Full fraction 1.0
        full_segs = compute_meter_segments(100.0, 10.0, fraction=1.0)
        self.assertTrue(len(full_segs) > 0)
        self.assertTrue(all(s["filled"] for s in full_segs))
        # Top segments should trigger warning
        self.assertTrue(any(s["warning"] for s in full_segs))

    def test_meter_segments_warning_threshold(self):
        # At 50% fraction, none of the filled segments should be in warning zone (>= 75%)
        half_segs = compute_meter_segments(100.0, 10.0, fraction=0.50)
        filled = [s for s in half_segs if s["filled"]]
        self.assertTrue(len(filled) > 0)
        self.assertFalse(any(s["warning"] for s in filled))

        # At 90% fraction, warning segments should be present
        high_segs = compute_meter_segments(100.0, 10.0, fraction=0.90)
        warn_filled = [s for s in high_segs if s["filled"] and s["warning"]]
        self.assertTrue(len(warn_filled) > 0)

    def test_meter_segments_clamping(self):
        neg_segs = compute_meter_segments(100.0, 10.0, fraction=-0.5)
        self.assertFalse(any(s["filled"] for s in neg_segs))

        over_segs = compute_meter_segments(100.0, 10.0, fraction=1.5)
        self.assertTrue(all(s["filled"] for s in over_segs))


if __name__ == "__main__":
    unittest.main()
