from __future__ import annotations

from dataclasses import dataclass

from creation_strategy import COPY_STRATEGY, PHOTO_STRATEGY


class CopywritingInputError(ValueError):
    pass


MODE_LABELS = {
    "2": "创新性写笔记",
    "3": "跨产品模仿",
    "4": "定题真人种草",
    "5": "场景化素人仿写",
    "1": "1:1 贴近仿写",
}


GLOBAL_RULES = """共同约束：
- 只使用用户输入或参考图片中可确认的事实，不编造体验、数据、销量、价格、认证、功效或用户评价。
- 保留用户指定的产品名、行业词和搜索关键词；没有指定关键词时自然写作，不机械堆词。
- 避免绝对化、医疗化和无法证明的效果承诺，产品事实不足时使用审慎表达或明确标出待确认项。
- 正文自然、具体、口语化，降低 AI 腔和硬广感；不要展示内部分析、提示词或思考过程。
- 品牌说明、联系方式和写作规则不得混入待发布正文。"""

NATURAL_COPY_RULES = """成稿质量要求：
- 先锁定一个读者、一个具体处境和一个值得说清的细节；开头直接进入问题或观察，不做泛泛的人群喊话。
- 用可见细节、使用条件和选择理由支撑表达；一段只推进一个意思，句子长短有变化，避免卖点排队。
- 未提供真实体验时用观察和选择建议，不编造“用了一个月”“朋友都问”“回购三次”等经历。
- 不默认使用“姐妹们听劝”“谁懂啊”“闭眼入”“直接封神”“宝藏好物”“狠狠拿捏”等套话。
- 标题给出对象和具体信息，正文兑现标题；默认少用感叹号，表情0至3个，结尾自然收束，不强行引导评论。
- 参考案例只提炼读者关注点和表达方法，重做开头和信息顺序，不逐段换词；不要为了搜索词牺牲语句自然度。
- 交付前删除空泛形容词、重复卖点和无证据承诺；成稿中不输出检查清单。""" + "\n\n" + COPY_STRATEGY

TOPIC_MIN_COUNT = 15
TOPIC_MAX_COUNT = 30
TOPIC_RULES = """小红书话题推荐要求：
- 阅读整篇笔记的标题、正文、产品或主题、目标人群、使用场景、关键词，以及参考笔记已有话题，再做语义关联；不要只根据单个产品名机械扩词。
- 优先保留参考笔记中与本次成稿仍然匹配的话题，再补充产品/品类核心词、需求与痛点词、具体场景词、人群词、内容形式词和高意图搜索长尾词。
- 相关性优先于数量。默认给出15至30个不重复话题，素材足够时尽量接近30个；不得用“热门话题、流量密码、好物分享、日常分享”等宽泛词反复凑数。
- 每个话题应是用户可能主动搜索且能被正文兑现的短语，通常2至15个汉字；不得添加正文没有依据的品牌、地点、节日、功效、身份、价格或热点事件。
- 先在内部去重并删除同义重复、上下位词堆叠和无关大词；必须保留用户指定的搜索关键词，并将其转换成自然话题。
- 最终成稿末尾另起一段，以“推荐话题：”开头，随后用空格分隔“#话题”；不要解释选择过程。正文篇幅要求不计算标题和推荐话题。"""


MODE_RULES = {
    "1": """模式 1：1:1 贴近仿写。
参考笔记来自用户自己的账号且已经成为爆款，本次用于复刻自己的爆款。保持原文段落数量、信息顺序、篇幅比例、情绪、人称和语感，仅重写非关键词表达。不得新增经历、案例、观点或原文没有的事实。指定关键词原样保留并自然分布在标题、开头、中段和结尾的至少三个位置。默认只输出标题和完整正文。""",
    "2": """模式 2：创新性写笔记。
保留对标笔记的成交逻辑、用户心理推进、核心卖点、情绪节奏、信任建立方式和行动引导作用，但重做第一屏、开头切口、人物场景、案例、信息顺序、表达角度和语言。不能逐段镜像或只替换同义词，避免沿用原文连续表达。默认输出标题和完整正文。""",
    "3": """模式 3：跨产品模仿。
先在内部把其他品类对标笔记抽象为内容公式、心理链路、说服技巧和节奏，再用新产品的真实资料重建人物、场景、冲突、证据和措辞。不得迁移对方产品的数据、证言或品牌资产。默认依次输出：通用内容公式、2 个标题、3 个开头、1 篇完整正文、3 个结尾和封面图建议。""",
    "4": """模式 4：定题真人种草。
围绕产品真实资料、同行参考、封面和标题创作。标题已提供时原样列为主标题，再给 9 个不同切口的备选；未提供时给 10 个不同切口的标题。随后输出 3 篇有实质差异的正文：A 为个人体验或生活记录切口，B 为痛点或使用场景切口，C 为朋友聊天或真实发现切口。缺少真实体验时改用观察、选择过程、产品细节和适用场景，不伪造使用经历。每篇适量使用 3 至 8 个符合语境的表情，降低营销感。""",
    "5": """模式 5：场景化素人仿写。
把原文改写为 160 至 210 个汉字左右的三段式第一人称素人分享。三段依次承担日常处境或情绪切入、具体场景中的产品体验与作用、自然总结或分享理由。使用适合目标人群的通勤、上课、工作、逛街、居家或学习场景，保持因果推进，不写卖点清单，不写结构标签，不附分析。不要照搬原文连续表达。""",
}


