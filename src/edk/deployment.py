"""Local six-slot wiring configuration. Labels are declarations, not attestation."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
from typing import Any

from .jsonio import encode_document, identifier, integer, keys, read_document

TOPOLOGY_SCHEMA = "edk.hardware-topology/v1"


@dataclass(frozen=True)
class NodeSlot:
    index: int
    adapter: str
    failure_domain: str

    def __post_init__(self) -> None:
        integer(self.index, 1, 6)
        if (not isinstance(self.adapter, str)
                or not re.fullmatch(r"/dev/i2c-(0|[1-9][0-9]{0,4})", self.adapter)):
            raise ValueError("canonical Linux I2C adapter path required")
        identifier(self.failure_domain)

    def to_dict(self) -> dict[str, Any]:
        return {"index": self.index, "adapter": self.adapter, "failure_domain": self.failure_domain}


@dataclass(frozen=True)
class HardwareTopology:
    topology_id: str
    nodes: tuple[NodeSlot, ...]
    threshold: int = 3
    schema_version: str = TOPOLOGY_SCHEMA

    def __post_init__(self) -> None:
        identifier(self.topology_id)
        if self.schema_version != TOPOLOGY_SCHEMA or type(self.threshold) is not int or self.threshold != 3:
            raise ValueError("unsupported hardware topology")
        if (type(self.nodes) is not tuple or len(self.nodes) != 6
                or any(not isinstance(n, NodeSlot) for n in self.nodes)
                or tuple(n.index for n in self.nodes) != tuple(range(1, 7))):
            raise ValueError("six slots in index order required")
        if len({n.adapter for n in self.nodes}) != 6:
            raise ValueError("duplicate adapter path")

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "topology_id": self.topology_id,
                "threshold": self.threshold, "nodes": [n.to_dict() for n in self.nodes]}

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(encode_document(self.to_dict())).hexdigest()

    @property
    def colocated_quorum(self) -> bool:
        domains = [n.failure_domain for n in self.nodes]
        return any(domains.count(d) >= self.threshold for d in set(domains))

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "HardwareTopology":
        keys(value, {"schema_version", "topology_id", "threshold", "nodes"})
        if type(value["nodes"]) is not list or len(value["nodes"]) != 6:
            raise ValueError("six hardware slots required")
        nodes = []
        for node in value["nodes"]:
            keys(node, {"index", "adapter", "failure_domain"})
            nodes.append(NodeSlot(**node))
        return cls(value["topology_id"], tuple(nodes), value["threshold"], value["schema_version"])

    @classmethod
    def load(cls, path: str | Path) -> "HardwareTopology":
        return cls.from_dict(read_document(path))
