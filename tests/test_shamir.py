import itertools
import secrets
import unittest
from dataclasses import replace
from edk.shamir import Share, split, recover, repair_share
from edk.volatile import VolatileNode, NodeUnavailable


class ShamirTests(unittest.TestCase):
    def setUp(self):
        self.master = secrets.token_bytes(32)
        self.shares = split(self.master, threshold=3, count=6)

    def test_all_twenty_three_share_quorums(self):
        for subset in itertools.combinations(self.shares, 3):
            self.assertEqual(recover(subset), self.master)

    def test_less_than_threshold(self):
        for count in (0, 1, 2):
            with self.assertRaises(ValueError):
                recover(self.shares[:count])

    def test_duplicate_index_rejected(self):
        with self.assertRaises(ValueError):
            recover([self.shares[0], self.shares[0], self.shares[1]])

    def test_mixed_generation_rejected(self):
        foreign = split(secrets.token_bytes(32))[2]
        with self.assertRaises(ValueError):
            recover([self.shares[0], self.shares[1], foreign])

    def test_extra_share_consistency(self):
        corrupt = replace(self.shares[3], payload=bytes(32))
        with self.assertRaises(ValueError):
            recover(self.shares[:3] + [corrupt])

    def test_repair_reproduces_original(self):
        replacement = repair_share(self.shares[:3], missing_index=5)
        self.assertEqual(replacement, self.shares[4])

    def test_node_expire_and_reprovision(self):
        node = VolatileNode.provision(self.shares[4])
        node.expire()
        with self.assertRaises(NodeUnavailable):
            node.read()
        node.reprovision(repair_share(self.shares[:3], missing_index=5))
        self.assertEqual(node.read(), self.shares[4])


if __name__ == "__main__":
    unittest.main()
