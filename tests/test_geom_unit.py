"""Unit tests for kcslib.geom input checks and point helpers. No KiCad needed.

Run: python -m unittest tests/test_geom_unit.py -v
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "kicad" / "scripts"))
from kcslib import geom


class SnapTest(unittest.TestCase):
    def test_snaps_to_default_grid(self):
        self.assertEqual(geom.snap(1.3), 1.27)
        self.assertEqual(geom.snap(-1.9), -1.27)

    def test_snaps_to_custom_grid(self):
        self.assertEqual(geom.snap(0.26, grid=0.5), 0.5)

    def test_zero_grid_raises(self):
        with self.assertRaisesRegex(ValueError, "grid must be positive"):
            geom.snap(1.0, grid=0)

    def test_negative_grid_raises(self):
        with self.assertRaisesRegex(ValueError, "grid must be positive"):
            geom.snap(1.0, grid=-1.27)

    def test_callers_propagate_bad_grid(self):
        with self.assertRaises(ValueError):
            geom.snap_pt((1.0, 2.0), grid=0)
        with self.assertRaises(ValueError):
            geom.on_grid(1.0, grid=0)


class PtOnGridTest(unittest.TestCase):
    def test_on_grid(self):
        self.assertTrue(geom.pt_on_grid((0.0, 0.0)))
        self.assertTrue(geom.pt_on_grid((2.54, -12.7)))

    def test_x_off_grid(self):
        self.assertFalse(geom.pt_on_grid((1.0, 2.54)))

    def test_y_off_grid(self):
        self.assertFalse(geom.pt_on_grid((2.54, 1.0)))

    def test_within_tolerance(self):
        self.assertTrue(geom.pt_on_grid((1.2705, 2.5395)))
        self.assertFalse(geom.pt_on_grid((1.2705, 2.54), tol=1e-4))

    def test_custom_grid(self):
        self.assertTrue(geom.pt_on_grid((0.5, 1.5), grid=0.5))
        self.assertFalse(geom.pt_on_grid((0.5, 1.5), grid=1.0))

    def test_bad_grid_raises(self):
        with self.assertRaises(ValueError):
            geom.pt_on_grid((0.0, 0.0), grid=0)


class BboxPtsTest(unittest.TestCase):
    def test_single_point(self):
        self.assertEqual(geom.bbox_pts([(3.0, -4.0)]), (3.0, -4.0, 3.0, -4.0))

    def test_several_points(self):
        pts = [(1.0, 5.0), (-2.0, 3.0), (4.0, -1.0)]
        self.assertEqual(geom.bbox_pts(pts), (-2.0, -1.0, 4.0, 5.0))

    def test_accepts_generator(self):
        self.assertEqual(geom.bbox_pts((x, -x) for x in range(3)), (0, -2, 2, 0))

    def test_empty_list_raises(self):
        with self.assertRaises(ValueError):
            geom.bbox_pts([])

    def test_empty_generator_raises(self):
        with self.assertRaises(ValueError):
            geom.bbox_pts(p for p in [])


class PinDirectionTest(unittest.TestCase):
    def test_cardinal_angles(self):
        self.assertEqual(geom.pin_direction(0), (-1, 0))
        self.assertEqual(geom.pin_direction(90), (0, 1))
        self.assertEqual(geom.pin_direction(180), (1, 0))
        self.assertEqual(geom.pin_direction(270), (0, -1))

    def test_equivalent_angles(self):
        self.assertEqual(geom.pin_direction(-90), geom.pin_direction(270))
        self.assertEqual(geom.pin_direction(450), geom.pin_direction(90))
        self.assertEqual(geom.pin_direction(90.0), geom.pin_direction(90))

    def test_rotation_still_applies(self):
        self.assertEqual(geom.pin_direction(0, rot=90), (0, 1))

    def test_non_multiple_of_90_raises(self):
        for angle in (1, 45, 30.5, 89.999, -45, 135):
            with self.subTest(angle=angle):
                with self.assertRaises(ValueError):
                    geom.pin_direction(angle)


class DistAndFmtPtTest(unittest.TestCase):
    def test_dist_3_4_5(self):
        self.assertAlmostEqual(geom.dist((0.0, 0.0), (3.0, 4.0)), 5.0)
        self.assertAlmostEqual(geom.dist((1.27, 2.54), (1.27, 2.54)), 0.0)

    def test_manhattan(self):
        self.assertAlmostEqual(geom.manhattan((0.0, 0.0), (3.0, -4.0)), 7.0)
        self.assertAlmostEqual(geom.manhattan((1.27, 2.54), (3.81, 0.0)), 5.08)

    def test_fmt_pt(self):
        self.assertEqual(geom.fmt_pt((1.27, -2.54)), "1.27 -2.54")
        self.assertEqual(geom.fmt_pt((-0.0, 5.0)), "0 5")


if __name__ == "__main__":
    unittest.main()
