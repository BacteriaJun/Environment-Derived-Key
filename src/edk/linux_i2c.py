"""Linux i2c-dev transport using combined I2C_RDWR transactions, no force flag."""

from __future__ import annotations

import array
import ctypes
import os
import re
import stat
import sys
import threading
from typing import Any

from .jsonio import integer

I2C_SLAVE = 0x0703
I2C_FUNCS = 0x0705
I2C_RDWR = 0x0707


class _Message(ctypes.Structure):
    _fields_ = [("addr", ctypes.c_uint16), ("flags", ctypes.c_uint16),
                ("length", ctypes.c_uint16), ("buffer", ctypes.POINTER(ctypes.c_uint8))]


class _Transfer(ctypes.Structure):
    _fields_ = [("messages", ctypes.POINTER(_Message)), ("count", ctypes.c_uint32)]


class LinuxI2C:
    def __init__(self, path: str, *, address: int = 0x6F) -> None:
        if sys.platform != "linux":
            raise RuntimeError("physical I2C transport requires Linux")
        if not isinstance(path, str) or not re.fullmatch(r"/dev/i2c-[0-9]+", path):
            raise ValueError("explicit /dev/i2c-N adapter required")
        if type(address) is not int or address != 0x6F:
            raise ValueError("MCP7940N transport is restricted to address 0x6f")
        import fcntl
        self.address = address
        # ctypes releases the GIL around ioctl. Keep close and transfers under
        # the same lock so another thread cannot close/reuse this descriptor
        # during a transaction. Multi-transaction chip operations still require
        # the caller's single-writer ownership; this is not an operation lock.
        self._lock = threading.RLock()
        self._fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            info = os.fstat(self._fd)
            if not stat.S_ISCHR(info.st_mode) or os.major(info.st_rdev) != 89:
                raise ValueError("I2C adapter must be a Linux major-89 character device")
            if os.minor(info.st_rdev) != int(path.rsplit("-", 1)[1]):
                raise ValueError("I2C adapter device number does not match its selected path")
            self.identity = info.st_rdev
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.ioctl(self._fd, I2C_SLAVE, address)  # Does not force a bound kernel device.
            functions = array.array("L", [0])
            fcntl.ioctl(self._fd, I2C_FUNCS, functions, True)
            if not functions[0] & 1:  # I2C_FUNC_I2C
                raise ValueError("adapter does not support combined plain I2C transfers")
            self._libc = ctypes.CDLL(None, use_errno=True)
            self._ioctl = self._libc.ioctl
            self._ioctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_void_p]
            self._ioctl.restype = ctypes.c_int
        except BaseException:
            os.close(self._fd)
            self._fd = -1
            raise

    def __enter__(self) -> "LinuxI2C":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def close(self) -> None:
        with self._lock:
            if self._fd >= 0:
                descriptor = self._fd
                # Do not retry close after an error: on Linux the descriptor
                # may already have been released and reused by another opener.
                self._fd = -1
                os.close(descriptor)

    def _transaction(self, messages: Any) -> None:
        with self._lock:
            if self._fd < 0:
                raise ValueError("I2C adapter is closed")
            transfer = _Transfer(messages, len(messages))
            if self._ioctl(self._fd, I2C_RDWR, ctypes.byref(transfer)) != len(messages):
                raise OSError("I2C combined transfer failed or was incomplete")

    def read(self, register: int, length: int) -> bytes:
        integer(register, 0, 0x5F)
        integer(length, 1, 64)
        if register + length > (0x20 if register < 0x20 else 0x60):
            raise ValueError("register read out of range")
        pointer = (ctypes.c_uint8 * 1)(register)
        result = (ctypes.c_uint8 * length)()
        messages = (_Message * 2)(_Message(self.address, 0, 1, pointer),
                                   _Message(self.address, 1, length, result))
        self._transaction(messages)
        return bytes(result)

    def write(self, register: int, data: bytes) -> None:
        integer(register, 0, 0x5F)
        if (not isinstance(data, bytes) or not 1 <= len(data) <= 64
                or register + len(data) > (0x20 if register < 0x20 else 0x60)):
            raise ValueError("register write out of range")
        buffer = (ctypes.c_uint8 * (len(data) + 1)).from_buffer_copy(bytes([register]) + data)
        messages = (_Message * 1)(_Message(self.address, 0, len(buffer), buffer))
        self._transaction(messages)
