"""Readable annotation cues shared by rendering and editable subtitle export."""
import math
import re
from pathlib import Path

from video_compositor import SubtitleCue, VideoToolError


def caption_cues(clips):
    """Time scene annotations within their clip; these are not ASR word timings."""
    cues, clock = [], 0.0
    for clip in clips:
        duration = float(clip['end']) - float(clip['start'])
        text = str(clip.get('caption', '')).strip()
        if not math.isfinite(duration) or duration <= 0 or not text:
            raise VideoToolError('字幕需要非空文字和有效的片段时长')
        # Prefer punctuation boundaries; long legacy captions are paged without dropping text.
        pieces = re.findall(r'[^，。！？；、,!?;\n]+[，。！？；、,!?;]?|\n', text)
        pages, current = [], ''
        for piece in pieces:
            piece = piece.strip()
            if not piece:
                continue
            while len(piece) > 22:
                if current:
                    pages.append(current); current = ''
                pages.append(piece[:22]); piece = piece[22:]
            if current and len(current + piece) > 22:
                pages.append(current); current = ''
            current += piece
        if current:
            pages.append(current)
        if not pages:
            pages = [text]
        weights = [max(6, len(page)) for page in pages]
        if len(pages) > 1 and duration * min(weights) / sum(weights) < .9:
            raise VideoToolError('本段字幕来不及读完，请缩短说明或延长完整镜头')
        elapsed = 0
        for i, page in enumerate(pages):
            start = clock + duration * elapsed / sum(weights)
            elapsed += weights[i]
            end = clock + duration * elapsed / sum(weights)
            cues.append(SubtitleCue(start=round(start, 3), end=round(end, 3), text=page,
                                    position=clip.get('caption_position') or None))
        clock = round(clock + duration, 3)
    return cues


def write_srt(cues, path):
    def stamp(seconds):
        milliseconds = round(seconds * 1000)
        hours, milliseconds = divmod(milliseconds, 3600000)
        minutes, milliseconds = divmod(milliseconds, 60000)
        seconds, milliseconds = divmod(milliseconds, 1000)
        return f'{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}'
    body = '\n\n'.join(f'{i}\n{stamp(c.start)} --> {stamp(c.end)}\n{c.text}' for i,c in enumerate(cues,1))
    Path(path).write_text(body + '\n', encoding='utf-8-sig')
