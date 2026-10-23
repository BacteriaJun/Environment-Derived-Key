"""HKDF composition of environmental bytes and a volatile secret, with PIN mapping.

The environmental source's unpredictability is a property of its physical
generation and adversary model, separate from this deterministic computation.
"""

from __future__ import annotations

import hashlib
import hmac


DOMAIN = b"EDK-LAB/v0.1-alpha"  # Changing this changes the derived PIN!
PIN_SPACE = 10**12


def hkdf_extract(salt: bytes, ikm: bytes) -> bytes:
    """RFC 5869 HKDF-Extract/HMAC-SHA256."""
    if not isinstance(salt, bytes) or not isinstance(ikm, bytes):
        raise ValueError("HKDF salt and input must be bytes")
    if not salt:
        salt = bytes(32)
    return hmac.new(salt, ikm, hashlib.sha256).digest()


def hkdf_expand(prk: bytes, info: bytes, length: int) -> bytes:
    """RFC 5869 HKDF-Expand/HMAC-SHA256."""
    if type(length) is not int or not 0 <= length <= 255 * 32:
        raise ValueError("invalid HKDF length")
    if not isinstance(prk, bytes) or len(prk) != 32:
        raise ValueError("SHA256 PRK must be exactly 32 bytes")
    if not isinstance(info, bytes):
        raise ValueError("HKDF context must be bytes")
    previous, output = b"", bytearray()
    for i in range(1, (length + 31) // 32 + 1):
        previous = hmac.new(prk, previous + info + bytes([i]), hashlib.sha256).digest()
        output.extend(previous)
    return bytes(output[:length])


def _accepted_pin(value: str) -> bool:
    """Reject obviously invalid keypad PINs, including simple cyclic runs."""
    if (not isinstance(value, str) or len(value) != 12
            or any(ch not in "0123456789" for ch in value)):
        return False
    if len(set(value)) == 1:
        return False
    for step in (1, -1):
        if all((int(value[j]) + step) % 10 == int(value[j+1]) for j in range(len(value)-1)):
            return False
    return True


def derive_pin(
    environment: bytes, volatile_secret: bytes, *, salt: bytes, device_id: str
) -> str:
    """Return a 12-digit PIN from two required inputs and public context.

    The 32-byte salt and stable device_id are retained across sessions.
    """
    if not isinstance(environment, bytes) or not 1 <= len(environment) <= 65535:
        raise ValueError("environment must be 1..65535 canonical bytes")
    if not isinstance(volatile_secret, bytes) or len(volatile_secret) != 32:
        raise ValueError("volatile secret must be 32 bytes")
    if not isinstance(salt, bytes) or len(salt) != 32:
        raise ValueError("public enrollment salt must be 32 bytes")
    if not isinstance(device_id, str) or not device_id:
        raise ValueError("nonempty device identifier required (max 255 UTF-8 bytes)")
    try:
        context = device_id.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("device identifier must be valid UTF-8 text") from None
    if len(context) > 255:
        raise ValueError("device identifier exceeds 255 UTF-8 bytes")
    # Explicit length framing and fixed source order eliminate concatenation ambiguity.
    ikm = (len(environment).to_bytes(2, "big") + environment
           + len(volatile_secret).to_bytes(2, "big") + volatile_secret)
    prk = hkdf_extract(salt, DOMAIN + b"/ikm/" + ikm)
    # Rejection sampling avoids modulo bias; reject disallowed keypad patterns.
    cutoff = (1 << 64) - ((1 << 64) % PIN_SPACE)
    for counter in range(10_000):
        info = DOMAIN + b"/pin/" + bytes([len(context)]) + context + counter.to_bytes(4, "big")
        candidate = int.from_bytes(hkdf_expand(prk, info, 8), "big")
        if candidate >= cutoff:
            continue
        pin = str(candidate % PIN_SPACE).zfill(12)
        if _accepted_pin(pin):
            return pin
    raise RuntimeError("unexpected PIN generation failure")
