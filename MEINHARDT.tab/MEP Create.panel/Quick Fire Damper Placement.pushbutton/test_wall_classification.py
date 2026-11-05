import unittest

from wall_classification import classify_wall_descriptors, classify_wall_material, is_rated_wall_material


class WallClassificationTests(unittest.TestCase):
    def test_explicit_ratings(self):
        self.assertEqual(classify_wall_material("Fire"), "FIRE")
        self.assertEqual(classify_wall_material("Smoke"), "SMOKE")
        self.assertEqual(classify_wall_material("Fire Rated"), "FIRE")
        self.assertEqual(classify_wall_material("Smoke Rated"), "SMOKE")
        self.assertEqual(classify_wall_material("Fire Rated / Smoke Rated"), "BOTH")
        self.assertEqual(classify_wall_material("FRL 120/120/120"), "FIRE")
        self.assertEqual(classify_wall_material("EI60 fire door assembly"), "FIRE")
        self.assertEqual(classify_wall_material("REI 120"), "FIRE")
        self.assertEqual(classify_wall_material("EN 13501-2"), "FIRE")
        self.assertEqual(classify_wall_material("F90"), "FIRE")
        self.assertEqual(classify_wall_material("120/120/120"), "FIRE")
        self.assertEqual(classify_wall_material("-/120/120"), "FIRE")
        self.assertEqual(classify_wall_material("UL 1784"), "SMOKE")
        self.assertEqual(classify_wall_material("EN 1634-3"), "SMOKE")
        self.assertEqual(classify_wall_material("S200"), "SMOKE")
        self.assertEqual(classify_wall_material("Sa"), "SMOKE")
        for value in ("F", "F-rated", "FR", "FRL", "FRR"):
            self.assertEqual(classify_wall_material(value), "FIRE")
        for value in ("ASTM E119", "UL 263", "BS 476", "AS 1530.4"):
            self.assertEqual(classify_wall_material(value), "FIRE")
        self.assertEqual(classify_wall_material("Smoke Resistant"), "SMOKE")

    def test_explicit_non_ratings(self):
        self.assertEqual(classify_wall_material("Non Rated"), "NOT_RATED")
        self.assertEqual(classify_wall_material("Non-Fire-Rated"), "NOT_RATED")
        self.assertEqual(classify_wall_material("Non-F-rated"), "NOT_RATED")
        self.assertEqual(classify_wall_material("Smoke Not Rated"), "NOT_RATED")
        self.assertEqual(classify_wall_material("Not UL 263 rated"), "NOT_RATED")
        self.assertEqual(classify_wall_material("Not EI 60 rated"), "NOT_RATED")
        self.assertEqual(classify_wall_material("UL 263 not applicable"), "NOT_RATED")
        self.assertEqual(classify_wall_material("UL 1784 not applicable"), "NOT_RATED")
        self.assertEqual(classify_wall_material("Unrated FRL 120/120/120"), "NOT_RATED")
        self.assertEqual(classify_wall_material("Non-Fire-Rated Smoke Rated"), "SMOKE")

    def test_ambiguous_and_unrelated_values_are_not_included(self):
        self.assertEqual(classify_wall_material(""), "UNKNOWN")
        self.assertEqual(classify_wall_material("Fireplace"), "UNKNOWN")
        self.assertEqual(classify_wall_material("Smoke Detector"), "SMOKE")
        self.assertEqual(classify_wall_material("XFR2"), "UNKNOWN")
        self.assertFalse(is_rated_wall_material("Fireplace"))

    def test_only_explicit_rating_classifications_are_included(self):
        self.assertTrue(is_rated_wall_material("Fire resistance level 120/120/120"))
        self.assertTrue(is_rated_wall_material("Smoke Resistant"))
        self.assertFalse(is_rated_wall_material("Not Fire Rated"))

    def test_positive_rating_in_any_source_wins_over_other_source_negatives(self):
        self.assertEqual(classify_wall_descriptors(["Fire Rated", "Unrated gypsum"]), "FIRE")
        self.assertEqual(classify_wall_descriptors(["Smoke", "Not Fire Rated"]), "SMOKE")
        self.assertEqual(classify_wall_descriptors(["Unrated", "Non-Fire-Rated"]), "NOT_RATED")


if __name__ == "__main__":
    unittest.main()