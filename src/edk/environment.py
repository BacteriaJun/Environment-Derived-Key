"""Strict canonicalization for a manual environmental observation.

This module DOES NOT implement fuzzy extraction, error correction, entropy
estimation, or physical unclonability. In v0.1 all readings must match exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Sequence


ENVIRONMENT_PROFILE = "EDK-LAB/manual-40x64/v1"


class EnvironmentUnavailable(ValueError):
    """The physical environment cannot be read unambiguously."""


@dataclass(frozen=True)
class AnchorDefinition:
    """Public reading rule. Do NOT put secret states into public manifests."""

    anchor_id: str
    location_hint: str
    reading_rule: str
    state_count: int = 64

    def __post_init__(self) -> None:
        if any(not isinstance(v, str) for v in
               (self.anchor_id, self.location_hint, self.reading_rule)):
            raise ValueError("anchor fields must be text")
        if not self.anchor_id.strip() or not self.reading_rule.strip():
            raise ValueError("anchor ID and reading rule must not be empty")
        if type(self.state_count) is not int or not 2 <= self.state_count <= 65536:
            raise ValueError("anchor state count must be 2..65536")


def canonicalize(readings: Sequence[int | None], *, expected_count: int = 40) -> bytes:
    """Encode ordered 0..63 observations as one byte per cell, without guessing.

    expected_count=40 is a HISTORICAL EXPERIMENTAL PROFILE, not validated
    evidence that an ordinary room contains 240 bits of secret entropy.
    """
    if type(expected_count) is not int or not 1 <= expected_count <= 65535:
        raise EnvironmentUnavailable("invalid environment cell count")
    if (not isinstance(readings, Sequence)
            or isinstance(readings, (str, bytes, bytearray, memoryview))):
        raise EnvironmentUnavailable("readings must be an integer observation sequence")
    if len(readings) != expected_count:
        raise EnvironmentUnavailable("unexpected number of environment cells")
    result = bytearray()
    for idx, value in enumerate(readings):
        if value is None:
            raise EnvironmentUnavailable(f"cell {idx} is unreadable; stop")
        if type(value) is not int or not 0 <= value < 64:
            raise EnvironmentUnavailable(f"cell {idx} must be an integer in 0..63")
        result.append(value)
    return bytes(result)
