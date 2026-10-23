"""Descriptor ownership tests using mocks; no physical I2C transactions."""

import os
import stat
import threading
import unittest
from unittest.mock import MagicMock, patch

from edk.linux_i2c import LinuxI2C


def transport():
    bus = object.__new__(LinuxI2C)
    bus.address, bus._fd = 0x6F, 123
    bus._lock = threading.RLock()
    return bus


class TransportEngineeringTests(unittest.TestCase):
    def test_close_waits_for_inflight_transaction(self):
        bus = transport()
        entered, release, closing, closed = (threading.Event() for _ in range(4))
        errors = []

        def ioctl(*_):
            entered.set()
            if not release.wait(2):
                raise RuntimeError("test transaction was not released")
            self.assertFalse(closed.is_set())
            return 2

        def read():
            try:
                bus.read(0x20, 1)
            except BaseException as error:
                errors.append(error)

        def close():
            closing.set()
            try:
                bus.close()
            except BaseException as error:
                errors.append(error)

        bus._ioctl = ioctl
        reader, closer = threading.Thread(target=read), threading.Thread(target=close)
        with patch("edk.linux_i2c.os.close", side_effect=lambda _: closed.set()) as close_fd:
            reader.start()
            try:
                self.assertTrue(entered.wait(2))
                closer.start()
                self.assertTrue(closing.wait(2))
                self.assertFalse(closed.wait(0.05))
            finally:
                release.set()
                reader.join(2)
                if closer.ident is not None:
                    closer.join(2)
            self.assertFalse(reader.is_alive())
            self.assertFalse(closer.is_alive())
            self.assertFalse(errors)
            close_fd.assert_called_once_with(123)
        self.assertEqual(bus._fd, -1)
        with self.assertRaises(ValueError):
            bus.read(0x20, 1)

    def test_concurrent_close_closes_descriptor_only_once(self):
        bus = transport()
        barrier = threading.Barrier(9)
        errors = []

        def close():
            try:
                barrier.wait(2)
                bus.close()
            except BaseException as error:
                errors.append(error)

        threads = [threading.Thread(target=close) for _ in range(8)]
        with patch("edk.linux_i2c.os.close") as close_fd:
            for thread in threads:
                thread.start()
            barrier.wait(2)
            for thread in threads:
                thread.join(2)
            self.assertFalse(any(thread.is_alive() for thread in threads))
            self.assertFalse(errors)
            close_fd.assert_called_once_with(123)

    def test_close_error_does_not_retry_a_reusable_descriptor(self):
        bus = transport()
        with patch("edk.linux_i2c.os.close", side_effect=OSError("close failed")) as close_fd:
            with self.assertRaises(OSError):
                bus.close()
            bus.close()
            close_fd.assert_called_once_with(123)
        self.assertEqual(bus._fd, -1)

    def test_adapter_minor_must_match_selected_path_before_any_ioctl(self):
        import fcntl

        info = MagicMock(st_mode=stat.S_IFCHR, st_rdev=os.makedev(89, 2))
        with patch("edk.linux_i2c.sys.platform", "linux"), \
                patch("edk.linux_i2c.os.open", return_value=123), \
                patch("edk.linux_i2c.os.fstat", return_value=info), \
                patch("edk.linux_i2c.os.close") as closed, \
                patch.object(fcntl, "flock") as flock, \
                patch.object(fcntl, "ioctl") as ioctl:
            with self.assertRaises(ValueError):
                LinuxI2C("/dev/i2c-1")
            closed.assert_called_once_with(123)
            flock.assert_not_called()
            ioctl.assert_not_called()


if __name__ == "__main__":
    unittest.main()
