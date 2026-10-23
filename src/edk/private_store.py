"""Owner-only POSIX storage; no automatic Git operations or secret backups."""

from __future__ import annotations

import os
from pathlib import Path
import re
import stat
from typing import Any

from .jsonio import MAX_DOCUMENT_BYTES, decode_document, encode_document
from .manifest import AnchorManifest
from .observations import ObservationSession


class PrivateStore:
    """No overwrite, final-component symlinks, broad permissions or foreign owners.

    This is filesystem access control, not encryption, secure erasure, ACL
    validation or protection from the same user, administrator, sync or backups.
    """

    def __init__(self, root: str | Path = ".edk-private", *, create: bool = True) -> None:
        if type(create) is not bool:
            raise ValueError("storage creation option must be boolean")
        if os.name != "posix" or not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
            raise RuntimeError("private collection requires supported POSIX file permissions")
        self.root = Path(root).expanduser().absolute()
        if create:
            try:
                self.root.mkdir(mode=0o700)
            except FileExistsError:
                pass
        self._fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            info = os.fstat(self._fd)
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise ValueError("private directory must be owned by current user with mode 0700")
            if not create:
                if self._read(".gitignore") != b"*\n":
                    raise ValueError("private store ignore file is not the expected deny-all rule")
            else:
                try:
                    self._write_new(".gitignore", b"*\n")
                except FileExistsError:
                    if self._read(".gitignore") != b"*\n":
                        raise ValueError("private store ignore file is not the expected deny-all rule")
        except BaseException:
            os.close(self._fd)
            self._fd = -1
            raise

    def __enter__(self) -> "PrivateStore":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def close(self) -> None:
        if self._fd >= 0:
            os.close(self._fd)
            self._fd = -1

    def _write_new(self, name: str, data: bytes) -> None:
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=self._fd)
        try:
            # A restrictive umask may remove owner bits; enforce the requested mode.
            os.fchmod(fd, 0o600)
            view = memoryview(data)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise OSError("short private record write")
                view = view[written:]
            os.fsync(fd)
        except BaseException:
            os.unlink(name, dir_fd=self._fd)
            raise
        finally:
            os.close(fd)
        os.fsync(self._fd)

    def _read(self, name: str) -> bytes:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self._fd)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
                raise ValueError("private file must be a single-link owner-only regular file")
            if info.st_size > MAX_DOCUMENT_BYTES:
                raise ValueError("private file exceeds size limit")
            chunks, size = [], 0
            while True:
                chunk = os.read(fd, min(65536, MAX_DOCUMENT_BYTES + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > MAX_DOCUMENT_BYTES:
                    raise ValueError("private file exceeds size limit")
            return b"".join(chunks)
        finally:
            os.close(fd)

    @staticmethod
    def _filename(session_id: str) -> str:
        if not isinstance(session_id, str) or not re.fullmatch(r"[0-9a-f]{32}", session_id):
            raise ValueError("invalid private session identifier")
        return session_id + ".edk-private.json"

    def save(self, manifest: AnchorManifest, session: ObservationSession) -> None:
        session.validate_for(manifest)
        self._write_new(self._filename(session.session_id), encode_document(session.to_dict()))

    def load(self, manifest: AnchorManifest, session_id: str) -> ObservationSession:
        session = ObservationSession.from_dict(decode_document(self._read(self._filename(session_id))), manifest)
        if session.session_id != session_id:
            raise ValueError("private file identifier mismatch")
        return session

    def session_ids(self) -> tuple[str, ...]:
        names = os.listdir(self._fd)
        return tuple(sorted(n[:-17] for n in names
                            if re.fullmatch(r"[0-9a-f]{32}\.edk-private\.json", n)))


def write_new_aggregate(path: str | Path, data: dict[str, Any]) -> None:
    """For internally constructed aggregate/synthetic reports, never raw sessions."""
    encoded = encode_document(data)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o644)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        os.unlink(path)
        raise
