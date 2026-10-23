"""Single-node public-pattern experiments. Never a key enrollment or erasure proof."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import platform
import re
import secrets
import stat
import sys
from typing import Any
import zlib

from .jsonio import keys, read_document
from .simulation import _nonnegative_finite
from .sram import COMMIT, MCP7940N, SRAM_START

TOKEN_SCHEMA = "edk.public-bench-token/v1"
TEST_PURPOSE = "PUBLIC_TEST_PATTERN_NOT_KEY_MATERIAL"


@dataclass(frozen=True)
class BenchToken:
    nonce: str
    created_at: str
    schema_version: str = TOKEN_SCHEMA
    purpose: str = TEST_PURPOSE

    def __post_init__(self) -> None:
        if not isinstance(self.nonce, str) or not re.fullmatch(r"[0-9a-f]{32}", self.nonce):
            raise ValueError("invalid public test nonce")
        if self.schema_version != TOKEN_SCHEMA or self.purpose != TEST_PURPOSE:
            raise ValueError("unsupported bench token")
        try:
            stamp = datetime.strptime(self.created_at, "%Y-%m-%dT%H:%M:%S.%fZ")
            if stamp.strftime("%Y-%m-%dT%H:%M:%S.%fZ") != self.created_at:
                raise ValueError
        except (ValueError, TypeError):
            raise ValueError("invalid bench token time") from None

    @classmethod
    def create(cls) -> "BenchToken":
        return cls(secrets.token_hex(16), datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"))

    def to_dict(self) -> dict[str, str]:
        return {"schema_version": self.schema_version, "purpose": self.purpose,
                "nonce": self.nonce, "created_at": self.created_at}

    @classmethod
    def load(cls, path: str | Path) -> "BenchToken":
        value = read_document(path)
        keys(value, {"schema_version", "purpose", "nonce", "created_at"})
        return cls(**value)


def public_test_image(token: BenchToken) -> bytes:
    if not isinstance(token, BenchToken):
        raise ValueError("public bench token required")
    nonce = bytes.fromhex(token.nonce)
    pattern = hashlib.sha256(b"EDK-PUBLIC-SRAM-TEST/v1\x00" + nonce).digest()
    body = b"EDKT\x01\x00\x00\x00" + nonce + pattern
    return body + zlib.crc32(body).to_bytes(4, "big") + COMMIT


def check_test_slot(device: MCP7940N, *, initialize_unrecognized: bool = False) -> None:
    if type(initialize_unrecognized) is not bool:
        raise ValueError("initialization option must be boolean")
    flags = device.status()
    if not flags["backup_enabled"]:
        raise ValueError("backup must be enabled for a retention experiment")
    prefix = device._read(SRAM_START, 4)
    # Protect even a damaged EDK share image; never reinterpret it as a test slot.
    if prefix == b"EDK1":
        raise ValueError("refuse test-pattern writes over an EDK share record")
    current = device._read(SRAM_START, 64)
    test_record = (current[:8] == b"EDKT\x01\x00\x00\x00" and current[60:] == COMMIT
                   and current[56:60] == zlib.crc32(current[:56]).to_bytes(4, "big"))
    if not test_record and current not in (bytes(64), b"\xff" * 64) and not initialize_unrecognized:
        raise ValueError("unrecognized SRAM needs explicit initialization")


def prepare_test(device: MCP7940N, token: BenchToken, *, initialize_unrecognized: bool = False) -> None:
    check_test_slot(device, initialize_unrecognized=initialize_unrecognized)
    image = public_test_image(token)
    device.bus.write(SRAM_START + 60, bytes(4))
    if device._read(SRAM_START + 60, 4) != bytes(4):
        raise OSError("test tag invalidation failed")
    for offset in range(0, 60, 16):
        device.bus.write(SRAM_START + offset, image[offset:min(offset + 16, 60)])
    if device._read(SRAM_START, 60) != image[:60]:
        raise OSError("test body readback failed")
    device.bus.write(SRAM_START + 60, COMMIT)
    if device._read(SRAM_START, 64) != image:
        raise OSError("test record final readback failed")


def check_test(device: MCP7940N, token: BenchToken, *, source: str,
               operator_vcc_off_seconds: float | None = None) -> dict[str, Any]:
    """Read-only with respect to control/SRAM data; pointer writes still occur."""
    if source not in ("physical_io", "synthetic_bus"):
        raise ValueError("explicit experiment source required")
    if operator_vcc_off_seconds is not None:
        _nonnegative_finite(operator_vcc_off_seconds, "operator VCC-off duration")
    before = device.status()
    if device._read(SRAM_START, 4) == b"EDK1":
        raise ValueError("refuse pattern comparison against an EDK share record")
    image = device._read(SRAM_START, 64)
    after = device.status()
    return {"schema_version": "edk.bench-observation/v1", "source": source,
            "purpose": TEST_PURPOSE, "public_test_nonce": token.nonce,
            "matches_public_pattern": image == public_test_image(token),
            "status_before": before, "status_after": after,
            "status_changed_during_read": before != after,
            "operator_vcc_off_seconds": operator_vcc_off_seconds,
            "duration_provenance": "operator supplied, not measured by this program",
            "observed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "interpretation": "A matching public pattern is an observation, not an erase, entropy or security proof."}


def doctor_report(bus: str = "/dev/i2c-1") -> dict[str, Any]:
    """Metadata only: no adapter opens, scans, ioctls, control or SRAM writes."""
    if not isinstance(bus, str) or not re.fullmatch(r"/dev/i2c-[0-9]+", bus):
        raise ValueError("explicit /dev/i2c-N path required")
    node = Path(bus)
    kind, major_ok, minor_ok, access = "missing", False, False, False
    try:
        info = node.lstat()
        kind = "symlink" if stat.S_ISLNK(info.st_mode) else (
            "character" if stat.S_ISCHR(info.st_mode) else "other")
        major_ok = kind == "character" and os.major(info.st_rdev) == 89
        minor_ok = kind == "character" and os.minor(info.st_rdev) == int(bus.rsplit('-', 1)[1])
        access = major_ok and minor_ok and os.access(bus, os.R_OK | os.W_OK)
    except FileNotFoundError:
        pass
    driver = Path(f"/sys/bus/i2c/devices/{int(bus.rsplit('-', 1)[1])}-006f/driver")
    bound = driver.is_symlink() if sys.platform == "linux" else False
    model = None
    if sys.platform == "linux":
        try:
            data = Path("/proc/device-tree/model").read_bytes()[:256].rstrip(b"\x00").decode("utf-8")
            model = data if all(32 <= ord(ch) != 127 for ch in data) else None
        except (OSError, UnicodeError):
            pass
    return {"schema_version": "edk.bench-host-check/v1", "platform": sys.platform,
            "architecture": platform.machine(), "python": platform.python_version(),
            "raspberry_pi_model_if_available": model, "selected_adapter": bus,
            "node_kind": kind, "linux_i2c_major_89": major_ok,
            "adapter_minor_matches_path": minor_ok,
            "read_write_access": access, "kernel_driver_bound_at_0x6f": bound,
            "host_preflight_passed": sys.platform == "linux" and major_ok and minor_ok and access and not bound,
            "device_transactions_performed": False, "electrical_checks_performed": False,
            "next": "Check wiring, 3.3V signal levels, independent VCC/VBAT and native ABI before laboratory I/O."}
