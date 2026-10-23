"""Bounded, strict JSON for research formats. No secret values in errors."""

from __future__ import annotations

import json
import math
from pathlib import Path
import re
from typing import Any

MAX_DOCUMENT_BYTES = 2 * 1024 * 1024


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _constant(_: str) -> None:
    raise ValueError("nonfinite JSON number")


def _float(token: str) -> float:
    value = float(token)
    if not math.isfinite(value):
        raise ValueError("nonfinite JSON number")
    return value


def decode_document(data: bytes) -> dict[str, Any]:
    if not isinstance(data, bytes) or len(data) > MAX_DOCUMENT_BYTES:
        raise ValueError("document exceeds size limit")
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=_constant, parse_float=_float)
    except (ValueError, UnicodeError, RecursionError):
        raise ValueError("invalid JSON document") from None
    if type(value) is not dict:
        raise ValueError("document must be a JSON object")
    return value


def read_document(path: str | Path) -> dict[str, Any]:
    with open(path, "rb") as stream:
        return decode_document(stream.read(MAX_DOCUMENT_BYTES + 1))


def encode_document(value: dict[str, Any]) -> bytes:
    try:
        data = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                           allow_nan=False) + "\n").encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise ValueError("document cannot be encoded") from None
    if len(data) > MAX_DOCUMENT_BYTES:
        raise ValueError("document exceeds size limit")
    return data


def keys(value: Any, required: set[str]) -> None:
    if type(value) is not dict or set(value) != required:
        raise ValueError("unexpected or missing document fields")


def integer(value: Any, low: int, high: int) -> None:
    if type(value) is not int or not low <= value <= high:
        raise ValueError("integer outside permitted range")


def text(value: Any, maximum: int, *, empty: bool = False) -> None:
    if (not isinstance(value, str) or len(value) > maximum
            or (not empty and not value.strip())
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in value)):
        raise ValueError("invalid text field")
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise ValueError("invalid Unicode text field") from None


def identifier(value: Any) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", value):
        raise ValueError("invalid public identifier")
