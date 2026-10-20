# 视频下载、混剪与去重方案
## 2026-09-18：完整讲话优先的混剪

一键混剪默认开启“保留完整讲话”。系统先用 faster-whisper 提取带字词时间戳的原声文字，并把句末标点、自然停顿以及“所以／但是／然后”等承接词组合为完整表达；自动选段只使用这些表达的起止边界。目标秒数是近似值：完整句与目标时长冲突时优先保留整句话，不再为了凑秒数从句中截断。无音轨或没有检测到讲话的素材继续使用均匀画面取段。

账号自动成片的候选视频目录现在同时提供时间轴抽帧和 `spoken_segments`。规划器可选择一个或多个相邻完整表达，单段允许超过原来的 8 秒限制；后端还会再次校验起止时间，凡是从讲话中间开始或结束的计划都会被拒绝。转写结果按素材状态和模型版本缓存到 `.video-transcripts/`，同一素材再次规划时直接复用。

处理顺序固定为：完整语句选段 → 水印跟踪修补 → 轻度时空降噪与锐化 → 满屏缩放裁切 → 字幕／音轨 → 贴纸 → H.264 CRF 17 导出。这样水印修补使用原始像素，画质处理发生在新字幕和贴纸之前，装饰层不会参与降噪或锐化。

默认语音模型是 `small`、中文、CPU int8；可通过 `XHS_WHISPER_MODEL`、`XHS_WHISPER_LANGUAGE`、`XHS_WHISPER_DEVICE`、`XHS_WHISPER_COMPUTE_TYPE` 和 `XHS_WHISPER_MODEL_DIR` 调整。首次使用对应模型时会下载模型文件。

## 2026-09-18：一键满屏混剪

### 配音、音乐、字幕与结尾水印

混剪窗口展开「配音、背景音乐与字幕」即可设置：原声/新配音升降3半音（不改变时长）、上传独立配音、上传或选择背景音乐、三路独立音量。选择新配音时默认关闭原声，音乐不足时循环，配音不足时补静音；混音限制峰值。变调只处理原音轨及独立配音，不处理新增背景音乐；原音轨内已混合的人声和音乐会一起变调。这是本地变调和音轨替换，不包含语音克隆或文本转语音；自动选段的语音转写只用于确定完整表达边界。

新增字幕按成片时间输入，每行`0-3|文字`，支持字号、颜色、上/中/下位置、描边/半透明底/纯文字三种样式。不填不产生文字框。字幕用Pillow渲染字面文本为透明图层，避免把用户文本当作FFmpeg表达式执行。原画面烧录的字幕没有可编辑字体信息，要先按区域修补旧文字再叠加新字；原背景细节可能受影响。

水印支持同一素材多个参考帧（最多8个）及各自生效区间，适合镜头切换、结尾水印位置/背景变化。重复框选会追加，不再覆盖前一个参考；旧版单参考配置仍可读取。低匹配帧跳过，复杂背景和遮挡需要抽查。原片67–73秒的移动“@薄荷yy”已作为末段加入44秒修订视频并检查修补结果，输出于`output/bead_pen_20260918/av_revision/MODIFIED_FILE.mp4`。

接口新增`POST /api/video/audio/upload`（MP3/WAV/M4A/AAC/OGG，128 MB，校验音轨，沿用登录和CSRF）。混剪请求支持`music`、`voiceover`、`original_volume`、`voice_volume`、`music_volume`、`voice_pitch`、`subtitles`及`subtitle_size/color/position/style`。每段的`watermarks`为列表，区域的`active_start/active_end`使用原片时间，字幕使用成片时间。字幕超出成片时长时任务明确报错，不发布半成品。

验证：`tests/test_remix_av.py`检查变调频率与时长、音乐循环、独立配音、字幕时间与颜色、失败清理；`tests/check_remix_av_browser.py`检查上传、原声关闭、样式选择与真实导出，以及无效音频拒绝与手机布局。

### 多视频一起剪辑

