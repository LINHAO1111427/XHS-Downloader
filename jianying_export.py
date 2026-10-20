"""Optional editable Jianying drafts from source clips, never a burned-in MP4."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import shutil
import zipfile

from subtitle_layout import caption_cues, write_srt
from video_compositor import asset_path, probe_video, VideoToolError


def export_editing_package(root, clips, assets, destination, *, name='XHS-editable'):
    try:
        import pyJianYingDraft as draft
    except ImportError as error:
        raise VideoToolError('剪映草稿组件尚未安装：pip install -r requirements-jianying.txt') from error
    root, destination = Path(root), Path(destination)
    by_id = {a['id']: a for a in assets if a['role'] in {'product_video', 'reference_video'}}
    if not clips or len(clips) > 20:
        raise VideoToolError('剪映编辑包需要1到20段带原始素材的分镜')
    cues = caption_cues(clips)
    sources = []
    for clip in clips:
        asset = by_id.get(clip['asset_id'])
        if not asset:
            raise VideoToolError('分镜原素材已移出当前商品素材库')
        source = asset_path(root, asset['path'])
        meta = probe_video(source)
        if clip['start'] < 0 or clip['end'] > meta['duration'] + .05:
            raise VideoToolError('分镜超出原素材时长')
        sources.append((source, meta))
    width, height = sources[0][1]['size']
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='jianying-', dir=destination.parent) as temporary:
        work = Path(temporary)
        script = draft.DraftFolder(str(work)).create_draft(name, width, height)
        folder = work / name
        media = folder / 'assets'; media.mkdir()
        script.append_track(draft.TrackSpec(draft.TrackType.video, '原片分镜'))
        script.append_track(draft.TrackSpec(draft.TrackType.text, '画面说明（可编辑）'))
        copied, clock = {}, 0
        for clip, (source, _meta) in zip(clips, sources):
            if source not in copied:
                target = media / (f'{len(copied)+1:02d}' + source.suffix.lower())
                shutil.copy2(source, target); copied[source] = target
            length = round((clip['end'] - clip['start']) * 1_000_000)
            segment = draft.VideoSegment(str(copied[source]), draft.Timerange(clock, length),
                source_timerange=draft.Timerange(round(clip['start'] * 1_000_000), length))
            script.add_segment(segment, '原片分镜'); clock += length
        for cue in cues:
            # Jianying's y axis is positive upwards; keep annotations above the bottom controls.
            y = {'top': .68, 'center': 0, 'bottom': -.48}[cue.position or 'bottom']
            segment = draft.TextSegment(cue.text,
                draft.Timerange(round(cue.start*1_000_000),round((cue.end-cue.start)*1_000_000)),
                style=draft.TextStyle(size=7, bold=True, align=1, auto_wrapping=True, max_line_width=.84),
                clip_settings=draft.ClipSettings(transform_y=y), border=draft.TextBorder(width=18))
            script.add_segment(segment, '画面说明（可编辑）')
        script.save()
        content_path = folder / 'draft_content.json'
        content = json.loads(content_path.read_text('utf8'))
        # A package must not depend on the temporary directory on the producing machine.
        for video in content['materials']['videos']:
            video['path'] = 'assets/' + Path(video['path']).name
        content_path.write_text(json.dumps(content,ensure_ascii=False),encoding='utf8')
        write_srt(cues, folder/'画面说明.srt')
        (folder/'字幕时间轴.json').write_text(json.dumps([c.model_dump() for c in cues],ensure_ascii=False,indent=2),encoding='utf8')
        (folder/'重定位素材.py').write_text(RELOCATE,encoding='utf8')
        (folder/'使用说明.txt').write_text(
            '这是原片分镜与独立说明字幕的可编辑草稿，不是最终成片复刻。\n'
            '1. 解压整个文件夹到剪映草稿位置，保留 assets 文件夹。\n'
            '2. 运行 python 重定位素材.py，再在剪映中刷新草稿列表并打开。\n'
            '3. 检查字体、原片自带字幕与商品位置，调整独立字幕轨后导出。\n'
            '画面说明是分镜注释，不是逐字语音识别字幕；SRT不包含字体和位置。\n'
            '原片已压制的文字仍在原视频里；后加AI转场、贴纸、去重叠层不在本编辑稿中。\n'
            '新版剪映的自动点击导出尚未接入。pyJianYingDraft 0.3.0 上游注明控件导出仅支持6及以下。\n',encoding='utf8')
        with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
            for file in sorted(folder.rglob('*')):
                if file.is_file(): archive.write(file, name+'/'+file.relative_to(folder).as_posix())
        with zipfile.ZipFile(destination) as archive:
            if archive.testzip(): raise VideoToolError('剪映编辑包校验失败')
            json.loads(archive.read(name+'/draft_content.json'))
    return destination


RELOCATE = '''from pathlib import Path
import json
root = Path(__file__).resolve().parent
path = root / 'draft_content.json'
data = json.loads(path.read_text('utf8'))
for item in data['materials']['videos']:
    source = root / 'assets' / Path(item['path']).name
    if not source.is_file(): raise FileNotFoundError(source.name)
    item['path'] = source.as_posix()
path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf8')
meta_path = root / 'draft_meta_info.json'
meta = json.loads(meta_path.read_text('utf8'))
meta.update(draft_name=root.name, draft_fold_path=root.as_posix(), draft_root_path=root.parent.as_posix(), draft_id=data['id'])
meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding='utf8')
print('READY: ' + root.name)
'''
