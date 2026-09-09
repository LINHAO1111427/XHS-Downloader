# 视频下载、混剪与去重方案

## 已集成

- **下载**：现有 XHS-Downloader 解析 `originVideoKey` / `video.media.stream`，按分辨率、码率或体积选择视频直链，保存为 MP4/MOV/M4V。
- **混剪**：新增 `video_tools.py`，使用 FFmpeg concat filter 统一尺寸、时间戳并合并多个片段，输出到 `视频混剪/`。任务通过 `/api/video/remix` 异步执行，支持 0.5x-2x 速度。
- **去重**：通过 SHA-256 + 文件大小识别完全相同的视频，接口为 `/api/video/dedupe`，不自动删除文件。
- **图片成片**：新增 `video_creator.py`，把选中的图片制作成 1080x1920 竖屏 MP4，可选择 `下载目录/音乐/` 下的 MP3、WAV、M4A、AAC 或 OGG 文件作为背景音乐。

## 开源参考

- FFmpeg：https://ffmpeg.org/ ，负责编码、滤镜和容器处理。
- MoviePy：https://github.com/Zulko/moviepy ，适合 Python 编排剪辑流程；当前实现直接调用 FFmpeg，减少中间文件和额外依赖。
- PySceneDetect：https://github.com/Breakthrough/PySceneDetect ，后续可用于按镜头切分素材。
- Auto-Editor：https://github.com/WyattBlue/Auto-Editor ，后续可用于静音检测和自动节奏剪辑。
- imageio-ffmpeg：https://github.com/imageio/imageio-ffmpeg ，项目已使用，用于跨平台提供 FFmpeg 可执行文件。

## 后续迁移点

1. 增加音频轨道混音与背景音乐淡入淡出。
2. 引入 PySceneDetect 做镜头级自动切片，再由 FFmpeg 合成。
3. 将视频指纹扩展为关键帧感知哈希，用于识别裁剪、加速后的近似重复。
4. 为混剪任务增加持久化表，重启后可恢复任务状态。

音乐文件不直接打包第三方平台热门歌曲；将已获得授权的音频放入 `Volume/Download/音乐/` 后，会自动出现在“图片成片”的选择列表中。

清晰增强默认删除本地原图片；部署到服务器时可设置 `XHS_DELETE_ENHANCED_SOURCE=false` 保留原文件。

AI 批量图片优化采用一次提交、后台分批执行：每批最多 3 张、逐张调用图片模型，前端通过 `/api/ai/images/edit/batch-status` 轮询进度，避免 12 张图片在单个请求中超时。
