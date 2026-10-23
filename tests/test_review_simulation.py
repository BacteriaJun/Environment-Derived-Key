import unittest

from edk.simulation import survival_probability


class ReviewedSimulationTests(unittest.TestCase):
    def test_invalid_parameters_cannot_silently_look_like_decay(self):
        cases = [dict(months=value) for value in
                 (-1, float("nan"), float("inf"), True, "12", None, 10**1000)]
        cases += [dict(env_hazard=value) for value in
                  (-1, float("nan"), float("inf"), True, "0", None)]
        cases += [dict(node_hazards=value) for value in
                  (None, "000000", (0,) * 5, (0,) * 5 + (float("nan"),),
                   (0,) * 5 + (float("inf"),), (0,) * 5 + (True,))]
        cases += [dict(trials=value) for value in (0, -1, True, 1.5, "10", None)]
        cases += [dict(threshold=value) for value in (0, 7, True, 3.0, None)]
        cases += [dict(seed=value) for value in (None, True, 1.5, "11")]
        for overrides in cases:
            params = dict(months=12, trials=10)
            params.update(overrides)
            with self.assertRaises(ValueError):
                survival_probability(**params)

    def test_zero_hazards_survive(self):
        result = survival_probability(1e6, trials=20, node_hazards=(0,) * 6, env_hazard=0)
        self.assertEqual(result["combined_recovery_rate"], 1)

    def test_joint_probability_is_bounded_by_both_sources(self):
        result = survival_probability(12, trials=1000, seed=2026)
        self.assertLessEqual(result["combined_recovery_rate"], result["node_recovery_rate"])
        self.assertLessEqual(result["combined_recovery_rate"], result["environment_recovery_rate"])

    def test_differing_node_hazards_and_nonimmortal_powered_node(self):
        result = survival_probability(1, trials=20,
                                      node_hazards=(0, 0, 1e6, 1e6, 1e6, 1e6), env_hazard=0)
        self.assertEqual(result["node_recovery_rate"], 0)
        # Individually finite integer parameters may have a product above float max.
        very_large = survival_probability(10**308, trials=1,
                                          node_hazards=(10**308,) * 6, env_hazard=10**308)
        self.assertEqual(very_large["combined_recovery_rate"], 0)


if __name__ == "__main__":
    unittest.main()
