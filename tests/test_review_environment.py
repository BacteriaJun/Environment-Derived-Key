import unittest

from edk.environment import AnchorDefinition, EnvironmentUnavailable, canonicalize


class ReviewedEnvironmentTests(unittest.TestCase):
    def test_count_and_container_validation(self):
        for count in (0, -1, 65536, True, 1.0, "40", None):
            with self.assertRaises(EnvironmentUnavailable):
                canonicalize([1] * 40, expected_count=count)
        for readings in (None, 40, "1" * 40, bytes(40), bytearray(40), iter([1] * 40)):
            with self.assertRaises(EnvironmentUnavailable):
                canonicalize(readings)

    def test_legacy_encoding_and_explicit_count(self):
        self.assertEqual(canonicalize([0, 63], expected_count=2), b"\x00\x3f")
        self.assertEqual(canonicalize(tuple(range(40))), bytes(range(40)))

    def test_ambiguous_values_fail_without_approximation(self):
        for reading in (None, "ambiguous", (1, 2), 1.0, True):
            with self.assertRaises(EnvironmentUnavailable):
                canonicalize([reading] + [1] * 39)

    def test_anchor_fields_are_validated(self):
        for args in ((None, "sample", "read"), ("id", None, "read"),
                     ("id", "sample", None), (" ", "sample", "read"),
                     ("id", "sample", " ")):
            with self.assertRaises(ValueError):
                AnchorDefinition(*args)


if __name__ == "__main__":
    unittest.main()