文件库可勾选多个视频后打开「视频混剪」。编辑器顶部新增「从文件库添加视频」多选列表与「上传多个视频」入口（MP4/MOV/M4V，每个最多256 MB）。追加时保留已有片段的起止时间、水印选框和商品轮廓；片段可上移、下移、移除，也可将同一素材添加成多个独立片段。单次最多20个片段，顶部显示视频数、片段数和原素材合计时长。移除片段只影响本次剪辑，不删除素材。

一键模式的目标时长作用于整条成片，各视频按时长比例分配取材预算；关闭自动选段则按列表顺序拼接各自裁剪区间。混合画幅以首段比例铺满；缺少原声的视频片段补静音。多文件上传单项失败会显示对应文件名，成功的文件仍加入列表。

`tests/check_multi_video_remix_browser.py`已通过真实浏览器验证：追加库内视频、双文件上传、保留裁剪、移除、重排、两视频真实合成、混合画幅、混合音轨、源文件哈希不变及手机布局；用绿色与蓝色视频抽帧确认成片顺序。

在文件库选择视频 →「视频混剪」→「一键混剪」。默认45秒、四边各裁4.7%、保留原声；自动按素材时长比例分配预算并从不同位置取互不重叠的片段，素材不足不循环凑时长。关闭自动选段后按已有片段顺序和起止时间拼接。输出不添加底部说明、边框或透明装饰层；不同比例素材居中裁切铺满首段比例。

水印处理：暂停到水印清楚的一帧，点「框选移动水印」，拖框紧贴文字。橙色框只在编辑器中显示，不烧录到视频。参考时间及选框按素材路径保存在浏览器本地，后续一键任务自动带入；清除按钮删除保存项。后端提取文字模板、逐帧匹配、仅对匹配字形做局部修补。低匹配帧跳过处理，细密纹理、文字变形和遮挡仍需检查成片；不承诺全部水印自动消失或平台去重通过。

API沿用`POST /api/video/remix`，新增`clean_mode`、`auto_cut`、`target_duration`、`edge_crop`，每个clip支持`watermark: {time,x,y,width,height}`（位置尺寸为源画面0–1比例，time为源视频秒数）。一键路径由`clean_remix.py`处理；高级商品轮廓/换背景流程继续沿用原合成器。视频中间文件使用FFV1/PCM，最后统一H.264/AAC；源视频保留、临时文件自动清理。依赖OpenCV与NumPy已加入pyproject及uv.lock。

新增测试：`tests/test_clean_remix.py`验证时长预算、非重复取材、移动文字修补、原商品区域不变、满屏无黑边、音轨与源文件保留；`tests/check_clean_remix_browser.py`验证真实页面框选、保存复用、异步导出与手机布局。原有视频混剪测试及浏览器回归通过。混剪窗口内部增加进度轮询，避免主页面暂停轮询导致任务状态停留在0%。

## 已集成

- **下载**：现有 XHS-Downloader 解析 `originVideoKey` / `video.media.stream`，按分辨率、码率或体积选择视频直链，保存为 MP4/MOV/M4V。
- **商品视频混剪**：`video_tools.py` 管理异步任务，`video_compositor.py` 使用 FFmpeg + Pillow 合成，`static/web/remix.js` 提供可视化编辑器。输出到 `视频混剪/`，支持排序、逐段裁剪、0.5x–2x 速度、原声保留、背景替换和半透明图片叠加。
- **去重**：通过 SHA-256 + 文件大小识别完全相同的视频，接口为 `/api/video/dedupe`，不自动删除文件。
- **图片成片**：新增 `video_creator.py`，把选中的图片制作成 1080x1920 竖屏 MP4，可选择 `下载目录/音乐/` 下的 MP3、WAV、M4A、AAC 或 OGG 文件作为背景音乐。

## 开源参考

