# Multi-platform reference videos

The reference import endpoint accepts one link from Xiaohongshu, Douyin, or Kuaishou. DouK-Downloader and KS-Downloader are kept under `vendor/` and used as parsing adapters; their desktop applications are not started by the web service.

The adapters normalize each result into the same `reference_video` asset shape. The downloaded MP4 is stored below `Volume/Download/多平台对标视频/<platform>/`, and the existing account factory then sends product videos plus every selected reference video to the AI planner. The planner analyzes sampled frames, visible selling points, source quality, and pacing before it writes the clip plan.

For links that require an authenticated session, set `DOUYIN_COOKIE` or `KUAISHOU_COOKIE` in the service environment. A cookie is not written into the exported publishing package.

Upstream projects:

- [DouK-Downloader](https://github.com/JoeanAmier/TikTokDownloader), GPL-3.0
- [KS-Downloader](https://github.com/JoeanAmier/KS-Downloader), GPL-3.0

