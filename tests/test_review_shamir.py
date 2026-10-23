"""Synthetic algebra fixtures and malformed-input regressions; no real shares."""

import itertools
import unittest
from dataclasses import replace
from unittest.mock import patch

from edk.shamir import Share, _inv, _mul, interpolate, recover, repair_share, split
from edk.volatile import VolatileNode


def polynomial_product(a: int, b: int) -> int:
    """Independent carryless polynomial multiplication then long division."""
    product = 0
    for bit in range(8):
        if (b >> bit) & 1:
            product ^= a << bit
    while product.bit_length() > 8:
        product ^= 0x11B << (product.bit_length() - 9)
    return product


class ReviewedShamirTests(unittest.TestCase):
    def setUp(self):
        self.secret = b"\x42" * 32
        with patch("edk.shamir.secrets.token_bytes", side_effect=[
                b"G" * 16, b"\x13" * 32, b"\x87" * 32]):
            self.shares = split(self.secret)

    def test_complete_field_multiplication_table(self):
        for a in range(256):
            for b in range(256):
                self.assertEqual(_mul(a, b), polynomial_product(a, b))

    def test_all_nonzero_field_inverses(self):
        for a in range(1, 256):
            self.assertEqual(_mul(a, _inv(a)), 1)
        with self.assertRaises(ValueError):
            _inv(0)

    def test_fixed_polynomial_fixture(self):
        # f(x) = 0x42 + 0x13*x + 0x87*x^2 over GF(256), each of 32 bytes.
        for index, value in enumerate((0xD6, 0x4E, 0xDA, 0xA6), 1):
            self.assertEqual(self.shares[index - 1].payload, bytes([value]) * 32)
        for size in range(3, 7):
            for subset in itertools.combinations(self.shares, size):
                self.assertEqual(recover(subset), self.secret)

    def test_repair_every_coordinate_from_every_available_quorum(self):
        for missing in self.shares:
            others = [s for s in self.shares if s.index != missing.index]
            for quorum in itertools.combinations(others, 3):
                self.assertEqual(repair_share(quorum, missing_index=missing.index), missing)

    def test_split_rejects_bad_thresholds_and_counts(self):
        for threshold, count in ((True, 6), (3.0, 6), (0, 6), (1, 6),
                                 (7, 6), (3, True), (3, 6.0), (3, 256)):
            with self.subTest(threshold=threshold, count=count), self.assertRaises(ValueError):
                split(self.secret, threshold=threshold, count=count)

    def test_share_shape_rejected_at_construction(self):
        fields = (("index", 0), ("index", 256), ("index", True), ("index", 1.5),
                  ("generation", b"x" * 15), ("generation", "x" * 16),
                  ("payload", b"x" * 31), ("payload", b"x" * 33),
                  ("payload", bytearray(32)), ("threshold", 1), ("threshold", True))
        for name, value in fields:
            with self.subTest(field=name), self.assertRaises(ValueError):
                replace(self.shares[0], **{name: value})

    def test_recovery_threshold_override_is_rejected(self):
        for threshold in (0, 1, 2, -1, 256, True, 3.0, "3", None):
            with self.subTest(threshold=threshold), self.assertRaises(ValueError):
                recover(self.shares, threshold=threshold)

    def test_custom_threshold_roundtrip_including_node_and_repair(self):
        for threshold, count in ((2, 3), (4, 6), (6, 6)):
            shares = split(self.secret, threshold=threshold, count=count)
            nodes = [VolatileNode.provision(s) for s in shares]
            quorum = [n.read() for n in nodes[:threshold]]
            self.assertEqual(recover(quorum, threshold=threshold), self.secret)
            if count > threshold:
                self.assertEqual(repair_share(quorum, missing_index=count,
                                              threshold=threshold), shares[-1])
            with self.assertRaises(ValueError):
                recover(quorum[:-1], threshold=threshold)

    def test_mixed_threshold_metadata_is_rejected(self):
        changed = replace(self.shares[2], threshold=2)
        with self.assertRaises(ValueError):
            recover([*self.shares[:2], changed])

    def test_bad_coordinates_and_containers_are_rejected(self):
        for x in (-1, 256, True, 1.0, "1", None):
            with self.subTest(x=x), self.assertRaises(ValueError):
                interpolate(self.shares, x=x)
        for missing in (0, 256, True, 1.5, 1):
            with self.subTest(missing=missing), self.assertRaises(ValueError):
                repair_share(self.shares[:3], missing_index=missing)
        for invalid in (None, b"abc", "abc", iter(self.shares), [None] * 3):
            with self.assertRaises(ValueError):
                recover(invalid)

    def test_exact_quorum_payload_corruption_remains_unauthenticated(self):
        # This deliberately records a LIMITATION, not a successful integrity check.
        bad = replace(self.shares[0], payload=b"\x00" * 32)
        self.assertNotEqual(recover([bad, *self.shares[1:3]]), self.secret)
        with self.assertRaises(ValueError):
            recover([bad, *self.shares[1:4]])

    def test_node_repr_redacts_payload_and_generation(self):
        share = self.shares[0]
        node = VolatileNode.provision(share)
        for value in (repr(node), repr(share)):
            self.assertNotIn(repr(share.payload), value)
            self.assertNotIn(repr(share.generation), value)
            self.assertNotIn(repr(bytearray(share.payload)), value)

    def test_failed_node_update_preserves_existing_state(self):
        node = VolatileNode.provision(self.shares[0])
        for replacement in (None, self.shares[1], self.shares[0]):
            with self.assertRaises(ValueError):
                node.reprovision(replacement)
            self.assertEqual(node.read(), self.shares[0])
        node.expire()
        node.expire()
        self.assertFalse(node.alive)
        node.reprovision(self.shares[0])
        self.assertEqual(node.read(), self.shares[0])

    def test_malformed_node_memory_fails_on_read(self):
        node = VolatileNode.provision(self.shares[0])
        node._memory.pop()
        with self.assertRaises(ValueError):
            node.read()


if __name__ == "__main__":
    unittest.main()