- FFmpeg：https://ffmpeg.org/ ，负责编码、滤镜和容器处理。
- MoviePy：https://github.com/Zulko/moviepy ，适合 Python 编排剪辑流程；当前实现直接调用 FFmpeg，减少中间文件和额外依赖。
- PySceneDetect：https://github.com/Breakthrough/PySceneDetect ，后续可用于按镜头切分素材。
- Auto-Editor：https://github.com/WyattBlue/Auto-Editor ，后续可用于静音检测和自动节奏剪辑。
- imageio-ffmpeg：https://github.com/imageio/imageio-ffmpeg ，项目已使用，用于跨平台提供 FFmpeg 可执行文件。

## 2026-09-16：保留商品主体的混剪

### 直接使用

1. 在已下载文件中选中视频，点击「视频混剪」；1688 / 小红书商品卡片中的视频也有「直接混剪」，会把视频副本送入编辑器。
2. 每个片段可单独指定开始、结束时间，用 ↑ / ↓ 排序。画布保持商品比例，其他比例的素材补边，画布比例取第一个片段。
3. 暂停预览，沿商品轮廓依次点至少三个点，点击「保存当前关键帧」。移动商品需要在后续时间拖动相同的轮廓点再保存；支持连续插值和镜头切换时保持轮廓。拖动时间轴、切换片段和提交前会保存当前有效轮廓。
4. 从素材库选择或上传背景图、叠加图；不透明度默认 25%，可调 0–100%，支持位置和大小调整，PNG 原有透明度也会保留。
5. 播放检查全片轮廓，点击「生成混剪视频」。任务在后台运行，完成后可播放、下载，文件库也会出现新的 MP4。

合成顺序为：新背景（或原背景）→ 半透明图片 → 遮罩内的原视频像素。
没有任何图片模型重画商品，图片叠加也在商品下层。多边形圈内的全部内容都会保留，因此轮廓要贴近商品边缘；宽泛矩形会连同圈内旧背景一起保留。快速运动、遮挡、镂空和复杂轮廓适合导入逐帧遮罩。预览是浏览器合成，最终 MP4 有 H.264 编码及色度采样差异，文件字节和像素并非无损复制。

片段先以 FFV1 RGB + PCM 无损中间格式合成，最后统一编码 H.264/AAC，避免每段单独 AAC 编码导致间隙累积。默认保留原声，无音轨片段补静音；变速使用 `atempo` 同步音频。成片为 30fps，最长边最多 1080 像素，最多 20 段 / 60 分钟。临时文件处理结束即清理，源视频和图片保留。任务列表保存在进程内，服务重启后已生成文件仍在文件库。

### 核对的开源实现及接入方式

