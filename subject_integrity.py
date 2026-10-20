"""Fail-closed product subject review, bound to final media bytes.

This gate validates evidence coverage and decisions, not a promise that a visual
model cannot miss a defect. Uncertain structure must remain awaiting review.
"""
from io import BytesIO
from pathlib import Path
import hashlib
import json
import cv2
from PIL import Image, ImageDraw
from xhs_operations import OperationError
from background_workflow import BACKGROUND_CHECKS, BACKGROUND_REVIEW_PROMPT

VERSION = 2
CHECKS = ('identity', 'shape_proportion', 'color_label', 'parts_connections',
          'contact_edges', 'temporal_consistency')
REVIEW_PROMPT = '''
主体商品是交付硬性条件，背景漂亮不能抵消主体错误。只依据实际原图和本次图片/连续帧核对：
同款外观、比例和完整轮廓、颜色标签、零件数量与连接、细杆杆尖到根部完整长度、手部接触和边缘、帧间稳定性。
透视变化可正常改变投影长度；突然截短、缺件、增生、假抖动、局部变形或漂移应判fail。
缩图看不清、没有对应原素材、细杆或关键结构无法确认时判uncertain，不允许猜pass。
动态接触图包含全部解码帧，但不等于原尺寸逐像素校验；细节不足必须写uncertain。
JSON另加subject_observations数组，每张配图index恰好一项，每项为
{"index":0,"checks":{"identity":{"status":"pass|fail|uncertain","evidence":"可见依据"},
"shape_proportion":{"status":"pass|fail|uncertain","evidence":"可见依据"},
"color_label":{"status":"pass|fail|uncertain","evidence":"可见依据"},
"parts_connections":{"status":"pass|fail|uncertain","evidence":"可见依据"},
"contact_edges":{"status":"pass|fail|uncertain","evidence":"可见依据"},
"temporal_consistency":{"status":"pass|fail|uncertain","evidence":"连续帧依据；静态图注明不涉及动态"}}}。
用户指定的纯文字封面不要求出现商品，但须逐项注明此例外。任何fail或uncertain均不得标为成品。
''' + BACKGROUND_REVIEW_PROMPT


def file_fingerprint(outputs, resolve):
    rows = []
    for output in outputs:
        files = {}
        for field in ('path', 'motion_path', 'preview_path'):
            if output.get(field):
                with Path(resolve(output[field])).open('rb') as stream:
                    files[field] = hashlib.file_digest(stream, 'sha256').hexdigest()
        if not files.get('path'):
            raise OperationError('主体核验缺少实际图片')
        rows.append({'files': files, 'source_original_sha256': output.get('source_original_sha256'),
                     'source_identity': output.get('source_identity')})
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()


def motion_sheets(path, index):
    """Decode each frame into chronological review sheets; never drop frames."""
    capture = cv2.VideoCapture(str(path))
    expected = round(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    frames, sheets, batch = 0, [], []
    def flush():
        canvas = Image.new('RGB', (960, 1104), '#eee')
        draw = ImageDraw.Draw(canvas)
        for j, (number, im) in enumerate(batch):
            x, y = j % 5 * 192, j // 5 * 276
            canvas.paste(im, (x, y + 20))
            draw.text((x+2, y+2), f'index={index} frame={number}', fill='black')
        buffer = BytesIO(); canvas.save(buffer, 'JPEG', quality=88)
        sheets.append(('image/jpeg', buffer.getvalue()))
        batch.clear()
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if frames >= 240:
                raise OperationError('主体动态核验超过240帧，请分段核对后继续')
            im = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            im.thumbnail((192,256)); batch.append((frames,im)); frames += 1
            if len(batch) == 20:
                flush()
        if batch:
            flush()
    finally:
        capture.release()
    if frames == 0 or (expected and frames != expected):
        raise OperationError('主体动态核验未完整解码，不能标成品')
    return sheets, {'index': index, 'decoded_frames': frames, 'provided_frames': frames,
                    'all_frames_provided': True, 'review_scope': 'chronological full-frame contact sheets'}


def assess(observations, outputs, coverage, resolve, *, version=VERSION):
    if type(version) is not int or version not in (1, VERSION):
        raise OperationError('不支持的商品场景核验版本')
    count = len(outputs); issues = []; by_index = {}
    if isinstance(observations, list):
        for row in observations:
            if isinstance(row, dict) and type(row.get('index')) is int:
                by_index.setdefault(row['index'], []).append(row)
    for index, output in enumerate(outputs):
        reasons = []
        rows = by_index.get(index, [])
        checks = rows[0].get('checks') if len(rows) == 1 else None
        if not isinstance(checks, dict) or set(checks) != set(CHECKS):
            reasons.append('主体核验缺少完整、逐项的观察依据')
        else:
            for key in CHECKS:
                value = checks[key]
                if (not isinstance(value, dict) or value.get('status') != 'pass'
                        or not isinstance(value.get('evidence'), str) or not value['evidence'].strip()):
                    reasons.append('主体核验未通过或无法确认：' + key)
        if version >= 2:
            background = rows[0].get('background_checks') if len(rows) == 1 else None
            if not isinstance(background, dict) or set(background) != set(BACKGROUND_CHECKS):
                reasons.append('商品场景核验缺少完整换景与真实感的逐项依据')
            else:
                for key in BACKGROUND_CHECKS:
                    value = background[key]
                    if (not isinstance(value, dict) or value.get('status') != 'pass'
                            or not isinstance(value.get('evidence'), str) or not value['evidence'].strip()):
                        reasons.append('商品场景未通过或无法确认：' + key)
        if output.get('kind') == 'live_photo':
            item = coverage.get(str(index), {})
            if (item.get('all_frames_provided') is not True
                    or type(item.get('decoded_frames')) is not int or item['decoded_frames'] < 1
                    or item.get('provided_frames') != item['decoded_frames']):
                reasons.append('主体动态核验未覆盖全部帧')
        if reasons:
            issues.append({'index': index, 'reason': '；'.join(reasons),
                           'repair_target': 'media', 'replacement_caption': ''})
    if (not isinstance(observations, list) or len(observations) != count
            or set(by_index) != set(range(count)) or any(len(v) != 1 for v in by_index.values())):
        if not issues:
            issues.append({'index': 0, 'reason': '主体核验页码不完整或重复', 'repair_target': 'media', 'replacement_caption': ''})
    return {'version': version, 'passed': not issues, 'observations': observations,
            'coverage': coverage, 'fingerprint': file_fingerprint(outputs, resolve),
            'user_confirmed': False}, issues


def validate_delivery(run, resolve):
    if run.get('content_type') != 'graphic' or not run['plan'].get('subject_integrity_version'):
        return
    saved = run['plan'].get('subject_integrity_review') or {}
    # Existing records retain their recorded review scope. A new review always
    # uses VERSION, set by the factory, and cannot reuse a legacy pass.
    version = run['plan']['subject_integrity_version']
    checked, _ = assess(saved.get('observations'), run['outputs'], saved.get('coverage') or {}, resolve, version=version)
    if (saved.get('version') != version or saved.get('passed') is not True
            or not checked['passed'] or saved.get('fingerprint') != checked['fingerprint']):
        raise OperationError('主体商品尚未核验、存在问题或媒体已变更，请复核后完成成品')