@dataclass(frozen=True)
class CopywritingBrief:
    mode: str
    product_name: str
    target_audience: str = ""
    selling_points: str = ""
    pain_points: str = ""
    keywords: tuple[str, ...] = ()
    product_purpose: str = ""
    cover_description: str = ""
    locked_title: str = ""
    prohibited_claims: str = ""
    own_post_confirmed: bool = False

    @property
    def label(self) -> str:
        return MODE_LABELS[self.mode]

    def validate(self, has_reference: bool) -> None:
        if self.mode not in MODE_LABELS:
            raise CopywritingInputError("未知的孟哥文案模式")
        missing: list[str] = []
        if not self.product_name.strip():
            missing.append("产品或主题")
        if not has_reference:
            missing.append("对标笔记正文或完整截图")
        if self.mode in {"2", "3", "4", "5"} and not self.target_audience.strip():
            missing.append("目标人群")
        if self.mode in {"2", "3", "4"} and not self.selling_points.strip():
            missing.append("真实卖点或产品资料")
        if self.mode in {"3", "4"} and not self.pain_points.strip():
            missing.append("用户痛点或使用场景")
        if self.mode == "5" and not self.product_purpose.strip():
            missing.append("产品用途或作用")
        if self.mode == "1":
            if not self.own_post_confirmed:
                raise CopywritingInputError(
                    "模式 1 仅用于复刻自己账号已经发布并成为爆款的笔记，请先确认来源"
                )
            if not self.keywords:
                missing.append("必须保留的搜索关键词")
        if missing:
            raise CopywritingInputError("请补充：" + "、".join(missing))

    def prompt(self, reference_text: str, additional_requirements: str) -> str:
        fields = [
            f"当前模式：{self.mode}. {self.label}",
            f"产品或主题：{self.product_name.strip()}",
        ]
        optional = (
            ("目标人群", self.target_audience),
            ("真实卖点、材质、成分或规格", self.selling_points),
            ("用户痛点或使用场景", self.pain_points),
            ("必须保留的搜索关键词", "、".join(self.keywords)),
            ("产品用途或作用", self.product_purpose),
            ("已定封面或画面", self.cover_description),
            ("已定标题", self.locked_title),
            ("禁用表述", self.prohibited_claims),
            ("对标笔记或待改写原文", reference_text),
            ("本次补充要求", additional_requirements),
        )
        fields.extend(f"{label}：{value.strip()}" for label, value in optional if value.strip())
        return "\n\n".join(
            (
                GLOBAL_RULES,
                NATURAL_COPY_RULES,
                MODE_RULES[self.mode],
                TOPIC_RULES,
                "\n".join(fields),
            )
        )

    def retrieval_text(self, reference_text: str, additional_requirements: str) -> str:
        return "\n".join(
            value
            for value in (
                self.label,
                self.product_name,
                self.target_audience,
                self.selling_points,
                self.pain_points,
                " ".join(self.keywords),
                self.product_purpose,
                self.cover_description,
                self.locked_title,
                reference_text,
                additional_requirements,
            )
            if value.strip()
        )

    def image_brief(self, generated_text: str) -> str:
        parts = [f"为小红书产品“{self.product_name.strip()}”创作配图。", PHOTO_STRATEGY]
        if self.cover_description.strip():
            parts.append(f"封面或画面要求：{self.cover_description.strip()}")
        if self.locked_title.strip():
            parts.append(f"内容主题：{self.locked_title.strip()}")
        if self.target_audience.strip():
            parts.append(f"目标受众：{self.target_audience.strip()}")
        if self.selling_points.strip():
            parts.append(f"只呈现可验证的产品信息：{self.selling_points.strip()}")
        parts.append("配图需要承接以下文案主题，但除非用户明确要求，不在画面中生成文字：")
        parts.append(generated_text[:1_500])
        return "\n\n".join(parts)


def normalize_keywords(values: list[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    for value in values:
        keyword = str(value).strip()
        if not keyword or keyword in normalized:
            continue
        if len(keyword) > 50:
            raise CopywritingInputError("单个关键词不能超过 50 个字符")
        normalized.append(keyword)
    if len(normalized) > 20:
        raise CopywritingInputError("关键词不能超过 20 个")
    return tuple(normalized)


def normalize_recommended_topics(values: list[str]) -> list[str]:
    topics: list[str] = []
    seen: set[str] = set()
    for value in values:
        topic = "".join(str(value).strip().lstrip("#＃").split())
        topic = topic.strip("#＃,，、。；;：:")
        if not topic or len(topic) > 30:
            continue
        key = topic.casefold()
        if key in seen:
            continue
        seen.add(key)
        topics.append(f"#{topic}")
        if len(topics) == TOPIC_MAX_COUNT:
            break
    return topics
