import copy
import json
import math
from pathlib import Path
import tempfile
import unittest

from edk.bench import BenchToken, check_test, prepare_test
from edk.bench_acceptance import analyze_bench_reports, load_bench_report, validate_bench_report
from edk.jsonio import encode_document
from edk.sram import MCP7940N, MemoryRegisterBus


def observation(index=1, *, source="synthetic_bus", duration=60):
    token = BenchToken(f"{index:032x}", "2000-01-01T00:00:00.000000Z")
    device = MCP7940N(MemoryRegisterBus())
    prepare_test(device, token)
    return check_test(device, token, source=source, operator_vcc_off_seconds=duration)


class BenchAcceptanceTests(unittest.TestCase):
    def test_generated_reports_parse_and_synthetic_cannot_satisfy_physical_gate(self):
        reports = [observation(i) for i in range(5)]
        result = analyze_bench_reports(reports, minimum_vcc_off_seconds=60)
        self.assertTrue(result["acceptance_criteria_passed"])
        self.assertFalse(result["declared_physical_workflow_criteria_passed"])
        self.assertFalse(result["physical_acceptance_verified"])
        self.assertEqual(result["trial_result_counts"], {"passed": 5, "failed": 0})
        self.assertEqual(result["duration_seconds"]["mean"], 60)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_bytes(encode_document(reports[0]))
            self.assertEqual(load_bench_report(path), reports[0])

    def test_declared_physical_workflow_criteria_do_not_attest_hardware(self):
        result = analyze_bench_reports([observation(i, source="physical_io") for i in range(5)])
        self.assertTrue(result["declared_physical_workflow_criteria_passed"])
        self.assertFalse(result["physical_acceptance_verified"])

    def test_insufficient_trials_and_each_failure_criterion_fail_closed(self):
        self.assertFalse(analyze_bench_reports([observation()])["acceptance_criteria_passed"])
        cases = []
        value = observation()
        value["matches_public_pattern"] = False
        cases.append((value, "pattern_match"))
        value = observation()
        value["status_before"]["backup_enabled"] = False
        value["status_after"]["backup_enabled"] = False
        cases.append((value, "backup_enabled_before_and_after"))
        value = observation()
        value["status_after"]["power_failure_recorded"] = True
        value["status_changed_during_read"] = True
        cases.append((value, "status_unchanged"))
        cases.append((observation(duration=None), "duration_supplied"))
        cases.append((observation(duration=59.9), "minimum_duration_met"))
        for report, criterion in cases:
            with self.subTest(criterion=criterion):
                result = analyze_bench_reports([report], minimum_trials=1, minimum_vcc_off_seconds=60)
                self.assertFalse(result["acceptance_criteria_passed"])
                self.assertEqual(result["criterion_counts"][criterion]["failed"], 1)
                self.assertEqual(result["trial_result_counts"]["failed"], 1)

    def test_duplicate_trial_and_source_pooling_are_rejected(self):
        with self.assertRaises(ValueError):
            analyze_bench_reports([observation(), observation()])
        with self.assertRaises(ValueError):
            analyze_bench_reports([observation(), observation(2, source="physical_io")])

    def test_unknown_fields_bad_types_and_inconsistent_status_are_rejected(self):
        original = observation()
        changes = [("unexpected", "SENSITIVE-SENTINEL"), ("schema_version", "future"),
                   ("source", "measured"), ("purpose", "secret"), ("matches_public_pattern", 1),
                   ("status_changed_during_read", 0), ("status_changed_during_read", True),
                   ("public_test_nonce", "A" * 32), ("observed_at", "2000-01-01T00:00:00Z"),
                   ("observed_at", "2000-01-01T00:00:00.000000+00:00"),
                   ("observed_at", "2000-02-30T00:00:00.000000Z"),
                   ("duration_provenance", "clock measured"), ("interpretation", "trusted")]
        for name, value in changes:
            report = copy.deepcopy(original)
            report[name] = value
            with self.subTest(name=name, value=value), self.assertRaises(ValueError) as raised:
                validate_bench_report(report)
            self.assertNotIn("SENSITIVE-SENTINEL", str(raised.exception))
        for status in ({}, {"backup_enabled": True, "power_failure_recorded": False,
                            "oscillator_running": 1},
                       {**original["status_before"], "unknown": True}):
            report = copy.deepcopy(original)
            report["status_before"] = status
            with self.assertRaises(ValueError):
                validate_bench_report(report)

    def test_duration_and_analysis_limits_are_strict(self):
        for duration in (-1, True, "60", float("nan"), float("inf"), 10 ** 1000):
            report = observation()
            report["operator_vcc_off_seconds"] = duration
            with self.subTest(duration=type(duration)), self.assertRaises(ValueError):
                analyze_bench_reports([report], minimum_trials=1)
        for minimum in (0, -1, 1001, True, 5.0):
            with self.assertRaises(ValueError):
                analyze_bench_reports([observation()], minimum_trials=minimum)
        for minimum in (-1, True, float("nan"), float("inf"), "60"):
            with self.assertRaises(ValueError):
                analyze_bench_reports([observation()], minimum_vcc_off_seconds=minimum)
        for reports in ([], {}, "string", [observation()] * 1001):
            with self.assertRaises(ValueError):
                analyze_bench_reports(reports)

    def test_no_durations_and_large_finite_summaries_remain_json_encodable(self):
        result = analyze_bench_reports([observation(duration=None)], minimum_trials=1)
        self.assertIsNone(result["duration_seconds"]["mean"])
        self.assertIsNone(result["duration_seconds"]["median"])
        self.assertEqual(result["duration_seconds"]["missing"], 1)
        result = analyze_bench_reports([observation(i, duration=1e308) for i in range(6)])
        self.assertEqual(result["duration_seconds"]["mean"], 1e308)
        self.assertEqual(result["duration_seconds"]["median"], 1e308)
        self.assertTrue(math.isfinite(result["duration_seconds"]["mean"]))
        encode_document(result)

    def test_loaded_duplicate_json_key_and_nonfinite_values_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            for data in (b'{"source":"physical_io","source":"synthetic_bus"}',
                         b'{"operator_vcc_off_seconds":NaN}',
                         b'{"operator_vcc_off_seconds":1e999}'):
                path.write_bytes(data)
                with self.assertRaises(ValueError):
                    load_bench_report(path)

    def test_aggregate_does_not_include_per_trial_identifiers_or_timestamps(self):
        reports = [observation(i, duration=i * 60) for i in range(1, 6)]
        before = copy.deepcopy(reports)
        result = analyze_bench_reports(reports)
        rendered = json.dumps(result)
        for report in reports:
            self.assertNotIn(report["public_test_nonce"], rendered)
            self.assertNotIn(report["observed_at"], rendered)
        self.assertEqual(reports, before)
        self.assertEqual(result["duration_seconds"]["minimum"], 60)
        self.assertEqual(result["duration_seconds"]["maximum"], 300)
        self.assertEqual(result["duration_seconds"]["median"], 180)
        self.assertEqual(result["duration_seconds"]["mean"], 180)


if __name__ == "__main__":
    unittest.main()
