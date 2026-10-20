"""Paired still + motion assets for account-scoped Live graphic notes."""
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
from types import SimpleNamespace
import hashlib
import math
import shutil

import cv2
from PIL import Image, ImageOps, ImageFilter

from live_photo import create_live_video
from livephoto_metadata import inject_exif, read_apple_makernote, remux, load, KEY_CONTENT_ID
from video_compositor import _run, probe_video


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def movie_identifier(path):
    _data, boxes = load(str(path))
    moov = next(box for box in boxes if box.type == b"moov")
    meta = moov.get(b"meta")
    if meta is None:
        raise ValueError("Live 动态组件缺少配对元数据")
    keys = meta.get(b"keys").payload
    pos, identifier_index = 8, None
    for index in range(1, int.from_bytes(keys[4:8], "big") + 1):
        size = int.from_bytes(keys[pos:pos + 4], "big")
        if size < 8 or pos + size > len(keys):
            raise ValueError("Live 配对元数据损坏")
        if keys[pos + 8:pos + size].decode("utf8") == KEY_CONTENT_ID:
            identifier_index = index
        pos += size
    if identifier_index is None:
        raise ValueError("Live 动态组件缺少配对标识")
    return meta.get(b"ilst").get(identifier_index.to_bytes(4, "big")).get(b"data").payload[8:].decode("ascii")


def validate_live_pair(still, motion, identifier=""):
    with Image.open(still) as image:
        still_size = image.size
        image.verify()
    cid = read_apple_makernote(Path(still).read_bytes())
    try:
        motion_id = movie_identifier(motion)
    except (StopIteration, AttributeError, IndexError, UnicodeError) as error:
        raise ValueError("Live 动态组件元数据损坏") from error
    if not cid or cid != motion_id or (identifier and cid != identifier):
        raise ValueError("Live 静态图与动态组件配对不一致")
    meta = probe_video(Path(motion))
    if tuple(meta['size']) != still_size:
        raise ValueError('Live 静态图与动态组件画幅不一致')
    if not .45 <= meta["duration"] <= 5.2:
        raise ValueError("Live 动态组件时长不正确")
    return cid


