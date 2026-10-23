"""Observation studies and laboratory SRAM operations; no real PIN recovery."""

from __future__ import annotations

import argparse
from contextlib import ExitStack
from dataclasses import replace
import getpass
import json
from pathlib import Path
import sys
import warnings

from .analysis import export_aggregate
from .bench import BenchToken, check_test, doctor_report, prepare_test
from .bench_acceptance import analyze_bench_reports, load_bench_report
from .concept import run_concept
from .deployment import HardwareTopology
from .formal_models import verify_models
from .jsonio import integer
from .lifecycle import DEFAULT_NODES, LifecycleConfig, lifecycle_report
from .manifest import load_manifest
from .observations import collect_session, synthetic_sessions
from .operations import OperationJournal, enroll, inspect_operation, load_journal
from .private_store import PrivateStore, write_new_aggregate
from .shamir import recover
from .sram import MCP7940N, MemoryRegisterBus, provision_six, repair_hardware_node
from .study_protocol import StudyPolicy, analyze_study


def _store_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--store", type=Path, default=Path(".edk-private"),
                        help="owner-only local study directory (default: .edk-private)")


def _check(args: argparse.Namespace) -> None:
    manifest = load_manifest(args.manifest)
    print(f"Valid public manifest: {len(manifest.anchors)} ordered anchors; {manifest.schema_version}")
    print(f"Public definition fingerprint: {manifest.fingerprint}")


def _collect(args: argparse.Namespace) -> None:
    manifest = load_manifest(args.manifest)
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise ValueError("manual collection requires an interactive, non-echo terminal")
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        session = collect_session(manifest, args.observer, getpass.getpass, annotate=args.annotate)
    with PrivateStore(args.store) as store:
        store.save(manifest, session)
    print(f"Private session saved: {session.session_id}; raw states are not displayed.")


def _sessions(args: argparse.Namespace) -> None:
    with PrivateStore(args.store) as store:
        for session_id in store.session_ids():
            print(session_id)


def _synthetic(args: argparse.Namespace) -> None:
    manifest = load_manifest(args.manifest)
    sessions = synthetic_sessions(manifest, count=args.count, seed=args.seed)
    with PrivateStore(args.store) as store:
        # Preflight existing IDs so a repeat seed fails before any new records.
        if set(store.session_ids()) & {s.session_id for s in sessions}:
            raise ValueError("synthetic session IDs already exist; use a separate private store")
        for session in sessions:
            store.save(manifest, session)
    print(f"Saved {len(sessions)} SYNTHETIC sessions; not physical measurements.")


def _analyze(args: argparse.Namespace) -> None:
    manifest = load_manifest(args.manifest)
    with PrivateStore(args.store) as store:
        ids = args.sessions if args.sessions is not None else store.session_ids()
        integer(len(ids), 5, 1000)
        sessions = tuple(store.load(manifest, session_id) for session_id in ids)
    report = export_aggregate(manifest, sessions, args.output)
    print(f"Aggregate report saved: {report['sessions']} sessions; no raw states or identifiers exported.")


