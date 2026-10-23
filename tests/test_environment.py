import unittest
from edk.environment import canonicalize, EnvironmentUnavailable


class EnvironmentTests(unittest.TestCase):
    def test_exact_reading(self):
        values = list(range(40))
        self.assertEqual(canonicalize(values), bytes(values))

    def test_erasure_fails_closed(self):
        with self.assertRaises(EnvironmentUnavailable):
            canonicalize([None] + [1] * 39)

    def test_invalid_readings_and_count(self):
        for invalid in (-1, 64, True, 3.2, "7"):
            with self.subTest(invalid=invalid), self.assertRaises(EnvironmentUnavailable):
                canonicalize([invalid] + [1]*39)
        with self.assertRaises(EnvironmentUnavailable):
            canonicalize([1]*39)


if __name__ == "__main__":
    unittest.main()
