import contextlib
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from edk.__main__ import main
from edk.deployment import HardwareTopology, NodeSlot
from edk.jsonio import encode_document
from edk.operations import OperationJournal, enroll, inspect_operation, load_journal, summarize_events
from edk.shamir import Share
from edk.sram import MCP7940N, MemoryRegisterBus, encode_share


def topology():
    return HardwareTopology("FictionalLab", tuple(NodeSlot(i, f"/dev/i2c-{i}", f"Domain{i}") for i in range(1, 7)))


class Bus(MemoryRegisterBus):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


class Rig:
    def __init__(self):
        self.buses = [Bus() for _ in range(6)]
        self.opens = []

    def open(self, path):
        self.opens.append(path)
        return self.buses[int(path.rsplit("-", 1)[1]) - 1]


class DeploymentTests(unittest.TestCase):
    def test_strict_topology_roundtrip_and_local_risk(self):
        original = topology()
        self.assertEqual(HardwareTopology.from_dict(original.to_dict()), original)
        self.assertFalse(original.colocated_quorum)
        value = original.to_dict()
        for slot in value["nodes"][:3]:
            slot["failure_domain"] = "Shared"
        risky = HardwareTopology.from_dict(value)
        self.assertTrue(risky.colocated_quorum)
        self.assertNotEqual(risky.fingerprint, original.fingerprint)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "op"
            with self.assertRaises(ValueError):
                OperationJournal(path, risky, source="synthetic_bus")
            self.assertFalse(path.exists())
            with OperationJournal(path, risky, source="synthetic_bus", allow_colocated_quorum=True):
                pass

    def test_topology_rejects_extra_missing_duplicate_and_wrong_types(self):
        mutations = [lambda v: v.update(secret_state=1), lambda v: v.update(threshold=True),
                     lambda v: v.update(schema_version="unknown"), lambda v: v.update(nodes=v["nodes"][:5]),
                     lambda v: v["nodes"][0].update(index=True),
                     lambda v: v["nodes"][0].update(index=2),
                     lambda v: v["nodes"][0].update(adapter="/dev/i2c-01"),
                     lambda v: v["nodes"][0].update(adapter="../dev/i2c-1"),
                     lambda v: v["nodes"][0].update(adapter=v["nodes"][1]["adapter"]),
                     lambda v: v["nodes"][0].update(failure_domain="private address with spaces"),
                     lambda v: v["nodes"][0].update(unknown=True)]
        for mutate in mutations:
            value = topology().to_dict()
            mutate(value)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                HardwareTopology.from_dict(value)


