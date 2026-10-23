import copy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from edk.jsonio import encode_document
from edk.observations import Reading, synthetic_sessions
from edk.study_protocol import StudyPolicy, analyze_study
from test_observations import manifest, session


def policy(m, **changes):
    parameters = {"manifest_fingerprint": m.fingerprint,
                  "created_at": "2000-01-01T00:00:00.000000Z", "minimum_sessions": 5,
                  "minimum_observers": 1, "minimum_span_seconds": 4,
                  "maximum_operational_erasure_rate": 0,
                  "maximum_pairwise_disagreement_rate": 0, "maximum_p95_reading_ms": 100}
    parameters.update(changes)
    return StudyPolicy(**parameters)


class StudyPolicyTests(unittest.TestCase):
    def test_policy_strict_roundtrip_and_bounded_json_loading(self):
        m = manifest()
        original = policy(m)
        self.assertEqual(StudyPolicy.from_dict(original.to_dict()), original)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "public-policy.json"
            path.write_bytes(encode_document(original.to_dict()))
            self.assertEqual(StudyPolicy.load(path), original)
            for data in (b'{"minimum_sessions":5,"minimum_sessions":6}',
                         b'{"minimum_span_seconds":NaN}', b'{"minimum_span_seconds":1e999}'):
                path.write_bytes(data)
                with self.assertRaises(ValueError):
                    StudyPolicy.load(path)

    def test_unknown_or_missing_policy_fields_are_rejected_without_echo(self):
        value = policy(manifest()).to_dict()
        for key in value:
            bad = {name: item for name, item in value.items() if name != key}
            with self.subTest(missing=key), self.assertRaises(ValueError):
                StudyPolicy.from_dict(bad)
        bad = {**value, "raw_state": "SENSITIVE-SENTINEL"}
        with self.assertRaises(ValueError) as raised:
            StudyPolicy.from_dict(bad)
        self.assertNotIn("SENSITIVE-SENTINEL", str(raised.exception))

    def test_policy_values_are_explicit_strict_and_finite(self):
        m = manifest()
        cases = {
            "schema_version": (None, "edk.study-policy/v2", 1),
            "manifest_fingerprint": ("a" * 63, "A" * 64, None, 1),
            "created_at": ("2000-01-01T00:00:00Z", "2000-01-01T00:00:00.000000+00:00",
                           "2000-02-30T00:00:00.000000Z", None),
            "minimum_sessions": (4, 1001, True, 5.0),
            "minimum_observers": (0, 1001, True, 1.0),
            "minimum_span_seconds": (-1, True, "4", float("nan"), float("inf"), 10 ** 1000),
            "maximum_operational_erasure_rate": (-0.1, 1.1, True, float("nan")),
            "maximum_pairwise_disagreement_rate": (-0.1, 1.1, True, float("inf")),
            "maximum_p95_reading_ms": (0, 86_400_001, True, 100.0),
        }
        for name, values in cases.items():
            for value in values:
                with self.subTest(name=name, value_type=type(value)), self.assertRaises(ValueError):
                    policy(m, **{name: value})


