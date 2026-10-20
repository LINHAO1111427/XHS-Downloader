"""Speech transcription, complete-thought grouping, and transcript caching for remixing."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Iterable

import imageio_ffmpeg


class SpeechTranscriptionError(RuntimeError):
    pass


@dataclass(frozen=True)
class SpeechSegment:
    start: float
    end: float
    text: str


_END_PUNCTUATION = re.compile(r"[。！？!?；;…][”’\"']?$")
_CONNECTOR = re.compile(
    r"^(?:所以|但是|但|因为|然后|而且|如果|虽然|不过|就是|那么|其实|这个时候|这样|接着|同时|另外|并且|可是|因此|于是)"
)
_CACHE_VERSION = 3
_MODEL_LOCK = Lock()
_MODELS: dict[tuple[str, str, str], object] = {}


def _clean_text(parts: Iterable[str]) -> str:
    text = "".join(parts).strip()
    text = re.sub(r"\s+([,.;:!?，。；：！？])", r"\1", text)
    return re.sub(r" {2,}", " ", text)


def build_complete_segments(
    words: Iterable[dict],
    *,
    duration: float | None = None,
    pause_seconds: float = 0.72,
    start_padding: float = 0.10,
    end_padding: float = 0.16,
) -> list[dict]:
    """Group timestamped ASR words at punctuation or natural pauses.

    Connective-led phrases are attached to their preceding sentence so clips do
    not begin with a dangling "所以/但是/然后". Padding is bounded and adjacent
    segments never overlap.
    """
    valid = []
    for item in words:
        try:
            start, end, text = float(item["start"]), float(item["end"]), str(item["text"])
        except (KeyError, TypeError, ValueError):
            continue
        if start < 0 or end <= start or not text.strip():
            continue
        valid.append({"start": start, "end": end, "text": text,
                      "segment_boundary": bool(item.get("segment_boundary"))})
    valid.sort(key=lambda item: (item["start"], item["end"]))
    if not valid:
        return []

    grouped: list[SpeechSegment] = []
    current: list[dict] = []

    def flush() -> None:
        nonlocal current
        if not current:
            return
        grouped.append(SpeechSegment(current[0]["start"], current[-1]["end"],
                                     _clean_text(word["text"] for word in current)))
        current = []

    for word in valid:
        if current and (word.get("segment_boundary")
                        or word["start"] - current[-1]["end"] >= pause_seconds):
            flush()
        current.append(word)
        if _END_PUNCTUATION.search(word["text"].strip()):
            flush()
    flush()

    thoughts: list[SpeechSegment] = []
    for item in grouped:
        if (thoughts and _CONNECTOR.search(item.text)
                and item.start - thoughts[-1].end <= max(1.2, pause_seconds + .35)):
            previous = thoughts.pop()
            thoughts.append(SpeechSegment(previous.start, item.end,
                                          _clean_text((previous.text, item.text))))
        else:
            thoughts.append(item)

    padded = []
    for index, item in enumerate(thoughts):
        lower = 0.0 if index == 0 else (thoughts[index - 1].end + item.start) / 2
        upper = (duration if duration is not None else item.end + end_padding)
        if index + 1 < len(thoughts):
            upper = min(upper, (item.end + thoughts[index + 1].start) / 2)
        start = max(lower, item.start - start_padding)
        end = min(upper, item.end + end_padding)
        if end > start:
            padded.append({"start": round(start, 3), "end": round(end, 3), "text": item.text})
    return padded


def _cache_path(source: Path, cache_root: Path, model_name: str) -> Path:
    stat = source.stat()
    identity = f"{source.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|{model_name}|{_CACHE_VERSION}"
    return cache_root / (hashlib.sha256(identity.encode("utf-8")).hexdigest() + ".json")


def _load_model(model_name: str):
    device = os.environ.get("XHS_WHISPER_DEVICE", "cpu").strip() or "cpu"
    compute_type = os.environ.get(
        "XHS_WHISPER_COMPUTE_TYPE", "int8" if device == "cpu" else "float16"
    ).strip()
    key = (model_name, device, compute_type)
    with _MODEL_LOCK:
        if key not in _MODELS:
            try:
                from faster_whisper import WhisperModel
            except ImportError as error:
                raise SpeechTranscriptionError("缺少 faster-whisper 语音转写组件") from error
            try:
                _MODELS[key] = WhisperModel(
                    model_name,
                    device=device,
                    compute_type=compute_type,
                    download_root=os.environ.get("XHS_WHISPER_MODEL_DIR") or None,
                )
            except Exception as error:
                raise SpeechTranscriptionError(f"语音模型加载失败：{error}") from error
        return _MODELS[key]


def transcribe_video(source: Path, *, cache_root: Path, duration: float | None = None) -> list[dict]:
    """Return cached complete spoken thoughts with source-video timestamps."""
    source = Path(source)
    model_name = os.environ.get("XHS_WHISPER_MODEL", "small").strip() or "small"
    cache_root = Path(cache_root) / ".video-transcripts"
    cache_root.mkdir(parents=True, exist_ok=True)
    cached = _cache_path(source, cache_root, model_name)
    if cached.is_file():
        try:
            payload = json.loads(cached.read_text(encoding="utf-8"))
            if payload.get("version") == _CACHE_VERSION and isinstance(payload.get("segments"), list):
                return payload["segments"]
        except (OSError, ValueError, TypeError):
            pass

    language = os.environ.get("XHS_WHISPER_LANGUAGE", "zh").strip() or None
    try:
        stream, info = _load_model(model_name).transcribe(
            str(source), language=language, beam_size=5, vad_filter=True,
            word_timestamps=True, condition_on_previous_text=False,
        )
        words, fallback = [], []
        for segment in stream:
            if float(getattr(segment, "no_speech_prob", 0) or 0) >= .72:
                continue
            start, end = float(segment.start), float(segment.end)
            text = str(segment.text).strip()
            if text:
                fallback.append({"start": start, "end": end, "text": text,
                                 "segment_boundary": True})
            segment_words = []
            for word in getattr(segment, "words", None) or []:
                probability = float(getattr(word, "probability", 1) or 0)
                if word.start is not None and word.end is not None and probability >= .20:
                    segment_words.append({"start": float(word.start), "end": float(word.end),
                                          "text": str(word.word)})
            if segment_words:
                segment_words[0]["segment_boundary"] = True
                words.extend(segment_words)
        segments = build_complete_segments(words or fallback, duration=duration)
        payload = {"version": _CACHE_VERSION, "model": model_name,
                   "language": getattr(info, "language", language), "segments": segments}
        temporary = cached.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(cached)
        return segments
    except SpeechTranscriptionError:
        raise
    except Exception as error:
        raise SpeechTranscriptionError(f"语音转写失败：{error}") from error


def clip_uses_complete_segments(start: float, end: float, segments: list[dict], tolerance: float = .35) -> bool:
    """True when a clip contains no speech or starts/ends at complete-thought boundaries."""
    overlapping = [item for item in segments
                   if start < float(item["end"]) - tolerance and end > float(item["start"]) + tolerance]
    if not overlapping:
        return True
    return (abs(start - float(overlapping[0]["start"])) <= tolerance
            and abs(end - float(overlapping[-1]["end"])) <= tolerance)


def extract_audio_spine(source: Path, target: Path, start: float, end: float) -> Path:
    """Extract one continuous, lossless narration track for a narrative remix."""
    source, target = Path(source), Path(target)
    try:
        start, end = float(start), float(end)
    except (TypeError, ValueError) as error:
        raise SpeechTranscriptionError("主音频起止时间无效") from error
    if start < 0 or end <= start:
        raise SpeechTranscriptionError("主音频需要正向时间范围")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.stem + ".part" + target.suffix)
    command = [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
               "-nostdin", "-y", "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}",
               "-i", str(source), "-vn", "-ac", "2", "-ar", "48000",
               "-c:a", "pcm_s16le", str(temporary)]
    try:
        result = subprocess.run(command, capture_output=True, timeout=600)
    except subprocess.TimeoutExpired as error:
        temporary.unlink(missing_ok=True)
        raise SpeechTranscriptionError("主音频抽取超时") from error
    if result.returncode:
        temporary.unlink(missing_ok=True)
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise SpeechTranscriptionError("主音频抽取失败：" + detail[-600:])
    temporary.replace(target)
    return target


