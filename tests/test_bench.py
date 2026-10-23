import contextlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from edk.__main__ import main
from edk.bench import BenchToken, check_test, doctor_report, prepare_test, public_test_image
from edk.jsonio import encode_document
from edk.linux_i2c import LinuxI2C
from edk.native_abi import check_native_abi, expected_layout, layout_matches
from edk.shamir import Share
from edk.sram import MCP7940N, MemoryRegisterBus, RTCWKDAY, decode_share, encode_share


def token(nonce="a" * 32):
    return BenchToken(nonce, "2000-01-01T00:00:00.000000Z")


class BenchTests(unittest.TestCase):
    def test_public_token_strict_roundtrip_and_image_domain(self):
        original = token()
        image = public_test_image(original)
        self.assertEqual(len(image), 64)
        self.assertEqual(image[:4], b"EDKT")
        self.assertNotEqual(image, public_test_image(token("b" * 32)))
        with self.assertRaises(ValueError):
            decode_share(image)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "token.json"
            path.write_bytes(encode_document(original.to_dict()))
            self.assertEqual(BenchToken.load(path), original)
            bad = original.to_dict()
            bad["share"] = "SENSITIVE-SENTINEL"
            path.write_bytes(encode_document(bad))
            with self.assertRaises(ValueError):
                BenchToken.load(path)
        for bad in ("", "A" * 32, "../escape", None):
            with self.assertRaises(ValueError):
                token(bad)

    def test_prepare_read_only_check_and_observed_loss(self):
        bus = MemoryRegisterBus()
        device = MCP7940N(bus)
        prepare_test(device, token())
        self.assertTrue(all(register >= 0x20 for register, _ in bus.writes))
        bus.record_power_failure()
        before = len(bus.writes)
        report = check_test(device, token(), source="synthetic_bus", operator_vcc_off_seconds=60)
        self.assertTrue(report["matches_public_pattern"])
        self.assertTrue(report["status_after"]["power_failure_recorded"])
        self.assertEqual(len(bus.writes), before)
        self.assertEqual(report["operator_vcc_off_seconds"], 60)
        for field in ("actual_bytes", "actual_hash", "share", "pin", "key"):
            self.assertNotIn(field, report)
        bus.expire()
        self.assertFalse(check_test(device, token(), source="synthetic_bus")["matches_public_pattern"])

    def test_wrong_public_token_is_not_a_match(self):
        device = MCP7940N(MemoryRegisterBus())
        prepare_test(device, token())
        self.assertFalse(check_test(device, token("b" * 32), source="synthetic_bus")["matches_public_pattern"])

    def test_edk_share_even_corrupted_is_never_overwritten_or_compared(self):
        bus = MemoryRegisterBus()
        image = encode_share(Share(1, b"G" * 16, b"S" * 32))
        for corrupted in (image, image[:56] + bytes(4) + image[60:]):
            bus.write(0x20, corrupted)
            before = len(bus.writes)
            with self.assertRaises(ValueError):
                prepare_test(MCP7940N(bus), token(), initialize_unrecognized=True)
            with self.assertRaises(ValueError):
                check_test(MCP7940N(bus), token(), source="synthetic_bus")
            self.assertEqual(len(bus.writes), before)

    def test_existing_public_test_can_be_replaced_but_unknown_needs_option(self):
        bus = MemoryRegisterBus()
        device = MCP7940N(bus)
        bus.write(0x20, b"x" * 64)
        with self.assertRaises(ValueError):
            prepare_test(device, token())
        prepare_test(device, token(), initialize_unrecognized=True)
        prepare_test(device, token("b" * 32))
        self.assertTrue(check_test(device, token("b" * 32), source="synthetic_bus")["matches_public_pattern"])

    def test_no_backup_and_nonfinite_duration_fail_before_mutation(self):
        bus = MemoryRegisterBus()
        bus.write(RTCWKDAY, b"\x01")
        before = len(bus.writes)
        with self.assertRaises(ValueError):
            prepare_test(MCP7940N(bus), token())
        self.assertEqual(len(bus.writes), before)
        for invalid in (float("nan"), float("inf"), -1, True):
            with self.assertRaises(ValueError):
                check_test(MCP7940N(bus), token(), source="synthetic_bus", operator_vcc_off_seconds=invalid)

    def test_status_change_is_reported_without_clearing_flags(self):
        class ChangingBus(MemoryRegisterBus):
            change = False

            def read(self, register, length):
                data = super().read(register, length)
                if self.change and register == 0x20 and length == 64:
                    self.record_power_failure()
                return data
        bus = ChangingBus()
        device = MCP7940N(bus)
        prepare_test(device, token())
        bus.change = True
        self.assertTrue(check_test(device, token(), source="synthetic_bus")["status_changed_during_read"])

    def test_all_interrupted_public_pattern_prefixes_are_nonmatches(self):
        class InterruptBus(MemoryRegisterBus):
            def __init__(self, budget):
                super().__init__()
                self.budget = budget

            def write(self, register, data):
                for offset, value in enumerate(data):
                    if not self.budget:
                        raise OSError("simulated interruption")
                    super().write(register + offset, bytes([value]))
                    self.budget -= 1
        for budget in range(68):
            device = MCP7940N(InterruptBus(budget))
            with self.subTest(prefix=budget), self.assertRaises(OSError):
                prepare_test(device, token())
            self.assertFalse(check_test(device, token(), source="synthetic_bus")["matches_public_pattern"])

    def test_doctor_and_native_unavailable_check_do_not_open_adapters(self):
        with patch("edk.linux_i2c.os.open") as opened, patch("edk.bench.sys.platform", "darwin"):
            report = doctor_report()
            self.assertFalse(report["device_transactions_performed"])
            self.assertFalse(report["host_preflight_passed"])
            self.assertFalse(check_native_abi()["checked"])
            opened.assert_not_called()
        with self.assertRaises(ValueError):
            doctor_report("/tmp/not-an-adapter")

    def test_native_layout_comparison_is_strict(self):
        self.assertTrue(layout_matches(expected_layout()))
        bad = expected_layout()
        bad["buffer_offset"] += 1
        self.assertFalse(layout_matches(bad))
        bad = expected_layout()
        bad["I2C_M_RD"] = True
        self.assertFalse(layout_matches(bad))

    def test_linux_constructor_capabilities_major_and_cleanup_with_mocks(self):
        import fcntl
        info = MagicMock(st_mode=stat.S_IFCHR, st_rdev=os.makedev(89, 1))

        def ioctl(fd, request, value, *args):
            if request == 0x0705:
                value[0] = 1
            return 0
        with patch("edk.linux_i2c.sys.platform", "linux"), \
                patch("edk.linux_i2c.os.open", return_value=123), \
                patch("edk.linux_i2c.os.fstat", return_value=info), \
                patch("edk.linux_i2c.os.close") as closed, patch.object(fcntl, "flock"), \
                patch.object(fcntl, "ioctl", side_effect=ioctl), patch("edk.linux_i2c.ctypes.CDLL"):
            with LinuxI2C("/dev/i2c-1") as bus:
                self.assertEqual(bus.identity, info.st_rdev)
            closed.assert_called_once_with(123)
            with self.assertRaises(ValueError):
                bus.read(0x20, 1)
        info.st_rdev = os.makedev(1, 3)
        with patch("edk.linux_i2c.sys.platform", "linux"), \
                patch("edk.linux_i2c.os.open", return_value=123), \
                patch("edk.linux_i2c.os.fstat", return_value=info), \
                patch("edk.linux_i2c.os.close") as closed:
            with self.assertRaises(ValueError):
                LinuxI2C("/dev/i2c-1")
            closed.assert_called_once_with(123)

    def test_bench_cli_scope_and_synthetic_demo(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            main(["bench-demo"])
        self.assertIn("SIMULATED", out.getvalue())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "token.json"
            with patch("edk.linux_i2c.os.open") as opened, \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    main(["bench-prepare", "--bus", "/dev/i2c-1", "--token", str(path)])
            opened.assert_not_called()
            self.assertFalse(path.exists())
            class Adapter(MemoryRegisterBus):
                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    pass
            adapter = Adapter()
            with patch("edk.research_cli.sys.platform", "linux"), \
                    patch("edk.linux_i2c.LinuxI2C", return_value=adapter), \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                main(["bench-prepare", "--bus", "/dev/i2c-1", "--token", str(path), "--laboratory-hardware"])
                report_path = Path(directory) / "retained.json"
                main(["bench-check", "--bus", "/dev/i2c-1", "--token", str(path),
                      "--report", str(report_path), "--laboratory-hardware"])
                self.assertTrue(json.loads(report_path.read_text())["matches_public_pattern"])
                adapter.expire()
                report_path = Path(directory) / "lost.json"
                with self.assertRaises(SystemExit) as stopped:
                    main(["bench-check", "--bus", "/dev/i2c-1", "--token", str(path),
                          "--report", str(report_path), "--laboratory-hardware"])
                self.assertEqual(stopped.exception.code, 3)
                self.assertFalse(json.loads(report_path.read_text())["matches_public_pattern"])

    def test_existing_token_blocks_physical_prepare_before_adapter_opens(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "token.json"
            path.write_bytes(encode_document(token().to_dict()))
            with patch("edk.research_cli.sys.platform", "linux"), \
                    patch("edk.linux_i2c.LinuxI2C") as adapter, \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    main(["bench-prepare", "--bus", "/dev/i2c-1", "--token", str(path), "--laboratory-hardware"])
            adapter.assert_not_called()


if __name__ == "__main__":
    unittest.main()
