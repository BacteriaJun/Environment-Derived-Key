"""EDK exact-input concept profile: observations, threshold recovery and HKDF."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
import hashlib
from itertools import combinations
from pathlib import Path
import re
from typing import Any, Callable

from . import __version__
from .derivation import derive_pin
from .environment import AnchorDefinition
from .jsonio import integer, keys, read_document, text
from .manifest import AnchorManifest
from .observations import ObservationSession, Reading, exact_observation_bytes
from .shamir import Share, recover, repair_share, split

PROFILE = "edk.exact-input/v1"
CONTEXT_SCHEMA = "edk.concept-context/v1"


@dataclass(frozen=True)
class ConceptContext:
    """Public parameters retained with the registered public manifest."""

    manifest_fingerprint: str
    salt: bytes
    device_id: str
    profile: str = PROFILE
    schema_version: str = CONTEXT_SCHEMA

    def __post_init__(self) -> None:
        if self.profile != PROFILE or self.schema_version != CONTEXT_SCHEMA:
            raise ValueError("unsupported concept context")
        if (not isinstance(self.manifest_fingerprint, str)
                or not re.fullmatch(r"[0-9a-f]{64}", self.manifest_fingerprint)):
            raise ValueError("invalid public manifest fingerprint")
        if not isinstance(self.salt, bytes) or len(self.salt) != 32:
            raise ValueError("public salt must be 32 bytes")
        text(self.device_id, 255)
        if len(self.device_id.encode("utf-8")) > 255:
            raise ValueError("device context exceeds UTF-8 limit")

    def to_dict(self) -> dict[str, str]:
        return {"schema_version": self.schema_version, "profile": self.profile,
                "manifest_fingerprint": self.manifest_fingerprint, "salt_hex": self.salt.hex(),
                "device_id": self.device_id}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ConceptContext":
        keys(value, {"schema_version", "profile", "manifest_fingerprint", "salt_hex", "device_id"})
        if not isinstance(value["salt_hex"], str) or not re.fullmatch(r"[0-9a-f]{64}", value["salt_hex"]):
            raise ValueError("invalid public salt encoding")
        return cls(value["manifest_fingerprint"], bytes.fromhex(value["salt_hex"]), value["device_id"],
                   value["profile"], value["schema_version"])

    @classmethod
    def load(cls, path: str | Path) -> "ConceptContext":
        return cls.from_dict(read_document(path))


def derive_observation_pin(manifest: AnchorManifest, session: ObservationSession,
                           shares: Sequence[Share], context: ConceptContext) -> str:
    """Evaluate the exact-input reference algorithm entirely in memory.

    The environment encoding binds the complete public manifest and ordered
    normal observations. Readings are neither corrected nor authenticated here.
    The inherited KDF/PIN mapping is used without modifying its domain bytes.
    """
    if (not isinstance(manifest, AnchorManifest) or not isinstance(session, ObservationSession)
            or not isinstance(context, ConceptContext)):
        raise ValueError("validated concept inputs required")
    if manifest.fingerprint != context.manifest_fingerprint:
        raise ValueError("context belongs to another manifest")
    environment = exact_observation_bytes(manifest, session)
    if (not isinstance(shares, Sequence) or isinstance(shares, (str, bytes, bytearray))
            or not 3 <= len(shares) <= 6
            or any(not isinstance(s, Share) or not 1 <= s.index <= 6 for s in shares)):
        raise ValueError("three to six EDK node shares required")
    volatile_secret = recover(shares, threshold=3)
    return derive_pin(environment, volatile_secret, salt=context.salt, device_id=context.device_id)


def concept_fixture(seed: int) -> tuple[AnchorManifest, ObservationSession, bytes, ConceptContext]:
    """Public deterministic inputs for examples and known-answer vectors."""
    integer(seed, -(2**63), 2**63 - 1)
    prefix = b"EDK-PUBLIC-CONCEPT-FIXTURE/v1\x00" + seed.to_bytes(8, "big", signed=True)

    def material(label: bytes) -> bytes:
        return hashlib.sha256(prefix + label).digest()

    counts = (2, 3, 8, 16, 64, 256)
    manifest = AnchorManifest("concept-reference", tuple(
        AnchorDefinition(f"A{i}", "synthetic object", "Read the synthetic symbol.", state_count=count)
        for i, count in enumerate(counts)))
    readings = tuple(Reading(a.anchor_id, "normal", int.from_bytes(material(a.anchor_id.encode()), "big")
                             % a.state_count, 1000, "none") for a in manifest.anchors)
    session = ObservationSession(material(b"session")[:16].hex(), manifest.fingerprint, "synthetic-observer",
                                 "2000-01-01T00:00:00.000000Z", readings, "synthetic")
    return manifest, session, material(b"volatile"), ConceptContext(
        manifest.fingerprint, material(b"salt"), "concept-device")


def run_concept(seed: int = 2026) -> dict[str, Any]:
    """Exercise the complete concept profile and emit only public check results."""
    manifest, session, secret, context = concept_fixture(seed)
    shares = split(secret)
    outputs = [derive_observation_pin(manifest, session, quorum, context)
               for quorum in combinations(shares, 3)]
    repaired = repair_share(shares[:3], missing_index=5)

    def rejected(call: Callable[[], Any]) -> bool:
        try:
            call()
        except ValueError:
            return True
        return False

    checks = {"all_quorums_agree": len(set(outputs)) == 1,
              "repair_preserves_output": derive_observation_pin(
                  manifest, session, [shares[0], shares[3], repaired], context) == outputs[0],
              "public_context_roundtrip": ConceptContext.from_dict(context.to_dict()) == context,
              "missing_environment_rejected": rejected(lambda: derive_observation_pin(None, session, shares[:3], context)),
              "below_threshold_rejected": rejected(lambda: derive_observation_pin(manifest, session, shares[:2], context)),
              "mixed_generation_rejected": rejected(lambda: derive_observation_pin(
                  manifest, session, [shares[0], shares[1], replace(
                      shares[2], generation=bytes(b ^ 255 for b in shares[2].generation))], context))}
    for status in ("ambiguous", "unreadable"):
        changed = replace(session, readings=(replace(session.readings[0], status=status, value=None),
                                              *session.readings[1:]))
        checks[f"{status}_observation_rejected"] = rejected(
            lambda changed=changed: derive_observation_pin(manifest, changed, shares[:3], context))
    if not all(checks.values()):
        raise RuntimeError("concept execution checks failed")
    return {"schema_version": "edk.concept-run/v1", "mode": "concept_simulation", "source": "synthetic",
            "software_version": __version__, "profile": PROFILE, "seed": seed, "anchors": len(manifest.anchors),
            "verified_quorums": len(outputs), "checks": checks}
