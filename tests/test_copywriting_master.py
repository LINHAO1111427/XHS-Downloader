import unittest

from copywriting_master import (
    CopywritingBrief,
    CopywritingInputError,
    normalize_keywords,
)


class CopywritingMasterTests(unittest.TestCase):
    def test_mode_two_builds_fact_bounded_creative_prompt(self):
        brief = CopywritingBrief(
            mode="2",
            product_name="通勤帆布包",
            target_audience="上班族",
            selling_points="可放 14 英寸电脑；用户已确认",
            keywords=normalize_keywords(["通勤包", "通勤包"]),
        )
        brief.validate(has_reference=True)
        prompt = brief.prompt("对标笔记正文", "口语化")
        self.assertIn("模式 2", prompt)
        self.assertIn("重做第一屏", prompt)
        self.assertIn("不编造体验", prompt)
        self.assertIn("通勤包", prompt)

    def test_each_mode_enforces_its_material_requirements(self):
        with self.assertRaisesRegex(CopywritingInputError, "目标人群"):
            CopywritingBrief(
                mode="3",
                product_name="产品",
                selling_points="卖点",
                pain_points="痛点",
            ).validate(has_reference=True)
        with self.assertRaisesRegex(CopywritingInputError, "产品用途"):
            CopywritingBrief(
                mode="5",
                product_name="产品",
                target_audience="学生",
            ).validate(has_reference=True)

    def test_close_rewrite_requires_owned_proven_post_and_keywords(self):
        brief = CopywritingBrief(mode="1", product_name="同款产品")
        with self.assertRaisesRegex(CopywritingInputError, "自己账号"):
            brief.validate(has_reference=True)
        with self.assertRaisesRegex(CopywritingInputError, "搜索关键词"):
            CopywritingBrief(
                mode="1",
                product_name="同款产品",
                own_post_confirmed=True,
            ).validate(has_reference=True)

    def test_mode_four_image_brief_uses_product_not_reference_copy(self):
        brief = CopywritingBrief(
            mode="4",
            product_name="陶瓷杯",
            target_audience="居家办公人群",
            selling_points="白色陶瓷，容量 350ml",
            pain_points="桌面杯子容易显乱",
            cover_description="自然光桌面俯拍",
        )
        brief.validate(has_reference=True)
        image_brief = brief.image_brief("生成后的正文")
        self.assertIn("陶瓷杯", image_brief)
        self.assertIn("自然光桌面俯拍", image_brief)
        self.assertIn("生成后的正文", image_brief)


if __name__ == "__main__":
    unittest.main()
