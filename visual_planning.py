"""Reference selection and visual brief for account-scoped graphic planning."""
import hashlib
import re


VISUAL_BRIEF = """首图与组图设计：
先在内部比较三种首图：商品使用近景、清楚的局部与整体关系、商品参与的生活场景。选择最能兑现标题且能看清在售商品的一种。
封面必须能辨认当前在售商品，不能让豆材、成品摆件、装饰道具取代工具主体；同类工具和串豆针不等于本款商品。
按约180像素宽的信息流缩略图检查：一个明确视觉中心，商品与关键使用关系仍可见，不能只剩漂亮背景。
图2解释首图的具体问题，后续图补动作、细节或适用条件；每张提供不同的信息，至少一张能辨认商品整体。
有序排列、颜色对照、真实手持、装入或取出的瞬间可作为待测试构图；只用资料已确认的配色、零件和动作，不编造库存阵列或夸大性能。
低粉是账号快照，商品加购/销量不是封面点击效果。引用截图中的具体画面，记录观察与待验证假设，不把截图里所有笔记都称为爆款。
JSON另加visual_brief：hook（首图可见吸引点）、product_visibility（商品如何可辨认）、
title_image_match（标题如何被画面兑现）、test_variable（本次一个变量）、reference_asset_ids（实际参考素材ID数组）。
每张images另加visible_evidence（该张能看到的商品依据）与new_information（相对上一张增加什么）。这些字段仅作制作记录。
"""


# A deterministic rotation keeps a daily account feed from collapsing into one
# centered product shot while still requiring every direction to show the real
# SKU and a concrete use clue. The selected direction is stored with the plan.
COVER_DIRECTIONS = (
    {"key": "use-close", "name": "使用近景", "prompt": "以手部正在使用商品的近景做首图，商品落在画面偏左或偏右三分之一，保留可辨认的整体轮廓与接触点；背景只交代使用地点，不要正中陈列。"},
    {"key": "detail-whole", "name": "局部带整体", "prompt": "用一个能解释标题的局部细节作为视觉钩子，同时在后景保留同一商品的完整轮廓；局部必须是真实结构，不用材料或装饰物替代商品。"},
    {"key": "life-context", "name": "生活场景", "prompt": "把商品放入目标用户熟悉的生活位置，采用略偏的手机视角和前后层次；让商品正在解决一个可见的小问题，避免棚拍白底和统一广告光。"},
    {"key": "contrast-proof", "name": "前后反差", "prompt": "用同一空间里的可见反差吸引停留：前景呈现待处理的具体状态，商品在动作或结果位置清楚出现；不虚构前后效果，不做拼贴海报。"},
    {"key": "color-material", "name": "颜色材质", "prompt": "利用真实环境色和材质对比突出商品辨识度，采用低机位或侧上方视角，商品不居中；画面必须同时保留使用关系，不能只拍漂亮背景。"},
)


def cover_direction(run, history=()):
    """Return a stable, account-local first-frame direction for this run."""
    saved = (run.get("plan") or {}).get("cover_direction")
    if isinstance(saved, dict) and saved.get("key") and saved.get("prompt"):
        return saved
    seed = ":".join(str(run.get(key, "")) for key in ("day", "slot", "angle", "product_id"))
    start = int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8], 16) % len(COVER_DIRECTIONS)
    recent = [((item.get("plan") or {}).get("cover_direction") or {}).get("key") for item in history[-len(COVER_DIRECTIONS):]]
    for offset in range(len(COVER_DIRECTIONS)):
        candidate = COVER_DIRECTIONS[(start + offset) % len(COVER_DIRECTIONS)]
        if candidate["key"] not in recent:
            return dict(candidate)
    return dict(COVER_DIRECTIONS[start])


def cover_direction_prompt(run, history=()):
    direction = cover_direction(run, history)
    return (f"本篇首图构图方向：{direction['name']}（{direction['key']}）。{direction['prompt']}"
            "这是本篇首图的主变量；后续图片必须换景别或信息目的，不能把同一构图复制六次。")


def select_visual_references(assets, history, query, limit=4):
    refs = [a for a in assets if a.get('role') == 'reference_image']
    used = {}
    for run in history:
        actual = [s for output in run.get('outputs', []) for s in output.get('visual_reference_sources', [])]
        for source in actual or run.get('plan', {}).get('visual_reference_sources', []):
            key = source.get('id'); used[key] = used.get(key, 0) + 1
    tokens = set(re.findall(r'[a-zA-Z0-9]+|[\u4e00-\u9fff]{2}', query.lower()))
    def rank(asset):
        text = ' '.join((asset.get('title',''),asset.get('caption',''),' '.join(asset.get('tags',[])))).lower()
        matches = sum(t in text for t in tokens)
        return (-matches,used.get(asset['id'],0),asset['id'])
    # Assets already belong to this account and product; discard byte-identical references.
    result, seen = [], set()
    for asset in sorted(refs,key=rank):
        key=asset.get('sha256') or asset['id']
        if key in seen:continue
        result.append(asset);seen.add(key)
        if len(result)>=limit:break
    return result


def card_visual_references(plan, assets, index, identity_paths=()):
    """Resolve account/product-scoped references and rotate the default pool."""
    allowed = {a['id']: a for a in assets if a.get('role') == 'reference_image'}
    pool = [allowed[s['id']] for s in plan.get('visual_reference_sources', []) if s.get('id') in allowed]
    requested = plan['images'][index].get('reference_asset_ids')
    if requested is not None:
        candidates = [allowed[key] for key in requested if key in allowed]
    else:
        candidates = [pool[index % len(pool)]] if pool else []
    result, seen = [], set(identity_paths)
    hashes = {a.get('sha256') for a in assets if a.get('path') in identity_paths and a.get('sha256')}
    for asset in candidates:
        digest = asset.get('sha256') or asset['id']
        if asset['path'] in seen or digest in hashes:
            continue
        result.append(asset)
        seen.add(asset['path'])
        hashes.add(digest)
        if len(result) == 2:
            break
    return result
