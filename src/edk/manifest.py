"""Public anchor definitions only; schema validation cannot certify privacy."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
import hashlib
from pathlib import Path
from typing import Any

from .environment import AnchorDefinition
from .jsonio import encode_document, identifier, keys, read_document, text

MANIFEST_SCHEMA = "edk.anchor-manifest/v1"


@dataclass(frozen=True)
class AnchorManifest:
    manifest_id: str
    anchors: tuple[AnchorDefinition, ...]
    schema_version: str = MANIFEST_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != MANIFEST_SCHEMA:
            raise ValueError("unsupported manifest schema version")
        identifier(self.manifest_id)
        if type(self.anchors) is not tuple or not 1 <= len(self.anchors) <= 512:
            raise ValueError("manifest requires 1..512 ordered anchors")
        ids: set[str] = set()
        for anchor in self.anchors:
            if not isinstance(anchor, AnchorDefinition):
                raise ValueError("invalid anchor definition")
            identifier(anchor.anchor_id)
            text(anchor.location_hint, 256, empty=True)
            text(anchor.reading_rule, 1024)
            if anchor.anchor_id in ids:
                raise ValueError("duplicate anchor identifier")
            ids.add(anchor.anchor_id)

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "manifest_id": self.manifest_id,
                "anchors": [{"anchor_id": a.anchor_id, "location_hint": a.location_hint,
                             "reading_rule": a.reading_rule, "state_count": a.state_count}
                            for a in self.anchors]}

    @cached_property
    def fingerprint(self) -> str:
        """Hash of PUBLIC definitions only; never a hash of observations."""
        return hashlib.sha256(encode_document(self.to_dict())).hexdigest()

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "AnchorManifest":
        keys(value, {"schema_version", "manifest_id", "anchors"})
        if type(value["anchors"]) is not list or not 1 <= len(value["anchors"]) <= 512:
            raise ValueError("invalid anchor list")
        anchors = []
        for item in value["anchors"]:
            keys(item, {"anchor_id", "location_hint", "reading_rule", "state_count"})
            anchors.append(AnchorDefinition(**item))
        return cls(value["manifest_id"], tuple(anchors), value["schema_version"])


def load_manifest(path: str | Path) -> AnchorManifest:
    return AnchorManifest.from_dict(read_document(path))
