import unittest
from edk.derivation import hkdf_extract, hkdf_expand, derive_pin


class DerivationTests(unittest.TestCase):
    def test_rfc5869_test_case_one(self):
        ikm = bytes.fromhex("0b" * 22)
        salt = bytes.fromhex("000102030405060708090a0b0c")
        info = bytes.fromhex("f0f1f2f3f4f5f6f7f8f9")
        prk = hkdf_extract(salt, ikm)
        self.assertEqual(prk.hex(), "077709362c2e32df0ddc3f0dc47bba63"
                         "90b6c73bb50f9c3122ec844ad7c2b3e5")
        okm = hkdf_expand(prk, info, 42)
        self.assertEqual(okm.hex(), "3cb25f25faacd57a90434f64d0362f2a"
                         "2d2d0a90cf1a5a4c5db02d56ecc4c5bf34007208d5b887185865")

    def test_env_and_volatile_are_both_required(self):
        env = bytes(range(40))
        volatile = bytes(range(32))
        salt = bytes(range(32))
        pin = derive_pin(env, volatile, salt=salt, device_id="KP200-TEST")
        self.assertEqual(len(pin), 12)
        self.assertTrue(pin.isdigit())
        self.assertEqual(pin, derive_pin(env, volatile, salt=salt, device_id="KP200-TEST"))
        changed_env = bytearray(env)
        changed_env[0] ^= 1
        self.assertNotEqual(pin, derive_pin(bytes(changed_env), volatile, salt=salt, device_id="KP200-TEST"))
        changed_vol = bytearray(volatile)
        changed_vol[0] ^= 1
        self.assertNotEqual(pin, derive_pin(env, bytes(changed_vol), salt=salt, device_id="KP200-TEST"))
        self.assertNotEqual(pin, derive_pin(env, volatile, salt=salt, device_id="KP200-OTHER"))
        with self.assertRaises(ValueError):
            derive_pin(b"", volatile, salt=salt, device_id="KP200-TEST")


if __name__ == "__main__":
    unittest.main()
