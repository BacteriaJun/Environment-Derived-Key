"""Experimental MCP7940N share writer; CRC detects errors, NOT attackers.

Register map: Microchip DS20005010J. No hardware was available for validation.
The transport must address only the intended laboratory chip, under exclusive
access. A Linux adapter is supplied separately; tests use an in-memory bus.
"""

from __future__ import annotations

from dataclasses import dataclass
import secrets
from typing import Protocol, Sequence
import zlib

from .jsonio import integer
from .shamir import Share, repair_share, split, validate_share

SRAM_START = 0x20
SRAM_SIZE = 64
RTCWKDAY = 0x03
VBATEN = 0x08
PWRFAIL = 0x10
COMMIT = b"DONE"


class RegisterBus(Protocol):
    def read(self, register: int, length: int) -> bytes: ...
    def write(self, register: int, data: bytes) -> None: ...


def encode_share(share: Share) -> bytes:
    validate_share(share)
    body = b"EDK1" + bytes((1, share.index, share.threshold, 0)) + share.generation + share.payload
    return body + zlib.crc32(body).to_bytes(4, "big") + COMMIT


def decode_share(image: bytes) -> Share:
    if not isinstance(image, bytes) or len(image) != SRAM_SIZE:
        raise ValueError("invalid SRAM record length")
    if image[:5] != b"EDK1\x01" or image[7] != 0 or image[60:] != COMMIT:
        raise ValueError("uncommitted or unsupported SRAM record")
    if image[56:60] != zlib.crc32(image[:56]).to_bytes(4, "big"):
        raise ValueError("SRAM record checksum mismatch")
    return Share(image[5], image[8:24], image[24:56], threshold=image[6])


@dataclass(repr=False)
class MCP7940N:
    bus: RegisterBus

    def __repr__(self) -> str:
        return "MCP7940N(bus=<redacted>)"

    def _read(self, register: int, length: int) -> bytes:
        result = self.bus.read(register, length)
        if not isinstance(result, bytes) or len(result) != length:
            raise OSError("short or malformed I2C read")
        return result

    def status(self) -> dict[str, bool]:
        value = self._read(RTCWKDAY, 1)[0]
        return {"backup_enabled": bool(value & VBATEN), "power_failure_recorded": bool(value & PWRFAIL),
                "oscillator_running": bool(value & 0x20)}

    def enable_backup(self) -> None:
        value = self._read(RTCWKDAY, 1)[0]
        if value & PWRFAIL:
            raise ValueError("recorded power failure requires separate hardware investigation")
        if not value & VBATEN:
            self.bus.write(RTCWKDAY, bytes([value | VBATEN]))
        if not self.status()["backup_enabled"]:
            raise OSError("backup-enable readback failed")

    def _ready(self) -> None:
        flags = self.status()
        if not flags["backup_enabled"] or flags["power_failure_recorded"]:
            raise ValueError("backup disabled or recorded power failure; stop")

    def read_share(self) -> Share:
        self._ready()
        share = decode_share(self._read(SRAM_START, SRAM_SIZE))
        self._ready()
        return share

    def check_available(self, *, initialize_unrecognized: bool = False) -> None:
        if type(initialize_unrecognized) is not bool:
            raise ValueError("initialization option must be boolean")
        self._ready()
        existing = self._read(SRAM_START, SRAM_SIZE)
        if existing[:4] == b"EDK1":
            raise ValueError("refuse overwrite of an EDK share header, including damaged records")
        try:
            decode_share(existing)
        except ValueError:
            if existing not in (bytes(64), b"\xff" * 64) and not initialize_unrecognized:
                raise ValueError("unrecognized nonblank SRAM requires explicit initialization")
        else:
            raise ValueError("refuse overwrite of a committed share")

    def write_share(self, share: Share, *, initialize_unrecognized: bool = False) -> None:
        """Invalidate -> body/readback -> commit/readback. No in-place refresh."""
        validate_share(share)
        self.check_available(initialize_unrecognized=initialize_unrecognized)
        image = encode_share(share)
        self.bus.write(SRAM_START + 60, bytes(4))
        if self._read(SRAM_START + 60, 4) != bytes(4):
            raise OSError("SRAM invalidation readback failed")
        # 16-byte chunks avoid relying on SMBus's 32-byte block extension.
        for offset in range(0, 60, 16):
            self.bus.write(SRAM_START + offset, image[offset:min(offset + 16, 60)])
        if self._read(SRAM_START, 60) != image[:60]:
            raise OSError("SRAM body readback failed")
        self._ready()
        self.bus.write(SRAM_START + 60, COMMIT)
        if self.read_share() != share:
            raise OSError("SRAM final readback failed")


