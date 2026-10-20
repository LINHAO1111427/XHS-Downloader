"""Idempotently organize the existing bead-pen project into an account workspace."""
import argparse
import json
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from time import time
from types import SimpleNamespace
from uuid import uuid4

from account_factory import AccountFactory, SHANGHAI, digest, encode
from xhs_operations import OperationStore


def seed(root: Path, owner: str | None = None):
    project = root / "output/bead_pen_20260918"
    media_root = root / "Volume/Download"
    store = OperationStore(root / "Volume/xhs_operations.db")
    with store.connection() as db:
        owners = [r[0] for r in db.execute("SELECT DISTINCT owner_id FROM operation_spaces")]
    if owner is None:
        if len(owners) != 1:
            raise ValueError("请通过 --owner 指定案例所属用户")
        owner = owners[0]
    existing = next((s for s in store.spaces(owner) if s["name"] == "拼豆笔｜每日内容案例"), None)
    space = existing or store.create_space(owner, {
        "name": "拼豆笔｜每日内容案例", "account_name": "拼豆工具观察室",
        "positioning": "围绕拼豆笔的使用过程、可见结构、重复铺豆和细节补位，积累手工工具图文与演示视频。",
        "target_audience": "拼豆新手与经常做同色区域的手工爱好者；关注操作是否看得懂、铺豆与细节补位如何切换。",
        "tone": "有具体动作和细节的日常观察；允许惊喜和纠结。真实手工桌面、近景操作、自然光；少用空泛夸张词。",
        "keywords": ["拼豆笔", "滑豆", "拼豆工具", "拼豆新手", "手工DIY"],
    })
    folder = media_root / "账号素材" / space["id"] / "拼豆笔案例"
    folder.mkdir(parents=True, exist_ok=True)

    def copy(path, group):
        target = folder / group / path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or digest(target) != digest(path):
            shutil.copy2(path, target)
        return target.relative_to(media_root).as_posix()

    product_images = [copy(path, "商品原图") for path in sorted((project / "product/images").glob("*.jpg"))]
    source_videos = [copy(path, "商品演示视频") for path in (project / "videos").rglob("*.mp4")]
    if len(product_images) != 12 or not source_videos:
        raise ValueError("拼豆笔案例的商品原图或原始视频未齐备")
    product = store.add_product(owner, space["id"], {
        "title": "飞梭拼豆笔", "source_platform": "xhs", "source_product_id": "6a9f6afa1b9ae90001f9d740",
        "url": "https://xhslink.com/m/AAz4EuUDZYH", "category": "手工工具 / 拼豆",
        "description": "商品原图展示手握式长条装豆仓与导轨、前端细尖；展示按压与滑动两种操作。外观以原图为准。",
        "selling_points": "同色区域连续铺豆；前端笔尖可做单颗补位。只描述图像及演示中可见的结构与动作，不承诺不卡豆或效率倍数。",
        "target_audience": space["target_audience"], "keywords": space["keywords"],
        "image_paths": product_images, "video_paths": source_videos,
    })
    factory = AccountFactory(SimpleNamespace(store=store, runtime=SimpleNamespace(download_root=lambda: media_root)), None, None, None, None)
    original_url = "https://www.xiaohongshu.com/explore/6aabb52e000000002900c278"
    factory.add_assets(owner, space["id"], {"product_id": product["id"], "role": "product_image", "paths": product_images,
                                           "source_url": product["url"], "tags": ["商品原图", "结构依据"]})
    factory.add_assets(owner, space["id"], {"product_id": product["id"], "role": "product_video", "paths": source_videos,
        "source_url": original_url, "tags": ["演示", "滑豆", "原始素材"],
        "caption": "用户此前提供的同款演示。旧剪辑记录：0–5秒滑豆开场，10–22秒连续铺豆，43–58秒操作近景，64–75秒结构，75–83秒细节；以抽帧及实际视频为准。"})
    markdown = next(path for path in (project / "videos").rglob("*.md") if path.name != "video_plan.md")
    source_text = markdown.read_text(encoding="utf8")
    title = re.search(r"作品标题\*\*：([^\n]+)", source_text).group(1)
    body = re.search(r"作品描述\*\*：\s*\n\s*>\s*(.*?)\n", source_text).group(1)
    note = store.upsert_note(owner, space["id"], {"note_id": "6aabb52e000000002900c278", "url": original_url,
        "title": title, "body": body, "type": "video", "source_kind": "benchmark_note", "author": "薄荷yy",
        "tags": ["拼豆工具", "拼豆笔", "拼豆教程"], "metrics": {"likes": 1, "comments": 29, "shares": 1}})
    with store.connection() as db:
        db.execute("INSERT OR IGNORE INTO factory_note_links VALUES(?,?,?)", (space["id"], product["id"], note["id"]))
    # Preserve the full text archive outside the prompt, without promoting it to product facts.
    for path, group in [(project / "product/product_info.md", "资料原文"), (markdown, "资料原文"),
                        (project / "videos/video_plan.md", "历史成品"), (project / "graphic_posts/posts.md", "历史成品"),
                        (project / "graphic_posts/image_prompts.md", "历史成品")]:
        copy(path, group)

    def archive(kind, index, title, body, topics, path):
        role = "archive_image" if kind == "graphic" else "archive_video"
        relative = copy(path, "历史成品")
        factory.add_assets(owner, space["id"], {"product_id": product["id"], "role": role, "paths": [relative],
                                                "title": title, "caption": "此前项目已制作的内容，保留作账号历史对照，不当作新的商品事实。"})
        with store.connection() as db:
            found = db.execute("SELECT id FROM factory_runs WHERE space_id=? AND day='2026-09-18' AND content_type=? AND slot=?",
                               (space["id"], kind, 100 + index)).fetchone()
            if found:
                return
            run_id = uuid4().hex
            plan = {"title": title, "body": body, "topics": topics, "imported_archive": True}
            outputs = [{"path": relative, "kind": "image" if kind == "graphic" else "video", "role": "历史成品"}]
            db.execute("INSERT INTO factory_runs(id,space_id,product_id,day,content_type,slot,angle,state,plan,outputs,created_at,updated_at) "
                       "VALUES(?,?,?,'2026-09-18',?,?,?,'running',?,?,?,?)",
                       (run_id, space["id"], product["id"], kind, 100 + index, "历史内容归档", encode(plan), encode(outputs), time(), time()))
        factory.package({"id": run_id, "space_id": space["id"], "day": "2026-09-18", "angle": "历史内容归档", "plan": plan, "outputs": outputs})

    posts = (project / "graphic_posts/posts.md").read_text(encoding="utf8")
    sections = re.split(r"## 图文 \d+｜", posts)[1:]
    for i, section in enumerate(sections, 1):
        title = re.search(r"推荐标题：`([^`]+)`", section).group(1)
        match = re.search(r"封面短句：[^\n]+\n\n(.*?)\n\n`(#[^`]+)`", section, re.S)
        image = re.search(r"配图：`([^`]+)`", section).group(1)
        archive("graphic", i, title, match.group(1), match.group(2).split(), project / "graphic_posts" / image)
    videos = (project / "videos/video_plan.md").read_text(encoding="utf8")
    for i, section in enumerate(re.split(r"## 成片 \d+：", videos)[1:], 1):
        title = re.search(r"建议标题：`([^`]+)`", section).group(1)
        video = re.search(r"文件：`([^`]+)`", section).group(1)
        match = re.search(r"发布文案：\s*\n\s*\n\s*(.*?)\n\s*\n\s*`(#[^`]+)`", section, re.S)
        archive("video", i, title, match.group(1).strip(), match.group(2).split(), (project / "videos" / video).resolve())
    if factory.store.schedule(owner, space["id"]) is None:
        factory.store.save_schedule(owner, space["id"], {"product_id": product["id"], "enabled": True, "hour": 9,
            "graphic_count": 1, "video_count": 1, "image_count": 3,
            "start_date": (datetime.now(SHANGHAI).date() + timedelta(days=1)).isoformat()})
    report = {"space_id": space["id"], "product_id": product["id"], "reference_note_id": note["id"],
              "assets": len(factory.store.assets(owner, space["id"])), "archives": sum(r["slot"] >= 100 for r in factory.store.runs(owner, space["id"])),
              "schedule": factory.store.schedule(owner, space["id"]), "source_project": str(project)}
    factory.shutdown()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--owner")
    args = parser.parse_args()
    result = seed(args.root.resolve(), args.owner)
    output = args.root / "output/account-factory"
    output.mkdir(parents=True, exist_ok=True)
    (output / "case-import.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
