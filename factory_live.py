"""Account-scoped reuse of finished remixes for functional Live notes."""
import hashlib
import json
import math
from fractions import Fraction
from io import BytesIO
from time import time

import cv2
from PIL import Image, ImageDraw, ImageOps

from live_note import create_live_pair, framing_options
from video_compositor import probe_video
from xhs_operations import OperationError


def validate_recipe(cards):
    if (len(cards) != 6 or any(c.get('video_source') for c in cards[:2])
            or any(not isinstance(c.get('video_source'), dict) or not c['video_source'] for c in cards[2:])):
        raise OperationError('六张 Live 分镜须为前两张 AI 场景和后四张混剪选段')
    used = {}
    for card in cards[2:]:
        spec = card['video_source']
        start, duration = spec.get('start'), spec.get('duration')
        if (type(start) not in (int, float) or type(duration) not in (int, float)
                or not math.isfinite(start) or not math.isfinite(duration) or start < 0 or not .5 <= duration <= 5):
            raise OperationError('Live 选段时间无效')
        key = spec.get('run_id')
        if not isinstance(key, str) or not key:
            raise OperationError('Live 选段缺少来源混剪')
        end = start + duration
        if any(start < b and end > a for a, b in used.get(key, [])):
            raise OperationError('同篇四张混剪 Live 应展示不同选段，时间区间不得重叠')
        used.setdefault(key, []).append((start, end))


def resolve(factory, run, spec):
    if not isinstance(spec, dict):
        raise OperationError("Live 选段格式有误")
    source = factory.store.run(run['owner_id'], run['space_id'], spec.get('run_id', ''))
    if (source['product_id'] != run['product_id'] or source['content_type'] != 'video'
            or source['state'] not in {'ready', 'published'}):
        raise OperationError("请选择本账号当前商品的已完成混剪")
    item = next((o for o in source['outputs'] if o['kind'] == 'video'), None)
    if not item:
        raise OperationError("混剪成品缺少视频")
    path = factory.path(item['path'])
    start, duration = spec.get('start'), spec.get('duration')
    trim = spec.get('trim_bottom', 0)
    label = spec.get('source_label', '')
    try:
        framing_options((3, 4), spec.get('fit', 'cover'), spec.get('focal_y', .5))
    except ValueError as error:
        raise OperationError(str(error)) from error
    if not isinstance(label, str) or len(label) > 32:
        raise OperationError('来源标识须为不超过32字的说明')
    if type(trim) not in (int, float) or not math.isfinite(trim) or not 0 <= trim <= .25:
        raise OperationError('底部裁切比例应在 0 至 0.25 之间')
    if (type(start) not in (float, int) or type(duration) not in (float, int)
            or not math.isfinite(start) or not math.isfinite(duration) or start < 0
            or not .5 <= duration <= 5 or start + duration > probe_video(path)['duration'] + .04):
        raise OperationError("Live 选段超出视频范围；每段需 0.5 至 5 秒")
    return source, path


def contact_sheet(path, times):
    """Inspect real decoded frames without leaving review frames on disk."""
    sheet = Image.new('RGB', (800, 290 * math.ceil(len(times) / 4)), 'white')
    draw = ImageDraw.Draw(sheet)
    cap = cv2.VideoCapture(str(path))
    try:
        for i, timestamp in enumerate(times):
            cap.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
            ok, frame = cap.read()
            if not ok:
                raise OperationError("视频选段抽帧失败")
            tile = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            tile.thumbnail((196, 263))
            x, y = i % 4 * 200, i // 4 * 290
            sheet.paste(tile, (x, y + 24))
            draw.text((x + 4, y + 3), f'{timestamp:.2f}s', fill='black')
    finally:
        cap.release()
    buffer = BytesIO(); sheet.save(buffer, 'JPEG', quality=88)
    return 'image/jpeg', buffer.getvalue()


def planning_sources(factory, run, history, image_offset):
    uses = {}
    for prior in history:
        for item in prior.get('outputs', []):
            key = item.get('source_run_id')
            uses[key] = uses.get(key, 0) + 1
    candidates = [r for r in history if r['content_type'] == 'video'
                  and r['state'] in {'ready', 'published'} and r['product_id'] == run['product_id']]
    candidates.sort(key=lambda r: (uses.get(r['id'], 0), -r['created_at']))
    images, descriptors = [], []
    for source in candidates:
        if len(images) >= 3:
            break
        try:
            item = next(o for o in source['outputs'] if o['kind'] == 'video')
            path = factory.path(item['path'])
            duration = probe_video(path)['duration']
            times = [round(duration * (i + .3) / 16, 3) for i in range(16)]
            images.append(contact_sheet(path, times))
        except (OSError, ValueError, StopIteration):
            continue
        descriptors.append({'run_id': source['id'], 'duration': duration, 'times': times,
                            'title': source['plan']['title'], 'body': source['plan']['body'],
                            'source_identity': source['plan'].get('source_identity', ''),
                            'input_image_number': image_offset + len(images),
                            'previous_live_uses': uses.get(source['id'], 0)})
    return images, descriptors


