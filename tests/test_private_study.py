from dataclasses import replace
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest

from edk.analysis import analyze_sessions, export_aggregate
from edk.observations import Reading, synthetic_sessions
from edk.private_store import PrivateStore
from test_observations import manifest, session


@unittest.skipUnless(os.name == "posix", "owner-only POSIX collection")
class PrivateStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / ".edk-private"
        self.m = manifest()
        self.record = session(self.m)

    def test_modes_roundtrip_gitignore_and_no_overwrite(self):
        with PrivateStore(self.path) as store:
            store.save(self.m, self.record)
            self.assertEqual(store.session_ids(), (self.record.session_id,))
            self.assertEqual(store.load(self.m, self.record.session_id), self.record)
            with self.assertRaises(FileExistsError):
                store.save(self.m, self.record)
            with self.assertRaises(ValueError):
                store.load(self.m, "../escape")
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o700)
        for path in self.path.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual((self.path / ".gitignore").read_text(), "*\n")

    def test_broad_directory_or_file_modes_are_rejected(self):
        self.path.mkdir(mode=0o755)
        self.path.chmod(0o755)
        with self.assertRaises(ValueError):
            PrivateStore(self.path)
        self.path.chmod(0o700)
        with PrivateStore(self.path) as store:
            store.save(self.m, self.record)
            (self.path / (self.record.session_id + ".edk-private.json")).chmod(0o644)
            with self.assertRaises(ValueError):
                store.load(self.m, self.record.session_id)

    def test_symlink_store_and_record_are_rejected(self):
        target = Path(self.temporary.name) / "target"
        target.mkdir(mode=0o700)
        self.path.symlink_to(target, target_is_directory=True)
        with self.assertRaises(OSError):
            PrivateStore(self.path)
        self.path.unlink()
        with PrivateStore(self.path) as store:
            secret = target / "outside"
            secret.write_text("SENSITIVE-SENTINEL")
            (self.path / (self.record.session_id + ".edk-private.json")).symlink_to(secret)
            with self.assertRaises(OSError):
                store.load(self.m, self.record.session_id)
            with self.assertRaises(FileExistsError):
                store.save(self.m, self.record)
            self.assertEqual(secret.read_text(), "SENSITIVE-SENTINEL")

    def test_hard_link_and_fifo_records_are_rejected_without_blocking(self):
        with PrivateStore(self.path) as store:
            store.save(self.m, self.record)
            path = self.path / (self.record.session_id + ".edk-private.json")
            os.link(path, Path(self.temporary.name) / "copy")
            with self.assertRaises(ValueError):
                store.load(self.m, self.record.session_id)
            path.unlink()
            os.mkfifo(path, mode=0o600)
            with self.assertRaises(ValueError):
                store.load(self.m, self.record.session_id)

    def test_truncated_or_renamed_record_cannot_load(self):
        with PrivateStore(self.path) as store:
            store.save(self.m, self.record)
            path = self.path / (self.record.session_id + ".edk-private.json")
            other = "f" * 32
            path.rename(self.path / (other + ".edk-private.json"))
            with self.assertRaises(ValueError):
                store.load(self.m, other)
            (self.path / (other + ".edk-private.json")).write_text('{"readings":')
            with self.assertRaises(ValueError):
                store.load(self.m, other)


class AnalysisTests(unittest.TestCase):
    def test_pairwise_disagreement_does_not_invent_causes(self):
        m = manifest()
        a = session(m)
        b = replace(session(m, 1), readings=(Reading("A0", "normal", 1, 200), *a.readings[1:]))
        report = analyze_sessions(m, (a, b))
        self.assertEqual(report["pairwise_normal_comparisons"], 3)
        self.assertEqual(report["pairwise_disagreements"], 1)
        self.assertEqual(report["externally_labeled_events"]["unknown"], 1)
        self.assertEqual(report["externally_labeled_events"]["misread"], 0)

    def test_erasures_and_external_event_labels_remain_separate(self):
        m = manifest()
        a = session(m)
        b = replace(session(m, 1), readings=(Reading("A0", "ambiguous", None, 200),
                    Reading("A1", "unreadable", None, 200, "physical_erasure"),
                    Reading("A2", "normal", 1, 200, "state_change")))
        report = analyze_sessions(m, (a, b))
        self.assertEqual(report["operational_erasure_rate"], 2 / 6)
        self.assertEqual(report["pairwise_normal_comparisons"], 1)
        self.assertEqual(report["externally_labeled_events"]["physical_erasure"], 1)
        self.assertEqual(report["externally_labeled_events"]["state_change"], 1)
        self.assertEqual(report["externally_labeled_events"]["history_loss"], 0)

    def test_known_correlated_mismatch_pattern(self):
        m = manifest()
        records = []
        for index, value in enumerate((0, 0, 1, 0, 1)):
            records.append(session(m, index, tuple(Reading(a.anchor_id, "normal", value, 100)
                                                   for a in m.anchors)))
        report = analyze_sessions(m, records)
        self.assertEqual(report["correlated_disagreement"]["mean_phi"], 1)
        self.assertEqual(report["correlated_disagreement"]["defined_phi_pairs"], 3)

    def test_anonymous_export_allowlist_and_minimum_size(self):
        m = manifest()
        records = synthetic_sessions(m, count=5)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "aggregate.json"
            report = export_aggregate(m, records, path)
            serialized = path.read_text()
            for secret_field in ("manifest_id", "manifest_fingerprint", "observer_code", "started_at",
                                 "session_id", "anchor_id", '"value"', "SENSITIVE-SENTINEL"):
                self.assertNotIn(secret_field, serialized)
            self.assertEqual(json.loads(serialized), report)
            with self.assertRaises(FileExistsError):
                export_aggregate(m, records, path)
            with self.assertRaises(ValueError):
                export_aggregate(m, records[:2], Path(directory) / "small.json")

    def test_duplicate_mixed_source_and_incompatible_records_rejected(self):
        m = manifest()
        original = session(m)
        for records in ((original, original), (original, replace(session(m, 1), source="synthetic")),
                        (original, session(replace(m, manifest_id="other"), 1))):
            with self.assertRaises(ValueError):
                analyze_sessions(m, records)


if __name__ == "__main__":
    unittest.main()
