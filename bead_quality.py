"""Quality gates for practical bead pen content.

The gate is intentionally evidence-led.  A pleasing tabletop scene can be
kept as supporting material, but it cannot make a note publishable by itself.
"""

from __future__ import annotations

import re
from typing import Any

PRACTICAL_TERMS = (
    "同色区域", "连续", "单颗", "补位", "按压", "滑动", "笔尖", "落点",
    "空位", "铺豆", "装豆", "豆列", "前端", "导轨", "边线", "大块",
)
AESTHETIC_TERMS = ("好看", "戳", "樱花", "治愈", "上头", "放空", "心动", "漂亮")


def _text(plan: dict[str, Any]) -> str:
    return " ".join(str(plan.get(key) or "") for key in ("title", "body", "hook", "practical_point"))


def audit(plan: dict[str, Any], content_type: str) -> dict[str, Any]:
    text = _text(plan)
    practical = sorted({term for term in PRACTICAL_TERMS if term in text})
    aesthetic = sorted({term for term in AESTHETIC_TERMS if term in text})
    issues: list[str] = []
    if len(practical) < 2:
        issues.append("copy_has_no_two_visible_practical_points")
    if aesthetic and len(practical) < 3:
        issues.append("aesthetic_language_dominates_practical_reason")
    if not isinstance(plan.get("practical_point"), str) or not plan["practical_point"].strip():
        issues.append("missing_practical_point")
    if content_type == "graphic":
        cards = plan.get("images")
        if not isinstance(cards, list) or len(cards) < 3:
            issues.append("graphic_has_no_progression")
        else:
            action_cards = sum(
                any(term in f"{card.get('role','')} {card.get('prompt','')}" for term in PRACTICAL_TERMS)
                for card in cards[2:] if isinstance(card, dict)
            )
            if action_cards < 2:
                issues.append("live_cards_do_not_add_practical_evidence")
    elif content_type == "video":
        narrative = plan.get("narrative_plan")
        spine = plan.get("audio_spine")
        if plan.get("semantic_planning_version") == 2 and (not isinstance(narrative, dict) or not isinstance(spine, dict)):
            issues.append("video_missing_story_and_single_audio_spine")
    return {
        "status": "pass" if not issues else "needs_review",
        "issues": issues,
        "practical_terms": practical,
        "aesthetic_terms": aesthetic,
        "evidence_count": len(plan.get("visible_selling_points") or []),
    }


def require_pass(plan: dict[str, Any], content_type: str) -> dict[str, Any]:
    result = audit(plan, content_type)
    if result["status"] != "pass":
        raise ValueError("拼豆笔内容未通过实用性检查：" + ",".join(result["issues"]))
    return result

