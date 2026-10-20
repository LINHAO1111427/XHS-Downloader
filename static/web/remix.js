/* Product-preserving local video editor. Uses the same layer order as FFmpeg. */
(() => {
    "use strict";
    const dialog = document.createElement("dialog");
    dialog.id = "videoRemixDialog";
    dialog.className = "video-remix-dialog";
    dialog.innerHTML = `<div class="dialog-shell">
        <div class="dialog-heading"><div><h2>商品视频混剪</h2><p>一键选段拼接，满屏输出；也可手动精剪</p></div><button class="icon-button subtle remix-close" type="button" aria-label="关闭混剪">×</button></div>
        <div class="remix-inline">
            <button class="button secondary" id="remixAddLibrary" type="button">从文件库添加视频</button>
            <label class="button secondary">上传多个视频<input id="remixVideosUpload" type="file" accept=".mp4,.mov,.m4v,video/mp4,video/quicktime" multiple hidden></label>
            <span id="remixSourceSummary" aria-live="polite"></span>
        </div>
        <div id="remixLibraryPicker" hidden>
            <label class="select-field"><span>可多选视频，按列表顺序添加</span><select id="remixLibraryVideos" multiple size="5" aria-label="从文件库选择多个视频"></select></label>
            <button class="button secondary" id="remixConfirmAdd" type="button">添加选中视频</button>
        </div>
        <div class="remix-inline">
            <label><input id="remixAutoCut" type="checkbox" checked> 自动选段</label>
            <label><input id="remixSpeechAware" type="checkbox" checked> 保留完整讲话</label>
            <label>目标秒数<input id="remixTargetDuration" type="number" min="1" max="180" value="45"></label>
            <label>裁去边缘<select id="remixEdgeCrop"><option value="0">保留完整画面</option><option value="0.047" selected>四周各 4.7%</option><option value="0.08">四周各 8%</option></select></label>
            <button class="button primary" id="remixQuickSubmit" type="button">一键混剪</button>
        </div>
        <p class="remix-hint">成片铺满画面，不添加边框和底部说明。开启“保留完整讲话”后先转写原声，再按完整表达边界选段；目标秒数允许随完整句略微浮动。静音素材仍按画面取段，关闭自动选段后按下方片段顺序拼接。</p>
        <div class="remix-inline"><button class="button secondary" id="remixMarkWatermark" type="button">框选移动水印</button><button class="button secondary" id="remixClearWatermark" type="button">清除水印选框</button><span id="remixWatermarkStatus">水印修补未设置</span></div>
        <p class="remix-hint">需要修补时，暂停到水印清楚的一帧，点击“框选移动水印”后拖框紧贴文字。选框会按素材记住，一键混剪时跟踪修补；成片中可检查效果。</p>
        <div class="remix-inline"><label>水印生效起点<input id="remixWatermarkFrom" type="number" min="0" step="0.1" value="0"></label><label>水印生效终点（空为片尾）<input id="remixWatermarkUntil" type="number" min="0" step="0.1"></label></div>
        <p class="remix-hint">重复框选可补充不同镜头的参考帧，最多8个；起止时间以原视频为准，框选时保存。</p>
        <div id="remixWatermarkList" class="remix-keyframes" aria-label="水印参考帧列表"></div>
        <details id="remixAVSettings"><summary>配音、背景音乐与字幕</summary>
            <div class="remix-inline">
                <label>原声／配音音调<select id="remixVoicePitch"><option value="0">原音调</option><option value="-3">降低3半音</option><option value="3">提高3半音</option></select></label>
                <label>原声音量<input id="remixOriginalVolume" type="number" min="0" max="200" value="100">%</label>
            </div>
            <label class="select-field"><span>替换配音</span><select id="remixVoiceover"><option value="">不添加配音</option></select></label>
            <label class="remix-upload">上传配音<input id="remixVoiceUpload" type="file" accept=".mp3,.wav,.m4a,.aac,.ogg"></label>
            <label class="select-field"><span>背景音乐</span><select id="remixMusic"><option value="">不添加音乐</option></select></label>
            <label class="remix-upload">上传音乐<input id="remixMusicUpload" type="file" accept=".mp3,.wav,.m4a,.aac,.ogg"></label>
            <audio id="remixAudioPreview" controls hidden></audio>
            <div class="remix-inline"><label>配音音量<input id="remixVoiceVolume" type="number" min="0" max="200" value="100">%</label><label>音乐音量<input id="remixMusicVolume" type="number" min="0" max="200" value="20">%</label></div>
            <p class="remix-hint">变调作用于原音轨或上传的配音，不改变时长。原音轨里的人声和音乐会一起变调；选择配音后默认关闭原声。配音从成片开头播放，音乐不足时循环。</p>
            <label class="select-field"><span>新增字幕（成片秒数，每行：开始-结束|文字）</span><textarea id="remixSubtitles" rows="4" placeholder="0-3|先看铺豆效果&#10;3-6|再看操作细节"></textarea></label>
            <div class="remix-inline"><label>字号<input id="remixSubtitleSize" type="number" min="16" max="80" value="36"></label><label>颜色<input id="remixSubtitleColor" type="color" value="#ffffff"></label><label>位置<select id="remixSubtitlePosition"><option value="bottom">下方</option><option value="center">居中</option><option value="top">上方</option></select></label><label>样式<select id="remixSubtitleStyle"><option value="outline">描边</option><option value="box">半透明底</option><option value="plain">纯文字</option></select></label></div>
            <p class="remix-hint">这些样式只修改新增字幕。原视频烧录的文字先用水印选框修补，再添加新文字；选框内复杂背景可能留下修补痕迹。不填字幕时不添加文字或边框。</p>
        </details>
        <div class="remix-layout">
            <div class="remix-editor">
                <div id="remixClips" class="remix-clips" aria-label="混剪片段顺序"></div>
                <div class="remix-preview"><canvas id="remixCanvas" width="640" height="360" aria-label="点击圈定商品轮廓，拖动圆点调整位置"></canvas></div>
                <video id="remixSource" preload="auto" playsinline hidden></video><video id="remixMaskVideo" preload="auto" muted playsinline hidden></video>
                <div class="remix-playback"><button class="button secondary" id="remixPlay" type="button">播放预览</button><input id="remixSeek" type="range" min="0" max="0" value="0" step="0.01" aria-label="预览时间"><output id="remixTime">0.00 秒</output></div>
                <div class="remix-inline"><label>开始（秒）<input id="remixStart" type="number" min="0" step="0.01" value="0"></label><label>结束（秒）<input id="remixEnd" type="number" min="0.05" step="0.01"></label></div>
                <div class="remix-inline"><button class="button secondary" id="remixRedraw" type="button">重画轮廓</button><button class="button secondary" id="remixUndo" type="button">撤销一个点</button><button class="button primary" id="remixSaveMask" type="button">保存当前关键帧</button></div>
                <p class="remix-hint">暂停后，沿商品边缘依次点击至少 3 个点；拖动圆点微调。商品移动时，移到新时间，调整同一组圆点并保存。叠加图片始终位于商品下层。</p>
                <div id="remixKeyframes" class="remix-keyframes" aria-label="商品轮廓关键帧"></div>
                <label class="select-field"><span>关键帧之间</span><select id="remixInterpolation"><option value="linear">连续移动：平滑跟随轮廓</option><option value="hold">镜头切换：保持到下一关键帧</option></select></label>
                <details class="remix-mask-import"><summary>导入精细跟踪遮罩</summary><p class="remix-hint">可使用 SAM 2 等工具导出的黑白 MP4，或静态 PNG。白色是商品，黑色是背景；视频与原素材时间、取景一致。导入后替代手动画框。</p><input id="remixMaskUpload" type="file" accept="image/png,image/jpeg,image/webp,video/mp4,video/quicktime"><button id="remixClearMask" class="button secondary" type="button">移除导入遮罩</button><span id="remixMaskName"></span></details>
            </div>
            <div class="remix-controls">
                <label class="select-field"><span>替换背景</span><select id="remixBackground"><option value="">保留原背景</option></select></label>
                <label class="remix-upload">上传背景图片<input id="remixBackgroundUpload" type="file" accept="image/png,image/jpeg,image/webp"></label>
                <label class="select-field"><span>叠加图片</span><select id="remixOverlay"><option value="">不叠加图片</option></select></label>
                <label class="remix-upload">上传叠加图片<input id="remixOverlayUpload" type="file" accept="image/png,image/jpeg,image/webp"></label>
                <label class="range-field"><span>图片不透明度 <output id="remixOpacityValue">25%</output></span><input id="remixOpacity" type="range" min="0" max="100" value="25"></label>
                <label class="range-field"><span>图片大小 <output id="remixScaleValue">100%</output></span><input id="remixScale" type="range" min="10" max="100" value="100"></label>
                <label class="range-field"><span>水平位置</span><input id="remixX" type="range" min="0" max="100" value="50"></label>
                <label class="range-field"><span>垂直位置</span><input id="remixY" type="range" min="0" max="100" value="50"></label>
                <label class="select-field"><span>播放速度</span><select id="remixSpeed"><option value="0.5">0.5 倍</option><option value="0.75">0.75 倍</option><option value="1" selected>1 倍</option><option value="1.25">1.25 倍</option><option value="1.5">1.5 倍</option><option value="2">2 倍</option></select></label>
                <label><input id="remixAudio" type="checkbox" checked> 保留原声</label>
                <label><input id="remixOutline" type="checkbox" checked> 显示商品轮廓线</label>
                <p class="remix-hint">轮廓内使用原视频画面；请预览整个片段并检查边缘。静态轮廓适合固定商品，运动商品使用多个关键帧或跟踪遮罩。成片另存为 MP4。</p>
            </div>
        </div>
        <p id="remixError" role="alert" class="remix-error" hidden></p>
        <div id="remixStatus" class="remix-status" aria-live="polite"></div>
        <div class="dialog-actions"><button class="button secondary remix-close" type="button">关闭</button><button class="button primary" id="remixSubmit" type="button">生成混剪视频</button></div>
    </div>`;
    document.body.append(dialog);
    const $ = (id) => document.getElementById(id);
    const canvas = $("remixCanvas"), ctx = canvas.getContext("2d");
    const video = $("remixSource"), maskVideo = $("remixMaskVideo");
    const panel = document.createElement("div");
    panel.className = "remix-task-panel";
    panel.id = "remixTaskPanel";
    panel.hidden = true;
    document.querySelector(".library-heading").after(panel);
    let clips = [], active = 0, images = [], draft = [], draftTime = 0, dirty = false;
    let bgImage = null, overlayImage = null, maskImage = null, dragging = -1, raf = 0, opening = 0, uploading = 0;
    let watermarkMode = false, watermarkAnchor = null, watermarkDraft = null, quickSubmitting = false;
    let pendingTasks = false, dialogPolling = false;
    // The main page pauses its polls while a dialog is open.
    setInterval(async () => {
        if (!dialog.open || document.hidden || !pendingTasks || dialogPolling) return;
        dialogPolling = true;
        try { await refreshRemixTasks(); } finally { dialogPolling = false; }
    }, 1500);
    const watermarkKey = (path) => `remix-watermark-v1:${path}`;
    function storedWatermark(path) { try { return JSON.parse(localStorage.getItem(watermarkKey(path))) || null; } catch { return null; } }
    function watermarkStatus() {
        const regions = [...(clip()?.watermarks || []), ...(clip()?.watermark ? [clip().watermark] : [])];
        $("remixWatermarkStatus").textContent = regions.length ? `已保存 ${regions.length} 个水印参考帧` : "水印修补未设置";
        $("remixWatermarkList").replaceChildren();
        regions.forEach((region, index) => {
            const group = document.createElement("span"), seek = document.createElement("button"), remove = document.createElement("button");
            seek.type = remove.type = "button";
            seek.textContent = `${Number(region.time).toFixed(2)}秒 · ${region.active_start || 0}—${region.active_end ?? "片尾"}`;
            seek.onclick = () => { if (saveMask()) { $("remixWatermarkFrom").value = region.active_start || 0; $("remixWatermarkUntil").value = region.active_end ?? ""; seekTo(region.time); } };
            remove.textContent = "×"; remove.setAttribute("aria-label", `移除水印参考帧 ${index+1}`);
            remove.onclick = () => { clip().watermark = null; clip().watermarks = regions.filter((_, i) => i !== index); try { localStorage.setItem(watermarkKey(clip().path), JSON.stringify(clip().watermarks)); } catch {} watermarkStatus(); draw(); };
            group.append(seek, remove); $("remixWatermarkList").append(group);
        });
    }
    const clip = () => clips[active];
    const clone = (points) => points.map((point) => [...point]);
    const mediaUrl = (path) => `/media/${path.split("/").map(encodeURIComponent).join("/")}`;
    function error(message = "") { $("remixError").textContent = message; $("remixError").hidden = !message; }
    function pointsAt(item, time) {
        const frames = item.keyframes;
        if (!frames.length) return [];
        let previous = frames[0];
        for (const next of frames.slice(1)) {
            if (time < next.time) {
                if (item.interpolation === "hold" || time <= previous.time) return clone(previous.points);
                const fraction = (time - previous.time) / (next.time - previous.time);
                return previous.points.map(([x, y], i) => [x + (next.points[i][0] - x) * fraction, y + (next.points[i][1] - y) * fraction]);
            }
            previous = next;
        }
        return clone(previous.points);
    }
    function geometry() {
        const meta = clip()?.meta;
        if (!meta) return { x: 0, y: 0, w: canvas.width, h: canvas.height };
        const scale = Math.min(canvas.width / meta.width, canvas.height / meta.height);
        const w = meta.width * scale, h = meta.height * scale;
        return { x: (canvas.width - w) / 2, y: (canvas.height - h) / 2, w, h };
    }
    function cover(image) {
        const scale = Math.max(canvas.width / image.width, canvas.height / image.height);
        const w = image.width * scale, h = image.height * scale;
        ctx.drawImage(image, (canvas.width - w) / 2, (canvas.height - h) / 2, w, h);
    }
    const maskCanvas = document.createElement("canvas"), productCanvas = document.createElement("canvas");
    function draw() {
        if (!clip() || video.readyState < 2) return;
        const g = geometry(), w = canvas.width, h = canvas.height;
        const points = dirty ? draft : pointsAt(clip(), video.currentTime);
        ctx.fillStyle = "#000"; ctx.fillRect(0, 0, w, h);
        if (bgImage) cover(bgImage); else ctx.drawImage(video, g.x, g.y, g.w, g.h);
        if (overlayImage) {
            const size = Number($("remixScale").value) / 100;
            const ratio = Math.min(w * size / overlayImage.width, h * size / overlayImage.height);
            const iw = overlayImage.width * ratio, ih = overlayImage.height * ratio;
            ctx.globalAlpha = Number($("remixOpacity").value) / 100;
            ctx.drawImage(overlayImage, (w - iw) * Number($("remixX").value) / 100, (h - ih) * Number($("remixY").value) / 100, iw, ih);
            ctx.globalAlpha = 1;
        }
        if (clip().mask_path && (maskImage || maskVideo.readyState >= 2)) {
            maskCanvas.width = productCanvas.width = w; maskCanvas.height = productCanvas.height = h;
            const mctx = maskCanvas.getContext("2d", { willReadFrequently: true });
            mctx.drawImage(maskImage || maskVideo, g.x, g.y, g.w, g.h);
            const pixels = mctx.getImageData(0, 0, w, h);
            for (let i = 0; i < pixels.data.length; i += 4) {
                pixels.data[i + 3] = pixels.data[i] >= 128 ? 255 : 0;
            }
            mctx.putImageData(pixels, 0, 0);
            const pctx = productCanvas.getContext("2d");
            pctx.drawImage(video, g.x, g.y, g.w, g.h);
            pctx.globalCompositeOperation = "destination-in";
            pctx.drawImage(maskCanvas, 0, 0);
            ctx.drawImage(productCanvas, 0, 0);
        } else if (points.length >= 3) {
            ctx.save(); ctx.beginPath();
            points.forEach(([x, y], index) => ctx[index ? "lineTo" : "moveTo"](g.x + x * g.w, g.y + y * g.h));
            ctx.closePath(); ctx.clip(); ctx.drawImage(video, g.x, g.y, g.w, g.h); ctx.restore();
        } else if (bgImage || overlayImage) {
            ctx.drawImage(video, g.x, g.y, g.w, g.h);
        }
        if ($("remixOutline").checked && !clip().mask_path) {
            ctx.strokeStyle = "#33e8af"; ctx.fillStyle = "#fff"; ctx.lineWidth = 2;
            ctx.beginPath(); points.forEach(([x, y], i) => ctx[i ? "lineTo" : "moveTo"](g.x + x * g.w, g.y + y * g.h));
            if (points.length >= 3) ctx.closePath(); ctx.stroke();
            points.forEach(([x, y]) => { ctx.beginPath(); ctx.arc(g.x + x * g.w, g.y + y * g.h, 5, 0, Math.PI * 2); ctx.fill(); ctx.stroke(); });
        }
        const box = watermarkDraft || clip().watermark || clip().watermarks?.at(-1);
        if (box) { ctx.save(); ctx.strokeStyle = "#ff973b"; ctx.lineWidth = 2; ctx.setLineDash([5, 4]); ctx.strokeRect(g.x + box.x*g.w, g.y + box.y*g.h, box.width*g.w, box.height*g.h); ctx.restore(); }
        $("remixTime").textContent = `${video.currentTime.toFixed(2)} 秒`;
        $("remixSeek").value = video.currentTime;
    }
    function animate() { draw(); if (!video.paused && dialog.open) raf = requestAnimationFrame(animate); }
    function pause() { video.pause(); maskVideo.pause(); cancelAnimationFrame(raf); $("remixPlay").textContent = "播放预览"; }
    function saveMask() {
        if (!dirty) return true;
        if (draft.length < 3) { error("请至少点击三个点圈定商品，再保存关键帧。"); return false; }
        const area = Math.abs(draft.reduce((sum, [x, y], i) => sum + x * draft[(i + 1) % draft.length][1] - y * draft[(i + 1) % draft.length][0], 0)) / 2;
        if (area < 0.00001) { error("轮廓点需要围成一个区域。"); return false; }
        if (clip().interpolation === "linear" && clip().keyframes.some((frame) => Math.abs(frame.time - draftTime) > 0.02 && frame.points.length !== draft.length)) {
            error("连续移动请保持各关键帧的点数相同；重画不同轮廓时可选“镜头切换”。"); return false;
        }
        clip().keyframes = clip().keyframes.filter((frame) => Math.abs(frame.time - draftTime) > 0.02);
        clip().keyframes.push({ time: Number(draftTime.toFixed(3)), points: clone(draft) });
        clip().keyframes.sort((a, b) => a.time - b.time); dirty = false; error(); renderFrames(); draw(); return true;
    }
    function renderFrames() {
        const holder = $("remixKeyframes"); holder.replaceChildren();
        if (!clip().keyframes.length) holder.textContent = clip().mask_path ? "已使用导入遮罩" : "尚未圈定商品；仅拼接时可直接生成。";
        clip().keyframes.forEach((frame) => {
            const group = document.createElement("span"), seek = document.createElement("button"), remove = document.createElement("button");
            seek.type = remove.type = "button"; seek.textContent = `${frame.time.toFixed(2)} 秒`; remove.textContent = "×";
            remove.setAttribute("aria-label", `删除 ${frame.time.toFixed(2)} 秒关键帧`);
            seek.onclick = () => { if (saveMask()) seekTo(frame.time); };
            remove.onclick = () => { clip().keyframes = clip().keyframes.filter((item) => item !== frame); dirty = false; draft = pointsAt(clip(), video.currentTime); renderFrames(); draw(); };
            group.append(seek, remove); holder.append(group);
        });
    }
    function renderClips() {
        const sourceCount = new Set(clips.map((item) => item.path)).size;
        const seconds = clips.reduce((sum, item) => sum + Math.max(0, item.end-item.start), 0);
        $("remixSourceSummary").textContent = `${sourceCount} 个视频 · ${clips.length}/20 个片段 · 素材 ${seconds.toFixed(1)} 秒`;
        const holder = $("remixClips"); holder.replaceChildren();
        clips.forEach((item, index) => {
            const row = document.createElement("div"); row.className = `remix-clip${index === active ? " active" : ""}`;
            const select = document.createElement("button"); select.type = "button"; select.textContent = `${index + 1}. ${item.name}`;
            select.onclick = () => { if (saveMask()) selectClip(index); }; row.append(select);
            const duplicate = document.createElement("button"); duplicate.type = "button";
            duplicate.textContent = "添加片段"; duplicate.disabled = clips.length >= 20;
            duplicate.onclick = () => {
                if (uploading || clips.length >= 20) return;
                if (!saveMask()) return;
                const copy = JSON.parse(JSON.stringify(item));
                clips.splice(index + 1, 0, copy); $("remixAutoCut").checked = false;
                selectClip(index + 1); showToast("已添加同素材片段，可调整起止时间和顺序");
            }; row.append(duplicate);
            const remove = document.createElement("button"); remove.type = "button"; remove.textContent = "移除";
            remove.setAttribute("aria-label", `移除片段 ${index + 1}`); remove.disabled = clips.length <= 1;
            remove.onclick = () => {
                if (uploading || clips.length <= 1 || !saveMask()) return;
                const current = clip(); clips.splice(index, 1);
                active = Math.max(0, clips.indexOf(current)); resizeCanvas(); selectClip(active);
            }; row.append(remove);
            [-1, 1].forEach((direction) => {
                const button = document.createElement("button"); button.type = "button"; button.textContent = direction < 0 ? "↑" : "↓";
                button.setAttribute("aria-label", direction < 0 ? "片段前移" : "片段后移"); button.disabled = index + direction < 0 || index + direction >= clips.length;
                button.onclick = () => { if (!saveMask()) return; const current = clip(); [clips[index], clips[index + direction]] = [clips[index + direction], clips[index]]; active = clips.indexOf(current); resizeCanvas(); renderClips(); draw(); }; row.append(button);
            });
            holder.append(row);
        });
    }
    function resizeCanvas() {
        const meta = clips[0].meta, ratio = Math.min(1, 720 / Math.max(meta.width, meta.height));
        canvas.width = Math.max(2, Math.floor(meta.width * ratio / 2) * 2);
        canvas.height = Math.max(2, Math.floor(meta.height * ratio / 2) * 2);
    }
    function loadImage(path) { return new Promise((resolve, reject) => { const image = new Image(); image.onload = () => resolve(image); image.onerror = () => reject(new Error("图片加载失败")); image.src = mediaUrl(path); }); }
    async function selectClip(index) {
        pause(); active = index; dirty = false; draft = []; maskImage = null;
        watermarkMode = false; watermarkAnchor = watermarkDraft = null; watermarkStatus();
        maskVideo.removeAttribute("src"); maskVideo.load();
        $("remixStart").value = clip().start; $("remixEnd").value = clip().end;
        $("remixSeek").max = Math.max(0, clip().meta.duration - 0.001);
        $("remixInterpolation").value = clip().interpolation;
        $("remixMaskName").textContent = clip().mask_path ? "已导入商品遮罩" : "";
        video.src = clip().preview_url || mediaUrl(clip().path); video.load();
        if (clip().mask_path) {
            if (/\.(mp4|mov|m4v)$/i.test(clip().mask_path)) maskVideo.src = mediaUrl(clip().mask_path);
            else { try { maskImage = await loadImage(clip().mask_path); } catch (e) { error(e.message); } }
        }
        renderClips(); renderFrames(); draw();
    }
    function seekTo(time) { pause(); video.currentTime = Math.min(Number(time), clip().meta.duration - 0.001); }
    video.addEventListener("loadeddata", () => { if (clip()) { video.currentTime = clip().start; draw(); } });
    video.addEventListener("seeked", () => {
        draftTime = video.currentTime; draft = pointsAt(clip(), draftTime);
        if (maskVideo.getAttribute("src") && maskVideo.readyState >= 1) maskVideo.currentTime = draftTime;
        draw();
    });
    maskVideo.addEventListener("seeked", draw);
    video.addEventListener("timeupdate", () => { if (clip() && video.currentTime >= clip().end && !video.paused) { pause(); } });
    video.addEventListener("ended", pause);
    video.addEventListener("error", () => error("视频加载失败，请检查素材后重新打开混剪。"));
    $("remixPlay").onclick = async () => {
        if (!video.paused) { pause(); return; }
        if (!saveMask()) return;
        if (video.currentTime >= clip().end - 0.02 || video.currentTime < clip().start) video.currentTime = clip().start;
        video.playbackRate = Number($("remixSpeed").value); video.muted = !$("remixAudio").checked;
        try {
            await video.play();
            if (maskVideo.getAttribute("src")) { maskVideo.currentTime = video.currentTime; maskVideo.playbackRate = video.playbackRate; await maskVideo.play(); }
            $("remixPlay").textContent = "暂停预览"; animate();
        } catch (e) { pause(); error(e.message); }
    };
    $("remixSeek").oninput = () => { if (saveMask()) seekTo($("remixSeek").value); };
    $("remixStart").onchange = () => { clip().start = Number($("remixStart").value); renderClips(); };
    $("remixEnd").onchange = () => { clip().end = Number($("remixEnd").value); renderClips(); };
    $("remixInterpolation").onchange = () => { clip().interpolation = $("remixInterpolation").value; };
    $("remixSaveMask").onclick = saveMask;
    $("remixRedraw").onclick = () => { pause(); clip().mask_path = ""; maskImage = null; maskVideo.removeAttribute("src"); draft = []; draftTime = video.currentTime; dirty = true; $("remixMaskName").textContent = ""; draw(); };
    $("remixUndo").onclick = () => { pause(); if (!dirty) draft = pointsAt(clip(), video.currentTime); draft.pop(); draftTime = video.currentTime; dirty = true; draw(); };
    function pointer(event) {
        const rect = canvas.getBoundingClientRect(), g = geometry();
        return [Math.max(0, Math.min(1, ((event.clientX - rect.left) * canvas.width / rect.width - g.x) / g.w)),
            Math.max(0, Math.min(1, ((event.clientY - rect.top) * canvas.height / rect.height - g.y) / g.h))];
    }
    canvas.onpointerdown = (event) => {
        if (!clip() || clip().mask_path) return;
        pause(); if (!dirty) draft = pointsAt(clip(), video.currentTime);
        const point = pointer(event), g = geometry();
        const threshold = 14 * canvas.width / canvas.getBoundingClientRect().width;
        dragging = draft.findIndex(([x, y]) => Math.hypot((x - point[0]) * g.w, (y - point[1]) * g.h) < threshold);
        if (dragging < 0 && draft.length < 64) { draft.push(point); dragging = draft.length - 1; }
        draftTime = video.currentTime; dirty = true; canvas.setPointerCapture(event.pointerId); draw();
    };
    canvas.onpointermove = (event) => { if (dragging >= 0) { draft[dragging] = pointer(event); draw(); } };
    canvas.onpointerup = canvas.onpointercancel = () => { dragging = -1; };
    ["remixOpacity", "remixScale", "remixX", "remixY", "remixOutline"].forEach((id) => $(id).oninput = () => {
        $("remixOpacityValue").textContent = `${$("remixOpacity").value}%`; $("remixScaleValue").textContent = `${$("remixScale").value}%`; draw();
    });
    async function changeImage(kind) {
        const select = $(kind === "background" ? "remixBackground" : "remixOverlay"), path = select.value;
        try { const image = path ? await loadImage(path) : null; if (select.value !== path) return; if (kind === "background") bgImage = image; else overlayImage = image; draw(); }
        catch (e) { error(e.message); }
    }
    $("remixBackground").onchange = () => changeImage("background");
    $("remixOverlay").onchange = () => changeImage("overlay");
    async function upload(input, kind) {
        const file = input.files[0]; if (!file) return;
        const item = clip(); uploading += 1; $("remixSubmit").disabled = true; error();
        try {
            const { asset } = await api(`/api/video/assets/upload?filename=${encodeURIComponent(file.name)}`, { method: "POST", headers: { "Content-Type": file.type || "application/octet-stream" }, body: file });
            if (kind === "mask") {
                if (asset.media_kind === "video") { const meta = await api(`/api/video/info?path=${encodeURIComponent(asset.path)}`); if (meta.duration + 0.05 < item.end) throw new Error("遮罩时长需要覆盖所选片段"); }
                item.mask_path = asset.path; item.keyframes = []; dirty = false;
                await selectClip(clips.indexOf(item));
            } else {
                const select = $(kind === "background" ? "remixBackground" : "remixOverlay");
                select.append(new Option(asset.name, asset.path)); select.value = asset.path; await changeImage(kind);
            }
        } catch (e) { error(e.message); }
        finally { input.value = ""; uploading -= 1; $("remixSubmit").disabled = uploading > 0; }
    }
    $("remixBackgroundUpload").onchange = () => upload($("remixBackgroundUpload"), "background");
    $("remixOverlayUpload").onchange = () => upload($("remixOverlayUpload"), "overlay");
    $("remixMaskUpload").onchange = () => upload($("remixMaskUpload"), "mask");
    $("remixClearMask").onclick = () => { clip().mask_path = ""; selectClip(active); };
    $("remixSubmit").onclick = async () => {
        pause(); if (uploading || !saveMask()) return; error();
        const background = $("remixBackground").value, overlay = $("remixOverlay").value;
        const hasAV = $("remixMusic").value || $("remixVoiceover").value || $("remixSubtitles").value.trim() || Number($("remixVoicePitch").value) || Number($("remixOriginalVolume").value) !== 100 || clips.some((c) => c.watermark || c.watermarks?.length);
        if (hasAV) {
            if (background || overlay) { error("音轨、字幕和水印设置用于一键混剪，请先清空替换背景和叠加图片。"); return; }
            $("remixQuickSubmit").click(); return;
        }
        if ((background || overlay) && clips.some((item) => !item.mask_path && !item.keyframes.length)) { error("请为每个片段圈定商品轮廓或导入遮罩，再替换背景、叠加图片。"); return; }
        if (clips.some((item) => !Number.isFinite(item.start) || !Number.isFinite(item.end) || item.start < 0 || item.end > item.meta.duration + 0.05 || item.end - item.start < 0.05)) { error("请检查各片段的开始和结束时间。"); return; }
        $("remixSubmit").disabled = true;
        try {
            const result = await api("/api/video/remix", { method: "POST", body: JSON.stringify({
                clips: clips.map(({ path, start, end, keyframes, mask_path, interpolation }) => ({ path, start, end, keyframes, mask_path, interpolation })),
                speed: Number($("remixSpeed").value), background, overlay, opacity: Number($("remixOpacity").value) / 100,
                overlay_scale: Number($("remixScale").value) / 100, overlay_x: Number($("remixX").value) / 100, overlay_y: Number($("remixY").value) / 100,
                preserve_audio: $("remixAudio").checked,
            }) });
            renderTasks([result.task]); await refreshRemixTasks(); showToast("商品视频混剪已提交");
        } catch (e) { error(e.message); }
        finally { $("remixSubmit").disabled = false; }
    };
    $("remixMarkWatermark").onclick = () => {
        pause(); if (!clip() || video.readyState < 2) return;
        watermarkMode = true; watermarkAnchor = watermarkDraft = null;
        $("remixWatermarkStatus").textContent = "在画面上拖框，紧贴水印文字"; error();
    };
    $("remixClearWatermark").onclick = () => {
        if (!clip()) return;
        clip().watermark = null; clip().watermarks = []; watermarkMode = false; watermarkAnchor = watermarkDraft = null;
        try { localStorage.removeItem(watermarkKey(clip().path)); } catch {}
        watermarkStatus(); draw();
    };
    canvas.addEventListener("pointerdown", (event) => {
        if (!watermarkMode) return;
        event.stopImmediatePropagation(); event.preventDefault();
        watermarkAnchor = pointer(event); canvas.setPointerCapture(event.pointerId);
    }, true);
    canvas.addEventListener("pointermove", (event) => {
        if (!watermarkMode || !watermarkAnchor) return;
        event.stopImmediatePropagation(); const p = pointer(event), a = watermarkAnchor;
        watermarkDraft = { time: video.currentTime, x: Math.min(a[0],p[0]), y: Math.min(a[1],p[1]), width: Math.abs(a[0]-p[0]), height: Math.abs(a[1]-p[1]) }; draw();
    }, true);
    canvas.addEventListener("pointerup", (event) => {
        if (!watermarkMode) return;
        event.stopImmediatePropagation();
        const b = watermarkDraft;
        if (!b || b.width*clip().meta.width < 5 || b.height*clip().meta.height < 5 || b.width > .5 || b.height > .5) {
            error("请紧贴文字拖出选框，宽高最多为画面的一半。"); watermarkAnchor = watermarkDraft = null; return;
        }
        const from = Number($("remixWatermarkFrom").value), until = $("remixWatermarkUntil").value === "" ? null : Number($("remixWatermarkUntil").value);
        if (!Number.isFinite(from) || from < 0 || (until !== null && (!Number.isFinite(until) || until <= from))) { error("请检查水印生效时间。"); return; }
        const regions = [...(clip().watermarks || []), ...(clip().watermark ? [clip().watermark] : [])];
        if (regions.length >= 8) { error("最多8个水印参考帧，可清除后重新框选。"); watermarkMode = false; return; }
        regions.push({ ...b, active_start: from, active_end: until });
        clip().watermark = null; clip().watermarks = regions;
        try { localStorage.setItem(watermarkKey(clip().path), JSON.stringify(regions)); } catch {}
        watermarkMode = false; watermarkAnchor = watermarkDraft = null; watermarkStatus(); draw();
    }, true);
    $("remixQuickSubmit").onclick = async () => {
        pause(); if (uploading || quickSubmitting || !clips.length) return;
        error(); const duration = Number($("remixTargetDuration").value);
        if (!Number.isFinite(duration) || duration < 1 || duration > 180) { error("目标时长请输入 1 到 180 秒。"); return; }
        if (clips.some((c) => !Number.isFinite(c.start) || !Number.isFinite(c.end) || c.start < 0 || c.end > c.meta.duration+.05 || c.end-c.start < .05)) { error("请检查片段开始和结束时间。"); return; }
        let subtitles;
        try { subtitles = $("remixSubtitles").value.split(/\r?\n/).filter((s) => s.trim()).map((line) => {
            const m = line.match(/^\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*\|(.+)$/);
            if (!m || Number(m[2]) <= Number(m[1])) throw new Error("字幕请按“0-3|文字”填写，每行一条。");
            return { start: Number(m[1]), end: Number(m[2]), text: m[3] };
        }); } catch (e) { error(e.message); return; }
        quickSubmitting = true; $("remixQuickSubmit").disabled = true;
        try {
            const result = await api("/api/video/remix", { method: "POST", body: JSON.stringify({
                clean_mode: true, auto_cut: $("remixAutoCut").checked, speech_aware: $("remixSpeechAware").checked, target_duration: duration,
                edge_crop: Number($("remixEdgeCrop").value), speed: Number($("remixSpeed").value),
                preserve_audio: $("remixAudio").checked,
                clips: clips.map(({path,start,end,watermark,watermarks}) => ({path,start,end,watermark,watermarks})),
                music: $("remixMusic").value, voiceover: $("remixVoiceover").value,
                voice_pitch: Number($("remixVoicePitch").value), original_volume: Number($("remixOriginalVolume").value)/100,
                music_volume: Number($("remixMusicVolume").value)/100, voice_volume: Number($("remixVoiceVolume").value)/100,
                subtitles, subtitle_size: Number($("remixSubtitleSize").value), subtitle_color: $("remixSubtitleColor").value,
                subtitle_position: $("remixSubtitlePosition").value, subtitle_style: $("remixSubtitleStyle").value,
            }) });
            renderTasks([result.task]); await refreshRemixTasks(); showToast("一键混剪已开始，完成后可播放或下载");
        } catch (e) { error(e.message); }
        finally { quickSubmitting = false; $("remixQuickSubmit").disabled = false; }
    };
    dialog.querySelectorAll(".remix-close").forEach((button) => button.onclick = () => dialog.close());
    dialog.addEventListener("close", () => { pause(); $("remixAudioPreview").pause(); });
    function renderTasks(tasks) {
        pendingTasks = tasks.some((task) => task.state === "pending" || task.state === "processing");
        for (const holder of [panel, $("remixStatus")]) {
            holder.replaceChildren(); holder.hidden = !tasks.length;
            tasks.slice(0, 3).forEach((task) => {
                const row = document.createElement("div"), label = document.createElement("span");
                label.textContent = ({ pending: "混剪排队中", processing: `正在混剪 · ${task.progress || 0}%`, success: "混剪完成", failed: `混剪失败：${task.error}` })[task.state] || task.state;
                row.append(label);
                if (task.knowledge_used?.length) {
                    const details = document.createElement('details'), summary = document.createElement('summary');
                    const report = task.dedupe_report;
                    summary.textContent = `知识库多重去重 · ${report ? (report.passed ? '检查通过' : '需调整素材') : '检查中'}`;
                    const body = document.createElement('p');
                    body.textContent = (report ? `移除 ${report.removed_count} 个重复片段；比较 ${report.history_count} 条历史；已应用 ${report.layers?.length || 0} 层静音低透明度视频及入场动画。${report.speech_checked ? '已检查讲话文本。' : '本次未检查讲话文本。'}` : '')
                        + '参考：' + task.knowledge_used.map(source => source.title).join('；');
                    details.append(summary, body); row.append(details);
                }
                if (task.state === "success" && task.output) {
                    const preview = document.createElement("a"), download = document.createElement("a");
                    preview.textContent = "播放成片"; preview.href = mediaUrl(task.output); preview.target = "_blank"; preview.rel = "noopener";
                    download.textContent = "下载 MP4"; download.href = `/files/${task.output.split("/").map(encodeURIComponent).join("/")}`; download.download = "";
                    row.append(preview, download);
                }
                holder.append(row);
            });
        }
    }
    async function loadClip(item) {
        const meta = await api(`/api/video/info?path=${encodeURIComponent(item.path)}`);
        const saved = storedWatermark(item.path);
        return { ...item, name: item.name || item.path.split("/").pop(), meta, start: 0, end: meta.duration,
            keyframes: [], mask_path: "", interpolation: "linear", watermark: Array.isArray(saved) ? null : saved, watermarks: Array.isArray(saved) ? saved : [] };
    }
    function previewAudio(path) { const player = $("remixAudioPreview"); player.pause(); player.hidden = !path; if (path) player.src = mediaUrl(path); else player.removeAttribute("src"); }
    $("remixVoiceover").onchange = () => { if ($("remixVoiceover").value) $("remixAudio").checked = false; previewAudio($("remixVoiceover").value); };
    $("remixMusic").onchange = () => previewAudio($("remixMusic").value);
    async function uploadAudio(input, target) {
        const file = input.files[0]; input.value = ""; if (!file || uploading) return;
        if (!/\.(mp3|wav|m4a|aac|ogg)$/i.test(file.name) || file.size > 128*1024*1024) { error("请上传128 MB以内的 MP3、WAV、M4A、AAC 或 OGG。"); return; }
        const generation = opening; uploading += 1; additionBusy(true); error();
        try {
            const { asset } = await api(`/api/video/audio/upload?filename=${encodeURIComponent(file.name)}`, { method: "POST", headers: { "Content-Type": file.type || "application/octet-stream" }, body: file });
            if (generation !== opening) return;
            for (const id of ["remixMusic", "remixVoiceover"]) $(id).append(new Option(asset.name, asset.path));
            $(target).value = asset.path; $(target).onchange();
        } catch (e) { error(e.message); }
        finally { uploading -= 1; additionBusy(uploading > 0); }
    }
    $("remixVoiceUpload").onchange = () => uploadAudio($("remixVoiceUpload"), "remixVoiceover");
    $("remixMusicUpload").onchange = () => uploadAudio($("remixMusicUpload"), "remixMusic");
    function additionBusy(busy) {
        $("remixAddLibrary").disabled = $("remixConfirmAdd").disabled = $("remixVideosUpload").disabled = busy;
        $("remixQuickSubmit").disabled = busy || quickSubmitting;
        $("remixSubmit").disabled = busy;
    }
    $("remixAddLibrary").onclick = async () => {
        if (uploading || !saveMask()) return;
        error(); const generation = opening;
        try {
            const library = await api("/api/library?limit=1000");
            if (generation !== opening) return;
            const available = library.items.filter((item) => ["mp4", "mov", "m4v"].includes(item.suffix) && !clips.some((c) => c.path === item.path));
            $("remixLibraryVideos").replaceChildren();
            available.forEach((item) => $("remixLibraryVideos").append(new Option(item.path, item.path)));
            $("remixLibraryPicker").hidden = false;
            if (!available.length) error("文件库中暂无其他视频，可以上传多个视频。");
        } catch (e) { error(e.message); }
    };
    $("remixConfirmAdd").onclick = async () => {
        if (uploading || !saveMask()) return;
        const items = [...$("remixLibraryVideos").selectedOptions].map((option) => ({ path: option.value }));
        if (!items.length) { error("请先选择要添加的视频。"); return; }
        if (clips.length + items.length > 20) { error("单次最多 20 个片段，请减少所选视频。"); return; }
        const generation = opening; uploading += 1; additionBusy(true); error();
        try {
            const loaded = await Promise.all(items.map(loadClip));
            if (generation !== opening) return;
            clips.push(...loaded); renderClips(); $("remixLibraryPicker").hidden = true;
            showToast(`已添加 ${loaded.length} 个视频，原有裁剪设置已保留`);
        } catch (e) { error(e.message); }
        finally { uploading -= 1; additionBusy(uploading > 0); }
    };
    $("remixVideosUpload").onchange = async () => {
        const input = $("remixVideosUpload"), files = [...input.files]; input.value = "";
        if (!files.length || uploading || !saveMask()) return;
        if (clips.length + files.length > 20) { error("单次最多 20 个片段，请减少上传数量。"); return; }
        if (files.some((file) => !/\.(mp4|mov|m4v)$/i.test(file.name) || file.size > 256*1024*1024)) { error("请上传 MP4、MOV 或 M4V，每个文件最多 256 MB。"); return; }
        const generation = opening; uploading += 1; additionBusy(true); error();
        const failures = []; let added = 0;
        try {
            for (const file of files) {
                if (generation !== opening) break;
                $("remixSourceSummary").textContent = `正在上传 ${added+failures.length+1}/${files.length}：${file.name}`;
                try {
                    const { asset } = await api(`/api/video/assets/upload?filename=${encodeURIComponent(file.name)}`, { method: "POST", headers: { "Content-Type": file.type || "application/octet-stream" }, body: file });
                    const item = await loadClip(asset);
                    if (generation !== opening) break;
                    clips.push(item); added += 1;
                } catch (e) { failures.push(`${file.name}：${e.message}`); }
            }
            if (generation === opening) { renderClips(); if (failures.length) error(failures.join("；")); if (added) showToast(`已添加 ${added} 个视频`); }
        } finally { uploading -= 1; additionBusy(uploading > 0); }
    };
    async function open(items) {
        const generation = ++opening;
        try {
            if (!items.length || items.length > 20) throw new Error("请选择 1 到 20 个视频片段");
            const loaded = await Promise.all(items.map(loadClip));
            const library = await api("/api/library?limit=1000");
            const audioLibrary = await api("/api/video/music");
            if (opening !== generation) return;
            clips = loaded; active = 0; dirty = false;
            $("remixLibraryPicker").hidden = true;
            for (const id of ["remixMusic", "remixVoiceover"]) { $(id).replaceChildren(new Option(id === "remixMusic" ? "不添加音乐" : "不添加配音", "")); audioLibrary.items.forEach((item) => $(id).append(new Option(item.name,item.path))); }
            $("remixSubtitles").value = ""; $("remixVoicePitch").value = "0"; $("remixOriginalVolume").value = "100";
            $("remixWatermarkFrom").value = "0"; $("remixWatermarkUntil").value = ""; previewAudio("");
            images = library.items.filter((item) => item.media_kind === "image" && ["png", "jpg", "jpeg", "webp", "avif"].includes(item.suffix));
            for (const id of ["remixBackground", "remixOverlay"]) {
                $(id).replaceChildren(new Option(id === "remixBackground" ? "保留原背景" : "不叠加图片", ""));
                images.forEach((item) => $(id).append(new Option(item.name, item.path)));
            }
            bgImage = overlayImage = maskImage = null; error(); resizeCanvas();
            $("remixOpacity").value = "25"; $("remixScale").value = "100"; $("remixX").value = $("remixY").value = "50";
            $("remixOpacityValue").textContent = "25%"; $("remixScaleValue").textContent = "100%"; $("remixSpeed").value = "1";
            $("remixAudio").checked = $("remixOutline").checked = true;
            await selectClip(0); if (!dialog.open) dialog.showModal();
        } catch (e) { showToast(e.message, true); }
    }
    async function importProduct(platform, productId, index) {
        try {
            const item = await api(`/api/product-videos/${platform}/${encodeURIComponent(productId)}/${index}/import`, { method: "POST" });
            await refreshLibrary(); await open([item]);
        } catch (e) { showToast(e.message, true); }
    }
    window.videoRemix = { open, importProduct, renderTasks };
})();

