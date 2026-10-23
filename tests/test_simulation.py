import unittest
from edk.simulation import survival_probability


class SimulationTests(unittest.TestCase):
    def test_zero_time_full_survival(self):
        result = survival_probability(0, trials=100)
        self.assertEqual(result["combined_recovery_rate"], 1)

    def test_deterministic_seed(self):
        self.assertEqual(survival_probability(12, trials=1000, seed=11),
                         survival_probability(12, trials=1000, seed=11))

    def test_zero_nodes_wont_recover_late(self):
        result = survival_probability(1e6, trials=50, seed=1)
        self.assertEqual(result["combined_recovery_rate"], 0)


if __name__ == "__main__":
    unittest.main()
