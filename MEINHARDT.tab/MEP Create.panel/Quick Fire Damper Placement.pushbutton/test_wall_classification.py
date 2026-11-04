import unittest

from wall_classification import classify_wall_material, is_rated_wall_material


class WallClassificationTests(unittest.TestCase):
    def test_explicit_ratings(self):
        self.assertEqual(classify_wall_material("Fire Rated"), "FIRE")
        self.assertEqual(classify_wall_material("Smoke Rated"), "SMOKE")
        self.assertEqual(classify_wall_material("Fire Rated / Smoke Rated"), "BOTH")
        self.assertEqual(classify_wall_material("FRL 120/120/120"), "FIRE")

    def test_explicit_non_ratings(self):
        self.assertEqual(classify_wall_material("Non Rated"), "NOT_RATED")
        self.assertEqual(classify_wall_material("Non-Fire-Rated"), "NOT_RATED")
        self.assertEqual(classify_wall_material("Smoke Not Rated"), "NOT_RATED")

    def test_ambiguous_and_unrelated_values_are_not_included(self):
        self.assertEqual(classify_wall_material(""), "UNKNOWN")
        self.assertEqual(classify_wall_material("Fireplace"), "UNKNOWN")
        self.assertEqual(classify_wall_material("Smoke Detector"), "UNKNOWN")
        self.assertFalse(is_rated_wall_material("Fireplace"))

    def test_only_explicit_rating_classifications_are_included(self):
        self.assertTrue(is_rated_wall_material("Fire resistance level 120/120/120"))
        self.assertTrue(is_rated_wall_material("Smoke Resistant"))
        self.assertFalse(is_rated_wall_material("Not Fire Rated"))


if __name__ == "__main__":
    unittest.main()