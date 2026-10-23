"""Only public RFC vectors and deliberately synthetic compatibility fixtures."""

import unittest
from unittest.mock import patch

from edk.derivation import PIN_SPACE, _accepted_pin, derive_pin, hkdf_expand, hkdf_extract


class ReviewedDerivationTests(unittest.TestCase):
    def derive(self, **overrides):
        params = dict(environment=bytes(range(40)), volatile_secret=bytes(range(32)),
                      salt=bytes(range(32)), device_id="KP200-TEST")
        params.update(overrides)
        return derive_pin(**params)

    def test_rfc5869_sha256_long_vector(self):
        # RFC 5869 Appendix A.2, https://www.rfc-editor.org/rfc/rfc5869#appendix-A.2
        prk = hkdf_extract(bytes(range(0x60, 0xB0)), bytes(range(0x50)))
        self.assertEqual(prk.hex(), "06a6b88c5853361a06104c9ceb35b45c"
                         "ef760014904671014a193f40c15fc244")
        self.assertEqual(hkdf_expand(prk, bytes(range(0xB0, 0x100)), 82).hex(),
                         "b11e398dc80327a1c8e7f78c596a4934"
                         "4f012eda2d4efad8a050cc4c19afa97c"
                         "59045a99cac7827271cb41c65e590e09"
                         "da3275600c2f09b8367793a9aca3db71"
                         "cc30c58179ec3e87c14c01d5c1f3434f1d87")

    def test_rfc5869_sha256_empty_salt_context(self):
        # RFC 5869 Appendix A.3.
        prk = hkdf_extract(b"", b"\x0b" * 22)
        self.assertEqual(prk.hex(), "19ef24a32c717b167f33a91d6f648bdf"
                         "96596776afdb6377ac434c1c293ccb04")
        self.assertEqual(hkdf_expand(prk, b"", 42).hex(),
                         "8da4e775a563c18f715f802a063c5a31"
                         "b8a11f5c5ee1879ec3454e5f3c738d2d9d201395faa4b61a96c8")

    def test_legacy_synthetic_pin_vectors_are_unchanged(self):
        self.assertEqual(self.derive(), "548823446665")
        self.assertEqual(self.derive(device_id="KP200-OTHER"), "616929327638")
        self.assertEqual(self.derive(environment=b"\x00" * 40,
                                     volatile_secret=b"\xff" * 32,
                                     salt=b"\x55" * 32, device_id="合成设备"), "318216045395")

    def test_both_sources_and_public_salt_matter(self):
        with self.assertRaises(ValueError):
            self.derive(volatile_secret=b"")
        self.assertNotEqual(self.derive(), self.derive(salt=b"\xff" * 32))

    def test_bad_types_lengths_and_utf8_are_rejected(self):
        for name, values in {
            "environment": (None, "secret", [], bytearray(40), b"", b"x" * 65536),
            "volatile_secret": (None, "x" * 32, bytearray(32), b"x" * 31, b"x" * 33),
            "salt": (None, "x" * 32, bytearray(32), b"x" * 31, b"x" * 33),
            "device_id": (None, b"device", "", "x" * 256, "界" * 86, "\ud800"),
        }.items():
            for value in values:
                with self.subTest(field=name), self.assertRaises(ValueError):
                    self.derive(**{name: value})

    def test_utf8_context_length_boundary(self):
        self.assertEqual(len(self.derive(device_id="界" * 85)), 12)

    def test_hkdf_output_limits_and_empty_output(self):
        self.assertEqual(hkdf_expand(bytes(32), b"", 0), b"")
        self.assertEqual(len(hkdf_expand(bytes(32), b"", 8160)), 8160)
        for length in (-1, 8161, True, 1.5, None):
            with self.assertRaises(ValueError):
                hkdf_expand(bytes(32), b"", length)
        for prk, info in ((None, b""), (bytes(31), b""), (bytes(32), "x")):
            with self.assertRaises(ValueError):
                hkdf_expand(prk, info, 1)
        for salt, ikm in ((None, b""), (b"", None), ("", b"")):
            with self.assertRaises(ValueError):
                hkdf_extract(salt, ikm)

    def test_all_forbidden_12_digit_patterns(self):
        forbidden = {str(digit) * 12 for digit in range(10)}
        forbidden.update("".join(str((start + step * j) % 10) for j in range(12))
                         for step in (-1, 1) for start in range(10))
        self.assertEqual(len(forbidden), 30)
        for pin in forbidden:
            self.assertFalse(_accepted_pin(pin))
        for invalid in ("", "123", "x" * 12, "１" * 12, None):
            self.assertFalse(_accepted_pin(invalid))
        self.assertTrue(_accepted_pin("000000000042"))

    def test_rejection_sampling_rejects_cutoff_and_disallowed_patterns(self):
        cutoff = (1 << 64) - ((1 << 64) % PIN_SPACE)
        values = (cutoff, 0, 123456789012, 987654321098, PIN_SPACE + 42)
        with patch("edk.derivation.hkdf_expand",
                   side_effect=[v.to_bytes(8, "big") for v in values]) as expand:
            self.assertEqual(self.derive(), "000000000042")
            counters = [int.from_bytes(call.args[1][-4:], "big") for call in expand.call_args_list]
            self.assertEqual(counters, list(range(5)))

    def test_exhaustion_never_returns_a_pin(self):
        with patch("edk.derivation.hkdf_expand", return_value=bytes(8)):
            with self.assertRaises(RuntimeError):
                self.derive()


if __name__ == "__main__":
    unittest.main()
