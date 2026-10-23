import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from edk.__main__ import main
from edk.bench import BenchToken, check_test, prepare_test
from edk.jsonio import encode_document
from edk.operations import OperationJournal
from edk.private_store import PrivateStore
from edk.sram import MCP7940N, MemoryRegisterBus
from edk.observations import synthetic_sessions
from edk.study_protocol import StudyPolicy
from test_observations import manifest
from test_operations import topology, Rig


class EngineeringCLITests(unittest.TestCase):
    def test_study_assessment_cli_exports_aggregate_and_retains_negative_result(self):
        model = manifest()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            definition, policy_path, store_path = root / "manifest.json", root / "policy.json", root / "private"
            definition.write_bytes(encode_document(model.to_dict()))
            policy = StudyPolicy(model.fingerprint, "1999-01-01T00:00:00.000000Z", 5, 1, 0, 1, 1, 86400000)
            policy_path.write_bytes(encode_document(policy.to_dict()))
            with PrivateStore(store_path) as store:
                for session in synthetic_sessions(model, count=10, seed=2026):
                    store.save(model, session)
            with contextlib.redirect_stdout(io.StringIO()):
                main(["study-accept", str(definition), "--policy", str(policy_path), "--store", str(store_path),
                      "--output", str(root / "passed.json")])
            passed = json.loads((root / "passed.json").read_bytes())
            self.assertTrue(passed["study_quality_criteria_passed"])
            self.assertFalse(passed["manual_workflow_criteria_passed"])
            self.assertFalse(passed["environment_entropy_validated"])
            self.assertFalse(passed["real_key_derivation_approved"])
            document = policy.to_dict()
            document["minimum_observers"] = 1000
            policy_path.write_bytes(encode_document(document))
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as stopped:
                main(["study-accept", str(definition), "--policy", str(policy_path), "--store", str(store_path),
                      "--output", str(root / "failed.json")])
            self.assertEqual(stopped.exception.code, 3)
            self.assertFalse(json.loads((root / "failed.json").read_bytes())["study_quality_criteria_passed"])

    def test_study_assessment_does_not_create_missing_private_store(self):
        model = manifest()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            definition, policy_path, store_path = root / "manifest.json", root / "policy.json", root / "private"
            definition.write_bytes(encode_document(model.to_dict()))
            policy_path.write_bytes(encode_document(StudyPolicy(model.fingerprint, "1999-01-01T00:00:00.000000Z",
                                                               5, 1, 0, 1, 1, 86400000).to_dict()))
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stopped:
                main(["study-accept", str(definition), "--policy", str(policy_path), "--store", str(store_path),
                      "--output", str(root / "report.json")])
            self.assertEqual(stopped.exception.code, 2)
            self.assertFalse(store_path.exists())
    def test_doctor_strict_readiness_exit_and_no_device_access(self):
        report = {"host_preflight_passed": True, "device_transactions_performed": False}
        for abi, expected in ((None, 3), ({"checked": False, "matches": False}, 3),
                              ({"checked": True, "matches": False}, 3),
                              ({"checked": True, "matches": True}, 0)):
            with patch("edk.research_cli.doctor_report", return_value=dict(report)), \
                    patch("edk.native_abi.check_native_abi", return_value=abi), \
                    patch("edk.linux_i2c.os.open") as opened, contextlib.redirect_stdout(io.StringIO()):
                args = ["bench-doctor", "--require-ready"] + (["--check-abi"] if abi else [])
                if expected:
                    with self.assertRaises(SystemExit) as stopped:
                        main(args)
                    self.assertEqual(stopped.exception.code, expected)
                else:
                    main(args)
                opened.assert_not_called()

    def test_bench_accept_saves_failed_criteria_as_report_with_exit_three(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports = []
            for n in range(5):
                device = MCP7940N(MemoryRegisterBus())
                token = BenchToken(f"{n:032x}", "2000-01-01T00:00:00.000000Z")
                prepare_test(device, token)
                report = check_test(device, token, source="synthetic_bus", operator_vcc_off_seconds=60)
                path = root / f"trial-{n}.json"
                path.write_bytes(encode_document(report))
                reports.append(str(path))
            output = root / "passed.json"
            with contextlib.redirect_stdout(io.StringIO()):
                main(["bench-accept", *reports, "--minimum-vcc-off-seconds", "60", "--output", str(output)])
            passed = json.loads(output.read_bytes())
            self.assertTrue(passed["acceptance_criteria_passed"])
            self.assertFalse(passed["physical_acceptance_verified"])
            self.assertFalse(passed["declared_physical_workflow_criteria_passed"])
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as failed:
                main(["bench-accept", *reports, "--minimum-vcc-off-seconds", "61", "--output", str(root / "failed.json")])
            self.assertEqual(failed.exception.code, 3)
            self.assertFalse(json.loads((root / "failed.json").read_bytes())["acceptance_criteria_passed"])

    def test_incomplete_status_exit_three_and_no_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "op"
            with OperationJournal(root, topology(), source="synthetic_bus"):
                pass
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as stopped:
                main(["operation-status", "--journal", str(root)])
            self.assertEqual(stopped.exception.code, 3)
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})

    def test_enroll_failure_redacts_exception_and_preserves_journal(self):
        rig = Rig()
        rig.buses[0].write = lambda *_: (_ for _ in ()).throw(OSError("SENSITIVE-SENTINEL"))
        with tempfile.TemporaryDirectory() as directory:
            root, config = Path(directory) / "op", Path(directory) / "topology.json"
            config.write_bytes(encode_document(topology().to_dict()))
            out, err = io.StringIO(), io.StringIO()
            with patch("edk.research_cli.sys.platform", "linux"), \
                    patch("edk.linux_i2c.LinuxI2C", side_effect=rig.open), \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as stopped:
                main(["hardware-enroll", "--topology", str(config), "--journal", str(root), "--laboratory-hardware"])
            self.assertEqual(stopped.exception.code, 2)
            self.assertNotIn("SENSITIVE-SENTINEL", out.getvalue() + err.getvalue())
            self.assertNotIn("Traceback", err.getvalue())
            self.assertTrue(root.is_dir())
            self.assertEqual(json.loads(sorted(root.glob("*.event.json"))[-1].read_bytes())["event"], "stopped")


if __name__ == "__main__":
    unittest.main()
