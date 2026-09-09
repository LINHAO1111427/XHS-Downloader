import tempfile
import unittest
from pathlib import Path

from billing import BillingStore, QuotaExceeded


class BillingStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.store = BillingStore(Path(self.temporary.name) / "billing.db")

    def tearDown(self):
        self.temporary.cleanup()

    def test_daily_free_credits_and_idempotency(self):
        first = self.store.consume("u1", "text", 1, "req-1")
        self.assertEqual(first["free_units"], 1)
        repeated = self.store.consume("u1", "text", 1, "req-1")
        self.assertEqual(repeated["status"], "already_consumed")
        self.assertEqual(self.store.usage("u1")["free_remaining"], 19)

    def test_paid_credits_after_free_quota(self):
        for index in range(20):
            self.store.consume("u1", "text", 1, f"free-{index}")
        with self.assertRaises(QuotaExceeded) as raised:
            self.store.consume("u1", "text", 1, "over-limit")
        self.assertEqual(raised.exception.usage["available_units"], 0)
        self.store.grant("u1", 10)
        receipt = self.store.consume("u1", "text", 1, "paid-1")
        self.assertEqual(receipt["paid_units"], 1)
        self.assertEqual(self.store.usage("u1")["paid_credits"], 9)

    def test_image_cost_and_refund_restore_balance(self):
        receipt = self.store.consume("u1", "image", 5, "image-1")
        self.assertEqual(receipt["free_units"], 5)
        self.assertTrue(self.store.refund("u1", "image-1"))
        self.assertFalse(self.store.refund("u1", "image-1"))
        usage = self.store.usage("u1")
        self.assertEqual(usage["free_remaining"], 20)

    def test_plans_and_pending_order(self):
        order = self.store.create_order("u1", "starter")
        self.assertEqual(order["status"], "pending")
        self.assertEqual(order["credits"], 100)
        self.assertEqual(len(self.store.plans_payload()), 4)


if __name__ == "__main__":
    unittest.main()
