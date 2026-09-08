import time
import unittest

from batch_image_edit import BatchImageEditManager


class BatchImageEditManagerTests(unittest.TestCase):
    def test_submit_updates_background_task(self):
        manager = BatchImageEditManager()
        try:
            def worker(task_id):
                manager.update(task_id, state="processing", completed=1, outputs=[{"path": "x.png"}])
                manager.update(task_id, state="success", completed=1, finished_at=int(time.time()))

            task = manager.submit(1, worker)
            for _ in range(20):
                current = manager.snapshot()[0]
                if current["state"] == "success":
                    break
                time.sleep(0.01)
            self.assertEqual(current["state"], "success")
            self.assertEqual(current["outputs"][0]["path"], "x.png")
            owned = manager.submit(1, lambda task_id: None, owner_id="user-a")
            self.assertEqual(len(manager.snapshot("user-a")), 1)
            self.assertEqual(manager.snapshot("user-b"), [])
        finally:
            manager.shutdown()


if __name__ == "__main__":
    unittest.main()
