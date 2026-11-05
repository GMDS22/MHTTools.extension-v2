import math
import unittest

from placement_rules import DEFAULT_DUPLICATE_RADIUS_MM, millimeters_to_feet, points_within_radius


class PlacementRulesTests(unittest.TestCase):
    def test_default_radius_is_two_hundred_millimeters(self):
        radius_feet = millimeters_to_feet(DEFAULT_DUPLICATE_RADIUS_MM)
        self.assertAlmostEqual(radius_feet, 200.0 / 304.8)

    def test_radius_includes_exact_boundary_and_excludes_beyond(self):
        radius_feet = millimeters_to_feet(DEFAULT_DUPLICATE_RADIUS_MM)
        self.assertTrue(points_within_radius((0, 0, 0), (radius_feet, 0, 0), radius_feet))
        self.assertFalse(points_within_radius((0, 0, 0), (radius_feet + 0.001, 0, 0), radius_feet))

    def test_radius_uses_three_dimensional_distance(self):
        radius_feet = millimeters_to_feet(DEFAULT_DUPLICATE_RADIUS_MM)
        self.assertTrue(points_within_radius((0, 0, 0), (0, 0, radius_feet), radius_feet))
        self.assertFalse(points_within_radius((0, 0, 0), (radius_feet, radius_feet, 0), radius_feet))

    def test_radius_rejects_non_positive_and_non_finite_values(self):
        for value in (0, -1, float("nan"), float("inf"), -float("inf")):
            with self.assertRaises(ValueError):
                millimeters_to_feet(value)


if __name__ == "__main__":
    unittest.main()