def _study_accept(args: argparse.Namespace) -> None:
    manifest = load_manifest(args.manifest)
    policy = StudyPolicy.load(args.policy)
    if len(manifest.anchors) < 3 or policy.manifest_fingerprint != manifest.fingerprint:
        raise ValueError("study export needs three anchors and a matching policy")
    with PrivateStore(args.store, create=False) as store:
        ids = args.sessions if args.sessions is not None else store.session_ids()
        integer(len(ids), 5, 1000)
        sessions = tuple(store.load(manifest, session_id) for session_id in ids)
    report = analyze_study(manifest, sessions, policy)
    write_new_aggregate(args.output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["study_quality_criteria_passed"]:
        raise SystemExit(3)


def _lifecycle(args: argparse.Namespace) -> None:
    nodes = tuple(replace(n, stress_multiplier=args.vehicle_stress) if n.node_id == "S4" else n
                  for n in DEFAULT_NODES)
    config = LifecycleConfig(anchors=args.anchors, nodes=nodes,
                             location_hazards=(("home", args.home_hazard), ("vehicle", 0.02)),
                             maintenance_interval=args.maintenance_every,
                             maintenance_stop_after=args.maintenance_stop_after)
    report = lifecycle_report(config, months=args.months, trials=args.trials, seed=args.seed)
    write_new_aggregate(args.output, report)
    print("SYNTHETIC lifecycle report saved; no measured device lifetime or attacker success claim.")


def _model_check(_: argparse.Namespace) -> None:
    print(json.dumps(verify_models(), indent=2, sort_keys=True))


def _concept_run(args: argparse.Namespace) -> None:
    report = run_concept(args.seed)
    if args.output is not None:
        write_new_aggregate(args.output, report)
    print(json.dumps(report, indent=2, sort_keys=True))


def _hardware_demo(_: argparse.Namespace) -> None:
    devices = [MCP7940N(MemoryRegisterBus()) for _ in range(6)]
    summary = provision_six(devices)
    original = devices[4].read_share()
    devices[4].bus.expire()
    replacement = MCP7940N(MemoryRegisterBus())
    repair_hardware_node(devices[:3], replacement, missing_index=5)
    if replacement.read_share() != original:
        raise RuntimeError("synthetic SRAM repair mismatch")
    devices[4] = replacement
    if recover([d.read_share() for d in devices[:3]]) != recover([d.read_share() for d in devices[3:]]):
        raise RuntimeError("synthetic SRAM quorum mismatch")
    print(f"SIMULATED SRAM: {summary['committed_nodes']} records written/read back; repair verified. No physical I/O.")


def _bench_doctor(args: argparse.Namespace) -> None:
    report = doctor_report(args.bus)
    if args.check_abi:
        from .native_abi import check_native_abi
        report["native_abi"] = check_native_abi()
    if args.output is not None:
        write_new_aggregate(args.output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.require_ready:
        abi = report.get("native_abi", {})
        if not report["host_preflight_passed"] or not abi.get("checked") or not abi.get("matches"):
            raise SystemExit(3)


def _bench_accept(args: argparse.Namespace) -> None:
    # Bound argument count before opening any input documents.
    integer(len(args.reports), 1, 1000)
    report = analyze_bench_reports([load_bench_report(p) for p in args.reports],
                                  minimum_trials=args.minimum_trials,
                                  minimum_vcc_off_seconds=args.minimum_vcc_off_seconds)
    write_new_aggregate(args.output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["acceptance_criteria_passed"]:
        raise SystemExit(3)


def _topology_check(args: argparse.Namespace) -> None:
    topology = HardwareTopology.load(args.topology)
    report = {"schema_version": "edk.topology-check/v1", "nodes": 6, "threshold": 3,
              "topology_fingerprint": topology.fingerprint, "colocated_quorum": topology.colocated_quorum,
              "device_transactions_performed": False,
              "interpretation": "Operator-declared adapter and failure-domain mapping; no hardware identity attestation."}
    print(json.dumps(report, indent=2, sort_keys=True))
    if topology.colocated_quorum:
        raise SystemExit(3)


def _operation_status(args: argparse.Namespace) -> None:
    _, summary = load_journal(args.journal)
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not summary["completion_recorded"]:
        raise SystemExit(3)


def _engineering_physical(args: argparse.Namespace) -> None:
    from .linux_i2c import LinuxI2C
    if not args.laboratory_hardware or sys.platform != "linux":
        raise ValueError("engineering hardware operations require Linux and laboratory hardware")
    if args.command == "hardware-enroll":
        topology = HardwareTopology.load(args.topology)
        # The durable plan must exist before any adapter is opened.
        with OperationJournal(args.journal, topology, source="physical_io",
                              allow_colocated_quorum=args.allow_colocated_quorum,
                              initialize_unrecognized=args.initialize_unrecognized) as journal:
            summary = enroll(topology, journal, LinuxI2C)
    else:
        _, previous = load_journal(args.journal)
        if previous["source"] != "physical_io":
            raise ValueError("a physical operation journal is required")
        summary = inspect_operation(args.journal, LinuxI2C)
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not summary["completion_recorded"] or summary.get("all_six_consistent_now") is False:
        raise SystemExit(3)


def _bench_demo(_: argparse.Namespace) -> None:
    token = BenchToken.create()
    bus = MemoryRegisterBus()
    device = MCP7940N(bus)
    prepare_test(device, token)
    bus.record_power_failure()
    before = len(bus.writes)
    retained = check_test(device, token, source="synthetic_bus")
    if not retained["matches_public_pattern"] or len(bus.writes) != before:
        raise RuntimeError("synthetic retention read failed")
    bus.expire()
    lost = check_test(device, token, source="synthetic_bus")
    if lost["matches_public_pattern"]:
        raise RuntimeError("synthetic state loss was not observed")
    print("SIMULATED public-pattern bench: retention/loss observations verified; no physical I/O or PIN.")


def _bench_physical(args: argparse.Namespace) -> None:
    from .linux_i2c import LinuxI2C
    if not args.laboratory_hardware or sys.platform != "linux":
        raise ValueError("physical bench requires Linux and --laboratory-hardware")
    if args.command == "bench-prepare":
        token = BenchToken.create()
        # Reserve a new PUBLIC expected-pattern token before any device action.
        # This file is a plan, not proof that preparation succeeded.
        write_new_aggregate(args.token, token.to_dict())
    else:
        token = BenchToken.load(args.token)
        if args.vcc_off_seconds is not None:
            from .simulation import _nonnegative_finite
            _nonnegative_finite(args.vcc_off_seconds, "operator duration")
    with LinuxI2C(args.bus) as bus:
        device = MCP7940N(bus)
        if args.command == "bench-prepare":
            if args.enable_backup:
                device.enable_backup()
            prepare_test(device, token, initialize_unrecognized=args.initialize_unrecognized)
            print("Public test pattern committed and read back. No key or PIN enrolled.")
        else:
            report = check_test(device, token, source="physical_io", operator_vcc_off_seconds=args.vcc_off_seconds)
            write_new_aggregate(args.report, report)
            print(json.dumps(report, indent=2, sort_keys=True))
            if not report["matches_public_pattern"] or report["status_changed_during_read"]:
                raise SystemExit(3)


def _physical(args: argparse.Namespace) -> None:
    from .linux_i2c import LinuxI2C
    if not args.laboratory_hardware:
        raise ValueError("physical operations require the --laboratory-hardware option")
    paths = args.buses if args.command == "hardware-provision" else (
        [*args.sources, args.target] if args.command == "hardware-repair" else [args.bus])
    if len(set(paths)) != len(paths):
        raise ValueError("duplicate adapter path")
    if args.command == "hardware-repair":
        integer(args.index, 1, 6)
    with ExitStack() as stack:
        devices = [MCP7940N(stack.enter_context(LinuxI2C(path))) for path in paths]
        if len({device.bus.identity for device in devices}) != len(devices):
            raise ValueError("duplicate adapter identity")
        if args.command == "hardware-probe":
            print(json.dumps(devices[0].status(), sort_keys=True))
            return
        if args.enable_backup:
            for device in devices:
                device.enable_backup()
        if args.command == "hardware-provision":
            result = provision_six(devices, initialize_unrecognized=args.initialize_unrecognized)
            print(json.dumps(result, sort_keys=True))
        else:
            repair_hardware_node(devices[:3], devices[3], missing_index=args.index,
                                 initialize_unrecognized=args.initialize_unrecognized)
            print("Replacement share committed and read back. No PIN derived.")


def add_research_commands(sub: argparse._SubParsersAction) -> None:
    concept = sub.add_parser("concept-run", help="execute the exact-input concept algorithm with synthetic observations")
    concept.add_argument("--seed", type=int, default=2026)
    concept.add_argument("--output", type=Path, help="optional new public execution report")
    concept.set_defaults(handler=_concept_run)
    check = sub.add_parser("manifest-check", help="strictly validate PUBLIC anchor definitions")
    check.add_argument("manifest", type=Path)
    check.set_defaults(handler=_check)
    collect = sub.add_parser("collect", help="non-echo manual research collection; no PIN derivation")
    collect.add_argument("manifest", type=Path)
    collect.add_argument("--observer", default="observer-1", help="private pseudonym, not a name/address")
    collect.add_argument("--annotate", action="store_true", help="record externally supplied event labels")
    _store_args(collect)
    collect.set_defaults(handler=_collect)
    sessions = sub.add_parser("sessions", help="list private session IDs only")
    _store_args(sessions)
    sessions.set_defaults(handler=_sessions)
    synthetic = sub.add_parser("synthetic-study", help="generate reproducible synthetic observation data")
    synthetic.add_argument("manifest", type=Path)
    synthetic.add_argument("--count", type=int, default=30)
    synthetic.add_argument("--seed", type=int, default=2026)
    _store_args(synthetic)
    synthetic.set_defaults(handler=_synthetic)
    analyze = sub.add_parser("analyze", help="export anonymous aggregate statistics, never raw readings")
    analyze.add_argument("manifest", type=Path)
    analyze.add_argument("--sessions", nargs="+", help="private IDs; defaults to all sessions in store")
    analyze.add_argument("--output", type=Path, required=True, help="new aggregate file; never overwrite")
    _store_args(analyze)
    analyze.set_defaults(handler=_analyze)
    study = sub.add_parser("study-accept", help="evaluate declared environment study quality; never entropy certification")
    study.add_argument("manifest", type=Path)
    study.add_argument("--policy", type=Path, required=True)
    study.add_argument("--sessions", nargs="+")
    study.add_argument("--output", type=Path, required=True)
    _store_args(study)
    study.set_defaults(handler=_study_accept)
    lifecycle = sub.add_parser("simulate-lifecycle", help="synthetic correlated failure and maintenance trajectories")
    for name, default in (("months", 36), ("trials", 1000), ("seed", 2026), ("anchors", 8)):
        lifecycle.add_argument("--" + name, type=int, default=default)
    lifecycle.add_argument("--maintenance-every", type=int)
    lifecycle.add_argument("--maintenance-stop-after", type=int)
    lifecycle.add_argument("--vehicle-stress", type=float, default=2.0)
    lifecycle.add_argument("--home-hazard", type=float, default=0.01)
    lifecycle.add_argument("--output", type=Path, required=True)
    lifecycle.set_defaults(handler=_lifecycle)
    models = sub.add_parser("verify-models", help="exhaust declared finite models; not a physical security proof")
    models.set_defaults(handler=_model_check)
    hardware = sub.add_parser("hardware-demo", help="test the SRAM writer on synthetic in-memory chips")
    hardware.set_defaults(handler=_hardware_demo)
    doctor = sub.add_parser("bench-doctor", help="host metadata checks; no adapter opens or I2C transactions")
    doctor.add_argument("--bus", default="/dev/i2c-1")
    doctor.add_argument("--check-abi", action="store_true", help="compile Linux UAPI layout probe; no device I/O")
    doctor.add_argument("--require-ready", action="store_true", help="exit 3 unless host and requested ABI checks pass")
    doctor.add_argument("--output", type=Path)
    doctor.set_defaults(handler=_bench_doctor)
    bench_demo = sub.add_parser("bench-demo", help="synthetic public-pattern retention/loss workflow")
    bench_demo.set_defaults(handler=_bench_demo)
    accept = sub.add_parser("bench-accept", help="strict aggregate criteria for public bench observations")
    accept.add_argument("reports", nargs="+", type=Path)
    accept.add_argument("--minimum-trials", type=int, default=5)
    accept.add_argument("--minimum-vcc-off-seconds", type=float, default=0)
    accept.add_argument("--output", type=Path, required=True)
    accept.set_defaults(handler=_bench_accept)
    topology = sub.add_parser("topology-check", help="validate local six-slot wiring declarations without I/O")
    topology.add_argument("topology", type=Path)
    topology.set_defaults(handler=_topology_check)
    status = sub.add_parser("operation-status", help="read durable operation receipts without hardware I/O")
    status.add_argument("--journal", type=Path, required=True)
    status.set_defaults(handler=_operation_status)
    for command in ("hardware-enroll", "hardware-inspect"):
        operation = sub.add_parser(command, help="journaled Linux laboratory enrollment or read-only inspection")
        operation.add_argument("--journal", type=Path, required=True, help="owner-only operation directory; new for enroll")
        operation.add_argument("--laboratory-hardware", action="store_true")
        if command == "hardware-enroll":
            operation.add_argument("--topology", type=Path, required=True)
            operation.add_argument("--allow-colocated-quorum", action="store_true",
                                   help="explicitly accept a declared shared-domain quorum risk")
            operation.add_argument("--initialize-unrecognized", action="store_true",
                                   help="initialize verified new hardware with unknown SRAM; never overwrite an EDK1 header")
        operation.set_defaults(handler=_engineering_physical)
    for command in ("bench-prepare", "bench-check"):
        bench = sub.add_parser(command, help="single-node public-pattern bench; never real-key recovery")
        bench.add_argument("--bus", required=True)
        bench.add_argument("--token", type=Path, required=True, help="PUBLIC expected-pattern JSON, not secret shares")
        bench.add_argument("--laboratory-hardware", action="store_true")
        if command == "bench-prepare":
            bench.add_argument("--enable-backup", action="store_true")
            bench.add_argument("--initialize-unrecognized", action="store_true")
        else:
            bench.add_argument("--report", type=Path, required=True)
            bench.add_argument("--vcc-off-seconds", type=float,
                               help="operator-supplied measured duration; no duration is inferred by software")
        bench.set_defaults(handler=_bench_physical)
    for command in ("hardware-probe", "hardware-provision", "hardware-repair"):
        physical = sub.add_parser(command, help="Linux laboratory MCP7940N operation; no PIN recovery")
        physical.add_argument("--laboratory-hardware", action="store_true")
        if command == "hardware-probe":
            physical.add_argument("--bus", required=True)
        else:
            physical.add_argument("--enable-backup", action="store_true")
            physical.add_argument("--initialize-unrecognized", action="store_true",
                                  help="allow replacing an unrecognized image, never an EDK1 share header")
            if command == "hardware-provision":
                physical.add_argument("--buses", nargs=6, required=True, help="six distinct adapters, one laboratory node each")
            else:
                physical.add_argument("--sources", nargs=3, required=True)
                physical.add_argument("--target", required=True)
                physical.add_argument("--index", type=int, required=True)
        physical.set_defaults(handler=_physical)