| 方案 / 一手资料 | 对商品视频的用途 | 本次接入 |
| --- | --- | --- |
| [FFmpeg maskedmerge](https://ffmpeg.org/ffmpeg-filters.html#maskedmerge)、[overlay](https://ffmpeg.org/ffmpeg-filters.html#overlay-1)、[colorchannelmixer](https://ffmpeg.org/ffmpeg-filters.html#colorchannelmixer) | 遮罩选择原商品像素、图片透明度与背景合成 | 已实际调用；沿用项目已有 imageio-ffmpeg，新增依赖为零 |
| [Pillow ImageDraw](https://pillow.readthedocs.io/en/stable/reference/ImageDraw.html) / [许可证](https://github.com/python-pillow/Pillow/blob/main/LICENSE) | 生成轮廓遮罩、处理 EXIF、保留 PNG alpha | 已实际调用；MIT-CMU，沿用项目依赖 |
| [SAM 2 官方视频预测说明](https://github.com/facebookresearch/sam2#video-prediction) / [示例 notebook](https://github.com/facebookresearch/sam2/blob/main/notebooks/video_predictor_example.ipynb) | 点选商品并向后传播分割结果，适合任意商品而非仅人像 | 接入其结果：编辑器可上传对齐原视频的黑白 MP4/PNG 遮罩。当前应用没有内置 SAM 2 模型推理；其代码和权重为 Apache-2.0，官方环境要求 PyTorch ≥ 2.5.1、TorchVision ≥ 0.20.1，推荐 GPU |
| [rembg](https://github.com/danielgatis/rembg#rembg-b) | 可通过 FFmpeg 原始帧管道逐帧抠图，MIT；模型各有适用对象 | 已研究，未加入默认处理链。逐帧结果需要检查时间一致性，独立图片抠图不等于可靠的视频跟踪 |

以上 FFmpeg、SAM 2、rembg 官方文档及 Pillow LICENSE 已在本次实现时联网读取核对。没有安装或下载分割模型，没有把外部工具的自动分割精度视为保证。

### 跟踪遮罩约定

编辑器「导入精细跟踪遮罩」接受灰度 PNG/JPG/WebP 或 MP4/MOV/M4V。白色是需要保留的商品，黑色是替换背景；以 128 为阈值转为完全黑白，商品区域保持全不透明。透明底商品 PNG 不是这个接口的遮罩，需先导出黑白轮廓。

视频遮罩应与完整源视频的取景、时间零点一致，覆盖所选片段；不是仅对裁剪后的片段从零计时。实际裁剪和变速会同步作用于原视频与遮罩。静态遮罩适合固定商品。导入遮罩后替代当前片段的手动关键帧；「重画轮廓」可切回手动模式。

SAM 2 的 `propagate_in_video` 返回逐帧的 `out_mask_logits`，按 `> 0` 二值化，商品并集乘 255 保存成黑白 PNG 序列，再以源视频帧率编码为 MP4，即可上传到本编辑器。使用官方 notebook 的人工提示/修正流程检查商品标识、镂空和遮挡处，再合成。

### API 和验证

`POST /api/video/remix` 保留原 `paths` / `speed` 请求，新增 `clips`（path、start、end、keyframes、interpolation、mask_path）、`background`、`overlay`、`opacity`、`overlay_scale`、`overlay_x`、`overlay_y`、`preserve_audio`。
`keyframes.time` 是原视频秒数，`points` 为源画面中的 0–1 坐标；线性插值要求各关键帧点数和顺序相同。
例如：

```json
{
  "clips": [{
    "path": "商品素材/demo.mp4",
    "start": 0,
    "end": 5,
    "keyframes": [{"time": 0, "points": [[0.3,0.2],[0.7,0.2],[0.7,0.8],[0.3,0.8]]}]
  }],
  "background": "混剪素材/background.png",
  "overlay": "混剪素材/decoration.png",
  "opacity": 0.25,
  "preserve_audio": true
}
```

`GET /api/video/info?path=...` 提供素材尺寸、时长、帧率和音轨信息；`POST /api/video/assets/upload?filename=...` 以文件原始字节上传图片或跟踪遮罩；`POST /api/product-videos/{platform}/{product_id}/{index}/import` 把已采集商品视频复制到文件库。接口沿用登录、CSRF 和目录边界校验。更换背景或叠加图片时，各片段必须显式给出商品轮廓或遮罩，错误输入在创建任务前返回 422。

`tests/test_video_remix.py` 使用真实 FFmpeg 验证商品像素、背景与透明度、PNG alpha、移动轮廓、导入遮罩、裁剪/速度/不同宽高比、原声、失败清理、源文件哈希、素材上传、商品导入、任务状态及成片下载。`tests/check_video_remix_browser.py` 使用 Edge 验证画布编辑、预览像素、真实导出和移动端布局。

## 后续迁移点

1. 增加音频轨道混音与背景音乐淡入淡出。
2. 引入 PySceneDetect 做镜头级自动切片，再由 FFmpeg 合成。
3. 将视频指纹扩展为关键帧感知哈希，用于识别裁剪、加速后的近似重复。
4. 为混剪任务增加持久化表，重启后可恢复任务状态。

音乐文件不直接打包第三方平台热门歌曲；将已获得授权的音频放入 `Volume/Download/音乐/` 后，会自动出现在“图片成片”的选择列表中。

清晰增强默认删除本地原图片；部署到服务器时可设置 `XHS_DELETE_ENHANCED_SOURCE=false` 保留原文件。

AI 批量图片优化采用一次提交、后台分批执行：每批最多 3 张、逐张调用图片模型，前端通过 `/api/ai/images/edit/batch-status` 轮询进度，避免 12 张图片在单个请求中超时。


