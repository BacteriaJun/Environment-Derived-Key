"""Durable, metadata-only enrollment journal and read-only reconciliation.

An intent is synced before every device write. Missing readback receipts mean
unknown, never safe-to-retry. No journal contains KV, share payloads or their
hashes. This does not provide distributed atomicity or authenticated hardware.
"""

from __future__ import annotations

from contextlib import ExitStack, suppress
from datetime import datetime, timezone
import hmac
from itertools import combinations
import os
from pathlib import Path
import re
import secrets
from typing import Any, Callable, Sequence

from . import __version__
from .deployment import HardwareTopology
from .jsonio import decode_document, encode_document, integer, keys
from .private_store import PrivateStore
from .shamir import Share, recover, split
from .sram import MCP7940N

JOURNAL_SCHEMA = "edk.enrollment-event/v1"
SOURCES = ("physical_io", "synthetic_bus")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _stamp(value: Any) -> None:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
        if parsed.strftime("%Y-%m-%dT%H:%M:%S.%fZ") != value:
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError("invalid event time") from None


class OperationJournal:
    """New directory per operation; append-only records, no write-resume API.

    PrivateStore enforces POSIX ownership/modes and syncs each file + directory.
    A crash may leave a truncated final record; a reader rejects that journal.
    Local filesystem/hardware fsync semantics are assumed, not certified.
    """

    def __init__(self, root: str | Path, topology: HardwareTopology, *, source: str,
                 allow_colocated_quorum: bool = False, initialize_unrecognized: bool = False) -> None:
        if not isinstance(topology, HardwareTopology) or source not in SOURCES:
            raise ValueError("typed topology and explicit operation source required")
        if type(allow_colocated_quorum) is not bool or type(initialize_unrecognized) is not bool:
            raise ValueError("enrollment options must be boolean")
        if topology.colocated_quorum and not allow_colocated_quorum:
            raise ValueError("one failure domain contains a quorum")
        self.root = Path(root)
        self.root.mkdir(mode=0o700)  # Must be NEW, including before any adapter opens.
        parent_fd = os.open(self.root.absolute().parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent_fd)  # Persist the new operation directory's name as well.
        finally:
            os.close(parent_fd)
        self._store = PrivateStore(self.root)
        self.operation_id = secrets.token_hex(16)
        self.topology = topology
        self.source = source
        self._events: list[dict[str, Any]] = []
        try:
            self.append("planned", topology=topology.to_dict(), source=source,
                        software_version=__version__, allow_colocated_quorum=allow_colocated_quorum,
                        initialize_unrecognized=initialize_unrecognized)
        except BaseException:
            self.close()
            raise

    def __enter__(self) -> "OperationJournal":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def close(self) -> None:
        self._store.close()

    def append(self, event: str, **fields: Any) -> None:
        entry = {"schema_version": JOURNAL_SCHEMA, "operation_id": self.operation_id,
                 "sequence": len(self._events), "at": _now(), "event": event, **fields}
        candidate = [*self._events, entry]
        summarize_events(candidate)  # Strict transition validation, including no secret fields.
        self._store._write_new(f"{len(self._events):04d}.event.json", encode_document(entry))
        self._events.append(entry)

    def summary(self) -> dict[str, Any]:
        return summarize_events(self._events)


