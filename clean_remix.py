"""Full-frame montage, automatic non-repeating cuts and selected watermark tracking."""
from pathlib import Path
from server_limits import limited_media
from tempfile import TemporaryDirectory
from uuid import uuid4
import math
import subprocess

import cv2
import numpy as np
import imageio_ffmpeg

from video_compositor import RemixClip, VideoToolError, validate_recipe, _run
from speech_remix import SpeechTranscriptionError, transcribe_video


def _even_plan(sources, metas, recipe, shot_seconds=6):
    """Legacy visual sampling for silent material or explicitly disabled speech planning."""
    clips = recipe.clips or [RemixClip(path=p.name) for p in sources]
    lengths = [(c.end if c.end is not None else m['duration']) - c.start for c, m in zip(clips, metas)]
    total = sum(lengths)
    budget = min(total, recipe.target_duration * recipe.speed) if recipe.auto_cut else total
    plan = []
    for source, clip, meta, length in zip(sources, clips, metas, lengths):
        take = length * budget / total
        count = max(1, min(60, math.ceil(take / (shot_seconds * recipe.speed)))) if recipe.auto_cut else 1
        window = take / count
        for i in range(count):
            start = clip.start + (length-window) * i / max(1, count-1)
            plan.append((source, clip.model_copy(update={'start': start, 'end': start+window}), meta))
    return plan


def _speech_plan(sources, metas, recipe, transcripts):
    clips = recipe.clips or [RemixClip(path=p.name) for p in sources]
    candidates = []
    for source_index, (source, clip, meta, segments) in enumerate(zip(sources, clips, metas, transcripts)):
        limit = clip.end if clip.end is not None else meta['duration']
        for segment in segments:
            start, end = float(segment['start']), float(segment['end'])
            if start + .05 < clip.start or end - .05 > limit or end - start < .35:
                continue
            candidates.append((source_index, source, clip.model_copy(update={
                'start': max(clip.start, start), 'end': min(limit, end),
            }), meta))
    if not candidates:
        return []

    durations = [item[2].end - item[2].start for item in candidates]
    target = min(sum(durations), recipe.target_duration * recipe.speed)
    target_ticks = max(1, round(target * 10))
    max_ticks = target_ticks + max(1, round(max(durations) * 10))
    # At each tenth of a second, retain the combination with the broadest source
    # coverage and then the fewest cuts. Final choice prioritizes target closeness.
    states = {0: ((), frozenset())}
    for index, (source_index, _source, _clip, _meta) in enumerate(candidates):
        ticks = max(1, round(durations[index] * 10))
        for current in sorted(tuple(states), reverse=True):
            chosen, covered = states[current]
            if len(chosen) >= 20 or current + ticks > max_ticks:
                continue
            proposal = (chosen + (index,), covered | {source_index})
            existing = states.get(current + ticks)
            if existing is None or (len(proposal[1]), -len(proposal[0])) > (len(existing[1]), -len(existing[0])):
                states[current + ticks] = proposal
    available = [(ticks, value) for ticks, value in states.items() if ticks]
    _ticks, (indices, _covered) = min(
        available,
        key=lambda item: (abs(item[0] - target_ticks), item[0] > target_ticks,
                          -len(item[1][1]), len(item[1][0])),
    )
    selected = [candidates[index] for index in indices]
    merged = []
    for source_index, source, clip, meta in selected:
        if (merged and merged[-1][0] == source_index
                and clip.start - merged[-1][2].end <= .35):
            previous = merged[-1][2]
            merged[-1] = (source_index, source, previous.model_copy(update={'end': clip.end}), meta)
        else:
            merged.append((source_index, source, clip, meta))
    return [(source, clip, meta) for _index, source, clip, meta in merged]


def plan_clips(sources, metas, recipe, transcripts=None, shot_seconds=6):
    """Plan whole spoken thoughts; silent material keeps bounded visual sampling."""
    if recipe.auto_cut and transcripts and any(transcripts):
        speech = _speech_plan(sources, metas, recipe, transcripts)
        if speech:
            return speech
    return _even_plan(sources, metas, recipe, shot_seconds)


