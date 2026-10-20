"""Local product-preserving composition: original video + background + mask.

White mask pixels select the original frame; black pixels select the edited
background. Masks may be hand-keyframed polygons or aligned SAM 2 mask exports.
No generative model modifies the product. MP4 encoding is still lossy.
"""

from __future__ import annotations

import math
import subprocess
from pathlib import Path
from server_limits import limited_media
from tempfile import TemporaryDirectory
from typing import Annotated, Literal
from uuid import uuid4

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageOps
from pydantic import BaseModel, ConfigDict, Field, model_validator


class VideoToolError(ValueError):
    pass


Unit = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
Seconds = Annotated[float, Field(ge=0, le=3600, allow_inf_nan=False)]


class MaskKeyframe(BaseModel):
    model_config = ConfigDict(extra="forbid")
    time: Seconds
    points: Annotated[list[tuple[Unit, Unit]], Field(min_length=3, max_length=64)]

    @model_validator(mode="after")
    def area(self):
        points = self.points
        area = abs(sum(x * points[(i + 1) % len(points)][1]
                       - y * points[(i + 1) % len(points)][0]
                       for i, (x, y) in enumerate(points))) / 2
        if area < 0.00001:
            raise ValueError("商品轮廓需要至少三个不共线的点")
        return self


class WatermarkRegion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    time: Seconds = 0
    x: Unit
    y: Unit
    width: Annotated[float, Field(gt=0, le=0.5, allow_inf_nan=False)]
    height: Annotated[float, Field(gt=0, le=0.5, allow_inf_nan=False)]
    active_start: Seconds = 0
    active_end: Seconds | None = None

    @model_validator(mode="after")
    def bounds(self):
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("水印选框需要位于画面内")
        if self.active_end is not None and self.active_end <= self.active_start:
            raise ValueError("水印生效结束时间需要大于开始时间")
        return self