class StudyAssessmentTests(unittest.TestCase):
    def test_manual_quality_pass_does_not_validate_entropy_or_approve_derivation(self):
        m = manifest()
        result = analyze_study(m, tuple(session(m, i) for i in range(5)), policy(m))
        self.assertTrue(result["study_quality_criteria_passed"])
        self.assertTrue(result["manual_workflow_criteria_passed"])
        self.assertFalse(result["environment_entropy_validated"])
        self.assertFalse(result["real_key_derivation_approved"])
        self.assertTrue(all(result["criteria"].values()))
        self.assertEqual(result["counts"]["observers"], 1)
        self.assertEqual(result["session_span_seconds"], 4)

    def test_synthetic_quality_pass_cannot_satisfy_manual_workflow(self):
        m = manifest()
        permissive = policy(m, maximum_operational_erasure_rate=1,
                            maximum_pairwise_disagreement_rate=1,
                            maximum_p95_reading_ms=86_400_000)
        result = analyze_study(m, synthetic_sessions(m, count=5), permissive)
        self.assertTrue(result["study_quality_criteria_passed"])
        self.assertFalse(result["manual_workflow_criteria_passed"])
        self.assertEqual(result["declared_source"], "synthetic")

    def test_each_explicit_quality_criterion_can_fail(self):
        m = manifest()
        records = tuple(session(m, i) for i in range(5))
        variants = [
            (policy(m, minimum_sessions=6), records, "minimum_sessions_met"),
            (policy(m, minimum_observers=2), records, "minimum_observers_met"),
            (policy(m, minimum_span_seconds=5), records, "minimum_span_met"),
            (policy(m, maximum_p95_reading_ms=99), records, "p95_reading_time_within_limit"),
        ]
        changed = replace(records[0], readings=(Reading("A0", "unreadable", None, 100), *records[0].readings[1:]))
        variants.append((policy(m), (changed, *records[1:]), "operational_erasure_rate_within_limit"))
        changed = replace(records[0], readings=(Reading("A0", "normal", 1, 100), *records[0].readings[1:]))
        variants.append((policy(m), (changed, *records[1:]), "pairwise_disagreement_rate_within_limit"))
        for chosen, values, criterion in variants:
            with self.subTest(criterion=criterion):
                result = analyze_study(m, values, chosen)
                self.assertFalse(result["criteria"][criterion])
                self.assertFalse(result["study_quality_criteria_passed"])
                self.assertFalse(result["manual_workflow_criteria_passed"])

    def test_multiple_observers_span_and_input_order(self):
        m = manifest()
        records = tuple(replace(session(m, i), observer_code=f"observer_{i % 2}") for i in range(5))
        chosen = policy(m, minimum_observers=2)
        result = analyze_study(m, records, chosen)
        self.assertEqual(result, analyze_study(m, tuple(reversed(records)), chosen))
        self.assertEqual(result["counts"]["observers"], 2)
        self.assertTrue(result["study_quality_criteria_passed"])

    def test_no_normal_comparisons_fail_even_with_permissive_limits(self):
        m = manifest()
        records = tuple(session(m, i, tuple(Reading(a.anchor_id, "ambiguous", None, 100)
                                            for a in m.anchors)) for i in range(5))
        result = analyze_study(m, records, policy(m, maximum_operational_erasure_rate=1,
                                                 maximum_pairwise_disagreement_rate=1))
        self.assertIsNone(result["aggregate"]["pairwise_disagreement_rate"])
        self.assertFalse(result["criteria"]["pairwise_disagreement_rate_within_limit"])
        self.assertFalse(result["study_quality_criteria_passed"])

    def test_binding_duplicates_sources_and_session_schema_errors_are_rejected(self):
        m = manifest()
        records = tuple(session(m, i) for i in range(5))
        other = replace(m, manifest_id="another-manifest")
        with self.assertRaises(ValueError):
            analyze_study(m, records, policy(other))
        cases = ((records[0], records[0]),
                 (records[0], replace(records[1], source="synthetic")),
                 (records[0], session(other, 1)),
                 (records[0], replace(records[1], readings=tuple(reversed(records[1].readings)))),
                 (records[0], object()), [], [records[0]], {}, "records")
        for values in cases:
            with self.subTest(kind=type(values)), self.assertRaises(ValueError):
                analyze_study(m, values, policy(m))

    def test_policy_timestamp_rejects_earlier_sessions_and_accepts_equal_start(self):
        m = manifest()
        records = tuple(session(m, i) for i in range(5))
        analyze_study(m, records, policy(m))
        with self.assertRaises(ValueError):
            analyze_study(m, records, policy(m, created_at="2000-01-01T00:00:00.000001Z"))

    def test_anonymous_assessment_excludes_private_fields_and_is_nonmutating(self):
        m = manifest()
        records = tuple(session(m, i) for i in range(5))
        chosen = policy(m)
        before = [copy.deepcopy(record.to_dict()) for record in records]
        result = analyze_study(m, records, chosen)
        rendered = json.dumps(result)
        for value in (chosen.created_at, m.fingerprint, m.manifest_id,
                      records[0].observer_code, *(record.session_id for record in records)):
            self.assertNotIn(value, rendered)
        for field in ('"value"', '"observer_code"', '"started_at"',
                      '"manifest_fingerprint"', '"session_id"', '"anchor_id"', '"created_at"'):
            self.assertNotIn(field, rendered)
        self.assertIs(type(result["aggregate"]["readings"]), int)
        self.assertEqual(before, [record.to_dict() for record in records])
        encode_document(result)


if __name__ == "__main__":
    unittest.main()
