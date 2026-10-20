"""Knowledge-backed montage rules and observable, local duplicate checks."""
from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher
from pathlib import Path

import cv2
import numpy as np

from video_compositor import VideoToolError, _run, probe_video


QUERY = "视频混剪手法去重 故事主线 完整介绍 连续主音频 音画匹配 完整讲话 画面字幕 音频 历史重复"


class RemixDuplicateError(VideoToolError):
    pass


def knowledge_policy(knowledge, query=""):
    # Re-read every time: confirmed feedback and pinned user requirements stay live.
    entries = knowledge.retrieve_for_creation(QUERY + " " + query, {"general", "note", "image"}, limit=12)
    context = knowledge.context(entries, max_chars=14000, query=QUERY + " " + query)
    course = [entry for entry in entries if "混剪" in entry["title"] or "去重" in entry["title"]]
    content = "\n".join(entry["content"] for entry in course)
    seconds = 3 if re.search(r"(?:隔|每).{0,6}3秒", content) else 5
    for entry in entries:
        if entry['origin'] == 'user_requirement':
            explicit = re.search(r"(?:隔|每).{0,6}([35])秒", entry['content'])
            if explicit:
                seconds = int(explicit.group(1))
                break
    return {
        "version": 1, "shot_seconds": seconds, "context": context,
        "overlay_layers": 2 if '画中画' in content and '不透明度' in content else 0,
        "sources": [{"id": entry["id"], "title": entry["title"], "origin": entry["origin"],
                     "digest": hashlib.sha256(entry["content"].encode()).hexdigest()}
                    for entry in entries],
        "prompt": ("混剪先写完整介绍或故事主线，再选同一素材的连续主音频，最后按主线逐句匹配画面；"
                   "视觉可多来源但必须与当前语义匹配，禁止拼接不同来源的零碎原声。找不到完整主线就报告素材缺口。"
                   f"无讲话镜头优先约{seconds}至5秒；有讲话时完整表达边界优先。"
                   "依据当前商品动作与讲述重新组织开场、展开和收尾，禁止只换文件名或打乱相同片段。"
                   "同一成片避免重复镜头、重复讲话；与历史成片比较镜头区间、画面、首句和字幕。"
                   "不同讲话可以使用相似商品画面；不要为了去重截断动作或编造卖点。"
                   "课程经验与历史生成稿均不是平台检测结论。"),
    }


def apply_knowledge_layers(video, sources, policy, work):
    """Apply the course's quiet video layers and brief entrance; preserve main audio."""
    count = min(2, max(0, int(policy.get('overlay_layers', 0))))
    if not count or not sources:
        return []
    meta = probe_video(video)
    width, height = meta['size']
    inputs = ['-i', str(video)]
    filters, previous, applied = [], '0:v', []
    unique = list(dict.fromkeys(sources))
    for index in range(count):
        source = unique[index % len(unique)]
        inputs += ['-stream_loop', '-1', '-i', str(source)]
        alpha = .01 if index == 0 else .02
        # Fade precedes alpha scaling so it never raises the layer above 1–2%.
        filters.append(f'[{index+1}:v]setpts=PTS-STARTPTS,fps=30,'
                       f'scale={width}:{height}:force_original_aspect_ratio=increase,'
                       f'crop={width}:{height},setsar=1,format=rgba,'
                       f'fade=t=in:st=0:d=0.2:alpha=1,colorchannelmixer=aa={alpha}[layer{index}]')
        filters.append(f'[{previous}][layer{index}]overlay=shortest=1:format=auto[blend{index}]')
        previous = f'blend{index}'
        applied.append({'kind':'quiet_video_layer', 'opacity':alpha, 'fade_seconds':.2,
                        'source':Path(source).name, 'audio':'muted'})
    target = work/'knowledge-layers.mp4'
    _run([*inputs, '-filter_complex', ';'.join(filters), '-map', f'[{previous}]', '-map', '0:a?',
          '-t', str(meta['duration']), '-c:v', 'libx264', '-crf', '17', '-preset', 'fast',
          '-pix_fmt', 'yuv420p', '-c:a', 'copy', '-movflags', '+faststart', str(target)])
    checked = probe_video(target)
    if checked['size'] != meta['size'] or abs(checked['duration']-meta['duration']) > .1:
        raise VideoToolError('知识库叠层输出与主视频尺寸或时长不一致')
    target.replace(video)
    return applied


def file_digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def normalized_text(text):
    return "".join(c for c in str(text).casefold() if c.isalnum())