class OperationTests(unittest.TestCase):
    def test_full_enrollment_inspection_permissions_and_no_secret_files(self):
        rig, layout = Rig(), topology()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "enroll.edk-operation"
            with OperationJournal(root, layout, source="synthetic_bus") as journal:
                result = enroll(layout, journal, rig.open)
                self.assertTrue(result["completion_recorded"])
                self.assertEqual(result["verified_slots"], list(range(1, 7)))
                with self.assertRaises(ValueError):
                    enroll(layout, journal, rig.open)
            files_before = {p.name: p.read_bytes() for p in root.iterdir()}
            writes_before = [list(bus.writes) for bus in rig.buses]
            report = inspect_operation(root, rig.open)
            self.assertTrue(report["all_six_consistent_now"])
            self.assertEqual([b.writes for b in rig.buses], writes_before)
            self.assertEqual(files_before, {p.name: p.read_bytes() for p in root.iterdir()})
            self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o700)
            for path in root.iterdir():
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            data = b"".join(files_before.values())
            for bus in rig.buses:
                payload = MCP7940N(bus).read_share().payload
                self.assertNotIn(payload, data)
                self.assertNotIn(payload.hex().encode(), data)
            for event_path in sorted(root.glob("*.event.json")):
                event = json.loads(event_path.read_bytes())
                self.assertNotIn("payload", event)
                self.assertNotIn("secret_hash", event)

    def test_each_write_has_a_synced_intent_before_any_byte(self):
        rig, layout = Rig(), topology()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "op"
            for index, bus in enumerate(rig.buses, 1):
                original = bus.write

                def write(register, data, original=original, index=index):
                    _, summary = load_journal(root)
                    self.assertEqual(summary["state"], "writing")
                    self.assertEqual(summary["uncertain_slots"], [index])
                    return original(register, data)
                bus.write = write
            with OperationJournal(root, layout, source="synthetic_bus") as journal:
                enroll(layout, journal, rig.open)

    def test_every_node_partial_write_failure_preserves_unknown_and_never_retries(self):
        for failed_slot in range(1, 7):
            rig, layout = Rig(), topology()
            def fail(*_):
                raise OSError("SENSITIVE-SENTINEL")
            rig.buses[failed_slot - 1].write = fail
            with tempfile.TemporaryDirectory() as directory, self.subTest(slot=failed_slot):
                root = Path(directory) / "op"
                with OperationJournal(root, layout, source="synthetic_bus") as journal:
                    with self.assertRaises(OSError):
                        enroll(layout, journal, rig.open)
                _, summary = load_journal(root)
                self.assertEqual(summary["verified_slots"], list(range(1, failed_slot)))
                self.assertEqual(summary["uncertain_slots"], [failed_slot])
                self.assertFalse(summary["completion_recorded"])
                before = [list(b.writes) for b in rig.buses]
                report = inspect_operation(root, rig.open)
                self.assertFalse(report["completion_recorded"])
                self.assertEqual(before, [b.writes for b in rig.buses])
                self.assertNotIn(b"SENSITIVE-SENTINEL", b"".join(p.read_bytes() for p in root.iterdir()))

    def test_readback_receipt_failure_leaves_committed_node_uncertain(self):
        rig, layout = Rig(), topology()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "op"
            with OperationJournal(root, layout, source="synthetic_bus") as journal:
                original = journal.append
                def append(event, **fields):
                    if event == "write_verified":
                        raise OSError("full disk")
                    return original(event, **fields)
                journal.append = append
                with self.assertRaises(OSError):
                    enroll(layout, journal, rig.open)
            _, summary = load_journal(root)
            self.assertEqual(summary["uncertain_slots"], [1])
            self.assertEqual(summary["verified_slots"], [])
            self.assertEqual(MCP7940N(rig.buses[0]).read_share().index, 1)
            observed = inspect_operation(root, rig.open)
            self.assertEqual(observed["observations"][0]["status"], "matching_metadata")
            self.assertFalse(observed["completion_recorded"])

    def test_intent_failure_prevents_device_mutation(self):
        rig, layout = Rig(), topology()
        with tempfile.TemporaryDirectory() as directory:
            with OperationJournal(Path(directory) / "op", layout, source="synthetic_bus") as journal:
                original = journal.append
                def append(event, **fields):
                    if event == "write_started":
                        raise OSError("full disk")
                    return original(event, **fields)
                journal.append = append
                with self.assertRaises(OSError):
                    enroll(layout, journal, rig.open)
            self.assertTrue(all(not b.writes for b in rig.buses))

    def test_all_preflight_before_rng_or_mutation_and_existing_journal_refused(self):
        rig, layout = Rig(), topology()
        rig.buses[-1].write(0x20, b"unrecognized")
        before = [list(b.writes) for b in rig.buses]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "op"
            with OperationJournal(root, layout, source="synthetic_bus") as journal:
                with patch("edk.operations.split") as split, self.assertRaises(ValueError):
                    enroll(layout, journal, rig.open)
                split.assert_not_called()
            self.assertEqual(before, [b.writes for b in rig.buses])
            with self.assertRaises(FileExistsError):
                OperationJournal(root, layout, source="synthetic_bus")

    def test_duplicate_adapter_identity_stops_before_writes(self):
        rig, layout = Rig(), topology()
        for bus in rig.buses:
            bus.identity = 1
        with tempfile.TemporaryDirectory() as directory:
            with OperationJournal(Path(directory) / "op", layout, source="synthetic_bus") as journal:
                with self.assertRaises(ValueError):
                    enroll(layout, journal, rig.open)
            self.assertTrue(all(not b.writes for b in rig.buses))

    def test_interruption_is_recorded_and_rethrown(self):
        rig, layout = Rig(), topology()
        rig.buses[0].write = lambda *_: (_ for _ in ()).throw(KeyboardInterrupt())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "op"
            with OperationJournal(root, layout, source="synthetic_bus") as journal:
                with self.assertRaises(KeyboardInterrupt):
                    enroll(layout, journal, rig.open)
            self.assertEqual(json.loads(sorted(root.glob("*.event.json"))[-1].read_bytes())["reason"], "interrupted")

    def test_readonly_inspection_detects_wellformed_payload_corruption(self):
        rig, layout = Rig(), topology()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "op"
            with OperationJournal(root, layout, source="synthetic_bus") as journal:
                enroll(layout, journal, rig.open)
            share = MCP7940N(rig.buses[-1]).read_share()
            forged = Share(share.index, share.generation, bytes([share.payload[0] ^ 1]) + share.payload[1:])
            rig.buses[-1].write(0x20, encode_share(forged))  # Deliberately recomputed CRC.
            self.assertFalse(inspect_operation(root, rig.open)["all_six_consistent_now"])

    def test_malformed_missing_or_broad_permission_journal_rejected(self):
        rig, layout = Rig(), topology()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "missing"
            with self.assertRaises(ValueError):
                load_journal(root)
            self.assertFalse(root.exists())
            with OperationJournal(root, layout, source="synthetic_bus"):
                pass
            event = root / "0000.event.json"
            event.write_bytes(b'{"incomplete":')
            with self.assertRaises(ValueError):
                load_journal(root)
            event.chmod(0o644)
            with self.assertRaises(ValueError):
                load_journal(root)

    def test_replay_rejects_type_errors_extra_fields_gaps_and_illegal_transition(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "op"
            with OperationJournal(root, topology(), source="synthetic_bus"):
                pass
            plan = json.loads((root / "0000.event.json").read_bytes())
            for bad in (None, {}, "string", [None], []):
                with self.subTest(bad=bad), self.assertRaises(ValueError):
                    summarize_events(bad)
            for field, value in (("event", []), ("sequence", True), ("sequence", 2),
                                 ("at", "bad"), ("payload", "SENSITIVE-SENTINEL")):
                wrong = deepcopy(plan)
                wrong[field] = value
                with self.subTest(field=field), self.assertRaises(ValueError):
                    summarize_events([wrong])
            wrong = {k: v for k, v in plan.items() if k in {"schema_version", "operation_id", "sequence", "at", "event"}}
            wrong.update(sequence=1, event="completed", quorums_verified=20)
            with self.assertRaises(ValueError):
                summarize_events([plan, wrong])
            (root / "0002.event.json").write_bytes(encode_document(wrong))
            (root / "0002.event.json").chmod(0o600)
            with self.assertRaises(ValueError):
                load_journal(root)

    def test_library_cannot_rebind_persisted_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            original = topology()
            with OperationJournal(Path(directory) / "op", original, source="synthetic_bus") as journal:
                other = HardwareTopology("OtherLayout", original.nodes)
                journal.topology = other
                rig = Rig()
                with self.assertRaises(ValueError):
                    enroll(other, journal, rig.open)
                self.assertFalse(rig.opens)

    def test_explicit_new_chip_initialization_never_overwrites_damaged_edk_header(self):
        layout, rig = topology(), Rig()
        for bus in rig.buses:
            bus.write(0x20, b"uninitialized".ljust(64, b"x"))
        with tempfile.TemporaryDirectory() as directory:
            with OperationJournal(Path(directory) / "new", layout, source="synthetic_bus",
                                  initialize_unrecognized=True) as journal:
                self.assertTrue(enroll(layout, journal, rig.open)["completion_recorded"])
            rig = Rig()
            rig.buses[-1].write(0x20, b"EDK1" + bytes(60))
            before = [list(b.writes) for b in rig.buses]
            with OperationJournal(Path(directory) / "damaged", layout, source="synthetic_bus",
                                  initialize_unrecognized=True) as journal:
                with self.assertRaises(ValueError):
                    enroll(layout, journal, rig.open)
            self.assertEqual(before, [b.writes for b in rig.buses])

    def test_cli_physical_enrollment_status_and_readonly_inspect(self):
        rig, layout = Rig(), topology()
        with tempfile.TemporaryDirectory() as directory:
            root, config = Path(directory) / "op", Path(directory) / "topology.json"
            config.write_bytes(encode_document(layout.to_dict()))
            with patch("edk.research_cli.sys.platform", "linux"), \
                    patch("edk.linux_i2c.LinuxI2C", side_effect=rig.open), contextlib.redirect_stdout(io.StringIO()) as out:
                main(["hardware-enroll", "--journal", str(root), "--topology", str(config), "--laboratory-hardware"])
                self.assertTrue(json.loads(out.getvalue())["completion_recorded"])
                out.seek(0)
                out.truncate()
                main(["hardware-inspect", "--journal", str(root), "--laboratory-hardware"])
                self.assertTrue(json.loads(out.getvalue())["all_six_consistent_now"])
            with contextlib.redirect_stdout(io.StringIO()) as out:
                main(["operation-status", "--journal", str(root)])
                self.assertTrue(json.loads(out.getvalue())["completion_recorded"])


if __name__ == "__main__":
    unittest.main()
