import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from knowledge_base import (
    GenerationRunNotFound,
    KnowledgeBase,
    KnowledgeBaseError,
    KnowledgeEntryNotFound,
)


class KnowledgeBaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.store = KnowledgeBase(Path(self.temporary.name) / "knowledge.db")

    def tearDown(self):
        self.temporary.cleanup()

    def test_seeds_search_and_context_usage(self):
        stats = self.store.stats()
        self.assertEqual(stats["entries"], 5)
        self.assertEqual(stats["active_entries"], 5)

        entries = self.store.retrieve("手机封面构图", {"general", "image"})
        self.assertEqual(entries[0]["kind"], "image")
        context = self.store.context(entries)
        self.assertIn("本地知识库参考", context)
        self.assertIn("移动端封面构图", context)
        self.assertGreater(self.store.stats()["uses"], 0)

    def test_entry_lifecycle_and_validation(self):
        created = self.store.create_entry(
            "note",
            "餐饮探店表达",
            "描述菜品时使用可观察的口感与分量，不代替读者作结论。",
            ["餐饮", "探店", "餐饮"],
            70,
            "admin-id",
        )
        self.assertEqual(created["tags"], ["餐饮", "探店"])

        updated = self.store.update_entry(
            created["id"],
            "note",
            "餐饮内容表达",
            created["content"],
            created["tags"],
            85,
            False,
        )
        self.assertFalse(updated["active"])
        self.assertEqual(updated["priority"], 85)
        self.store.delete_entry(created["id"])
        with self.assertRaises(KnowledgeEntryNotFound):
            self.store.delete_entry(created["id"])
        with self.assertRaises(KnowledgeBaseError):
            self.store.create_entry("unknown", "x", "y", [], 50, None)

    def test_generation_feedback_can_promote_reusable_lesson(self):
        run_id = self.store.record_run(
            "user-1",
            "create",
            True,
            "秋日穿搭",
            "自然光",
            "生成的笔记",
            ["AI生成/example.png"],
            ["seed-image-mobile-composition"],
            "demo-model",
        )
        result = self.store.add_feedback(
            run_id,
            "user-1",
            False,
            5,
            "这次构图清楚",
            "人物主体占画面约三分之二时，手机端辨识度更好。",
        )
        self.assertTrue(result["knowledge_entry"]["active"])
        self.assertEqual(result["knowledge_entry"]["kind"], "image")
        self.assertEqual(self.store.stats()["rated_runs"], 1)

        with self.assertRaises(GenerationRunNotFound):
            self.store.add_feedback(run_id, "another-user", False, 4, "", "")

        with self.store._connection() as connection:
            normalized = connection.execute(
                "SELECT COUNT(*) FROM generation_records WHERE id = ?", (run_id,)
            ).fetchone()[0]
            feedback = connection.execute(
                "SELECT rating, reusable_lesson FROM generation_feedback WHERE record_id = ?",
                (run_id,),
            ).fetchone()
        self.assertEqual(normalized, 1)
        self.assertEqual(feedback[0], 5)
        self.assertIn("手机端辨识度", feedback[1])

    def test_corpus_import_search_retrieval_and_context(self):
        export_root = Path(self.temporary.name) / "feishu_export"
        image_root = export_root / "images"
        image_root.mkdir(parents=True)
        (image_root / "1.png").write_bytes(b"example-image")
        export_path = export_root / "entries.json"
        export_path.write_text(
            json.dumps(
                {
                    "title": "爆款选品库",
                    "entries": [
                        {
                            "type": "product",
                            "number": 1,
                            "record_id": "cup-record",
                            "title": "陶瓷马克杯案例",
                            "name": "陶瓷马克杯",
                            "add_to_cart_24h": 680,
                            "paragraphs": [
                                "帐号亮点：【低粉爆款】【素材好拍】",
                                "居家办公场景用桌面凌乱切入，展示杯身细节。",
                            ],
                            "highlights": ["【低粉爆款】【素材好拍】"],
                            "source": "https://example.com/source",
                            "product_urls": ["https://example.com/product"],
                            "followers_as_written": "326",
                            "sales_as_written": "1200",
                            "images": [{"local_path": "images/1.png"}],
                        },
                        {
                            "type": "product",
                            "number": 2,
                            "record_id": "bag-record",
                            "title": "通勤收纳包案例",
                            "name": "通勤收纳包",
                            "add_to_cart_24h": 210,
                            "paragraphs": ["通勤人群需要轻便分区收纳。"],
                            "highlights": ["【解决痛点】"],
                            "images": [],
                        },
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        imported = self.store.import_corpus(export_path)
        self.assertEqual(imported["entries"], 2)
        self.assertEqual(self.store.stats()["corpus_entries"], 2)
        listed = self.store.list_corpus("马克杯")
        self.assertEqual(listed["total"], 1)
        self.assertEqual(listed["items"][0]["tags"], ["低粉爆款", "素材好拍"])
        detail = self.store.get_corpus_entry(listed["items"][0]["id"])
        self.assertEqual(detail["image_paths"], ["images/1.png"])

        retrieved = self.store.retrieve_corpus("居家办公陶瓷杯", limit=1)
        self.assertEqual(retrieved[0]["product_name"], "陶瓷马克杯")
        context = self.store.corpus_context(retrieved)
        self.assertIn("不得复制原文", context)
        self.assertIn("陶瓷马克杯", context)
        refreshed = self.store.get_corpus_entry(retrieved[0]["id"])
        self.assertEqual(refreshed["use_count"], 1)

    def test_generation_history_is_scoped_and_reusable(self):
        run_id = self.store.record_run(
            "user-1",
            "rewrite:mengge-2",
            False,
            "参考正文",
            "保持真实",
            "生成正文",
            [],
            ["seed-note-structure"],
            "demo-model",
            {"copywriting_mode": "2", "product_name": "马克杯"},
            ["corpus-1"],
        )
        own = self.store.list_runs("user-1", False)
        self.assertEqual(own["total"], 1)
        self.assertEqual(own["items"][0]["title"], "马克杯")
        self.assertEqual(self.store.list_runs("user-2", False)["total"], 0)
        detail = self.store.get_run(run_id, "admin", True)
        self.assertEqual(detail["request_payload"]["copywriting_mode"], "2")
        self.assertEqual(detail["corpus_ids"], ["corpus-1"])
        with self.assertRaises(GenerationRunNotFound):
            self.store.delete_run(run_id, "user-2", False)
        self.store.delete_run(run_id, "user-1", False)
        with self.assertRaises(GenerationRunNotFound):
            self.store.get_run(run_id, "user-1", False)

    def test_existing_generation_table_is_migrated(self):
        legacy_path = Path(self.temporary.name) / "legacy.db"
        connection = sqlite3.connect(legacy_path)
        try:
            connection.executescript(
                """
                CREATE TABLE generation_runs (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, mode TEXT NOT NULL,
                    generated_image INTEGER NOT NULL DEFAULT 0,
                    source_text TEXT NOT NULL, instructions TEXT NOT NULL,
                    output_text TEXT NOT NULL, image_paths TEXT NOT NULL DEFAULT '[]',
                    knowledge_ids TEXT NOT NULL DEFAULT '[]', model TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL, rating INTEGER,
                    feedback TEXT NOT NULL DEFAULT '', reusable_lesson TEXT NOT NULL DEFAULT '',
                    feedback_at INTEGER
                );
                INSERT INTO generation_runs(
                    id, user_id, mode, source_text, instructions, output_text,
                    image_paths, knowledge_ids, model, created_at
                ) VALUES ('legacy-run', 'user-1', 'rewrite', '旧输入', '', '旧输出',
                          '[]', '[]', 'old-model', 1);
                """
            )
            connection.commit()
        finally:
            connection.close()
        migrated = KnowledgeBase(legacy_path)
        run = migrated.get_run("legacy-run", "user-1", False)
        self.assertEqual(run["output_text"], "旧输出")
        self.assertEqual(run["request_payload"], {})
        self.assertEqual(run["corpus_ids"], [])
        with migrated._connection() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM generation_records WHERE id='legacy-run'"
                ).fetchone()[0],
                1,
            )
        self.assertEqual(migrated.stats()["history_schema_version"], 2)


if __name__ == "__main__":
    unittest.main()
