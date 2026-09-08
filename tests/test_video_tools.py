import tempfile
import unittest
from pathlib import Path

from video_tools import VideoToolError, duplicate_groups, remix_videos


class VideoToolsTests(unittest.TestCase):
    def test_duplicate_groups_detects_identical_videos(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "a.mp4").write_bytes(b"same")
            (root / "b.mp4").write_bytes(b"same")
            (root / "c.mp4").write_bytes(b"different")
            groups = duplicate_groups(root)
            self.assertEqual(len(groups), 1)
            self.assertEqual(groups[0]["duplicate_count"], 1)
            self.assertEqual(set(groups[0]["files"]), {"a.mp4", "b.mp4"})

    def test_remix_validates_speed_and_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "a.mp4"
            source.write_bytes(b"not-a-video")
            with self.assertRaises(VideoToolError):
                remix_videos([], root / "out.mp4")
            with self.assertRaises(VideoToolError):
                remix_videos([source], root / "out.mp4", speed=3)


if __name__ == "__main__":
    unittest.main()