def framing_options(canvas_ratio=None, fit='cover', focal_y=.5):
    if canvas_ratio is None:
        return None
    if (not isinstance(canvas_ratio, (tuple, list)) or len(canvas_ratio) != 2
            or any(type(n) is not int or not 1 <= n <= 100 for n in canvas_ratio)
            or fit not in {'cover', 'background'} or type(focal_y) not in (int, float)
            or not math.isfinite(focal_y) or not 0 <= focal_y <= 1):
        raise ValueError('Live 画幅、填充方式或取景位置无效')
    divisor = math.gcd(*canvas_ratio)
    return {'version': 1, 'canvas_ratio': [n // divisor for n in canvas_ratio],
            'fit': fit, 'focal_y': focal_y}


def framing_geometry(size, framing):
    """Exact even aspect ratio, square pixels, no stretching or unnecessary upscale."""
    width, height = size
    rw, rh = framing['canvas_ratio']
    unit = (min if framing['fit'] == 'cover' else max)(width / rw, height / rh)
    unit = max(2, int(unit) // 2 * 2)
    crop_width, crop_height = rw * unit, rh * unit
    output_unit = max(2, min(unit, int(min(1080 / rw, 1920 / rh)) // 2 * 2))
    x = max(0, (width - crop_width) // 4 * 2)
    y = max(0, int((height - crop_height) * framing['focal_y']) // 2 * 2)
    return (x, y, x + crop_width, y + crop_height), (rw * output_unit, rh * output_unit)


def create_live_pair(source: Path, folder: Path, duration=2.0, *, ai_generated=False, start=0.0, trim_bottom=0.0, source_label='',
                     canvas_ratio=None, fit='cover', focal_y=.5):
    """Keep source untouched; write matched JPEG/MOV and browser MP4 preview.

    Camera motion is intentionally recorded as camera motion, not object animation.
    Unique names avoid replacing assets still referenced by an existing publish pack.
    """
    source, folder = Path(source), Path(folder)
    framing = framing_options(canvas_ratio, fit, focal_y)
    is_video = source.suffix.lower() in {".mp4", ".mov", ".m4v"}
    if not isinstance(source_label, str) or len(source_label) > 32 or (source_label and not is_video):
        raise ValueError('来源标识须为不超过32字的视频说明')
    if not math.isfinite(trim_bottom) or not 0 <= trim_bottom <= .25 or (trim_bottom and not is_video):
        raise ValueError("视频底部裁切比例应在 0 至 0.25 之间")
    if (not math.isfinite(start) or not math.isfinite(duration) or start < 0
            or not .5 <= duration <= 5 or (not is_video and start != 0)):
        raise ValueError("Live 起点或时长无效（每段 0.5 至 5 秒）")
    if is_video and start + duration > probe_video(source)["duration"] + .04:
        raise ValueError("Live 选段超出原视频时长")
    # Provenance remains in the returned production record, but generation labels
    # must never be burned into a published graphic or Live frame.
    burn_source_label = source_label if not any(term in source_label for term in ("AI", "ai", "人工智能")) else ""
    folder.mkdir(parents=True, exist_ok=True)
    cid = uuid4().hex
    still, motion, preview = [folder / f"live_{cid}{suffix}" for suffix in (".jpg", ".mov", ".mp4")]
    try:
        with TemporaryDirectory(prefix="live-note-", dir=folder) as temporary:
            work = Path(temporary)
            local_source = work / ("source" + source.suffix)
            shutil.copy2(source, local_source)
            if source.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
                local_source = work / "oriented.png"
                with Image.open(source) as opened:
                    image = ImageOps.exif_transpose(opened).convert("RGB")
                    if framing:
                        box, size = framing_geometry(image.size, framing)
                        if fit == 'cover':
                            image = image.crop(box).resize(size, Image.Resampling.LANCZOS)
                        else:
                            background = ImageOps.fit(image, size).filter(ImageFilter.GaussianBlur(20))
                            image.thumbnail(size, Image.Resampling.LANCZOS)
                            background.paste(image, ((size[0]-image.width)//2, (size[1]-image.height)//2))
                            image = background
                    # AI provenance belongs to the saved production record. The user
                    # requested clean image pixels, including the Live motion frames.
                    image.save(local_source)
            video = create_live_video(local_source, start=start, duration=duration)
            if is_video:
                # Short visual excerpts are silent, so they never cut spoken sentences.
                silent = work / "silent.mov"
                encoding = (["-vf", f"crop=iw:trunc(ih*{1-trim_bottom}/2)*2:0:0", "-c:v", "libx264", "-crf", "18"]
                            if trim_bottom else ["-c:v", "copy"])
                _run(["-i", str(video), "-map", "0:v:0", "-an", *encoding, str(silent)])
                video = silent
                if framing:
                    # Crop after the requested bottom trim; apply the same framing to
                    # motion, its extracted still and the browser preview.
                    box, size = framing_geometry(probe_video(video)['size'], framing)
                    framed = work / 'framed.mov'
                    w, h = size
                    if fit == 'cover':
                        x, y, right, bottom = box
                        filters = ['-vf', f'crop={right-x}:{bottom-y}:{x}:{y},scale={w}:{h}:flags=lanczos,setsar=1']
                    else:
                        filters = ['-filter_complex',
                            f'[0:v]split[bg][fg];[bg]scale={w}:{h}:force_original_aspect_ratio=increase,'
                            f'crop={w}:{h},gblur=sigma=20[back];'
                            f'[fg]scale={w}:{h}:force_original_aspect_ratio=decrease:force_divisible_by=2[front];'
                            '[back][front]overlay=(W-w)/2:(H-h)/2,setsar=1[v]', '-map', '[v]']
                    _run(['-i', str(video), *filters, '-an', '-c:v', 'libx264', '-crf', '18',
                          '-pix_fmt', 'yuv420p', str(framed)])
                    video = framed
                if burn_source_label:
                    from remix_av import subtitle_image
                    width, height = probe_video(video)['size']
                    label = work / 'source-label.png'
                    label_height = subtitle_image(burn_source_label, width, height, SimpleNamespace(
                        subtitle_size=22, subtitle_style='outline', subtitle_color='white'), label)
                    marked = work / 'labelled.mov'
                    _run(['-i', str(video), '-loop', '1', '-i', str(label), '-filter_complex',
                          f'[0:v][1:v]overlay=0:{max(0, round(height*.95)-label_height)}:shortest=1[v]',
                          '-map', '[v]', '-an', '-c:v', 'libx264', '-crf', '18', '-pix_fmt', 'yuv420p', str(marked)])
                    video = marked
            remux(str(video), str(motion), cid, verify=True)
            capture = cv2.VideoCapture(str(motion))
            try:
                ok, frame = capture.read()
                if not ok:
                    raise ValueError("Live 首帧读取失败")
            finally:
                capture.release()
            buffer = BytesIO()
            Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).save(buffer, "JPEG", quality=97)
            still.write_bytes(inject_exif(buffer.getvalue(), cid))
            _run(["-i", str(motion), "-map", "0:v:0", "-an", "-c:v", "copy", "-movflags", "+faststart", str(preview)])
            validate_live_pair(still, motion, cid)
            probe_video(preview)
        return {"path": still, "motion_path": motion, "preview_path": preview,
                "asset_identifier": cid, "duration": probe_video(motion)["duration"],
                "motion_mode": "source_video" if is_video else "camera",
                "source_start": start, "source_end": start + duration,
                "trim_bottom": trim_bottom,
                **({'framing': framing} if framing else {}),
                "source_label": source_label,
                **({'visible_ai_label': 'none'} if not is_video else {}),
                "audio_policy": "silent_visual_excerpt" if is_video else "silent_camera_motion",
                "source_sha256": sha256(source)}
    except Exception:
        for target in (still, motion, preview):
            target.unlink(missing_ok=True)
        raise
