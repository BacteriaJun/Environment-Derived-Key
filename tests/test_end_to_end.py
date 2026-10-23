import secrets
import unittest
from edk.environment import canonicalize, EnvironmentUnavailable
from edk.shamir import split, recover, repair_share
from edk.volatile import VolatileNode, NodeUnavailable
from edk.derivation import derive_pin


class EndToEndTests(unittest.TestCase):
    def test_quorum_repair_and_environment_dependency(self):
        environment = canonicalize([i % 64 for i in range(40)])
        salt = secrets.token_bytes(32)
        original = secrets.token_bytes(32)
        nodes = [VolatileNode.provision(s) for s in split(original)]
        def read(indices, env=environment):
            secret = recover([nodes[i-1].read() for i in indices])
            return derive_pin(env, secret, salt=salt, device_id="example-keypad")
        expected = read((1, 2, 3))
        self.assertEqual(read((2, 5, 6)), expected)
        nodes[1].expire()
        with self.assertRaises(NodeUnavailable):
            read((1, 2, 3))
        nodes[1].reprovision(repair_share(
            [nodes[0].read(), nodes[2].read(), nodes[3].read()], missing_index=2))
        self.assertEqual(read((1, 2, 3)), expected)
        with self.assertRaises(EnvironmentUnavailable):
            canonicalize([None] + [i % 64 for i in range(1, 40)])
        changed = bytearray(environment)
        changed[0] = (changed[0] + 1) % 64
        self.assertNotEqual(read((1, 2, 3), bytes(changed)), expected)


if __name__ == "__main__":
    unittest.main()
