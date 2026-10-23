"""Disposable in-process emulator of a volatile SRAM share node.

Cannot simulate retention voltage, battery failure, MCU reset or secure wiping.
Python memory copies may persist after expire(). No data is saved to files.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from .shamir import Share, validate_share


class NodeUnavailable(RuntimeError):
    pass


@dataclass
class VolatileNode:
    index: int
    generation: bytes = field(repr=False)
    _memory: bytearray | None = field(repr=False)
    threshold: int = 3

    def __post_init__(self) -> None:
        if self._memory is not None and not isinstance(self._memory, bytearray):
            raise ValueError("node memory must be a bytearray or unavailable")
        Share(self.index, self.generation,
              bytes(self._memory) if self._memory is not None else bytes(32),
              threshold=self.threshold)

    @classmethod
    def provision(cls, share: Share) -> "VolatileNode":
        validate_share(share)
        return cls(share.index, share.generation, bytearray(share.payload), share.threshold)

    @property
    def alive(self) -> bool:
        return self._memory is not None

    def read(self) -> Share:
        if self._memory is None:
            raise NodeUnavailable(f"node {self.index} has lost its volatile state")
        return Share(self.index, self.generation, bytes(self._memory), self.threshold)

    def expire(self) -> None:
        """Logical erasure in model only; NOT verified physical zeroization."""
        if self._memory is not None:
            for i in range(len(self._memory)):
                self._memory[i] = 0
        self._memory = None

    def reprovision(self, share: Share) -> None:
        validate_share(share)
        if share.index != self.index:
            raise ValueError("share index does not match node")
        if self._memory is not None:
            raise ValueError("refuse overwrite of an existing live share")
        self.generation = share.generation
        self.threshold = share.threshold
        self._memory = bytearray(share.payload)