def similar_text(first, second):
    first, second = normalized_text(first), normalized_text(second)
    return len(first) >= 8 and len(second) >= 8 and SequenceMatcher(None, first, second, autojunk=False).ratio() >= .9


def visual_signature(path, start, end):
    cap = cv2.VideoCapture(str(path))
    samples = []
    try:
        for fraction in (.15, .5, .85):
            cap.set(cv2.CAP_PROP_POS_MSEC, (start + (end - start) * fraction) * 1000)
            ok, frame = cap.read()
            if not ok:
                raise VideoToolError("去重检查读取视频帧失败，请检查素材完整性")
            gray = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (32, 32))
            dct = cv2.dct(gray.astype(np.float32))[:8, :8].flatten()[1:]
            bits = dct > np.median(dct)
            color = cv2.resize(frame, (4, 4), interpolation=cv2.INTER_AREA).flatten()
            samples.append({"hash": "".join("1" if b else "0" for b in bits), "color": color.tolist()})
    finally:
        cap.release()
    return samples


def similar_visual(first, second):
    if len(first) != 3 or len(second) != 3:
        return False
    return all(sum(a != b for a, b in zip(x["hash"], y["hash"])) <= 5
               and np.mean(np.abs(np.array(x["color"], dtype=float) - y["color"])) <= 10
               for x, y in zip(first, second))


def duplicate_reason(first, second):
    overlap = max(0, min(first["end"], second["end"]) - max(first["start"], second["start"]))
    if first["sha256"] == second["sha256"] and overlap / (first["end"] - first["start"]) >= .8:
        return "相同素材区间（含改名副本）"
    if similar_text(first["speech"], second["speech"]):
        return "讲话内容近似重复"
    # Similar product shots can carry different spoken information. Unknown audio
    # is not equivalent to silence and must not be discarded on pixels alone.
    if not first["has_audio"] and not second["has_audio"] and similar_visual(first["visual"], second["visual"]):
        return "三帧画面近似重复"
    return ""


def inspect_plan(plan, *, policy, speech=None, history=(), remove_duplicates=False):
    """Return retained clips and an auditable report, never a platform pass score."""
    speech = speech or {}
    hashes, shots, kept, rejected = {}, [], [], []
    for index, (path, clip, meta) in enumerate(plan):
        key = str(path.resolve())
        if key not in hashes:
            hashes[key] = file_digest(path)
        spoken = " ".join(segment.get("text", "") for segment in speech.get(key, [])
                          if segment["start"] < clip.end and segment["end"] > clip.start)
        shot = {"sha256": hashes[key], "start": round(clip.start, 3), "end": round(clip.end, 3),
                "speech": spoken, "has_audio": bool(meta.get("audio_codec")),
                "visual": visual_signature(path, clip.start, clip.end)}
        reason = next((reason for old in shots if (reason := duplicate_reason(shot, old))), "")
        if reason:
            rejected.append({"index": index, "reason": reason})
            if remove_duplicates:
                continue
        shots.append(shot)
        kept.append((path, clip, meta))
    history_matches = []
    for previous in history:
        old = previous.get("shots", [])
        repeated = [shot for shot in shots if any(duplicate_reason(shot, other) for other in old)]
        total_seconds = sum(shot['end'] - shot['start'] for shot in shots)
        reused_seconds = sum(shot['end'] - shot['start'] for shot in repeated)
        if total_seconds and reused_seconds / total_seconds >= .8:
            history_matches.append({"reused": len(repeated), "total": len(shots),
                                    "reused_seconds": round(reused_seconds, 3), "total_seconds": round(total_seconds, 3)})
    report = {"version": 1, "sources": policy.get("sources", []), "shot_seconds": policy.get("shot_seconds"),
              "checks": ["素材哈希与区间", "三帧画面", "完整讲话文本", "历史镜头复用"],
              "shots": shots, "rejected": rejected, "history_matches": history_matches,
              "history_count": len(history), "speech_checked": any(speech.values()),
              "removed_count": len(rejected) if remove_duplicates else 0,
              "passed": (remove_duplicates or not rejected) and not history_matches and bool(shots)}
    return kept, report


def require_distinct(report):
    if not report["passed"]:
        reasons = list(dict.fromkeys(item["reason"] for item in report["rejected"]))
        if report["history_matches"]:
            reasons.append("至少80%的选段时长与历史成片重复，请补充新镜头或重新选段")
        raise RemixDuplicateError("多重去重检查未通过：" + "；".join(reasons))