def watermark_template(source, region):
    cap = cv2.VideoCapture(str(source))
    try:
        cap.set(cv2.CAP_PROP_POS_MSEC, region.time * 1000)
        ok, im = cap.read()
        if not ok:
            raise VideoToolError("水印参考帧读取失败，请重新选择时间")
        h, w = im.shape[:2]
        x, y = round(region.x*w), round(region.y*h)
        tw, th = round(region.width*w), round(region.height*h)
        gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
        # Both light and dark text are included. The user selects a tight text box.
        edge = cv2.absdiff(gray, cv2.GaussianBlur(gray, (0, 0), 3))
        template = edge[y:y+th, x:x+tw].copy()
        if template.size == 0 or float(template.std()) < 2:
            raise VideoToolError("选框内缺少清晰水印，请在水印清楚的画面重新框选")
        glyph = cv2.dilate((template > 18).astype(np.uint8)*255, np.ones((3, 3), np.uint8))
        return template, glyph
    finally:
        cap.release()


def repair_frame(im, template, glyph):
    gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    edge = cv2.absdiff(gray, cv2.GaussianBlur(gray, (0, 0), 3))
    match = cv2.matchTemplate(edge, template, cv2.TM_CCOEFF_NORMED)
    _, score, _, (x, y) = cv2.minMaxLoc(match)
    if score < 0.4:
        return im
    h, w = glyph.shape
    mask = np.zeros(im.shape[:2], np.uint8)
    mask[y:y+h, x:x+w] = glyph
    return cv2.inpaint(im, mask, 3, cv2.INPAINT_TELEA)




