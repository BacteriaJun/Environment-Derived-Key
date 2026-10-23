"""Compare ctypes I2C layout with compiled Linux UAPI headers; no device I/O."""

from __future__ import annotations

import ctypes
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any

from .linux_i2c import I2C_FUNCS, I2C_RDWR, I2C_SLAVE, _Message, _Transfer

_C_SOURCE = r'''
#include <linux/i2c.h>
#include <linux/i2c-dev.h>
#include <stddef.h>
#include <stdio.h>
int main(void) {
  printf("{\"message_size\":%zu,\"buffer_offset\":%zu,"
         "\"transfer_size\":%zu,\"count_offset\":%zu,"
         "\"I2C_SLAVE\":%lu,\"I2C_FUNCS\":%lu,\"I2C_RDWR\":%lu,"
         "\"I2C_FUNC_I2C\":%lu,\"I2C_M_RD\":%lu}\n",
         sizeof(struct i2c_msg), offsetof(struct i2c_msg, buf),
         sizeof(struct i2c_rdwr_ioctl_data), offsetof(struct i2c_rdwr_ioctl_data, nmsgs),
         (unsigned long)I2C_SLAVE, (unsigned long)I2C_FUNCS, (unsigned long)I2C_RDWR,
         (unsigned long)I2C_FUNC_I2C, (unsigned long)I2C_M_RD);
  return 0;
}
'''


def expected_layout() -> dict[str, int]:
    return {"message_size": ctypes.sizeof(_Message), "buffer_offset": _Message.buffer.offset,
            "transfer_size": ctypes.sizeof(_Transfer), "count_offset": _Transfer.count.offset,
            "I2C_SLAVE": I2C_SLAVE, "I2C_FUNCS": I2C_FUNCS, "I2C_RDWR": I2C_RDWR,
            "I2C_FUNC_I2C": 1, "I2C_M_RD": 1}


def layout_matches(value: Any) -> bool:
    return (type(value) is dict and all(type(v) is int for v in value.values())
            and value == expected_layout())


def check_native_abi() -> dict[str, Any]:
    base: dict[str, Any] = {"schema_version": "edk.linux-native-abi/v1",
                            "checked": False, "matches": False, "device_io": False}
    if sys.platform != "linux":
        return {**base, "reason": "Linux required"}
    compiler = shutil.which("cc")
    if compiler is None:
        return {**base, "reason": "C compiler unavailable"}
    try:
        with tempfile.TemporaryDirectory(prefix="edk-native-abi-") as directory:
            root = Path(directory)
            source, binary = root / "layout.c", root / "layout"
            source.write_text(_C_SOURCE, encoding="utf-8")
            result = subprocess.run([compiler, "-std=c11", "-Wall", "-Werror", str(source), "-o", str(binary)],
                                    capture_output=True, text=True, timeout=20)
            if result.returncode:
                return {**base, "reason": "C compilation or Linux UAPI headers unavailable"}
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
            if result.returncode:
                return {**base, "reason": "native layout executable failed"}
            native = json.loads(result.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {**base, "reason": "native check unavailable or invalid"}
    return {**base, "checked": True, "matches": layout_matches(native),
            "python_layout": expected_layout(), "native_layout": native}
