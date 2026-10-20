"""Color anchors shared by planning, visual review and Live packaging."""
import hashlib
import json
import re

from xhs_operations import OperationError

COLORS = {
    'pink': ('粉色', '粉红', '樱花粉'), 'purple': ('紫色', '淡紫', '香芋紫'),
    'blue': ('蓝色', '天蓝'), 'green': ('绿色', '薄荷绿'), 'yellow': ('黄色', '奶油黄'),
    'white': ('白色', '奶白'), 'black': ('黑色',), 'red': ('红色',),
}
COLOR_BRIEF = '''单篇颜色一致：先看真实动作素材中主体商品的颜色，再决定整篇主题。JSON增加color_anchor（pink/purple/blue/green/yellow/white/black/red之一；确实没有单色主题时为空字符串）和color_reference（商品原图的asset_id）。
标题、正文或封面以某一商品颜色为吸引点时，全部分镜必须用同色主体；背景配色、豆子颜色不等于笔身颜色。每张images填写product_color，video_source也填写实际观察到的product_color。先核对原图和候选片段再填写，禁止按想要的颜色填写。
粉色主题不得混用紫色、白色或其他颜色的笔；同类参考标识不豁免颜色一致。只有同色且结构相符的动作才可入选。实拍不足时报告同色素材缺口，或重新规划有实拍支持的主题；保留稿的已确认主题须保持。不得自动给视频套全局改色滤镜。'''


def normalize(value):
    if not isinstance(value, str):
        return ''
    value = value.strip().lower()
    if value in COLORS:
        return value
    return next((key for key, labels in COLORS.items() if value in labels), '')


def claimed_colors(plan):
    text = '。'.join(str(plan.get(k, '')) for k in ('title', 'body'))
    topics = ' '.join(plan.get('topics', []))
    result = set()
    for color, names in COLORS.items():
        for name in names:
            # A pink bead or a pink desk alone is not a claim about the pen.
            if (re.search(r'(?:这支|那支|笔身|笔是|商品是|这款)[^。\n，]{0,5}' + name, text)
                    or re.search(name + r'[^。\n，]{0,3}(?:拼豆笔|豆笔|笔身|款)', text)
                    or '#' + name + '控' in topics):
                result.add(color)
    return result


def validate_color_plan(plan, assets=None):
    claimed = claimed_colors(plan)
    raw = plan.get('color_anchor', '')
    anchor = normalize(raw)
    if raw and not anchor:
        raise OperationError('商品颜色锚点格式有误')
    if claimed and not anchor:
        raise OperationError('单色商品主题缺少颜色锚点，请核对全部配图和 Live')
    if claimed and claimed != {anchor}:
        raise OperationError('标题正文的商品颜色与颜色锚点不一致')
    if not anchor:
        return ''
    reference = plan.get('color_reference')
    if not isinstance(reference, dict) or not reference.get('asset_id'):
        raise OperationError('颜色锚点缺少商品原图依据')
    if assets is not None and reference['asset_id'] not in {
            a['id'] for a in assets if a.get('role') == 'product_image'}:
        raise OperationError('颜色依据须为本商品素材库中的原图')
    cards = plan.get('images', [])
    if not cards:
        raise OperationError('颜色主题缺少分镜')
    for index, card in enumerate(cards):
        if normalize(card.get('product_color')) != anchor:
            raise OperationError(f'第{index + 1:02d}张商品颜色与{anchor}主题不一致或未核对')
        spec = card.get('video_source')
        if spec and normalize(spec.get('product_color')) != anchor:
            raise OperationError(f'第{index + 1:02d}张 Live 缺少同色动作素材，请重新选段')
    return anchor


def review_color_issues(plan, observations, count):
    anchor = validate_color_plan(plan)
    if not anchor:
        return []
    if not isinstance(observations, list):
        observations = []
    issues = []
    for index in range(count):
        found = [o for o in observations if isinstance(o, dict)
                 and type(o.get('index')) is int and o['index'] == index]
        if (len(found) != 1 or normalize(found[0].get('product_color')) != anchor
                or found[0].get('consistent_throughout') is not True
                or not isinstance(found[0].get('evidence'), str) or not found[0]['evidence'].strip()):
            issues.append({'index': index, 'reason': f'第{index + 1:02d}张未通过{anchor}商品颜色逐帧复核；请补充或替换同色素材',
                           'replacement_caption': ''})
    return issues


def media_fingerprint(plan, outputs, path_for):
    """Bind a color verdict to the copy, selections and exact reviewed source bytes."""
    data = {k: plan.get(k) for k in ('title', 'body', 'topics', 'color_anchor', 'color_reference', 'images')}
    data['media'] = []
    for item in outputs:
        path = path_for(item.get('source_path') or item['path'])
        entry = {k: item.get(k) for k in ('source_start', 'duration', 'framing', 'product_color')}
        # Camera conversion adds these defaults after review; normalize them here.
        if item.get('ai_generated'):
            entry = {'ai_generated': True, 'product_color': item.get('product_color')}
        with path.open('rb') as stream:
            entry['source_sha256'] = hashlib.file_digest(stream, 'sha256').hexdigest()
        if item.get('motion_mode') == 'source_video':
            with path_for(item['preview_path']).open('rb') as stream:
                entry['preview_sha256'] = hashlib.file_digest(stream, 'sha256').hexdigest()
        data['media'].append(entry)
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def validate_color_delivery(plan, outputs, path_for):
    anchor = validate_color_plan(plan)
    if not anchor:
        return
    review = plan.get('quality_review', {})
    if review.get('passed') is not True or review_color_issues(plan, review.get('color_observations'), len(outputs)):
        raise OperationError('单色主题尚未通过全部画面颜色复核')
    if len(outputs) != len(plan['images']) or any(normalize(o.get('product_color')) != anchor for o in outputs):
        raise OperationError('成品商品颜色记录与整篇主题不一致')
    if review.get('color_media_fingerprint') != media_fingerprint(plan, outputs, path_for):
        raise OperationError('颜色复核后媒体或文案已变化，请重新检查')