class RemixClip(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: Annotated[str, Field(min_length=1, max_length=2048)]
    start: Seconds = 0
    end: Seconds | None = None
    keyframes: Annotated[list[MaskKeyframe], Field(max_length=120)] = Field(default_factory=list)
    interpolation: Literal["linear", "hold"] = "linear"
    mask_path: Annotated[str, Field(max_length=2048)] = ""
    watermark: WatermarkRegion | None = None
    watermarks: Annotated[list[WatermarkRegion], Field(max_length=8)] = Field(default_factory=list)

    @model_validator(mode="after")
    def timeline(self):
        if self.end is not None and self.end <= self.start:
            raise ValueError("片段结束时间需要大于开始时间")
        times = [frame.time for frame in self.keyframes]
        if times != sorted(set(times)):
            raise ValueError("商品关键帧时间需要递增且互不重复")
        if self.interpolation == "linear" and len({len(frame.points) for frame in self.keyframes}) > 1:
            raise ValueError("连续移动的关键帧需要保持相同的轮廓点数")
        if self.mask_path and self.keyframes:
            raise ValueError("请选择轮廓关键帧或导入遮罩其中一种")
        if len(self.watermarks) + bool(self.watermark) > 8:
            raise ValueError("每个片段最多8个水印参考帧")
        return self


class SubtitleCue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: Seconds
    end: Seconds
    text: Annotated[str, Field(min_length=1, max_length=300)]
    position: Literal["top", "center", "bottom"] | None = None

    @model_validator(mode="after")
    def timing(self):
        if self.end <= self.start:
            raise ValueError("字幕结束时间需要大于开始时间")
        return self


class RemixRecipe(BaseModel):
    model_config = ConfigDict(extra="forbid")
    speed: Annotated[float, Field(ge=0.5, le=2, allow_inf_nan=False)] = 1
    clips: Annotated[list[RemixClip], Field(max_length=20)] = Field(default_factory=list)
    background: Annotated[str, Field(max_length=2048)] = ""
    overlay: Annotated[str, Field(max_length=2048)] = ""
    opacity: Unit = 0.25
    overlay_scale: Annotated[float, Field(ge=0.1, le=1, allow_inf_nan=False)] = 1
    overlay_x: Unit = 0.5
    overlay_y: Unit = 0.5
    sticker_overlay: Annotated[str, Field(max_length=2048)] = ""
    preserve_audio: bool = True
    clean_mode: bool = False
    auto_cut: bool = False
    speech_aware: bool = True
    target_duration: Annotated[float, Field(ge=1, le=180, allow_inf_nan=False)] = 45
    edge_crop: Annotated[float, Field(ge=0, le=0.15, allow_inf_nan=False)] = 0
    music: Annotated[str, Field(max_length=2048)] = ""
    voiceover: Annotated[str, Field(max_length=2048)] = ""
    original_volume: Annotated[float, Field(ge=0, le=2, allow_inf_nan=False)] = 1
    music_volume: Annotated[float, Field(ge=0, le=2, allow_inf_nan=False)] = 0.2
    voice_volume: Annotated[float, Field(ge=0, le=2, allow_inf_nan=False)] = 1
    voice_pitch: Annotated[float, Field(ge=-6, le=6, allow_inf_nan=False)] = 0
    subtitles: Annotated[list[SubtitleCue], Field(max_length=120)] = Field(default_factory=list)
    subtitle_size: Annotated[int, Field(ge=16, le=80)] = 36
    subtitle_color: Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")] = "#ffffff"
    subtitle_position: Literal["top", "center", "bottom"] = "bottom"
    subtitle_bottom_margin: Annotated[float, Field(ge=0, le=.4, allow_inf_nan=False)] = .10
    subtitle_style: Literal["outline", "box", "plain"] = "outline"


def probe_video(path: Path) -> dict:
    reader = imageio_ffmpeg.read_frames(str(path))
    try:
        meta = next(reader)
        if not math.isfinite(meta.get("duration", 0)) or not 0 < meta["duration"] <= 3600:
            raise VideoToolError("视频时长需要在 0 到 3600 秒之间")
        if max(meta["size"]) > 8192:
            raise VideoToolError("视频分辨率超过 8192 像素，请先缩小素材")
        return meta
    except (OSError, RuntimeError, StopIteration) as error:
        raise VideoToolError(f"视频读取失败：{path.name}") from error
    finally:
        reader.close()


def asset_path(root: Path, name: str) -> Path:
    target = (root / name).resolve()
    if not target.is_relative_to(root.resolve()) or not target.is_file():
        raise VideoToolError("混剪素材不存在")
    return target


def validate_recipe(root: Path, sources: list[Path], recipe: RemixRecipe) -> list[dict]:
    if not recipe.clean_mode and (recipe.music or recipe.voiceover or recipe.subtitles or recipe.voice_pitch or recipe.original_volume != 1):
        raise VideoToolError("音轨与字幕编辑请使用一键混剪")
    for name in (recipe.music, recipe.voiceover):
        if name:
            audio = asset_path(root, name)
            if audio.suffix.lower() not in {".mp3", ".wav", ".m4a", ".aac", ".ogg"}:
                raise VideoToolError("请选择 MP3、WAV、M4A、AAC 或 OGG 音频")
    if recipe.auto_cut and not recipe.clean_mode:
        raise VideoToolError("自动选段请使用一键混剪模式")
    if recipe.edge_crop and not recipe.clean_mode:
        raise VideoToolError("边缘裁切请使用一键混剪模式")
    if recipe.clean_mode and (recipe.background or recipe.overlay):
        raise VideoToolError("一键混剪使用满屏画面，请清空背景和叠加图片")
    if not 1 <= len(sources) <= 20:
        raise VideoToolError("请选择 1 到 20 个视频片段")
    if recipe.clips and len(recipe.clips) != len(sources):
        raise VideoToolError("片段配置与视频数量不一致")
    metas = [probe_video(source) for source in sources]
    total = 0
    for index, meta in enumerate(metas):
        clip = recipe.clips[index] if recipe.clips else RemixClip(path=sources[index].name)
        end = meta["duration"] if clip.end is None else clip.end
        if end > meta["duration"] + 0.05 or end - clip.start < 0.05:
            raise VideoToolError(f"片段 {index + 1} 的裁剪时间超出视频范围")
        if any(frame.time > meta["duration"] + 0.05 for frame in clip.keyframes):
            raise VideoToolError(f"片段 {index + 1} 的关键帧超出视频时长")
        for region in ([clip.watermark] if clip.watermark else []) + clip.watermarks:
            if not recipe.clean_mode:
                raise VideoToolError("水印修补请使用一键混剪模式")
            if region.time >= meta["duration"]:
                raise VideoToolError("水印参考帧超出视频时长")
            if region.active_start >= meta["duration"] or (region.active_end is not None and region.active_end > meta["duration"]+.05):
                raise VideoToolError("水印生效时间超出原视频时长")
            if region.width * meta["size"][0] < 5 or region.height * meta["size"][1] < 5:
                raise VideoToolError("水印选框太小，请重新框选")
        total += (end - clip.start) / recipe.speed
        if (recipe.background or recipe.overlay) and not (clip.keyframes or clip.mask_path):
            raise VideoToolError(f"请先圈定片段 {index + 1} 的商品轮廓或导入商品遮罩")
        if clip.mask_path:
            mask = asset_path(root, clip.mask_path)
            if mask.suffix.lower() in {".mp4", ".mov", ".m4v"}:
                mask_meta = probe_video(mask)
                if mask_meta["duration"] + 0.05 < end:
                    raise VideoToolError("跟踪遮罩需要覆盖所选片段的完整时间")
            else:
                _check_image(mask)
    if total > 3600:
        raise VideoToolError("单次混剪成片时长最多 60 分钟")
    for name in (recipe.background, recipe.overlay, recipe.sticker_overlay):
        if name:
            _check_image(asset_path(root, name))
    return metas


def _check_image(path: Path) -> None:
    try:
        with Image.open(path) as image:
            if image.width * image.height > 40_000_000:
                raise VideoToolError("图片像素总数超过 4000 万")
            image.verify()
    except (OSError, ValueError, Image.DecompressionBombError) as error:
        raise VideoToolError(f"图片读取失败：{path.name}") from error


def polygon_at(clip: RemixClip, seconds: float) -> list[tuple[float, float]]:
    frames = clip.keyframes
    if not frames:
        return []
    previous = frames[0]
    for following in frames[1:]:
        if seconds < following.time:
            if clip.interpolation == "hold" or seconds <= previous.time:
                return previous.points
            fraction = (seconds - previous.time) / (following.time - previous.time)
            return [(x + (nx - x) * fraction, y + (ny - y) * fraction)
                    for (x, y), (nx, ny) in zip(previous.points, following.points)]
        previous = following
    return previous.points


def fit_size(source: tuple[int, int], canvas: tuple[int, int]) -> tuple[int, int]:
    ratio = min(canvas[0] / source[0], canvas[1] / source[1])
    return tuple(max(2, int(value * ratio) // 2 * 2) for value in source)


def mask_frame(clip: RemixClip, seconds: float, canvas: tuple[int, int], fitted: tuple[int, int]) -> Image.Image:
    mask = Image.new("L", canvas, 0)
    ox, oy = (canvas[0] - fitted[0]) // 2, (canvas[1] - fitted[1]) // 2
    points = [(round(x * (fitted[0] - 1)) + ox, round(y * (fitted[1] - 1)) + oy)
              for x, y in polygon_at(clip, seconds)]
    if points:
        ImageDraw.Draw(mask).polygon(points, fill=255)
    return mask


def _run(arguments: list[str], *, cwd: Path | None = None) -> None:
    command = [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
               "-nostdin", "-y", "-filter_complex_threads", "1", *arguments]
    try:
        result = subprocess.run(command, capture_output=True, cwd=cwd, timeout=7200)
    except subprocess.TimeoutExpired as error:
        raise VideoToolError("混剪处理超时，请缩短片段后重试") from error
    if result.returncode:
        detail = result.stderr.decode("utf8", "replace").strip()
        raise VideoToolError("视频合成失败：" + detail[-1200:])


def _write_mask(path: Path, clip: RemixClip, duration: float, speed: float,
                canvas: tuple[int, int], fitted: tuple[int, int]) -> None:
    # FFV1 preserves the full white foreground (255), avoiding limited-range
    # H.264 mask levels that would mix the new background into the product.
    command = [imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-y", "-f", "rawvideo",
               "-pix_fmt", "gray", "-s", f"{canvas[0]}x{canvas[1]}", "-r", "30",
               "-i", "pipe:0", "-an", "-c:v", "ffv1", str(path)]
    from tempfile import TemporaryFile

    with TemporaryFile() as errors:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=errors)
        try:
            for index in range(math.ceil(duration * 30)):
                process.stdin.write(mask_frame(clip, clip.start + index / 30 * speed, canvas, fitted).tobytes())
            process.stdin.close()
            process.wait(timeout=120)
            if process.returncode:
                raise VideoToolError("商品遮罩生成失败")
        except BaseException:
            process.kill()
            process.wait()
            raise
        finally:
            process.stdin.close()


def _prepare_image(source: Path, target: Path, size: tuple[int, int], *, cover=False, gray=False):
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened).convert("L" if gray else "RGBA")
        if cover:
            image = ImageOps.fit(image, size, method=Image.Resampling.LANCZOS)
        else:
            image = image.resize(size, Image.Resampling.NEAREST if gray else Image.Resampling.LANCZOS)
        image.save(target, "PNG")




@limited_media
def render_remix(sources: list[Path], output: Path, *, root: Path, recipe: RemixRecipe,
                 progress=None) -> None:
    if output.resolve() in [path.resolve() for path in sources]:
        raise VideoToolError("输出路径需要与源视频分开")
    metas = validate_recipe(root, sources, recipe)
    original_size = metas[0]["size"]
    ratio = min(1, 1080 / max(original_size))
    canvas = tuple(max(2, int(value * ratio) // 2 * 2) for value in original_size)
    width, height = canvas
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.stem}.{uuid4().hex}.part.mp4")
    try:
        with TemporaryDirectory(prefix=".remix-", dir=output.parent) as folder:
            work = Path(folder)
            for index, (source, meta) in enumerate(zip(sources, metas)):
                if progress:
                    progress(index, len(sources))
                clip = recipe.clips[index] if recipe.clips else RemixClip(path=source.name)
                end = clip.end if clip.end is not None else meta["duration"]
                duration = (end - clip.start) / recipe.speed
                fitted = fit_size(meta["size"], canvas)
                inputs = ["-ss", str(clip.start), "-t", str(end - clip.start), "-i", str(source)]
                filters = [f"[0:v:0]setpts=(PTS-STARTPTS)/{recipe.speed},fps=30,"
                           f"scale={fitted[0]}:{fitted[1]},pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
                           "setsar=1,format=gbrp[original]"]
                next_input = 1
                edited = bool(recipe.background or recipe.overlay)
                if edited:
                    if recipe.background:
                        bg = work / "background.png"
                        _prepare_image(asset_path(root, recipe.background), bg, canvas, cover=True)
                        inputs.extend(["-loop", "1", "-framerate", "30", "-i", str(bg)])
                        filters.append(f"[{next_input}:v]format=gbrp,setsar=1[base]")
                        next_input += 1
                        foreground = "original"
                    else:
                        filters.append("[original]split=2[base][foreground]")
                        foreground = "foreground"
                    base = "base"
                    if recipe.overlay:
                        layer = asset_path(root, recipe.overlay)
                        with Image.open(layer) as img:
                            oriented = ImageOps.exif_transpose(img)
                            factor = min(width * recipe.overlay_scale / oriented.width,
                                         height * recipe.overlay_scale / oriented.height)
                            layer_size = (max(1, round(oriented.width * factor)), max(1, round(oriented.height * factor)))
                        layer_file = work / "overlay.png"
                        _prepare_image(layer, layer_file, layer_size)
                        inputs.extend(["-loop", "1", "-framerate", "30", "-i", str(layer_file)])
                        filters.append(f"[{next_input}:v]format=rgba,colorchannelmixer=aa={recipe.opacity}[layer]")
                        filters.append(f"[base][layer]overlay=x=(W-w)*{recipe.overlay_x}:y=(H-h)*{recipe.overlay_y}:"
                                       "shortest=1:format=rgb,format=gbrp[decorated]")
                        next_input += 1
                        base = "decorated"
                    if clip.mask_path:
                        mask = asset_path(root, clip.mask_path)
                        if mask.suffix.lower() in {".mp4", ".mov", ".m4v"}:
                            inputs.extend(["-ss", str(clip.start), "-t", str(end - clip.start), "-i", str(mask)])
                            timing = f"setpts=(PTS-STARTPTS)/{recipe.speed},fps=30,"
                        else:
                            normalized = work / "imported-mask.png"
                            _prepare_image(mask, normalized, fitted, gray=True)
                            inputs.extend(["-loop", "1", "-framerate", "30", "-i", str(normalized)])
                            timing = ""
                        filters.append(f"[{next_input}:v]{timing}scale={fitted[0]}:{fitted[1]}:flags=neighbor,"
                                       f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,format=gray,"
                                       "lut=y='if(gte(val,128),255,0)',format=gbrp,setsar=1[mask]")
                    else:
                        mask = work / "mask.mkv"
                        _write_mask(mask, clip, duration, recipe.speed, canvas, fitted)
                        inputs.extend(["-i", str(mask)])
                        filters.append(f"[{next_input}:v]format=gbrp,setsar=1[mask]")
                    filters.append(f"[{base}][{foreground}][mask]maskedmerge[outv]")
                else:
                    filters.append("[original]null[outv]")
                audio_map = []
                if recipe.preserve_audio:
                    if meta.get("audio_codec"):
                        filters.append(f"[0:a:0]asetpts=PTS-STARTPTS,atempo={recipe.speed},aresample=48000,"
                                       f"aformat=channel_layouts=stereo,apad,atrim=duration={duration}[outa]")
                    else:
                        filters.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={duration}[outa]")
                    audio_map = ["-map", "[outa]", "-c:a", "pcm_s16le"]
                _run([*inputs, "-filter_complex", ";".join(filters), "-map", "[outv]", *audio_map,
                      "-t", str(duration), "-c:v", "ffv1", "-level", "3", "-pix_fmt", "bgr0",
                      str(work / f"clip{index:02d}.mkv")])
            # Lossless clip intermediates keep RGB product pixels intact and
            # avoid accumulating AAC encoder delay at every clip boundary.
            (work / "clips.txt").write_text("".join(f"file 'clip{i:02d}.mkv'\n" for i in range(len(sources))), encoding="ascii")
            _run(["-f", "concat", "-safe", "1", "-i", "clips.txt", "-map", "0", "-vf", "fps=30",
                  "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                  "-c:a", "aac", "-b:a", "192k",
                  "-movflags", "+faststart", str(temporary.resolve())], cwd=work)
            temporary.replace(output)
            if progress:
                progress(len(sources), len(sources))
    finally:
        temporary.unlink(missing_ok=True)

