"""Local voice pitch, independent audio mixing and literal-text subtitle overlays."""
from pathlib import Path
import os
from PIL import Image, ImageDraw, ImageFont
from video_compositor import VideoToolError, asset_path, probe_video, _run


def subtitle_image(text, width, height, recipe, output):
    size = max(12, round(min(recipe.subtitle_size * width / 720, height * .085)))
    fonts = [Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts/msyhbd.ttc',
             Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'),
             Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')]
    font = next((ImageFont.truetype(str(p), size) for p in fonts if p.is_file()), None)
    if font is None:
        raise VideoToolError("字幕字体未安装，请安装微软雅黑或 Noto Sans CJK")
    lines=[]
    for paragraph in text.splitlines():
        line=''
        for char in paragraph:
            if font.getlength(line+char)>width*.84 and line:
                lines.append(line);line=''
            line+=char
        lines.append(line)
    line_height=round(size*1.5)
    if len(lines) > 2 or len(lines)*line_height>height*.45:
        raise VideoToolError("单屏字幕最多两行，请按短句拆分后显示")
    image=Image.new('RGBA',(width,len(lines)*line_height+12),(0,0,0,0));draw=ImageDraw.Draw(image)
    if recipe.subtitle_style=='box':
        draw.rounded_rectangle((width*.04,0,width*.96,image.height),radius=6,fill=(0,0,0,165))
    for i,line in enumerate(lines):
        draw.text(((width-font.getlength(line))/2,6+i*line_height),line,font=font,fill=recipe.subtitle_color,
                  stroke_width=max(1,size//14) if recipe.subtitle_style=='outline' else 0,stroke_fill='black')
    image.save(output)
    return image.height


def apply_av_edits(video, *, root, recipe, work):
    if not (recipe.music or recipe.voiceover or recipe.subtitles or recipe.voice_pitch or recipe.original_volume != 1):
        return
    meta=probe_video(video);duration=meta['duration'];width,height=meta['size']
    if any(cue.end>duration+.05 for cue in recipe.subtitles):
        raise VideoToolError(f"字幕时间超出成片时长（{duration:.2f}秒）")
    inputs=['-i',str(video)];filters=[];audio=[];index=1
    pitch=f'rubberband=pitch={2**(recipe.voice_pitch/12)},' if recipe.voice_pitch else ''
    if recipe.preserve_audio and meta.get('audio_codec') and recipe.original_volume:
        filters.append(f'[0:a]aresample=48000,{pitch}volume={recipe.original_volume},apad,atrim=duration={duration}[originalaudio]')
        audio.append('[originalaudio]')
    for kind,path,volume in [('voice',recipe.voiceover,recipe.voice_volume),('music',recipe.music,recipe.music_volume)]:
        if not path:continue
        if kind=='music':inputs+=['-stream_loop','-1']
        inputs+=['-i',str(asset_path(root,path))]
        transform=pitch if kind=='voice' else ''
        filters.append(f'[{index}:a]aresample=48000,{transform}volume={volume},apad,atrim=duration={duration},'
                       f'afade=t=in:d=0.15,afade=t=out:st={max(0,duration-.4)}:d=0.4[{kind}]')
        audio.append(f'[{kind}]');index+=1
    video_label='0:v'
    for n,cue in enumerate(recipe.subtitles):
        png=work/f'subtitle{n}.png';sh=subtitle_image(cue.text,width,height,recipe,png)
        inputs+=['-loop','1','-i',str(png)]
        position = cue.position or recipe.subtitle_position
        y={'top':round(height*.12),'center':round((height-sh)/2),
           'bottom':round(height*(1-recipe.subtitle_bottom_margin)-sh)}[position]
        label=f'sub{n}'
        filters.append(f'[{video_label}][{index}:v]overlay=x=0:y={y}:enable=\'gte(t,{cue.start})*lt(t,{cue.end})\':shortest=1[{label}]')
        video_label=label;index+=1
    mapping=['-map',f'[{video_label}]' if recipe.subtitles else '0:v']
    if audio:
        filters.append(''.join(audio)+f'amix=inputs={len(audio)}:normalize=0,alimiter=limit=0.95:latency=1,atrim=duration={duration}[audio]')
        mapping+=['-map','[audio]','-c:a','aac','-b:a','160k']
    vcodec=['-c:v','libx264','-preset','fast','-crf','17','-pix_fmt','yuv420p'] if recipe.subtitles else ['-c:v','copy']
    target=work/'av_final.mp4'
    _run([*inputs,*(['-filter_complex',';'.join(filters)] if filters else []),*mapping,*vcodec,
          '-t',str(duration),'-movflags','+faststart',str(target)])
    target.replace(video)