def provision_six(devices: Sequence[MCP7940N], *, initialize_unrecognized: bool = False) -> dict[str, int | str]:
    """Generate KV/shares in RAM and write six laboratory nodes; emit no secrets.

    Partial failure may leave committed nodes and cannot be made atomic on six
    independent 64-byte devices. No retry/rollback or secret disk recovery file.
    """
    if len(devices) != 6 or any(not isinstance(d, MCP7940N) for d in devices):
        raise ValueError("six independent SRAM devices required")
    identities = [getattr(d.bus, "identity", id(d.bus)) for d in devices]
    if len(set(identities)) != 6:
        raise ValueError("duplicate device/adapter identity")
    for device in devices:
        device.check_available(initialize_unrecognized=initialize_unrecognized)
    shares = split(secrets.token_bytes(32))
    for device, share in zip(devices, shares):
        device.write_share(share, initialize_unrecognized=initialize_unrecognized)
    return {"committed_nodes": 6, "threshold": 3,
            "purpose": "laboratory volatile-share storage only; no real PIN enrolled"}


def repair_hardware_node(sources: Sequence[MCP7940N], target: MCP7940N, *, missing_index: int,
                         initialize_unrecognized: bool = False) -> None:
    """Only for a confirmed destroyed share; this cannot revoke stolen copies."""
    if len(sources) != 3 or any(not isinstance(d, MCP7940N) for d in (*sources, target)):
        raise ValueError("three source devices and one empty target required")
    identities = [getattr(d.bus, "identity", id(d.bus)) for d in (*sources, target)]
    if len(set(identities)) != 4:
        raise ValueError("duplicate device/adapter identity")
    target.check_available(initialize_unrecognized=initialize_unrecognized)
    replacement = repair_share([device.read_share() for device in sources], missing_index=missing_index)
    target.write_share(replacement, initialize_unrecognized=initialize_unrecognized)


class MemoryRegisterBus:
    """Synthetic register bus, explicitly not a model of power retention."""

    def __init__(self) -> None:
        self._registers = bytearray(0x60)
        self._registers[RTCWKDAY] = VBATEN | 1
        self.writes: list[tuple[int, int]] = []  # Addresses and lengths, never payloads.

    def __repr__(self) -> str:
        return "MemoryRegisterBus(registers=<redacted>)"

    def expire(self) -> None:
        """Logical simulated SRAM loss, never a physical erasure guarantee."""
        self._registers[SRAM_START:] = bytes(SRAM_SIZE)

    def record_power_failure(self) -> None:
        """Inject a hardware-set flag; software writes cannot set PWRFAIL."""
        self._registers[RTCWKDAY] |= PWRFAIL

    def read(self, register: int, length: int) -> bytes:
        integer(register, 0, 0x5F)
        integer(length, 1, 64)
        if register + length > (0x20 if register < 0x20 else 0x60):
            raise ValueError("register read out of range")
        return bytes(self._registers[register:register + length])

    def write(self, register: int, data: bytes) -> None:
        integer(register, 0, 0x5F)
        if (not isinstance(data, bytes) or not data
                or register + len(data) > (0x20 if register < 0x20 else 0x60)):
            raise ValueError("register write out of range")
        self.writes.append((register, len(data)))
        for offset, value in enumerate(data):
            address = register + offset
            if address == RTCWKDAY:
                # Datasheet: every RTCWKDAY write clears PWRFAIL; OSCRUN is read-only.
                self._registers[address] = (value & 0x0F) | (self._registers[address] & 0x20)
            else:
                self._registers[address] = value
