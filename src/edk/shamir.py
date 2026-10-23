"""EDUCATIONAL GF(256) Shamir 3-of-6 implementation.

Correct algebra is not a security certification. Variable-time Python,
unprotected memory and unauthenticated shares are unsuitable for real keys.
Use an audited implementation in a secure hardware environment for deployment.
"""

from __future__ import annotations

from dataclasses import dataclass
import secrets
from collections.abc import Sequence


@dataclass(frozen=True)
class Share:
    index: int
    generation: bytes  # 16-byte PUBLIC grouping ID; not a secret
    payload: bytes     # SECRET; in v0.1 demo, 32 bytes
    threshold: int = 3  # Public configuration, NOT authenticated metadata.

    def __post_init__(self) -> None:
        validate_share(self)

    def __repr__(self) -> str:
        return (f"Share(index={self.index}, threshold={self.threshold}, "
                "generation=<redacted>, payload=<redacted>)")


def _integer(value: int, low: int, high: int, message: str) -> None:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(message)


def validate_share(share: Share) -> None:
    """Validate shape/configuration only; cannot authenticate a share's value."""
    if not isinstance(share, Share):
        raise ValueError("expected a Share object")
    _integer(share.index, 1, 255, "invalid share index")
    _integer(share.threshold, 2, 255, "invalid share threshold")
    if not isinstance(share.generation, bytes) or len(share.generation) != 16:
        raise ValueError("generation must be 16 bytes")
    if not isinstance(share.payload, bytes) or len(share.payload) != 32:
        raise ValueError("share payload must be 32 bytes")


def _mul(a: int, b: int) -> int:
    """GF(2^8) multiplication, irreducible polynomial 0x11b."""
    out = 0
    for _ in range(8):
        if b & 1:
            out ^= a
        hi = a & 0x80
        a = (a << 1) & 0xff
        if hi:
            a ^= 0x1b
        b >>= 1
    return out


def _pow(a: int, n: int) -> int:
    out = 1
    while n:
        if n & 1:
            out = _mul(out, a)
        a = _mul(a, a)
        n >>= 1
    return out


def _inv(a: int) -> int:
    if a == 0:
        raise ValueError("no inverse for zero")
    return _pow(a, 254)


def _validate(shares: Sequence[Share], threshold: int) -> None:
    _integer(threshold, 2, 255, "invalid recovery threshold")
    if not isinstance(shares, Sequence) or isinstance(shares, (str, bytes, bytearray)):
        raise ValueError("expected a sequence of Share objects")
    if len(shares) > 255:
        raise ValueError("too many shares")
    if len(shares) < threshold:
        raise ValueError(f"at least {threshold} independent shares are required")
    for share in shares:
        validate_share(share)
        if share.threshold != threshold:
            raise ValueError("share threshold does not match recovery configuration")
    ids = [s.index for s in shares]
    if any(not 1 <= x <= 255 for x in ids) or len(set(ids)) != len(ids):
        raise ValueError("shares must have distinct nonzero indices")
    if any(len(s.generation) != 16 or s.generation != shares[0].generation for s in shares):
        raise ValueError("mixed share generations")


def split(secret: bytes, *, threshold: int = 3, count: int = 6) -> list[Share]:
    if not isinstance(secret, bytes) or len(secret) != 32:
        raise ValueError("this proof-of-concept supports 32-byte secrets")
    _integer(threshold, 2, 255, "invalid threshold/count")
    _integer(count, 2, 255, "invalid threshold/count")
    if threshold > count:
        raise ValueError("invalid threshold/count")
    generation = secrets.token_bytes(16)
    # Each byte is a separately randomized polynomial of degree threshold-1.
    coefficients = [secret] + [secrets.token_bytes(len(secret)) for _ in range(threshold - 1)]
    result: list[Share] = []
    for x in range(1, count + 1):
        payload = bytearray(len(secret))
        for byte_index in range(len(secret)):
            value = coefficients[-1][byte_index]
            for coefficient in reversed(coefficients[:-1]):
                value = _mul(value, x) ^ coefficient[byte_index]
            payload[byte_index] = value
        result.append(Share(x, generation, bytes(payload), threshold=threshold))
    return result


def interpolate(shares: Sequence[Share], *, x: int, threshold: int = 3) -> bytes:
    """Evaluate the ORIGINAL sharing polynomial at x (0 gives the secret).

    Extra supplied shares are checked for consistency with the first t shares.
    This consistency check is NOT share authentication: a malicious party
    with control over t shares may forge an entire consistent polynomial.
    """
    _integer(x, 0, 255, "interpolation point out of range")
    _validate(shares, threshold)
    selected = list(shares[:threshold])
    result = bytearray(len(selected[0].payload))
    for i, share in enumerate(selected):
        basis = 1
        for j, other in enumerate(selected):
            if i == j:
                continue
            basis = _mul(basis, _mul(x ^ other.index, _inv(share.index ^ other.index)))
        for b, value in enumerate(share.payload):
            result[b] ^= _mul(basis, value)
    if len(shares) > threshold:
        for extra in shares[threshold:]:
            predicted = interpolate(selected, x=extra.index, threshold=threshold)
            if predicted != extra.payload:
                raise ValueError("inconsistent extra share")
    return bytes(result)


def recover(shares: Sequence[Share], *, threshold: int = 3) -> bytes:
    """Recover with an explicitly matching threshold; metadata is not a MAC."""
    return interpolate(shares, x=0, threshold=threshold)


def repair_share(shares: Sequence[Share], *, missing_index: int, threshold: int = 3) -> Share:
    """Repair a destroyed (NOT stolen) node, preserving the original polynomial."""
    _validate(shares, threshold)
    _integer(missing_index, 1, 255, "invalid replacement index")
    if missing_index in {s.index for s in shares}:
        raise ValueError("replacement index is already present")
    payload = interpolate(shares, x=missing_index, threshold=threshold)
    return Share(missing_index, shares[0].generation, payload, threshold=threshold)
