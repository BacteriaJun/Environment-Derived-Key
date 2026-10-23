import copy
from dataclasses import replace
import json
import unittest

from edk.analysis import analyze_sessions
from edk.environment import AnchorDefinition, EnvironmentUnavailable
from edk.jsonio import MAX_DOCUMENT_BYTES, decode_document, encode_document
from edk.manifest import AnchorManifest
from edk.observations import (ObservationSession, Reading, collect_session,
                              exact_observation_bytes, parse_reading, synthetic_sessions)


def manifest(count=3):
    return AnchorManifest("synthetic-study", tuple(
        AnchorDefinition(f"A{i}", "fictional sample", "read integer index", 4 + i)
        for i in range(count)))


def session(m, index=0, readings=None):
    return ObservationSession(f"{index + 1:032x}", m.fingerprint, "private-observer",
                              f"2000-01-01T00:00:{index:02d}.000000Z",
                              tuple(readings) if readings is not None else tuple(
                                  Reading(a.anchor_id, "normal", 0, 100, "none") for a in m.anchors))


class ManifestTests(unittest.TestCase):
    def test_strict_roundtrip_and_public_only_hash(self):
        m = manifest()
        self.assertEqual(AnchorManifest.from_dict(decode_document(encode_document(m.to_dict()))), m)
        changed = replace(m, anchors=tuple(reversed(m.anchors)))
        self.assertNotEqual(m.fingerprint, changed.fingerprint)

    def test_unknown_secret_fields_and_missing_fields_rejected(self):
        for secret in ("state", "pin", "credentials", "secret"):
            value = manifest().to_dict()
            value[secret] = "SENSITIVE-SENTINEL"
            with self.assertRaises(ValueError):
                AnchorManifest.from_dict(value)
        value = manifest().to_dict()
        value["anchors"][0]["value"] = 1
        with self.assertRaises(ValueError):
            AnchorManifest.from_dict(value)

    def test_versions_state_counts_order_duplicates_and_types(self):
        original = manifest().to_dict()
        variations = []
        for version in (None, "edk.anchor-manifest/v2", 1):
            value = copy.deepcopy(original)
            value["schema_version"] = version
            variations.append(value)
        for count in (True, 1, 65537, 3.5, "4"):
            value = copy.deepcopy(original)
            value["anchors"][0]["state_count"] = count
            variations.append(value)
        value = copy.deepcopy(original)
        value["anchors"][1]["anchor_id"] = value["anchors"][0]["anchor_id"]
        variations.append(value)
        for value in variations:
            with self.assertRaises(ValueError):
                AnchorManifest.from_dict(value)

    def test_terminal_control_characters_and_unicode_errors_rejected(self):
        for bad in ("\x1b[2J", "line\nnext", "\ud800"):
            value = manifest().to_dict()
            value["anchors"][0]["reading_rule"] = bad
            with self.assertRaises(ValueError):
                AnchorManifest.from_dict(value)

    def test_strict_json_bounds_duplicates_nonfinite_and_depth(self):
        for data in (b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}',
                     b'{"a":1e999}', b'[]', b'\xff', b'[' * 2000 + b']' * 2000,
                     b' ' * (MAX_DOCUMENT_BYTES + 1)):
            with self.assertRaises(ValueError):
                decode_document(data)


class ObservationTests(unittest.TestCase):
    def test_three_statuses_and_arbitrary_state_counts(self):
        self.assertEqual(parse_reading("A", 1000, "999", 12).value, 999)
        self.assertEqual(parse_reading("A", 4, "?", 12).status, "ambiguous")
        self.assertEqual(parse_reading("A", 4, "-", 12).status, "unreadable")
        for bad in ("4", "-1", "1.0", "1 2", "１", "1\n2"):
            with self.assertRaises(ValueError):
                parse_reading("A", 4, bad, 12)

    def test_no_values_on_erasures_and_no_approximate_encoding(self):
        m = manifest()
        original = session(m)
        for status in ("ambiguous", "unreadable"):
            with self.assertRaises(ValueError):
                Reading("A0", status, 1, 10)
            changed = replace(original, readings=(Reading("A0", status, None, 10), *original.readings[1:]))
            with self.assertRaises(EnvironmentUnavailable):
                exact_observation_bytes(m, changed)

    def test_binding_order_range_and_versions_rejected(self):
        m = manifest()
        record = session(m).to_dict()
        for field, value in (("schema_version", "future"), ("session_id", "../escape"),
                             ("observer_code", "name with spaces"), ("started_at", "today")):
            bad = copy.deepcopy(record)
            bad[field] = value
            with self.assertRaises(ValueError):
                ObservationSession.from_dict(bad, m)
        for readings in (list(reversed(record["readings"])), record["readings"][:-1]):
            bad = copy.deepcopy(record)
            bad["readings"] = readings
            with self.assertRaises(ValueError):
                ObservationSession.from_dict(bad, m)
        with self.assertRaises(ValueError):
            session(m).validate_for(replace(m, manifest_id="other-study"))
        bad = copy.deepcopy(record)
        bad["readings"][0]["value"] = 4
        with self.assertRaises(ValueError):
            ObservationSession.from_dict(bad, m)

    def test_private_serialization_roundtrip_and_repr(self):
        m = manifest()
        original = session(m)
        self.assertEqual(ObservationSession.from_dict(original.to_dict(), m), original)
        self.assertNotIn("private-observer", repr(original))
        self.assertNotIn("value=", repr(original.readings[0]))

    def test_exact_encoding_is_versioned_and_bound_without_kdf(self):
        m = manifest()
        original = session(m)
        encoded = exact_observation_bytes(m, original)
        self.assertTrue(encoded.startswith(b"EDK-OBS/v1\x00"))
        changed = replace(original, readings=(replace(original.readings[0], value=1), *original.readings[1:]))
        self.assertNotEqual(encoded, exact_observation_bytes(m, changed))

    def test_collection_timing_statuses_and_abort(self):
        m = manifest()
        answers = iter(("1", "?", "-"))
        times = iter((0, 10_000_000, 20_000_000, 50_000_000, 60_000_000, 100_000_000))
        record = collect_session(m, "observer-test", lambda _: next(answers), clock_ns=lambda: next(times))
        self.assertEqual([r.duration_ms for r in record.readings], [10, 30, 40])
        self.assertEqual([r.status for r in record.readings], ["normal", "ambiguous", "unreadable"])
        with self.assertRaises(ValueError):
            collect_session(m, "observer-test", lambda _: "invalid")

    def test_synthetic_data_and_aggregates_reproduce(self):
        m = manifest(6)
        a = synthetic_sessions(m, count=30, seed=2026)
        b = synthetic_sessions(m, count=30, seed=2026)
        self.assertEqual(a, b)
        self.assertEqual(analyze_sessions(m, a), analyze_sessions(m, b))
        self.assertNotEqual(a, synthetic_sessions(m, count=30, seed=2027))


if __name__ == "__main__":
    unittest.main()
