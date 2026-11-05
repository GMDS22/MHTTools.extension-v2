import math
import unittest

from placement_rules import (
    DEFAULT_DUPLICATE_RADIUS_MM,
    adjust_point_away_from_points,
    closest_clear_point,
    millimeters_to_feet,
    points_within_radius,
)


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

    def test_intersection_midpoint_is_preserved_when_clear(self):
        point = adjust_point_away_from_points((0, 0, 0), (10, 0, 0), [], 1)
        self.assertEqual(point, (5.0, 0.0, 0.0))

    def test_point_moves_within_intersection_segment_to_clear_obstacle(self):
        point = adjust_point_away_from_points((0, 0, 0), (10, 0, 0), [(5, 0, 0)], 2)
        self.assertIsNotNone(point)
        self.assertTrue(0 <= point[0] <= 10)
        self.assertGreaterEqual(abs(point[0] - 5), 2)

    def test_no_point_is_returned_when_whole_segment_is_within_clearance(self):
        point = adjust_point_away_from_points((0, 0, 0), (1, 0, 0), [(0.5, 0, 0)], 2)
        self.assertIsNone(point)

    def test_multiple_obstacles_must_all_be_cleared(self):
        point = adjust_point_away_from_points(
            (0, 0, 0), (10, 0, 0), [(2, 0, 0), (8, 0, 0)], 2
        )
        self.assertIsNotNone(point)
        self.assertTrue(all(not points_within_radius(point, obstacle, 2) for obstacle in [(2, 0, 0), (8, 0, 0)]))

    def test_curved_path_adjustment_uses_only_sampled_curve_points(self):
        candidates = [
            (math.cos(index * math.pi / 200.0), math.sin(index * math.pi / 200.0), 0.0)
            for index in range(101)
        ]
        midpoint = candidates[50]
        selected = closest_clear_point(candidates, [midpoint], 0.1)
        self.assertIn(selected, candidates)
        self.assertNotEqual(selected, midpoint)
        self.assertGreaterEqual(math.dist(selected, midpoint), 0.1)

    def test_curved_path_returns_no_position_when_all_samples_are_blocked(self):
        candidates = [(float(index) / 100.0, 0.0, 0.0) for index in range(101)]
        self.assertIsNone(closest_clear_point(candidates, [(0.5, 0.0, 0.0)], 1.0))


if __name__ == "__main__":
    unittest.main()