def summarize_events(events: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if (not isinstance(events, Sequence) or isinstance(events, (str, bytes, bytearray))
            or not 1 <= len(events) <= 32):
        raise ValueError("invalid journal event count")
    operation_id = events[0].get("operation_id") if type(events[0]) is dict else None
    if not isinstance(operation_id, str) or not re.fullmatch(r"[0-9a-f]{32}", operation_id):
        raise ValueError("invalid operation identifier")
    state, generation, topology, source = "new", None, None, None
    verified: list[int] = []
    pending = None
    common = {"schema_version", "operation_id", "sequence", "at", "event"}
    last_stamp = ""
    for sequence, event in enumerate(events):
        if type(event) is not dict:
            raise ValueError("invalid event")
        kind = event.get("event")
        if not isinstance(kind, str):
            raise ValueError("invalid event kind")
        extra = {"planned": {"topology", "source", "software_version", "allow_colocated_quorum", "initialize_unrecognized"},
                 "preflight_ok": set(), "generation_created": {"generation"},
                 "write_started": {"slot"}, "write_verified": {"slot"},
                 "completed": {"quorums_verified"}, "stopped": {"reason"}}.get(kind)
        if extra is None:
            raise ValueError("unsupported enrollment event")
        keys(event, common | extra)
        integer(event["sequence"], 0, 31)
        if (event["schema_version"] != JOURNAL_SCHEMA or event["operation_id"] != operation_id
                or event["sequence"] != sequence or state in ("completed", "stopped")):
            raise ValueError("invalid event sequence")
        _stamp(event["at"])
        # Wall-clock movement does not reorder the durable sequence.
        last_stamp = event["at"]
        if kind == "planned":
            if sequence != 0 or state != "new":
                raise ValueError("plan must be first")
            topology = HardwareTopology.from_dict(event["topology"])
            source = event["source"]
            if (source not in SOURCES or type(event["allow_colocated_quorum"]) is not bool
                    or type(event["initialize_unrecognized"]) is not bool
                    or (topology.colocated_quorum and not event["allow_colocated_quorum"])
                    or not isinstance(event["software_version"], str)
                    or not re.fullmatch(r"[0-9][0-9A-Za-z.+!-]{0,63}", event["software_version"])):
                raise ValueError("invalid enrollment plan")
            state = "planned"
        elif kind == "preflight_ok":
            if state != "planned":
                raise ValueError("invalid preflight transition")
            state = "preflight_ok"
        elif kind == "generation_created":
            if (state != "preflight_ok" or not isinstance(event["generation"], str)
                    or not re.fullmatch(r"[0-9a-f]{32}", event["generation"])):
                raise ValueError("invalid generation transition")
            generation, state = event["generation"], "ready"
        elif kind == "write_started":
            integer(event["slot"], 1, 6)
            if state not in ("ready", "verified") or event["slot"] != len(verified) + 1:
                raise ValueError("invalid write intent")
            pending, state = event["slot"], "writing"
        elif kind == "write_verified":
            integer(event["slot"], 1, 6)
            if state != "writing" or event["slot"] != pending:
                raise ValueError("missing write intent")
            verified.append(pending)
            pending, state = None, "verified"
        elif kind == "completed":
            if (state != "verified" or len(verified) != 6
                    or type(event["quorums_verified"]) is not int or event["quorums_verified"] != 20):
                raise ValueError("invalid completion")
            state = "completed"
        else:
            if sequence == 0 or event["reason"] not in ("io_error", "invalid_state", "interrupted", "internal_error"):
                raise ValueError("invalid stop event")
            state = "stopped"
    if topology is None:
        raise ValueError("journal has no plan")
    return {"schema_version": "edk.enrollment-summary/v1", "operation_id": operation_id,
            "source": source, "topology_fingerprint": topology.fingerprint,
            "generation": generation, "state": state, "last_event_at": last_stamp,
            "verified_slots": verified, "uncertain_slots": [] if pending is None else [pending],
            "not_started_slots": [n for n in range(1, 7) if n not in verified and n != pending],
            "completion_recorded": state == "completed", "automatic_resume_allowed": False,
            "initialize_unrecognized": events[0]["initialize_unrecognized"],
            "interpretation": "Local unauthenticated receipts; no secret backup, hardware attestation or PIN enrollment."}


def load_journal(root: str | Path) -> tuple[HardwareTopology, dict[str, Any]]:
    # PrivateStore normally creates roots. Inspection must never create a missing operation.
    if not Path(root).is_dir():
        raise ValueError("operation directory missing")
    with PrivateStore(root, create=False) as store:
        names = sorted(n for n in os.listdir(store._fd) if n != ".gitignore")
        if (not 1 <= len(names) <= 32
                or names != [f"{i:04d}.event.json" for i in range(len(names))]):
            raise ValueError("incomplete or unexpected journal records")
        events = [decode_document(store._read(name)) for name in names]
    summary = summarize_events(events)
    return HardwareTopology.from_dict(events[0]["topology"]), summary


def _consistent(shares: Sequence[Share], expected: bytes | None = None) -> int:
    """Compare only in RAM; no persisted secret hash or derived verifier."""
    if len(shares) != 6 or [s.index for s in shares] != list(range(1, 7)):
        raise ValueError("six ordered shares required")
    base = recover(shares)
    if expected is not None and not hmac.compare_digest(base, expected):
        raise ValueError("readback secret mismatch")
    for quorum in combinations(shares, 3):
        if not hmac.compare_digest(recover(quorum), base):
            raise ValueError("inconsistent readback quorum")
    return 20


def enroll(topology: HardwareTopology, journal: OperationJournal, opener: Callable[[str], Any]) -> dict[str, Any]:
    """New enrollment only, one writer thread. Never retry, refresh or rollback."""
    planned = journal.summary()
    if (journal.topology != topology or planned["state"] != "planned"
            or planned["topology_fingerprint"] != topology.fingerprint):
        raise ValueError("new matching operation required")
    try:
        with ExitStack() as stack:
            devices = [MCP7940N(stack.enter_context(opener(n.adapter))) for n in topology.nodes]
            if len({getattr(d.bus, "identity", id(d.bus)) for d in devices}) != 6:
                raise ValueError("duplicate device identity")
            # No backup/control mutation; initialization policy is fixed in the plan.
            for device in devices:
                device.check_available(initialize_unrecognized=planned["initialize_unrecognized"])
            journal.append("preflight_ok")
            secret = secrets.token_bytes(32)
            shares = split(secret)
            journal.append("generation_created", generation=shares[0].generation.hex())
            for device, share in zip(devices, shares):
                journal.append("write_started", slot=share.index)
                device.write_share(share, initialize_unrecognized=planned["initialize_unrecognized"])
                journal.append("write_verified", slot=share.index)
            readback = [device.read_share() for device in devices]
            if readback != shares:
                raise ValueError("final node readback mismatch")
            journal.append("completed", quorums_verified=_consistent(readback, secret))
    except BaseException as error:
        reason = ("interrupted" if isinstance(error, KeyboardInterrupt) else
                  "io_error" if isinstance(error, OSError) else
                  "invalid_state" if isinstance(error, ValueError) else "internal_error")
        # The prior synced intent is authoritative even if recording the stop fails.
        with suppress(Exception):
            journal.append("stopped", reason=reason)
        raise
    return journal.summary()


def inspect_operation(root: str | Path, opener: Callable[[str], Any]) -> dict[str, Any]:
    """Observe current slots without control/SRAM writes or journal mutation.

    Read transactions write a register pointer. Current observations cannot turn
    an interrupted enrollment into a completed one or revoke copied shares.
    """
    topology, summary = load_journal(root)
    observed, shares = [], []
    with ExitStack() as stack:
        identities = set()
        for slot in topology.nodes:
            try:
                bus = stack.enter_context(opener(slot.adapter))
                identity = getattr(bus, "identity", id(bus))
                if identity in identities:
                    raise ValueError("duplicate device identity")
                identities.add(identity)
                share = MCP7940N(bus).read_share()
                matches = (share.index == slot.index and share.threshold == 3
                           and share.generation.hex() == summary["generation"])
                observed.append({"slot": slot.index, "status": "matching_metadata" if matches else "different_metadata"})
                if matches:
                    shares.append(share)
            except (ValueError, RuntimeError, OSError):
                observed.append({"slot": slot.index, "status": "unavailable_or_invalid"})
        consistent = False
        if len(shares) == 6:
            try:
                consistent = _consistent(shares) == 20
            except ValueError:
                pass
    return {**summary, "observations": observed, "all_six_consistent_now": consistent,
            "device_data_or_control_writes_performed": False,
            "interpretation": "Read-only current consistency; no authentication, historical completion, repair or PIN release."}
