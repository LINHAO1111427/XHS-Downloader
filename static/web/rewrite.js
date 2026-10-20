/* Uses the existing authenticated api() helper; all generated text is rendered as text. */
(() => {
    const el = (id) => document.getElementById(id);
    let fingerprint = "";
    let pendingRequest = null;
    let polling = false;
    let activeOwner = "";
    let submitting = false;
    const edits = new Map();
    const expanded = new Set();
    let latestTasks = [];
    let latestLivePhotos = [];

    function savedBriefKey() { return `xhs-rewrite-brief:${currentUser?.id || ""}`; }
    function restoreBrief() {
        let saved = {};
        try { saved = JSON.parse(localStorage.getItem(savedBriefKey()) || "{}"); } catch (_) { /* optional preferences */ }
        for (const id of ["rewriteFacts", "rewriteAudience", "rewriteInstructions"]) el(id).value = saved[id] || "";
        el("rewriteArticleCount").value = "10";
        if ([...el("rewriteArticleCount").options].some((option) => option.value === saved.rewriteArticleCount)) {
            el("rewriteArticleCount").value = saved.rewriteArticleCount;
        }
    }
    function saveBrief() {
        const saved = Object.fromEntries(["rewriteFacts", "rewriteAudience", "rewriteInstructions"].map((id) => [id, el(id).value]));
        saved.rewriteArticleCount = el("rewriteArticleCount").value;
        try { localStorage.setItem(savedBriefKey(), JSON.stringify(saved)); } catch (_) { /* storage may be disabled */ }
    }
    function button(label, action) {
        const node = document.createElement("button");
        node.type = "button"; node.className = "button secondary"; node.textContent = label;
        node.addEventListener("click", action); return node;
    }
    async function exportFiles({ paths = [], text, title = "", kind = "file", textFilename = "文案.txt" }) {
        const result = await api("/api/exports", { method: "POST", body: JSON.stringify({
            paths, text, title, kind, text_filename: textFilename,
        }) });
        showToast(`已保存 ${result.count} 个文件到 ${result.directory}`);
        return result;
    }
    async function loadExportSettings() {
        const config = await api("/api/export-settings");
        el("rewriteExportDirectory").value = config.directory;
        el("rewriteExportDirectoryState").textContent = config.directory;
        return config;
    }
    async function openExportSettings() {
        try {
            await loadExportSettings();
            el("rewriteExportDialog").showModal();
            el("rewriteExportDirectory").focus();
        } catch (error) { showToast(error.message, true); }
    }
    function livePhotoFor(path) {
        return latestLivePhotos.find((task) => task.source === path);
    }
    function render(tasks) {
        latestTasks = tasks;
        const query = el("rewriteSearch").value.trim().toLowerCase();
        const next = JSON.stringify([tasks, query, latestLivePhotos.map((task) => [task.task_id, task.state, task.output, task.error])]);
        if (next === fingerprint) return;
        fingerprint = next;
        // Preserve manual edits and focus while image jobs update.
        const focused = document.activeElement?.dataset.rewriteEditor;
        const selection = focused ? [document.activeElement.selectionStart, document.activeElement.selectionEnd] : null;
        el("rewriteResults").replaceChildren();
        const busy = tasks.some((task) => ["pending", "processing"].includes(task.state));
        el("rewriteNoteButton").disabled = busy || submitting;
        el("rewriteSummary").textContent = tasks.length ? `已保存 ${tasks.length} 篇 · 点击条目查看详情${busy ? " · 后台正在生成配图" : ""}` : "粘贴一篇对标链接，点击一键改写图文";
        for (const task of tasks) {
            const title = task.plan?.title || task.text?.split("\n")[0] || task.source?.title || "对标笔记改写";
            if (query && ![title, task.product_name, task.creative_theme, task.text].filter(Boolean).join(" ").toLowerCase().includes(query)) continue;
            const article = document.createElement("details"); article.className = "rewrite-result";
            article.dataset.rewriteId = task.id;
            article.open = expanded.has(task.id);
            article.addEventListener("toggle", () => {
                if (!article.isConnected) return;
                if (article.open) expanded.add(task.id); else expanded.delete(task.id);
            });
            const summary = document.createElement("summary"); summary.className = "rewrite-row";
            const cover = task.outputs.find((item) => item.position === 0);
            if (cover) {
                const thumb = document.createElement("img"); thumb.className = "rewrite-cover";
                thumb.src = cover.preview_url; thumb.alt = ""; thumb.loading = "lazy"; summary.append(thumb);
            } else {
                const placeholder = document.createElement("span"); placeholder.className = "rewrite-cover rewrite-cover-pending";
                placeholder.textContent = "配图待完成"; summary.append(placeholder);
            }
            const info = document.createElement("div"); info.className = "rewrite-row-info";
            const heading = document.createElement("h3"); heading.textContent = title;
            const status = document.createElement("p"); status.className = "rewrite-status";
            status.textContent = `${task.phase} · 配图 ${task.completed}/${task.total}`;
            const meta = document.createElement("p"); meta.className = "rewrite-meta";
            const batchPosition = task.variant_total > 1 ? `第 ${task.variant_index}/${task.variant_total} 篇` : "";
            meta.textContent = [batchPosition, task.batch_angle, task.product_name, task.creative_theme, new Date(task.created_at * 1000).toLocaleDateString("zh-CN")].filter(Boolean).join(" · ");
            info.append(heading, meta, status);
            const affordance = document.createElement("span"); affordance.className = "rewrite-open-label";
            affordance.textContent = "查看详情"; summary.append(info, affordance); article.append(summary);
            if (task.ima_status && task.ima_status !== "未启用 IMA") {
                const ima = document.createElement("p"); ima.className = "rewrite-status";
                ima.textContent = `${task.ima_status}：${(task.ima_sources || []).map((item) => `${item.library} / ${item.title}（${item.kind}）`).join("、")}${task.ima_warnings?.length ? "；" + task.ima_warnings.join("；") : ""}`;
                article.append(ima);
            }
            if (task.text) {
                const area = document.createElement("textarea"); area.className = "rewrite-output"; area.rows = 9;
                area.setAttribute("aria-label", "改写文案"); area.dataset.rewriteEditor = task.id;
                area.value = edits.get(task.id) ?? task.text;
                area.addEventListener("input", () => edits.set(task.id, area.value));
                const actions = document.createElement("div"); actions.className = "rewrite-actions";
                actions.append(button("复制文案", async () => {
                    try { await navigator.clipboard.writeText(area.value); showToast("文案已复制"); }
                    catch (_) { area.focus(); area.select(); showToast("文案已选中，请按 Ctrl+C 复制"); }
                }));
                actions.append(button("下载当前文案", async () => {
                    try { await exportFiles({ text: area.value, title, kind: "text", textFilename: "改写文案.txt" }); }
                    catch (error) { showToast(error.message, true); }
                }));
                if (task.outputs.length) {
                    actions.append(button("下载整套图文", async () => {
                        try { await exportFiles({ paths: task.outputs.map((item) => item.path), text: area.value, title, kind: "graphic", textFilename: "改写文案.txt" }); }
                        catch (error) { showToast(error.message, true); }
                    }));
                    actions.append(button("一键下载实况图", async () => {
                        const pairs = task.outputs.map((item) => ({ item, live: livePhotoFor(item.path) }))
                            .filter(({ live }) => live?.state === "success" && live.output);
                        if (!pairs.length) { showToast("请先为配图生成实况", true); return; }
                        try {
                            await exportFiles({
                                paths: pairs.flatMap(({ item, live }) => [item.path, live.output]),
                                text: area.value, title, kind: "live_photo", textFilename: "改写文案.txt",
                            });
                        } catch (error) { showToast(error.message, true); }
                    }));
                }
                article.append(area, actions);
            }
            if (task.outputs.length) {
                const gallery = document.createElement("div"); gallery.className = "rewrite-gallery";
                for (const item of task.outputs) {
                    const figure = document.createElement("figure");
                    const img = document.createElement("img"); img.src = item.preview_url; img.alt = item.role; img.loading = "lazy";
                    const caption = document.createElement("figcaption");
                    caption.textContent = `${item.position + 1}. ${item.role} · ${item.image_origin === "source_crop" ? "采集原图" : "AI 场景示意"}`;
                    const imageActions = document.createElement("div"); imageActions.className = "rewrite-image-actions";
                    imageActions.append(button("下载图片", async () => {
                        try { await exportFiles({ paths: [item.path], title: `${title}-${item.position + 1}`, kind: "file" }); }
                        catch (error) { showToast(error.message, true); }
                    }));
                    const liveTask = livePhotoFor(item.path);
                    const liveButton = button(liveTask?.state === "processing" ? "实况生成中"
                        : liveTask?.state === "pending" ? "实况排队中"
                        : liveTask?.state === "failed" ? "重试生成实况"
                        : liveTask?.state === "success" ? "重新生成实况" : "生成实况", () => {
                            window.dispatchEvent(new CustomEvent("open-live-photo-editor", { detail: {
                                path: item.path, name: item.name, size: item.size, preview_url: item.preview_url, media_kind: "image",
                            } }));
                        });
                    liveButton.classList.add("live-photo");
                    liveButton.disabled = ["pending", "processing"].includes(liveTask?.state);
                    imageActions.append(liveButton);
                    if (liveTask?.state === "success" && liveTask.output) imageActions.append(button("下载实况", async () => {
                        try { await exportFiles({ paths: [item.path, liveTask.output], title: `${title}-${item.position + 1}`, kind: "live_photo" }); }
                        catch (error) { showToast(error.message, true); }
                    }));
                    if (liveTask?.state === "failed") {
                        const error = document.createElement("span"); error.className = "rewrite-live-error"; error.textContent = liveTask.error || "实况生成失败";
                        imageActions.append(error);
                    }
                    figure.append(img, caption, imageActions); gallery.append(figure);
                }
                article.append(gallery);
            }
            if (task.observations?.length || task.viral_sources_used?.length) {
                const details = document.createElement("details"); const summary = document.createElement("summary"); summary.textContent = "图片优化依据与参考来源";
                const notes = document.createElement("p"); notes.textContent = (task.observations || []).join("\n");
                const sources = document.createElement("p");
                sources.textContent = `爆款正文：${task.viral_sources_used?.map((item) => item.title).join("、") || "未匹配到可读正文"}。历史案例：${task.corpus_used?.map((item) => item.title).join("、") || "未匹配"}；实际读取案例图 ${task.case_images_used?.length || 0} 张。知识：${task.knowledge_used?.map((item) => item.title).join("、") || "未匹配"}。`;
                const adaptation = document.createElement("p");
                adaptation.textContent = `产品外观锚点：${task.product_anchor || "以本次采集原图为准"}\n迁移结构：${task.viral_adaptation?.borrowed?.join("；") || "未记录"}\n排除内容：${task.viral_adaptation?.discarded?.join("；") || "未记录"}`;
                details.append(summary, notes, sources, adaptation); article.append(details);
            }
            for (const error of task.errors) {
                const line = document.createElement("p"); line.className = "rewrite-error";
                line.textContent = `${error.position === undefined ? "" : `第 ${error.position + 1} 张：`}${error.message}`; article.append(line);
            }
            if (["partial", "failed", "interrupted"].includes(task.state)) article.append(button("继续未完成部分", async (event) => {
                event.currentTarget.disabled = true;
                try { await api(`/api/ai/rewrites/${task.id}/retry`, { method: "POST" }); fingerprint = ""; await refresh(); }
                catch (error) { showToast(error.message, true); event.currentTarget.disabled = false; }
            }));
            el("rewriteResults").append(article);
        }
        if (!el("rewriteResults").childElementCount) {
            const empty = document.createElement("p"); empty.className = "rewrite-status";
            empty.textContent = query ? "没有匹配的文章，试试其他标题或产品关键词" : "还没有文章，生成后会按篇保存在这里";
            el("rewriteResults").append(empty);
        }
        if (focused) {
            const area = [...el("rewriteResults").querySelectorAll("textarea")].find((node) => node.dataset.rewriteEditor === focused);
            if (area) { area.focus({ preventScroll: true }); area.setSelectionRange(...selection); }
        }
    }
    async function refresh() {
        if (!currentUser) {
            if (activeOwner) { activeOwner = ""; fingerprint = ""; edits.clear(); expanded.clear(); latestTasks = []; latestLivePhotos = []; el("rewriteResults").replaceChildren(); }
            return;
        }
        el("rewriteExportSettings").hidden = currentUser.role !== "admin";
        if (polling) return;
        polling = true;
        const owner = currentUser.id;
        if (owner !== activeOwner) { activeOwner = owner; fingerprint = ""; edits.clear(); expanded.clear(); pendingRequest = null; el("rewriteSearch").value = ""; restoreBrief(); }
        try {
            const [result, liveResult] = await Promise.all([api("/api/ai/rewrites"), api("/api/live-photos")]);
            if (currentUser?.id === owner) {
                latestLivePhotos = liveResult.tasks;
                render(result.tasks);
            }
        } catch (error) { el("rewriteSummary").textContent = `进度读取失败：${error.message}`; }
        finally { polling = false; }
    }
    async function start() {
        if (submitting) return;
        const content = el("urlInput").value.trim();
        if (!content) { showToast("请先粘贴一篇对标笔记链接", true); el("urlInput").focus(); return; }
        saveBrief();
        const payload = { content, style: el("rewriteStyle").value, article_count: Number(el("rewriteArticleCount").value),
            image_count: Number(el("rewriteCount").value),
            product_facts: el("rewriteFacts").value.trim(), target_audience: el("rewriteAudience").value.trim(),
            instructions: el("rewriteInstructions").value.trim() };
        const signature = JSON.stringify(payload);
        if (!pendingRequest || pendingRequest.signature !== signature) pendingRequest = { signature, id: crypto.randomUUID() };
        submitting = true; el("rewriteNoteButton").disabled = true;
        try {
            const result = await api("/api/ai/rewrites", { method: "POST", body: JSON.stringify({ ...payload, request_id: pendingRequest.id }) });
            pendingRequest = null; fingerprint = "";
            showToast(`已开始生成 ${result.article_count} 篇图文，每篇 ${payload.image_count} 张图`);
        } catch (error) { showToast(error.message, true); }
        finally { submitting = false; el("rewriteNoteButton").disabled = false; await refresh(); }
    }
    window.addEventListener("live-photo-task-submitted", (event) => {
        if (!event.detail?.task) return;
        latestLivePhotos = [event.detail.task, ...latestLivePhotos.filter((task) => task.task_id !== event.detail.task.task_id)];
        fingerprint = "";
        render(latestTasks);
    });
    el("rewriteNoteButton").addEventListener("click", start);
    el("refreshRewrites").addEventListener("click", () => { fingerprint = ""; refresh(); });
    el("rewriteExportSettings").addEventListener("click", openExportSettings);
    el("rewriteExportForm").addEventListener("submit", async (event) => {
        event.preventDefault();
        const save = el("saveRewriteExportDirectory"); save.disabled = true;
        try {
            const config = await api("/api/export-settings", { method: "PUT", body: JSON.stringify({ directory: el("rewriteExportDirectory").value.trim() }) });
            el("rewriteExportDirectoryState").textContent = config.directory;
            el("rewriteExportDialog").close();
            showToast(`图文下载目录已设为 ${config.directory}`);
        } catch (error) { showToast(error.message, true); }
        finally { save.disabled = false; }
    });
    el("rewriteSearch").addEventListener("input", () => render(latestTasks));
    for (const id of ["rewriteFacts", "rewriteAudience", "rewriteInstructions", "rewriteArticleCount"]) el(id).addEventListener("change", saveBrief);
    window.addEventListener("rewrite-note", (event) => {
        el("urlInput").value = event.detail.url; window.location.hash = "download"; start();
    });
    el("knowledgeImportFile").addEventListener("change", async (event) => {
        const file = event.target.files[0]; if (!file) return;
        const status = el("knowledgeImportStatus"); event.target.disabled = true;
        try {
            if (file.size > 1024 * 1024) throw new Error("文档请控制在 1 MB 内");
            status.textContent = "正在分段导入知识文档…";
            const result = await api(`/api/knowledge/import-document?filename=${encodeURIComponent(file.name)}&kind=${el("knowledgeKind").value}`,
                { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file });
            status.textContent = `${result.source}：新增 ${result.imported} 条，跳过 ${result.duplicates} 条重复知识。下次生成将自动检索。`;
            await loadKnowledge();
        } catch (error) { status.textContent = error.message; showToast(error.message, true); }
        finally { event.target.disabled = false; event.target.value = ""; }
    });
    setInterval(() => { if (!pollingPaused()) refresh(); }, 3000);
    refresh();
})();