@limited_media
def render_clean_remix(sources, output, *, root, recipe, progress=None, dedupe=None):
    if output.resolve() in [s.resolve() for s in sources]:
        raise VideoToolError("成片需要另存，不能覆盖源视频")
    metas = validate_recipe(root, sources, recipe)
    transcripts = None
    if recipe.auto_cut and recipe.speech_aware and recipe.preserve_audio:
        transcripts = []
        try:
            for source, meta in zip(sources, metas):
                transcripts.append(transcribe_video(
                    source, cache_root=root, duration=meta['duration'],
                ) if meta.get('audio_codec') else [])
        except SpeechTranscriptionError as error:
            raise VideoToolError(f"完整讲话转写失败：{error}") from error
    plan = plan_clips(sources, metas, recipe, transcripts,
                      (dedupe or {}).get('policy', {}).get('shot_seconds', 6))
    if dedupe is not None:
        from remix_knowledge import inspect_plan, require_distinct
        speech = {str(path.resolve()): segments for path, segments in zip(sources, transcripts or [])}
        if dedupe.get('prechecked'):
            report = dedupe['prechecked']
        else:
            plan, report = inspect_plan(plan, policy=dedupe['policy'], speech=speech,
                                        history=dedupe.get('history', []),
                                        remove_duplicates=recipe.auto_cut and not recipe.subtitles and not recipe.voiceover)
        dedupe['report'] = report
        require_distinct(report)
    ratio = min(1, 1080 / max(metas[0]['size']))
    width, height = [max(2, int(v*ratio)//2*2) for v in metas[0]['size']]
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f'.{output.stem}.{uuid4().hex}.part.mp4')
    try:
        with TemporaryDirectory(prefix='.clean-remix-', dir=output.parent) as folder:
            work = Path(folder)
            templates = {}
            for i, (source, clip, meta) in enumerate(plan):
                duration = (clip.end-clip.start)/recipe.speed
                input_args = ['-ss', str(clip.start), '-t', str(clip.end-clip.start), '-i', str(source)]
                video_input, audio_input = 0, 0
                repaired = None
                regions = ([clip.watermark] if clip.watermark else []) + clip.watermarks
                if regions:
                    selected_templates = []
                    for region in regions:
                        key = (str(source), region.model_dump_json())
                        if key not in templates:
                            templates[key] = watermark_template(source, region)
                        selected_templates.append((region, templates[key]))
                    repaired = work/f'repaired{i}.mkv'
                    cap = cv2.VideoCapture(str(source))
                    fps = cap.get(cv2.CAP_PROP_FPS)
                    cap.set(cv2.CAP_PROP_POS_MSEC, clip.start*1000)
                    sw, sh = meta['size']
                    command = [imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-y', '-f', 'rawvideo',
                               '-pix_fmt', 'bgr24', '-s', f'{sw}x{sh}', '-r', str(fps), '-i', 'pipe:0',
                               '-c:v', 'ffv1', str(repaired)]
                    with (work/'repair.log').open('wb') as err:
                        process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=err)
                        try:
                            count = max(1, round((clip.end-clip.start)*fps))
                            for f in range(count):
                                ok, im = cap.read()
                                if not ok:
                                    raise VideoToolError("修补片段读取不完整，请缩短结束时间")
                                seconds = clip.start + f/fps
                                for region, template in selected_templates:
                                    if seconds >= region.active_start and (region.active_end is None or seconds < region.active_end):
                                        im = repair_frame(im, *template)
                                process.stdin.write(im.tobytes())
                                if progress and f % 30 == 0:
                                    progress(i+f/count*0.8, len(plan)+1)
                            process.stdin.close()
                            if process.wait(timeout=120):
                                raise VideoToolError("水印修补编码失败")
                        finally:
                            cap.release()
                            if process.poll() is None:
                                process.kill()
                                process.wait()
                    input_args = ['-i', str(repaired), *input_args]
                    audio_input = 1
                edge = recipe.edge_crop
                crop = f'crop=trunc(iw*{1-2*edge}/2)*2:trunc(ih*{1-2*edge}/2)*2,' if edge else ''
                filters = [f'[{video_input}:v]setpts=(PTS-STARTPTS)/{recipe.speed},fps=30,{crop}'
                           f'scale={width}:{height}:force_original_aspect_ratio=increase,'
                           f'crop={width}:{height},setsar=1,'
                           f'hqdn3d=1.2:1.0:3.0:2.5,unsharp=5:5:0.25:3:3:0.10,'
                           f'format=bgr0[v]']
                audio_map = []
                if recipe.preserve_audio:
                    if meta.get('audio_codec'):
                        filters.append(f'[{audio_input}:a]asetpts=PTS-STARTPTS,atempo={recipe.speed},'
                                       f'aresample=48000,aformat=channel_layouts=stereo,apad,atrim=duration={duration},'
                                       f'afade=t=in:d=0.04,afade=t=out:st={max(0,duration-0.04)}:d=0.04[a]')
                    else:
                        filters.append(f'anullsrc=r=48000:cl=stereo,atrim=duration={duration}[a]')
                    audio_map = ['-map', '[a]', '-c:a', 'pcm_s16le']
                _run([*input_args, '-filter_complex', ';'.join(filters), '-map', '[v]', *audio_map,
                      '-t', str(duration), '-c:v', 'ffv1', str(work/f'clip{i}.mkv')])
                if repaired:
                    repaired.unlink()
                if progress:
                    progress(i+1, len(plan)+1)
            (work/'concat.txt').write_text(''.join(f"file 'clip{i}.mkv'\n" for i in range(len(plan))), encoding='ascii')
            _run(['-f', 'concat', '-safe', '1', '-i', 'concat.txt', '-map', '0',
                  '-c:v', 'libx264', '-crf', '17', '-preset', 'fast', '-pix_fmt', 'yuv420p',
                  '-c:a', 'aac', '-b:a', '160k', '-movflags', '+faststart', str(temporary.resolve())], cwd=work)
            from remix_av import apply_av_edits
            if dedupe is not None:
                from remix_knowledge import apply_knowledge_layers
                dedupe['report']['layers'] = apply_knowledge_layers(temporary, sources, dedupe['policy'], work)
            apply_av_edits(temporary, root=root, recipe=recipe, work=work)
            if recipe.sticker_overlay:
                stickered = work / 'stickered.mp4'
                _run([
                    '-i', str(temporary),
                    '-loop', '1', '-i', str(root / recipe.sticker_overlay),
                    '-filter_complex',
                    '[1:v]format=rgba[sticker];'
                    '[0:v][sticker]overlay=0:0:format=auto:shortest=1[outv]',
                    '-map', '[outv]', '-map', '0:a?',
                    '-c:v', 'libx264', '-preset', 'fast', '-crf', '17',
                    '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '160k',
                    '-movflags', '+faststart', str(stickered),
                ])
                stickered.replace(temporary)
            temporary.replace(output)
            if dedupe is not None:
                dedupe['report']['duration'] = round(sum(c.end-c.start for _, c, _ in plan)/recipe.speed, 3)
                dedupe['report']['edits'] = {'edge_crop': recipe.edge_crop, 'speed': recipe.speed,
                    'subtitles': len(recipe.subtitles), 'music': bool(recipe.music),
                    'voiceover': bool(recipe.voiceover), 'voice_pitch': recipe.voice_pitch,
                    'sticker_overlay': bool(recipe.sticker_overlay), 'denoise_and_sharpen': True}
            if progress:
                progress(len(plan)+1, len(plan)+1)
    finally:
        temporary.unlink(missing_ok=True)

