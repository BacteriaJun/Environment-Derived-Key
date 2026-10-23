import contextlib
from dataclasses import replace
import io
from itertools import combinations
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from edk.__main__ import main
from edk.concept import ConceptContext, PROFILE, concept_fixture, derive_observation_pin, run_concept
from edk.derivation import derive_pin
from edk.jsonio import encode_document
from edk.observations import exact_observation_bytes
from edk.shamir import Share, repair_share, split


class ConceptTests(unittest.TestCase):
    def setUp(self):
        self.manifest, self.session, self.secret, self.context = concept_fixture(2026)
        self.shares = split(self.secret)

    def derive(self, shares=None, session=None, context=None, manifest=None):
        return derive_observation_pin(manifest or self.manifest, session or self.session,
                                      self.shares[:3] if shares is None else shares, context or self.context)

    def test_known_answer_all_quorums_and_inherited_kdf_composition(self):
        expected = "488096914862"  # Public synthetic fixture, seed 2026.
        self.assertEqual(self.manifest.fingerprint, "a578e937121c21248711bd42824c45f73034aabe199211c72a3b674474203af9")
        for quorum in combinations(self.shares, 3):
            self.assertEqual(self.derive(quorum), expected)
        self.assertEqual(self.derive(self.shares), expected)
        self.assertEqual(expected, derive_pin(exact_observation_bytes(self.manifest, self.session), self.secret,
                                              salt=self.context.salt, device_id=self.context.device_id))
        repaired = repair_share(self.shares[:3], missing_index=5)
        self.assertEqual(self.derive([self.shares[0], self.shares[3], repaired]), expected)

    def test_context_strict_roundtrip_duplicate_unknown_and_invalid_fields(self):
        public = self.context.to_dict()
        self.assertEqual(ConceptContext.from_dict(public), self.context)
        self.assertEqual(set(public), {"schema_version", "profile", "manifest_fingerprint", "salt_hex", "device_id"})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.json"
            path.write_bytes(encode_document(public))
            self.assertEqual(ConceptContext.load(path), self.context)
            path.write_bytes(b'{"profile":"a","profile":"b"}')
            with self.assertRaises(ValueError):
                ConceptContext.load(path)
        for field, value in (("salt_hex", "A" * 64), ("salt_hex", None), ("profile", "other"),
                             ("schema_version", "other"), ("device_id", ""), ("device_id", "line\nbreak"),
                             ("device_id", "中" * 86), ("manifest_fingerprint", "A" * 64), ("secret", "SENTINEL")):
            bad = {**public, field: value}
            with self.subTest(field=field), self.assertRaises(ValueError):
                ConceptContext.from_dict(bad)
        with self.assertRaises(ValueError):
            replace(self.context, salt=bytearray(32))

    def test_metadata_changes_do_not_change_environment_input_or_output(self):
        changed = replace(self.session, session_id="b" * 32, observer_code="another_observer",
                          started_at="2026-10-23T00:00:00.000000Z", source="manual",
                          readings=tuple(replace(r, duration_ms=42, event_label="unknown") for r in self.session.readings))
        self.assertEqual(self.derive(session=changed), self.derive())

    def test_manifest_context_and_order_are_bound(self):
        renamed = replace(self.manifest, manifest_id="renamed")
        with self.assertRaises(ValueError):
            self.derive(manifest=renamed)
        with self.assertRaises(ValueError):
            self.derive(session=replace(self.session, readings=tuple(reversed(self.session.readings))))
        # Even reading-rule text enters the public manifest fingerprint.
        amended = replace(self.manifest, anchors=(replace(self.manifest.anchors[0], reading_rule="A revised rule"),
                                                  *self.manifest.anchors[1:]))
        observation = replace(self.session, manifest_fingerprint=amended.fingerprint)
        context = replace(self.context, manifest_fingerprint=amended.fingerprint)
        before = exact_observation_bytes(self.manifest, self.session)
        after = exact_observation_bytes(amended, observation)
        self.assertNotEqual(before, after)
        self.assertEqual(self.derive(manifest=amended, session=observation, context=context),
                         derive_pin(after, self.secret, salt=context.salt, device_id=context.device_id))

    def test_missing_ambiguous_unreadable_and_out_of_range_refused_before_recovery(self):
        for status in ("ambiguous", "unreadable"):
            changed = replace(self.session, readings=(replace(self.session.readings[0], status=status, value=None),
                                                      *self.session.readings[1:]))
            with patch("edk.concept.recover") as recover, self.assertRaises(ValueError):
                self.derive(session=changed)
            recover.assert_not_called()
        missing = replace(self.session, readings=self.session.readings[:-1])
        bad_range = replace(self.session, readings=(replace(self.session.readings[0], value=2), *self.session.readings[1:]))
        for changed in (missing, bad_range):
            with self.assertRaises(ValueError):
                self.derive(session=changed)
        for manifest, session, context in ((None, self.session, self.context), (self.manifest, None, self.context),
                                           (self.manifest, self.session, None)):
            with self.assertRaises(ValueError):
                derive_observation_pin(manifest, session, self.shares[:3], context)

    def test_quorum_coordinate_threshold_generation_and_corruption_rejected(self):
        share = self.shares[0]
        cases = (None, [], self.shares[:2], "shares", [share] * 3, self.shares + [share],
                 [*self.shares[:2], replace(self.shares[2], generation=bytes(b ^ 255 for b in share.generation))],
                 [*self.shares[:2], replace(self.shares[2], threshold=2)],
                 [*self.shares[:2], replace(self.shares[2], index=7)],
                 [*self.shares[:2], object()])
        for bad in cases:
            with self.subTest(kind=type(bad)), self.assertRaises(ValueError):
                self.derive(shares=bad) if bad is not None else derive_observation_pin(
                    self.manifest, self.session, None, self.context)
        corrupt = replace(self.shares[-1], payload=bytes([self.shares[-1].payload[0] ^ 1]) + self.shares[-1].payload[1:])
        with self.assertRaises(ValueError):
            self.derive([*self.shares[:5], corrupt])

    def test_changed_valid_reading_is_evaluated_exactly(self):
        first = self.session.readings[0]
        changed = replace(self.session, readings=(replace(first, value=1 - first.value), *self.session.readings[1:]))
        output = self.derive(session=changed)
        self.assertEqual(output, derive_pin(exact_observation_bytes(self.manifest, changed), self.secret,
                                           salt=self.context.salt, device_id=self.context.device_id))
        # No claim that every distinct input has a distinct truncated PIN.
        self.assertEqual(len(output), 12)

    def test_seed_bounds_and_reproducible_report_without_secret_outputs(self):
        first = run_concept(2026)
        self.assertEqual(first, run_concept(2026))
        self.assertEqual(first["source"], "synthetic")
        self.assertEqual(first["profile"], PROFILE)
        self.assertEqual(first["verified_quorums"], 20)
        self.assertTrue(all(first["checks"].values()))
        text = json.dumps(first)
        for forbidden in (self.secret.hex(), "488096914862", '"pin"', '"payload"', '"salt"'):
            self.assertNotIn(forbidden, text)
        for seed in (True, None, "2026", 1.0, -(2**63) - 1, 2**63):
            with self.assertRaises(ValueError):
                run_concept(seed)

    def test_cli_optional_report_no_overwrite_and_failure_redaction(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            with contextlib.redirect_stdout(io.StringIO()) as out:
                main(["concept-run", "--seed", "2026", "--output", str(path)])
            self.assertEqual(json.loads(out.getvalue()), json.loads(path.read_bytes()))
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), \
                    self.assertRaises(SystemExit) as stopped:
                main(["concept-run", "--output", str(path)])
            self.assertEqual(stopped.exception.code, 2)
            out, err = io.StringIO(), io.StringIO()
            with patch("edk.concept.derive_observation_pin", side_effect=ValueError("SENSITIVE-SENTINEL")), \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as stopped:
                main(["concept-run"])
            self.assertEqual(stopped.exception.code, 2)
            self.assertEqual(out.getvalue(), "")
            self.assertNotIn("SENSITIVE-SENTINEL", err.getvalue())

    def test_cli_creates_no_files_in_current_directory(self):
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"), PYTHONDONTWRITEBYTECODE="1")
        with tempfile.TemporaryDirectory() as directory:
            process = subprocess.run([sys.executable, "-O", "-m", "edk", "concept-run", "--seed", "2026"],
                                     cwd=directory, env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(list(Path(directory).iterdir()), [])
            self.assertEqual(json.loads(process.stdout)["verified_quorums"], 20)


if __name__ == "__main__":
    unittest.main()