def canvas_ratio(factory, run):
    """Follow the first picture so an album never alternates wide and narrow Live frames."""
    ratio = run['plan'].get('live_canvas_ratio')
    if ratio:
        return framing_options(ratio)['canvas_ratio']
    for item in run.get('outputs', [])[:1]:
        if item.get('motion_mode') != 'source_video' and item.get('kind') in {'image', 'live_photo'}:
            with Image.open(factory.path(item['path'])) as image:
                image = ImageOps.exif_transpose(image)
                value = Fraction(image.width, image.height).limit_denominator(20)
                return [value.numerator, value.denominator]
    return [3, 4]


def extract(factory, run, card):
    spec = card['video_source']
    source, path = resolve(factory, run, spec)
    folder = factory.root / '账号成品' / run['space_id'] / run['id'] / 'live'
    pair = create_live_pair(path, folder, start=spec['start'], duration=spec['duration'],
                            trim_bottom=spec.get('trim_bottom', 0), source_label=spec.get('source_label', ''),
                            canvas_ratio=canvas_ratio(factory, run), fit=spec.get('fit', 'cover'),
                            focal_y=spec.get('focal_y', .5))
    return {**pair, 'kind': 'live_photo', 'role': card['role'],
            'product_color': card.get('product_color', ''),
            'source_path': path.relative_to(factory.root).as_posix(), 'source_run_id': source['id'],
            'source_title': source['plan']['title'],
            'source_identity': source['plan'].get('source_identity', ''),
            **{key: pair[key].relative_to(factory.root).as_posix()
               for key in ('path', 'motion_path', 'preview_path')}}


def enqueue_from_video(factory, owner, space, run_id, segments):
    source = factory.store.run(owner, space, run_id)
    run = {**source, 'owner_id': owner}
    cards = []
    for segment in segments:
        spec = {'run_id': run_id, 'start': segment['start'], 'duration': segment['duration']}
        if segment.get('trim_bottom'):
            spec['trim_bottom'] = segment['trim_bottom']
        resolve(factory, run, spec)
        cards.append({'role': segment['role'], 'prompt': segment['role'], 'video_source': spec})
    # A deterministic key survives retries and double clicks, even after plan enrichment.
    key = hashlib.sha256(json.dumps([space, run_id, cards], sort_keys=True).encode()).hexdigest()[:32]
    with factory.service.store.connection() as db:
        if db.execute('SELECT id FROM factory_runs WHERE id=?', (key,)).fetchone():
            return factory.store.run(owner, space, key)
    product = factory.service.store.get_product(owner, space, source['product_id'])
    context_run = {**run, 'content_type': 'graphic'}
    factory._context(context_run, product, factory._history(run))
    plan = {k: source['plan'][k] for k in ('title', 'body', 'topics')}
    plan.update(images=cards, image_count=len(cards), product_anchor=product['description'],
                content_alignment_version=1,
                graphic_format='live_photo', source_kind='remix_live_excerpt', source_run_id=run_id,
                source_identity=source['plan'].get('source_identity', ''),
                source_plan_sha256=hashlib.sha256(json.dumps(source['plan'], sort_keys=True).encode()).hexdigest(),
                source_references={k: v for k, v in source['plan'].items() if 'source' in k or 'reference' in k},
                note_knowledge_sources=context_run.get('retrieval_sources', []),
                corpus_sources=context_run.get('corpus_sources', []),
                benchmark_sources=context_run.get('benchmark_sources', []),
                copy_policy='继承来源文案；发布前检查正文是否与所选片段对应')
    # A color-led title is not a license to reuse arbitrary colored excerpts.
    from live_color import claimed_colors
    if claimed_colors(plan) or source['plan'].get('color_anchor'):
        raise OperationError('该混剪含商品单色主题，请在图文分镜中核对颜色锚点和每段动作后制作 Live')
    with factory.service.store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        if not db.execute('SELECT id FROM factory_runs WHERE id=?', (key,)).fetchone():
            lowest = db.execute("SELECT MIN(slot) FROM factory_runs WHERE space_id=? AND day=? AND content_type='graphic'",
                                (space, source['day'])).fetchone()[0]
            db.execute("INSERT INTO factory_runs (id,space_id,product_id,day,content_type,slot,angle,state,stage,plan,created_at,updated_at) "
                       "VALUES(?,?,?,?,'graphic',?,?,'queued','已保存选段，等待制作 Live',?,?,?)",
                       (key, space, source['product_id'], source['day'], min(-1, (lowest or 0)-1),
                        '从混剪提取功能 Live', json.dumps(plan, ensure_ascii=False), time(), time()))
    return factory.store.run(owner, space, key)
