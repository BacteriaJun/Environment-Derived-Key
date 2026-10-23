import ctypes
from dataclasses import replace
import threading
import unittest
from unittest.mock import patch

from edk.formal_models import verify_models
from edk.linux_i2c import I2C_RDWR, LinuxI2C, _Transfer
from edk.shamir import Share, recover
from edk.sram import (MCP7940N, MemoryRegisterBus, PWRFAIL, RTCWKDAY, SRAM_START,
                      VBATEN, decode_share, encode_share, provision_six, repair_hardware_node)


class SRAMTests(unittest.TestCase):
    def setUp(self):
        self.share = Share(1, b"G" * 16, b"\x42" * 32)

    def test_record_layout_roundtrip_and_all_single_bit_errors(self):
        image = encode_share(self.share)
        self.assertEqual(len(image), 64)
        self.assertEqual(decode_share(image), self.share)
        for bit in range(512):
            corrupted = bytearray(image)
            corrupted[bit // 8] ^= 1 << (bit % 8)
            with self.subTest(bit=bit), self.assertRaises(ValueError):
                decode_share(bytes(corrupted))

    def test_checksum_is_not_authentication(self):
        forged = replace(self.share, payload=b"\xff" * 32)
        self.assertEqual(decode_share(encode_share(forged)), forged)
        self.assertNotEqual(forged, self.share)

    def test_program_readback_and_no_rtc_writes(self):
        bus = MemoryRegisterBus()
        device = MCP7940N(bus)
        device.write_share(self.share)
        self.assertEqual(device.read_share(), self.share)
        self.assertTrue(all(0x20 <= register and register + size <= 0x60 for register, size in bus.writes))
        with self.assertRaises(ValueError):
            device.write_share(self.share, initialize_unrecognized=True)
        self.assertNotIn("payload", repr(bus))

    def test_every_interrupted_program_prefix_is_rejected(self):
        class InterruptBus(MemoryRegisterBus):
            def __init__(self, budget):
                super().__init__()
                self.budget = budget

            def write(self, register, data):
                for offset, value in enumerate(data):
                    if self.budget == 0:
                        raise OSError("simulated power interruption")
                    super().write(register + offset, bytes([value]))
                    self.budget -= 1

        for prefix in range(68):
            bus = InterruptBus(prefix)
            device = MCP7940N(bus)
            with self.subTest(prefix=prefix), self.assertRaises(OSError):
                device.write_share(self.share)
            with self.assertRaises(ValueError):
                device.read_share()
        bus = InterruptBus(68)
        device = MCP7940N(bus)
        device.write_share(self.share)
        self.assertEqual(device.read_share(), self.share)

    def test_power_flags_and_backup_configuration(self):
        bus = MemoryRegisterBus()
        bus.write(RTCWKDAY, b"\x03")
        device = MCP7940N(bus)
        with self.assertRaises(ValueError):
            device.write_share(self.share)
        device.enable_backup()
        self.assertEqual(bus.read(RTCWKDAY, 1), bytes([3 | VBATEN]))
        bus.record_power_failure()
        before = len(bus.writes)
        with self.assertRaises(ValueError):
            device.enable_backup()
        with self.assertRaises(ValueError):
            device.read_share()
        self.assertEqual(before, len(bus.writes))

    def test_unrecognized_sram_requires_explicit_initialization(self):
        bus = MemoryRegisterBus()
        bus.write(SRAM_START, b"x" * 64)
        device = MCP7940N(bus)
        with self.assertRaises(ValueError):
            device.write_share(self.share)
        device.write_share(self.share, initialize_unrecognized=True)
        self.assertEqual(device.read_share(), self.share)

    def test_short_read_and_failed_body_verification_do_not_commit(self):
        class ShortBus(MemoryRegisterBus):
            def read(self, register, length):
                return super().read(register, length)[:-1]
        with self.assertRaises(OSError):
            MCP7940N(ShortBus()).read_share()

        class DroppingBus(MemoryRegisterBus):
            def write(self, register, data):
                if register != SRAM_START:
                    super().write(register, data)
        bus = DroppingBus()
        with self.assertRaises(OSError):
            MCP7940N(bus).write_share(self.share)
        with self.assertRaises(ValueError):
            decode_share(bus.read(SRAM_START, 64))

    def test_six_nodes_repair_and_duplicate_adapter_rejection(self):
        devices = [MCP7940N(MemoryRegisterBus()) for _ in range(6)]
        result = provision_six(devices)
        self.assertEqual(result["committed_nodes"], 6)
        shares = [d.read_share() for d in devices]
        self.assertEqual(recover(shares[:3]), recover(shares[3:]))
        replacement = MCP7940N(MemoryRegisterBus())
        repair_hardware_node(devices[:3], replacement, missing_index=5)
        self.assertEqual(replacement.read_share(), shares[4])
        with self.assertRaises(ValueError):
            provision_six([devices[0]] * 6)
        with self.assertRaises(ValueError):
            repair_hardware_node(devices[:3], devices[0], missing_index=5)

    def test_group_preflight_prevents_writes_if_a_node_is_occupied(self):
        devices = [MCP7940N(MemoryRegisterBus()) for _ in range(6)]
        devices[5].write_share(self.share)
        with self.assertRaises(ValueError):
            provision_six(devices)
        self.assertEqual(sum(len(d.bus.writes) for d in devices[:5]), 0)

    def test_linux_combined_transaction_abi_and_bounds_without_hardware(self):
        transport = object.__new__(LinuxI2C)
        transport.address, transport._fd = 0x6F, 123
        transport._lock = threading.RLock()
        transfers = []

        def ioctl(fd, request, pointer):
            transfer = ctypes.cast(pointer, ctypes.POINTER(_Transfer)).contents
            self.assertEqual((fd, request), (123, I2C_RDWR))
            transfers.append(transfer.count)
            first = transfer.messages[0]
            self.assertEqual(first.addr, 0x6F)
            self.assertEqual(first.buffer[0], SRAM_START)
            if transfer.count == 2:
                second = transfer.messages[1]
                self.assertEqual(second.flags, 1)
                for i in range(second.length):
                    second.buffer[i] = i
            return transfer.count

        transport._ioctl = ioctl
        self.assertEqual(transport.read(SRAM_START, 4), b"\x00\x01\x02\x03")
        transport.write(SRAM_START, b"\x42" * 32)
        self.assertEqual(transfers, [2, 1])
        for register, length in ((0x5F, 2), (0x1F, 2), (-1, 1), (True, 1), (0, 65)):
            with self.assertRaises(ValueError):
                transport.read(register, length)
        with self.assertRaises(ValueError):
            transport.write(0x1F, b"12")
        transport._ioctl = lambda *_: -1
        with self.assertRaises(OSError):
            transport.read(SRAM_START, 1)

    def test_linux_transport_does_not_open_on_other_operating_systems(self):
        with patch("edk.linux_i2c.sys.platform", "darwin"), patch("edk.linux_i2c.os.open") as opened:
            with self.assertRaises(RuntimeError):
                LinuxI2C("/dev/i2c-1")
            opened.assert_not_called()

    def test_bounded_formal_models(self):
        result = verify_models()
        self.assertTrue(result["all_invariants_hold"])
        self.assertEqual(result["gate_states"], 256)
        self.assertEqual(result["gf7_reconstruction_cases"], 6860)
        self.assertEqual(result["sram_write_prefixes"], 138)


if __name__ == "__main__":
    unittest.main()
