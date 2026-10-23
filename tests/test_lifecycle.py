from dataclasses import replace
import unittest

from edk.lifecycle import DEFAULT_NODES, LifecycleConfig, NodeModel, lifecycle_report


def ideal(**overrides):
    params = dict(anchors=3, nodes=tuple(replace(n, monthly_hazard=0) for n in DEFAULT_NODES),
                  location_hazards=(), drift_hazard=0, physical_erasure_hazard=0,
                  history_loss_hazard=0, misread_probability=0, ambiguous_probability=0)
    params.update(overrides)
    return LifecycleConfig(**params)


class LifecycleTests(unittest.TestCase):
    def test_seed_reproduces_full_trajectories(self):
        config = LifecycleConfig()
        self.assertEqual(lifecycle_report(config, months=6, trials=30, seed=12),
                         lifecycle_report(config, months=6, trials=30, seed=12))

    def test_ideal_model_has_full_recovery(self):
        for row in lifecycle_report(ideal(), months=3, trials=10)["months"]:
            self.assertEqual(row["normal_recovery_rate"], 1)
            self.assertEqual(row["system_recoverable_in_model_rate"], 1)

    def test_common_location_can_destroy_quorum(self):
        nodes = tuple(replace(n, location="home" if index < 4 else "office")
                      for index, n in enumerate(ideal().nodes))
        config = ideal(nodes=nodes, location_hazards=(("home", 1e6),))
        row = lifecycle_report(config, months=1, trials=10)["months"][-1]
        self.assertEqual(row["electronic_quorum_rate"], 0)
        self.assertEqual(row["environment_information_survival_rate"], 1)

    def test_maintenance_repairs_only_with_quorum(self):
        nodes = tuple(replace(n, monthly_hazard=1e6 if index == 0 else 0)
                      for index, n in enumerate(ideal().nodes))
        row = lifecycle_report(ideal(nodes=nodes, maintenance_interval=1), months=1, trials=10)["months"][-1]
        self.assertEqual(row["node_repairs"], 10)
        self.assertEqual(row["electronic_quorum_rate"], 1)
        nodes = tuple(replace(n, monthly_hazard=1e6) for n in nodes)
        row = lifecycle_report(ideal(nodes=nodes, maintenance_interval=1), months=1, trials=10)["months"][-1]
        self.assertEqual(row["node_repairs"], 0)
        self.assertEqual(row["electronic_quorum_rate"], 0)

    def test_restoration_cannot_reverse_history_loss(self):
        row = lifecycle_report(ideal(history_loss_hazard=1e6, maintenance_interval=1),
                               months=1, trials=10)["months"][-1]
        self.assertEqual(row["historical_loss_fraction"], 1)
        self.assertEqual(row["environment_information_survival_rate"], 0)
        self.assertEqual(row["system_recoverable_in_model_rate"], 0)
        self.assertEqual(row["environment_repairs"], 0)

    def test_erasure_misread_and_history_are_separate(self):
        row = lifecycle_report(ideal(misread_probability=1), months=0, trials=10)["months"][0]
        self.assertEqual(row["misread_fraction"], 1)
        self.assertEqual(row["historical_loss_fraction"], 0)
        self.assertEqual(row["system_recoverable_in_model_rate"], 1)
        self.assertEqual(row["normal_recovery_rate"], 0)
        row = lifecycle_report(ideal(physical_erasure_hazard=1e6), months=1, trials=10)["months"][-1]
        self.assertEqual(row["physical_erasure_fraction"], 1)
        self.assertEqual(row["historical_loss_fraction"], 0)

    def test_maintenance_stop_and_vehicle_stress_are_effective(self):
        base = ideal(drift_hazard=1e6, maintenance_interval=1, maintenance_stop_after=1)
        rows = lifecycle_report(base, months=2, trials=10)["months"]
        self.assertEqual(rows[1]["normal_recovery_rate"], 1)
        self.assertEqual(rows[2]["normal_recovery_rate"], 0)
        nodes = tuple(replace(n, monthly_hazard=1, stress_multiplier=1e6) if index < 4 else n
                      for index, n in enumerate(ideal().nodes))
        row = lifecycle_report(ideal(nodes=nodes), months=1, trials=10)["months"][-1]
        self.assertEqual(row["electronic_quorum_rate"], 0)

    def test_powered_s5_is_not_immortal_in_default_model(self):
        s5 = DEFAULT_NODES[4]
        self.assertTrue(s5.continuously_powered)
        self.assertGreater(s5.monthly_hazard, 0)

    def test_invalid_model_parameters_and_work_limit(self):
        for params in (dict(anchors=True), dict(nodes=()), dict(misread_probability=2),
                       dict(history_loss_hazard=float("nan")), dict(maintenance_stop_after=1),
                       dict(location_hazards=(("unknown", 1),)), dict(maintenance_interval=0)):
            with self.assertRaises(ValueError):
                LifecycleConfig(**params)
        with self.assertRaises(ValueError):
            lifecycle_report(LifecycleConfig(), months=600, trials=100000)


if __name__ == "__main__":
    unittest.main()
