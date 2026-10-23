"""Private research records. These records are not an enrollment verifier."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import random
import re
from typing import Any, Callable
from uuid import uuid4
import time

from .environment import EnvironmentUnavailable
from .jsonio import identifier, integer, keys
from .manifest import AnchorManifest

OBSERVATION_SCHEMA = "edk.observations/v1"
EVENT_LABELS = ("unknown", "none", "misread", "state_change", "physical_erasure", "history_loss")


@dataclass(frozen=True)
class Reading:
    anchor_id: str
    status: str
    value: int | None = field(repr=False)
    duration_ms: int
    event_label: str = "unknown"

    def __post_init__(self) -> None:
        identifier(self.anchor_id)
        if self.status not in ("normal", "ambiguous", "unreadable"):
            raise ValueError("invalid reading status")
        if self.status == "normal":
            integer(self.value, 0, 65535)
        elif self.value is not None:
            raise ValueError("ambiguous or unreadable observations must have no value")
        integer(self.duration_ms, 0, 86_400_000)
        if self.event_label not in EVENT_LABELS:
            raise ValueError("invalid external event label")

    def to_dict(self) -> dict[str, Any]:
        return {"anchor_id": self.anchor_id, "status": self.status, "value": self.value,
                "duration_ms": self.duration_ms, "event_label": self.event_label}


@dataclass(frozen=True)
class ObservationSession:
    session_id: str
    manifest_fingerprint: str = field(repr=False)
    observer_code: str = field(repr=False)
    started_at: str = field(repr=False)
    readings: tuple[Reading, ...] = field(repr=False)
    source: str = "manual"
    schema_version: str = OBSERVATION_SCHEMA

    def __post_init__(self) -> None:
        if not isinstance(self.session_id, str) or not re.fullmatch(r"[0-9a-f]{32}", self.session_id):
            raise ValueError("invalid session identifier")
        if (not isinstance(self.manifest_fingerprint, str)
                or not re.fullmatch(r"[0-9a-f]{64}", self.manifest_fingerprint)):
            raise ValueError("invalid public manifest fingerprint")
        identifier(self.observer_code)
        if self.source not in ("manual", "synthetic") or self.schema_version != OBSERVATION_SCHEMA:
            raise ValueError("unsupported observation format")
        try:
            stamp = datetime.strptime(self.started_at, "%Y-%m-%dT%H:%M:%S.%fZ")
            if stamp.strftime("%Y-%m-%dT%H:%M:%S.%fZ") != self.started_at:
                raise ValueError
        except (ValueError, TypeError):
            raise ValueError("timestamp must be canonical UTC text") from None
        if type(self.readings) is not tuple or not 1 <= len(self.readings) <= 512:
            raise ValueError("invalid session reading count")
        if any(not isinstance(r, Reading) for r in self.readings):
            raise ValueError("invalid reading object")
        if len({r.anchor_id for r in self.readings}) != len(self.readings):
            raise ValueError("duplicate session anchor")

    def validate_for(self, manifest: AnchorManifest) -> None:
        if self.manifest_fingerprint != manifest.fingerprint:
            raise ValueError("observation belongs to a different public manifest")
        if tuple(r.anchor_id for r in self.readings) != tuple(a.anchor_id for a in manifest.anchors):
            raise ValueError("observation order/count does not match manifest")
        for anchor, reading in zip(manifest.anchors, self.readings):
            if reading.status == "normal" and reading.value >= anchor.state_count:
                raise ValueError("observation outside anchor state range")

    def to_dict(self) -> dict[str, Any]:
        """SECRET serialization. Write only through PrivateStore, never public export."""
        return {"schema_version": self.schema_version, "session_id": self.session_id,
                "manifest_fingerprint": self.manifest_fingerprint, "observer_code": self.observer_code,
                "started_at": self.started_at, "source": self.source,
                "readings": [r.to_dict() for r in self.readings]}

    @classmethod
    def from_dict(cls, value: dict[str, Any], manifest: AnchorManifest) -> "ObservationSession":
        keys(value, {"schema_version", "session_id", "manifest_fingerprint", "observer_code",
                     "started_at", "source", "readings"})
        if type(value["readings"]) is not list or not 1 <= len(value["readings"]) <= 512:
            raise ValueError("invalid readings array")
        readings = []
        for item in value["readings"]:
            keys(item, {"anchor_id", "status", "value", "duration_ms", "event_label"})
            readings.append(Reading(**item))
        params = {k: v for k, v in value.items() if k != "readings"}
        session = cls(**params, readings=tuple(readings))
        session.validate_for(manifest)
        return session


def parse_reading(anchor_id: str, state_count: int, raw: str, duration_ms: int,
                  event_label: str = "unknown") -> Reading:
    integer(state_count, 2, 65536)
    if not isinstance(raw, str):
        raise ValueError("invalid reading input")
    token = raw.strip()
    if token == "?":
        return Reading(anchor_id, "ambiguous", None, duration_ms, event_label)
    if token == "-":
        return Reading(anchor_id, "unreadable", None, duration_ms, event_label)
    if not re.fullmatch(r"[0-9]{1,5}", token):
        raise ValueError("expected an integer, ? or -")
    value = int(token)
    if value >= state_count:
        raise ValueError("reading outside anchor state range")
    return Reading(anchor_id, "normal", value, duration_ms, event_label)


def collect_session(manifest: AnchorManifest, observer_code: str,
                    reader: Callable[[str], str], *, annotate: bool = False,
                    clock_ns: Callable[[], int] = time.monotonic_ns) -> ObservationSession:
    """Reader must hide raw input. Invalid input aborts without a partial record."""
    identifier(observer_code)
    start = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    readings = []
    for anchor in manifest.anchors:
        prompt = (f"{anchor.anchor_id} ({anchor.location_hint}) | {anchor.reading_rule}\n"
                  f"0..{anchor.state_count - 1}, ? ambiguous, - unreadable: ")
        before = clock_ns()
        raw = reader(prompt)
        elapsed = (clock_ns() - before) // 1_000_000
        event = reader("External event label (blank = unknown): ").strip() if annotate else "unknown"
        readings.append(parse_reading(anchor.anchor_id, anchor.state_count, raw, elapsed, event or "unknown"))
    session = ObservationSession(uuid4().hex, manifest.fingerprint, observer_code, start, tuple(readings))
    session.validate_for(manifest)
    return session


def exact_observation_bytes(manifest: AnchorManifest, session: ObservationSession) -> bytes:
    """Exact-input encoding used by the manifest-bound concept profile."""
    session.validate_for(manifest)
    if any(r.status != "normal" for r in session.readings):
        raise EnvironmentUnavailable("ambiguous or missing observation; stop")
    return (b"EDK-OBS/v1\x00" + bytes.fromhex(manifest.fingerprint)
            + len(session.readings).to_bytes(2, "big")
            + b"".join(r.value.to_bytes(2, "big") for r in session.readings))


def synthetic_sessions(manifest: AnchorManifest, *, count: int = 30,
                       seed: int = 2026) -> tuple[ObservationSession, ...]:
    """Deterministic teaching data; the baseline here is never a real secret."""
    integer(count, 2, 1000)
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    rng = random.Random(seed)
    baseline = [rng.randrange(a.state_count) for a in manifest.anchors]
    sessions = []
    for index in range(count):
        group_error = rng.random() < 0.12 if index else False
        readings = []
        for pos, anchor in enumerate(manifest.anchors):
            value, status, event = baseline[pos], "normal", "none"
            sample = rng.random() if index else 1.0
            if sample < 0.04:
                value, status, event = None, "ambiguous", "unknown"
            elif sample < 0.08:
                value, status, event = None, "unreadable", "physical_erasure"
            elif sample < 0.14 or (group_error and pos % 2 == 0):
                value = (value + 1) % anchor.state_count
                event = "misread"
            elif sample < 0.18:
                value = (value + 1) % anchor.state_count
                event = "state_change"
            readings.append(Reading(anchor.anchor_id, status, value, rng.randrange(500, 8001), event))
        stamp = (datetime(2000, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=index))
        sessions.append(ObservationSession(f"{rng.getrandbits(128):032x}", manifest.fingerprint,
                                           "synthetic-observer", stamp.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                                           tuple(readings), "synthetic"))
    return tuple(sessions)
