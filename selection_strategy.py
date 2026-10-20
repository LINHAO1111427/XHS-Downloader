"""Local, traceable product-selection plans and conservative evidence checks."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import re
from time import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CN = timezone(timedelta(hours=8))
METHODS = (
    ("broad", "广选：同款 → 同类 → 同需求", ("广选", "同需求")),
    ("screen", "严筛：近期、低粉，分别核验加购与销量", ("低粉", "加购")),
    ("platform", "小红书优先；抖音线索回小红书验证", ("抖音", "小红书")),
    ("value", "拆解购买理由：功能、颜值、情绪、性价比与素材可得性", ("情绪", "素材", "性价比")),
    ("test", "多测：小批量测品，复盘商品访客、支付转化与实际订单", ("测品", "复盘")),
)
METHOD_TITLES = {
    "broad": ("爆品三板斧",),
    "screen": ("爆品长什么样", "什么样的品能爆", "爆品三板斧"),
    "platform": ("抖音实操", "2.7", "爆品三板斧"),
    "value": ("爆品长什么样", "什么样的品能爆", "电商进阶认知"),
    "test": ("如何测品", "复盘测品数据"),
}
STATUS = {"review": "优先核验", "observe": "继续观察", "missing": "数据待补", "filtered": "未达笔记条件", "inspiration": "热词灵感"}


class SelectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    space_id: str = Field(default="", max_length=64)
    product_id: str = Field(default="", max_length=64)
    product: str = Field(default="", max_length=100)
    category: str = Field(default="", max_length=100)
    need: str = Field(default="", max_length=100)
    audience: str = Field(default="", max_length=100)
    scene: str = Field(default="", max_length=100)
    preset: Literal["broad", "recent", "today"] = "recent"
    cart_min: int = Field(default=200, ge=0, le=100000000)
    # Optional overrides for the daily product-discovery workflow.  Manual
    # plans retain their preset behaviour unless these values are supplied.
    window_days: int | None = Field(default=None, ge=1, le=180)
    max_followers: int | None = Field(default=None, ge=0, le=1_000_000)
    min_likes: int | None = Field(default=None, ge=0, le=100_000_000)
    require_attached_product: bool = False
    image_text_only: bool = False

    @model_validator(mode="after")
    def account_product(self):
        if self.product_id and not self.space_id:
            raise ValueError("请选择商品所属账号")
        return self


def terms(value):
    return list(dict.fromkeys(s.strip() for s in re.split(r"[,，、/；;\n\s]+", value) if len(s.strip()) >= 2))[:12]


def extract_knowledge_constraints(entries):
    """Extract explicit discovery rules from the local knowledge corpus.

    Historical examples are not treated as live rules.  We only consider
    entries that mention the low-follower/product-discovery scope and return
    source ids so the saved plan remains auditable.
    """
    constraints = {}
    source_ids = []
    def count_value(value):
        """Parse the compact count spellings used in local research notes."""
        value = str(value).replace(",", "").strip().lower()
        multiplier = 1
        if value.endswith("万"):
            multiplier, value = 10_000, value[:-1]
        elif value.endswith("亿"):
            multiplier, value = 100_000_000, value[:-1]
        try:
            return max(0, int(float(value) * multiplier))
        except (TypeError, ValueError):
            return None

    for entry in entries:
        text = f"{entry.get('title', '')}\n{entry.get('content', '')}"
        if not re.search(r"低粉|爆款|挂商品|挂载商品|挂车|带货|商品链接|加购|图文", text, re.I):
            continue
        found = {}
        day = re.search(r"(?:近|最近|过去)\s*(\d{1,3}|一|两|二|三|四|五|六|七)\s*(?:天|日)", text)
        hour = re.search(r"(?:近|最近|过去)\s*(\d{1,4})\s*小时", text)
        if day:
            token = day.group(1)
            found["days"] = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7}[token] if token in "一两二三四五六七" else int(token)
        elif hour:
            found["days"] = max(1, min(180, (int(hour.group(1)) + 23) // 24))
        follower = re.search(
            r"(?:粉丝(?:数|量)?|低粉)[^。；;\n]{0,30}"
            r"(?:少于|小于|低于|不超过|不高于|至多|以下|以内|<|<=|≤)\s*([\d,.]+(?:万|亿)?)",
            text,
            re.I,
        )
        if follower:
            value = count_value(follower.group(1))
            if value is not None:
                found["max_followers"] = value
        interactions = re.search(r"(?:互动|赞藏评|赞藏评转|点赞)[^。；;,，\n]{0,30}(?:至少|不少于|大于等于|>=|≥|>)\s*([\d,.]+(?:万|亿)?)", text, re.I)
        if interactions:
            value = count_value(interactions.group(1))
            if value is not None:
                found["min_interactions"] = value
        likes = re.search(r"点赞[^。；;,，\n]{0,30}(?:至少|不少于|大于等于|>=|≥|>)\s*([\d,.]+(?:万|亿)?)", text, re.I)
        if likes:
            value = count_value(likes.group(1))
            if value is not None:
                found["min_likes"] = value
        carts = re.search(
            r"(?:24\s*小时|本篇|笔记)?\s*加购(?:数|量|人数)?[^。；;,，\n]{0,30}"
            r"(?:大于|至少|不少于|超过|>=|>|≥)\s*([\d,.]+(?:万|亿)?)",
            text,
            re.I,
        )
        if carts:
            value = count_value(carts.group(1))
            if value is not None:
                found["cart_gt"] = value
        if re.search(r"挂商品|挂载商品|商品链接|挂车|带货", text, re.I):
            found["require_attached_product"] = True
        if re.search(r"图文笔记|图文内容|图文为主|仅图文", text, re.I):
            found["image_text_only"] = True
        if found:
            source_ids.append(entry["id"])
            for key, value in found.items():
                if key in {"days", "max_followers"}:
                    constraints[key] = min(constraints.get(key, value), value)
                elif key in {"min_interactions", "min_likes", "cart_gt"}:
                    constraints[key] = max(constraints.get(key, value), value)
                else:
                    constraints[key] = bool(constraints.get(key)) or value
    return constraints, list(dict.fromkeys(source_ids))


def excerpt(content, anchors):
    hits = [content.find(word) for word in anchors if word in content]
    start = max(0, min(hits) - 100) if hits else 0
    return content[start:start + 900]


def reference(entry, kind, anchors=()):
    content = entry.get("content", "")
    return {"id": entry["id"], "title": entry.get("title", ""), "type": kind,
            "origin": entry.get("origin", "corpus"), "updated_at": entry.get("updated_at", entry.get("imported_at")),
            "digest": sha256(content.encode("utf-8")).hexdigest(), "excerpt": excerpt(content, anchors)}


class SelectionStrategy:
    def __init__(self, knowledge=None, operations=None):
        self.knowledge, self.operations = knowledge, operations

    def plan(self, request, owner_id=""):
        selected = request.selection
        # Retrieve active local methods and confirmed reusable lessons on every plan/run.
        entries = []
        if self.knowledge:
            with self.knowledge._connection() as db:
                entries = [self.knowledge._entry_payload(row) for row in db.execute(
                    "SELECT * FROM knowledge_entries WHERE active=1 AND kind IN ('general','note') ORDER BY updated_at DESC, id ASC"
                ).fetchall()]
        required = [reference(e, "user_requirement") for e in entries if e["origin"] == "user_requirement"]
        sources = {e["id"]: e for e in required}
        knowledge_constraints, knowledge_rule_ids = extract_knowledge_constraints(entries)
        for entry in entries:
            if entry["id"] in knowledge_rule_ids:
                sources.setdefault(entry["id"], reference(entry, "local_method"))
        rules = []
        for key, label, anchors in METHODS:
            matches = [e for e in entries if e["origin"] not in {"feedback", "user_requirement"}
                       and not any(word in e["title"] for word in ("爆品监测库", "低粉爆款-", "历史生成", "历史稿"))
                       and sum(a in e["content"] for a in anchors) >= 2]
            matches.sort(key=lambda e: (any(t in e["title"] for t in METHOD_TITLES[key]), sum(a in e["title"] for a in anchors), sum(e["content"].count(a) for a in anchors)), reverse=True)
            for e in matches[:2]:
                sources[e["id"]] = reference(e, "local_method", anchors)
            rules.append({"id": key, "label": label, "source_ids": [e["id"] for e in matches[:2]],
                          "grounded": bool(matches)})

        space, product, benchmarks, feedback = {}, {}, [], []
        if selected.space_id:
            if not self.operations or not owner_id:
                raise KeyError(selected.space_id)
            space = self.operations.get_space(owner_id, selected.space_id)
            if selected.product_id:
                product = self.operations.get_product(owner_id, selected.space_id, selected.product_id)
        focus = {"product": selected.product or product.get("title", ""),
                 "category": selected.category or product.get("category", ""),
                 "need": selected.need, "scene": selected.scene,
                 "audience": selected.audience or product.get("target_audience") or space.get("target_audience", "")}
        directions = [
            {"relation": "同款", "keywords": terms(focus["product"]) or (terms(request.query) if request.mode == "search" else [])},
            {"relation": "同类", "keywords": terms(focus["category"])},
            {"relation": "同需求", "keywords": terms(focus["need"]) + terms(focus["scene"])},
        ]
        if product.get("keywords"):
            aliases = [word for word in product["keywords"] if word.casefold() in focus["product"].casefold()]
            directions[0]["keywords"] = list(dict.fromkeys(directions[0]["keywords"] + aliases))[:12]
        related_keywords = [word for word in product.get("keywords", []) if word not in directions[0]["keywords"]][:12]
        keywords = list(dict.fromkeys(word for group in directions for word in group["keywords"]))
        lessons = [e for e in entries if e["origin"] == "feedback" and any(w.casefold() in (e["title"] + e["content"]).casefold() for w in keywords)]
        for entry in lessons[:4]:
            sources[entry["id"]] = reference(entry, "confirmed_lesson", keywords)
        cases, case_ids = [], set()
        if self.knowledge:
            for direction in directions:
                if not direction["keywords"] or len(cases) >= 3:
                    continue
                for case in self.knowledge.retrieve_corpus(" ".join(direction["keywords"]), limit=3):
                    # Retrieval includes fuzzy Chinese terms; a relation label needs a literal match.
                    searchable = case["product_name"] if direction["relation"] == "同款" else case["product_name"] + case["content"]
                    matched = [w for w in direction["keywords"] if w.casefold() in searchable.casefold()]
                    if not matched:
                        continue
                    if case["id"] not in case_ids and len(cases) < 3:
                        case_ids.add(case["id"])
                        cases.append(case | {"reference_relation": direction["relation"] + "词匹配，待核对", "matched_terms": matched})
        for case in cases:
            ref = reference(case, "historical_product_analysis", keywords)
            ref["historical_metrics"] = {k: case.get(k) for k in ("add_to_cart_24h", "followers_text", "sales_text")}
            ref["source_url"] = case.get("source_url", "")
            ref["reference_relation"] = case["reference_relation"]
            ref["matched_terms"] = case["matched_terms"]
            sources[ref["id"]] = ref
        if space:
            notes = self.operations.notes(owner_id, selected.space_id)
            for note in notes:
                haystack = (note["title"] + note["body"]).casefold()
                matched = [word for word in keywords if word.casefold() in haystack]
                if matched:
                    benchmarks.append({k: note.get(k) for k in ("id", "title", "body", "source_kind", "url", "metrics", "updated_at")} | {"matched_terms": matched})
            benchmarks.sort(key=lambda n: (len(n["matched_terms"]), n["updated_at"]), reverse=True)
            benchmarks = benchmarks[:4]
            with self.operations.connection() as db:
                if db.execute("SELECT 1 FROM sqlite_master WHERE name='factory_runs'").fetchone():
                    rows = db.execute("SELECT f.id, f.product_id, f.rating, f.lesson, f.metrics, f.published_url, f.updated_at FROM factory_runs f JOIN operation_spaces s ON s.id=f.space_id WHERE s.owner_id=? AND f.space_id=? AND (?='' OR f.product_id=?) AND (f.rating IS NOT NULL OR f.lesson!='' OR f.metrics!='{}') ORDER BY f.updated_at DESC LIMIT 5", (owner_id, selected.space_id, selected.product_id, selected.product_id)).fetchall()
                    for row in rows:
                        item = dict(row)
                        if selected.product_id and item["product_id"] != selected.product_id:
                            continue
                        item["metrics"] = json.loads(item["metrics"] or "{}")
                        item["usage"] = "问题案例" if item["rating"] is not None and item["rating"] < 4 else "用户反馈；评分与运营数据分别保留"
                        feedback.append(item)
                        if len(feedback) == 5:
                            break
        preset = selected.preset
        requested_days = selected.window_days if selected.window_days is not None else knowledge_constraints.get("days", 7 if preset == "recent" else None)
        requested_followers = selected.max_followers if selected.max_followers is not None else (1000 if preset != "broad" else None)
        knowledge_followers = knowledge_constraints.get("max_followers")
        if requested_followers is None:
            effective_followers = knowledge_followers
        elif knowledge_followers is None:
            effective_followers = requested_followers
        else:
            effective_followers = min(requested_followers, knowledge_followers)
        if preset == "broad" and selected.min_likes is None and "min_likes" not in knowledge_constraints:
            effective_likes = None
        else:
            requested_likes = selected.min_likes if selected.min_likes is not None else (500 if preset == "today" else 0)
            effective_likes = max(requested_likes, knowledge_constraints.get("min_likes", 0))
        criteria = {"preset": preset,
                    "days": requested_days,
                    "today_beijing": preset == "today",
                    "followers_lt": effective_followers,
                    "likes_gte": effective_likes,
                    "require_attached_product": bool(selected.require_attached_product or knowledge_constraints.get("require_attached_product")),
                    "image_text_only": bool(selected.image_text_only or knowledge_constraints.get("image_text_only")),
                    "knowledge_constraints": knowledge_constraints,
                    "knowledge_rule_ids": knowledge_rule_ids,
                    "cart_gt": max(selected.cart_min, knowledge_constraints.get("cart_gt", 0)),
                    "origin": "本次可选筛选条件；今日/1000/500/加购>200 预设源自 docs/xhs-product-collection-research.md；近期7天/低粉参考本地2.4课程"}
        same_product_cases = sum(c["reference_relation"].startswith("同款") for c in cases)
        return {"version": 1, "created_at": time(), "focus": focus, "directions": directions, "related_keywords": related_keywords,
                "context": {"space_id": selected.space_id, "space_name": space.get("name", ""), "product_id": selected.product_id},
                "criteria": criteria, "rules": rules, "sources": list(sources.values()),
                "benchmarks": benchmarks, "account_feedback": feedback,
                "coverage": {"methods": sum(r["grounded"] for r in rules), "cases": len(cases), "same_product_cases": same_product_cases, "lessons": len(lessons[:4])},
                "platform_priority": ["xiaohongshu", "douyin"],
                "notes": [("历史案例有商品词匹配，仍需核对是否同款。" if same_product_cases else "未找到商品词匹配的历史案例；实际同类/需求参考见来源，不称为同款。"),
                          "本批只执行当前关键词；点击同款、同类、同需求词可发起下一批采集。",
                          "历史商品分析与对标快照仅作参考，历史加购不代入当前商品。",
                          "当前两路采集未提供已核验的商品24小时加购、销量和成本；保留待核验。",
                          "评论按词语匹配标记购买意向与疑虑，仅代表已采样本，需结合原文复核。"]}

    @staticmethod
    def evaluate(item, plan):
        now, c = item["collected_at"], plan["criteria"]
        checks = []
        def check(key, label, passed, value):
            checks.append({"field": key, "label": label, "status": "unknown" if passed is None else "pass" if passed else "fail", "value": value})
        haystack = f"{item.get('title', '')} {item.get('body', '')}".casefold()
        words = [word for d in plan["directions"] for word in d["keywords"]]
        matched = list(dict.fromkeys(w for w in words if w.casefold() in haystack))
        check("relevance", "商品 / 类目 / 需求词匹配（人工复核语义）", bool(matched) if words else None, matched)
        if item.get("kind") != "topic":
            published = item.get("published_at")
            if c["today_beijing"] or c["days"]:
                passed = None
                if isinstance(published, (float, int)) and 0 < published <= now:
                    passed = (datetime.fromtimestamp(published, CN).date() == datetime.fromtimestamp(now, CN).date()) if c["today_beijing"] else now - published <= c["days"] * 86400
                check("published_at", "北京时间今日发布" if c["today_beijing"] else "近7天发布", passed, published)
            for key, threshold, label, compare in (("followers", c["followers_lt"], "粉丝严格少于", lambda a, b: a < b), ("likes", c["likes_gte"], "点赞至少", lambda a, b: a >= b)):
                if threshold is not None:
                    value = item.get(key)
                    check(key, f"{label}{threshold}", compare(value, threshold) if isinstance(value, (int, float)) and value >= 0 else None, value)
            if c.get("require_attached_product"):
                products = item.get("products")
                product_count = len(products) if isinstance(products, list) else None
                check("attached_product", "attached product required",
                      bool(product_count) if product_count is not None else None, product_count)
            if c.get("image_text_only"):
                note_type = str(item.get("note_type") or item.get("type") or "").casefold()
                video_markers = {"video", "videonote", "video_note", "video_note_type", "视频", "视频笔记"}
                image_markers = {"normal", "image", "image_text", "image-text", "图文", "图文笔记"}
                if note_type in video_markers or "video" in note_type or "视频" in note_type:
                    passed = False
                elif note_type in image_markers:
                    passed = True
                elif isinstance(item.get("video"), (dict, list)) or item.get("video_url") or item.get("videoUrl"):
                    passed = False
                elif isinstance(item.get("images"), list) and item.get("images"):
                    passed = True
                else:
                    passed = None
                check("image_text", "image-text note required", passed, item.get("type"))
        # Do not accept counters in raw payloads as cart/sales evidence. Neither adapter has a verified product-metric contract.
        check("add_to_cart_24h", f"真实24小时加购严格大于{c['cart_gt']}", None, None)
        check("sales_trend", "商品销量与近期增量", None, None)
        signals = []
        patterns = {"购买意向": r"哪里买|怎么买|求链接|求个链接|蹲链接|多少钱|想买|想要|求推荐", "疑虑": r"好用吗|有用吗|值不值|质量|容易坏|退货|不好用|太贵|不耐用|不想买|不买", "场景需求": r"适合|新手|宿舍|通勤|送礼|收纳|手工"}
        for comment in item.get("comment_items", []):
            text = comment.get("text", "")
            labels = [label for label, pattern in patterns.items() if re.search(pattern, text)]
            if labels:
                signals.append({"id": comment.get("id", ""), "text": text, "labels": labels})
        hypotheses = []
        for label, pattern in {"功能 / 效率": r"省时|省力|方便|清洁|收纳|效率|好用", "颜值 / 风格": r"好看|颜值|配色|美学|可爱", "情绪 / 礼物": r"礼物|送礼|治愈|情绪|仪式感", "价格 / 平替": r"平替|便宜|性价比|价格", "季节 / 节点": r"换季|开学|中秋|春节|夏季|冬季"}.items():
            hits = list(dict.fromkeys(re.findall(pattern, haystack)))
            if hits:
                hypotheses.append({"dimension": label, "matched_words": hits, "status": "正文提及，购买理由待验证"})
        gaps = [v["label"] for v in checks if v["status"] == "unknown"]
        gaps += ["1688成本、小红书可售价格与实际毛利", "供应稳定性、素材与内容制作可行性"]
        if item.get("platform") != "xiaohongshu":
            gaps.append("回小红书搜索同款/同类/同需求，验证近期需求")
        note_checks = [v for v in checks if v["field"] not in {"add_to_cart_24h", "sales_trend", "relevance"}]
        if item.get("kind") == "topic":
            stage = "inspiration"
        elif any(v["status"] == "fail" for v in note_checks):
            stage = "filtered"
        elif any(v["status"] == "unknown" for v in note_checks) or not words:
            stage = "missing"
        elif matched and item.get("platform") == "xiaohongshu":
            stage = "review"
        else:
            stage = "observe"
        return {"version": 1, "stage": stage, "label": STATUS[stage], "checks": checks,
                "reasons": [v["label"] for v in checks if v["status"] == "pass"],
                "gaps": gaps, "comment_signals": signals, "comment_sample_size": len(item.get("comment_items", [])),
                "buying_hypotheses": hypotheses,
                "product_status": "待核验", "source_ids": [s["id"] for s in plan["sources"]],
                "next_step": "回小红书验证商品和需求" if item.get("platform") == "douyin" else "核验商品加购、销量、毛利和供应后安排小批量测品"}
