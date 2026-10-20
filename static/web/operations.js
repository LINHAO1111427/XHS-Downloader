(function () {
    "use strict";

    const bridge = window.operationBridge;
    if (!bridge) return;
    const { api, showToast, refreshIcons, navigateTo } = bridge;
    const el = (id) => document.getElementById(id);
    const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[character]);
    const splitKeywords = (value) => [...new Set(String(value || "").split(/[,，、\n]/).map((item) => item.trim()).filter(Boolean))];
    const state = {
        spaces: [],
        selectedId: "",
        detail: null,
        productCatalog: [],
        rewriteTasks: [],
        timer: null,
        loading: false,
        detailRequest: 0,
        activeTab: "factory",
        profileDirty: false,
        initialized: false,
        discoveryRunId: "",
    };

    function mediaUrl(path) {
        return `/media/${String(path || "").split("/").map(encodeURIComponent).join("/")}`;
    }

    function sourceLabel(kind) {
        return ({ benchmark_account: "账号同步", benchmark_account_viral: "账号低粉爆款", benchmark_note: "指定爆款", traffic_note: "同品爆款" })[kind] || "参考笔记";
    }

    function preferredSpace(value) {
        try {
            const key = `xhs-operation-space:${bridge.currentUser()?.id || "local"}`;
            if (value !== undefined) localStorage.setItem(key, value);
            return localStorage.getItem(key) || "";
        } catch (_) { return ""; }
    }

    function statusLabel(generation) {
        if (generation.content_type === "graphic" && generation.rewrite_job_ids?.length) {
            const jobs = generation.rewrite_job_ids.map((id) => state.rewriteTasks.find((task) => task.id === id)).filter(Boolean);
            if (jobs.length) {
                if (jobs.every((job) => job.state === "success")) return "已完成";
                if (jobs.some((job) => ["pending", "processing"].includes(job.state))) return "生成中";
                if (jobs.some((job) => job.state === "partial")) return "部分完成";
                if (jobs.every((job) => ["failed", "interrupted"].includes(job.state))) return "失败";
            }
        }
        return ({ pending: "等待中", processing: "生成中", success: "已完成", failed: "失败" })[generation.status] || generation.status;
    }

    function openSpaceDialog() {
        el("operationCreateSpaceForm").reset();
        el("operationSpaceDialog").showModal();
        el("operationCreateName").focus();
    }

    function renderSpaces() {
        el("operationSpaceCount").textContent = `${state.spaces.length} 个`;
        const list = el("operationSpaceList");
        list.replaceChildren();
        if (!state.spaces.length) {
            const empty = document.createElement("div");
            empty.className = "empty-state";
            empty.innerHTML = '<i data-lucide="layout-dashboard"></i><span>还没有账号空间</span>';
            list.append(empty);
        } else {
            for (const space of state.spaces) {
                const button = document.createElement("button");
                button.type = "button";
                button.className = `operation-space-item${space.id === state.selectedId ? " active" : ""}`;
                const initial = Array.from(space.account_name || space.name || "号")[0] || "号";
                button.setAttribute("aria-pressed", String(space.id === state.selectedId));
                button.title = space.name;
                button.innerHTML = `<span class="operation-space-avatar">${escapeHtml(initial)}</span><span class="operation-space-copy"><strong>${escapeHtml(space.name)}</strong><small>${space.product_count || 0} 商品 · ${space.note_count || 0} 对标笔记</small></span>`;
                button.addEventListener("click", () => selectSpace(space.id));
                list.append(button);
            }
        }
        el("operationEmpty").hidden = Boolean(state.selectedId);
        el("operationDetail").hidden = !state.selectedId;
        refreshIcons();
    }

    function renderAccounts() {
        const accounts = state.detail?.benchmark_accounts || [];
        el("operationAccountCount").textContent = accounts.length;
        const list = el("operationAccountList");
        list.replaceChildren();
        if (!accounts.length) {
            list.innerHTML = '<div class="empty-state"><span>先添加一个真正要研究的对标账号</span></div>';
            return;
        }
        for (const account of accounts) {
            const item = document.createElement("article");
            item.className = "operation-record";
            item.innerHTML = `<div class="operation-record-main"><strong>${escapeHtml(account.nickname || account.platform_user_id || "待识别账号")}</strong><p>${escapeHtml(account.status)}${account.followers == null ? "" : ` · 粉丝 ${Number(account.followers).toLocaleString("zh-CN")}`} · 已存 ${account.note_count || 0} 篇${account.last_error ? ` · ${escapeHtml(account.last_error)}` : ""}</p></div><div class="operation-record-actions"><button class="button secondary" type="button" data-action="sync"><i data-lucide="refresh-cw"></i>同步</button><button class="icon-button subtle operation-danger" type="button" data-action="delete" aria-label="删除对标账号"><i data-lucide="trash-2"></i></button></div>`;
            item.querySelector('[data-action="sync"]').addEventListener("click", (event) => syncAccount(account.id, event.currentTarget));
            item.querySelector('[data-action="delete"]').addEventListener("click", () => deleteAccount(account));
            list.append(item);
        }
    }

    function renderNotes() {
        const notes = state.detail?.notes || [];
        el("operationNoteCount").textContent = notes.length;
        const list = el("operationNoteList");
        list.replaceChildren();
        if (!notes.length) {
            list.innerHTML = '<div class="empty-state"><span>还没有对标笔记，先指定核心笔记或同步对标账号</span></div>';
        }
        for (const note of notes) {
            const item = document.createElement("article");
            item.className = "operation-record";
            const metric = note.metrics || {};
            const cover = note.image_paths?.[0] ? mediaUrl(note.image_paths[0]) : note.cover || note.image_urls?.[0] || "";
            const badgeClass = note.source_kind === "traffic_note" ? " traffic" : "";
            const assets = `${note.image_paths?.length || note.image_urls?.length || 0} 图 · ${note.products?.length || 0} 商品`;
            item.innerHTML = `<div class="operation-note-row">${cover ? `<img class="operation-note-cover" src="${escapeHtml(cover)}" alt="" loading="lazy">` : '<span class="operation-note-cover"></span>'}<div class="operation-record-main"><strong><span class="operation-source-badge${badgeClass}">${sourceLabel(note.source_kind)}</span>${escapeHtml(note.title || "无标题")}</strong><p>${escapeHtml(note.author || "未知作者")}${metric.interactions == null ? "" : ` · 互动 ${Number(metric.interactions).toLocaleString("zh-CN")}`}${metric.ratio == null ? "" : ` · 互动粉丝比 ${(Number(metric.ratio) * 100).toFixed(1)}%`} · ${assets} · ${note.structure?.paragraph_count || 0} 段 / ${note.structure?.body_chars || 0} 字</p></div></div><div class="operation-record-actions">${note.url ? '<a class="icon-button subtle" data-action="open" target="_blank" rel="noopener noreferrer" aria-label="打开原笔记"><i data-lucide="external-link"></i></a>' : ""}<button class="icon-button subtle operation-danger" type="button" data-action="delete" aria-label="删除笔记"><i data-lucide="trash-2"></i></button></div>`;
            const open = item.querySelector('[data-action="open"]');
            if (open) open.href = note.url;
            item.querySelector('[data-action="delete"]').addEventListener("click", () => deleteNote(note));
            list.append(item);
        }
        renderReferencePicker();
    }

    function renderProducts() {
        const products = state.detail?.products || [];
        el("operationProductCount").textContent = products.length;
        const list = el("operationProductList");
        list.replaceChildren();
        if (!products.length) list.innerHTML = '<div class="empty-state"><span>还没有商品。建议先在“商品素材”采集原图，再导入这里。</span></div>';
        for (const product of products) {
            const card = document.createElement("article");
            card.className = "operation-product-card";
            const cover = product.image_paths?.[0] ? mediaUrl(product.image_paths[0]) : product.image_urls?.[0] || "";
            card.innerHTML = `<div class="operation-product-cover">${cover ? `<img src="${escapeHtml(cover)}" alt="" loading="lazy">` : '<i data-lucide="package-open"></i>'}</div><div class="operation-product-body"><strong>${escapeHtml(product.title)}</strong><p>${escapeHtml(product.selling_points || product.description || "尚未补充真实商品资料")}</p><div class="operation-product-actions"><span>${product.image_paths?.length || 0} 原图 · ${product.video_paths?.length || 0} 视频</span><div>${product.video_paths?.length ? '<button class="button secondary" type="button" data-action="remix"><i data-lucide="scissors"></i>视频混剪</button>' : ""}<button class="icon-button subtle operation-danger" type="button" data-action="delete" aria-label="删除商品"><i data-lucide="trash-2"></i></button></div></div></div>`;
            card.querySelector('[data-action="delete"]').addEventListener("click", () => deleteProduct(product));
            card.querySelector('[data-action="remix"]')?.addEventListener("click", () => openProductRemix(product));
            list.append(card);
        }
        const select = el("operationGenerateProduct");
        const current = select.value;
        select.innerHTML = '<option value="">选择本次要生成的商品</option>' + products.map((product) => `<option value="${escapeHtml(product.id)}">${escapeHtml(product.title)}${product.image_paths?.length ? ` · ${product.image_paths.length} 张原图` : " · 无本地原图"}</option>`).join("");
        if (products.some((product) => product.id === current)) select.value = current;
    }

    function renderReferencePicker() {
        const notes = state.detail?.notes || [];
        const picker = el("operationReferencePicker");
        const selected = new Set([...picker.querySelectorAll("input:checked")].map((input) => input.value));
        picker.replaceChildren();
        if (!notes.length) {
            picker.innerHTML = '<span class="operation-record-main"><small>请先建立对标笔记池</small></span>';
            return;
        }
        for (const note of notes) {
            const label = document.createElement("label");
            label.className = "operation-reference-option";
            label.innerHTML = `<input type="checkbox" value="${escapeHtml(note.id)}"><span><strong>${escapeHtml(note.title || "无标题")}</strong><small>${sourceLabel(note.source_kind)} · ${note.structure?.paragraph_count || 0} 段 / ${note.structure?.body_chars || 0} 字</small></span>`;
            const input = label.querySelector("input");
            input.checked = selected.has(note.id);
            input.addEventListener("change", () => {
                const checked = picker.querySelectorAll("input:checked");
                if (checked.length > 6) {
                    input.checked = false;
                    showToast("一次最多选择 6 篇对标笔记", true);
                }
            });
            picker.append(label);
        }
    }

    function videoOutput(result) {
        if (!result || !Object.keys(result).length) return "";
        const shots = (result.shots || []).map((shot, index) => `${index + 1}. ${shot.seconds || ""}｜${shot.visual || ""}\n屏幕：${shot.on_screen_text || "无"}\n口播：${shot.voiceover || ""}\n素材：${shot.asset_source || ""}`).join("\n\n");
        return `${result.title || ""}\n\n${result.caption || ""}\n\n前3秒：${result.hook || ""}\n时长：${result.duration_seconds || ""} 秒\n\n完整口播：\n${result.voiceover || ""}\n\n分镜：\n${shots}`;
    }

    function renderGenerations() {
        const generations = state.detail?.generations || [];
        el("operationGenerationCount").textContent = generations.length;
        const list = el("operationGenerationList");
        list.replaceChildren();
        if (!generations.length) {
            list.innerHTML = '<div class="empty-state"><span>还没有生成记录</span></div>';
            return;
        }
        const products = Object.fromEntries((state.detail?.products || []).map((product) => [product.id, product]));
        for (const generation of generations) {
            const item = document.createElement("details");
            item.className = "operation-generation";
            const product = products[generation.product_id];
            const label = generation.content_type === "graphic" ? "图文" : "视频";
            const status = statusLabel(generation);
            item.innerHTML = `<summary><div class="operation-generation-head"><strong>${escapeHtml(generation.title || product?.title || "内容生成")}</strong><span>${label} · ${escapeHtml(status)}</span></div><p class="operation-generation-meta">${new Date(generation.created_at * 1000).toLocaleString("zh-CN")}${generation.error ? ` · ${escapeHtml(generation.error)}` : ""}</p></summary>`;
            if (generation.content_type === "video" && generation.result && Object.keys(generation.result).length) {
                const output = document.createElement("pre");
                output.className = "operation-generation-output";
                output.textContent = videoOutput(generation.result);
                const copy = document.createElement("button");
                copy.type = "button";
                copy.className = "button secondary";
                copy.textContent = "复制视频方案";
                copy.addEventListener("click", async () => {
                    try { await navigator.clipboard.writeText(output.textContent); showToast("视频脚本与分镜已复制"); }
                    catch (_) { showToast("复制失败，请手动选择文本", true); }
                });
                item.append(output, copy);
                const mediaTask = generation.result.media_task;
                if (mediaTask) {
                    const mediaState = document.createElement("p");
                    mediaState.className = "operation-generation-meta";
                    if (mediaTask.state === "success" && mediaTask.output) {
                        mediaState.textContent = mediaTask.kind === "product_video_remix" ? "商品视频初稿已生成" : "商品图片竖版视频已生成";
                        const mediaActions = document.createElement("div");
                        mediaActions.className = "rewrite-actions";
                        const preview = document.createElement("a");
                        preview.className = "button secondary";
                        preview.href = mediaUrl(mediaTask.output);
                        preview.target = "_blank";
                        preview.rel = "noopener noreferrer";
                        preview.textContent = "预览视频初稿";
                        const download = document.createElement("a");
                        download.className = "button secondary";
                        download.href = `/files/${String(mediaTask.output).split("/").map(encodeURIComponent).join("/")}`;
                        download.download = "";
                        download.textContent = "下载视频";
                        mediaActions.append(preview, download);
                        item.append(mediaState, mediaActions);
                    } else {
                        mediaState.textContent = mediaTask.state === "failed" ? `视频初稿生成失败：${mediaTask.error || "未知错误"}` : "正在根据商品素材生成视频初稿";
                        item.append(mediaState);
                    }
                }
            } else if (generation.content_type === "graphic") {
                const actions = document.createElement("div");
                actions.className = "rewrite-actions";
                const open = document.createElement("button");
                open.type = "button";
                open.className = "button secondary";
                open.textContent = status === "已完成" || status === "部分完成" ? "查看图文结果" : "查看生成进度";
                open.addEventListener("click", () => {
                    navigateTo("download");
                    setTimeout(() => document.getElementById("rewriteHeading")?.scrollIntoView({ behavior: "smooth" }), 50);
                });
                actions.append(open);
                item.append(actions);
            }
            list.append(item);
        }
    }

    function renderDetail() {
        if (!state.detail) return;
        el("operationWorkspaceName").textContent = state.detail.space.name;
        el("operationWorkspaceAccount").textContent = state.detail.space.account_name || "账号昵称待设置";
        const space = state.detail.space;
        el("operationSpaceTitle").textContent = space.account_name || space.name;
        el("operationSpaceMeta").textContent = `${state.detail.notes.length} 篇笔记 · ${state.detail.products.length} 个商品 · ${state.detail.generations.length} 条生成记录`;
        if (!state.profileDirty) {
            el("operationSpaceName").value = space.name || "";
            el("operationAccountName").value = space.account_name || "";
            el("operationPositioning").value = space.positioning || "";
            el("operationAudience").value = space.target_audience || "";
            el("operationTone").value = space.tone || "";
            el("operationKeywords").value = (space.keywords || []).join("，");
        }
        renderAccounts();
        renderNotes();
        renderProducts();
        renderGenerations();
        window.dispatchEvent(new CustomEvent("operation-space-loaded", { detail: state.detail }));
        refreshIcons();
    }

    async function loadProductCatalog() {
        const [alibaba, xhs] = await Promise.all([api("/api/1688/products"), api("/api/xhs/products")]);
        state.productCatalog = [
            ...(alibaba.products || []).map((item) => ({ platform: "1688", ...item })),
            ...(xhs.products || []).map((item) => ({ platform: "xhs", ...item })),
        ];
        const select = el("operationCollectedProduct");
        select.innerHTML = '<option value="">选择已采集商品</option>' + state.productCatalog.map((product, index) => `<option value="${index}">${product.platform === "1688" ? "1688" : "小红书"} · ${escapeHtml(product.title || product.product_id)}</option>`).join("");
    }

    async function loadSpaces({ preserve = true } = {}) {
        if (!bridge.currentUser()) return;
        const result = await api("/api/operations/spaces");
        state.spaces = result.spaces || [];
        const base = result.base_knowledge || {};
        el("operationBaseKnowledge").innerHTML = `<i data-lucide="database"></i>基础知识 ${base.entries || 0} 条 · 案例 ${base.corpus_entries || 0} 条`;
        if (!preserve || !state.spaces.some((space) => space.id === state.selectedId)) {
            const preferred = preferredSpace();
            const preferredSpaceRecord = state.spaces.find(space => space.id === preferred);
            const preferredIsHistory = /历史内容/.test(preferredSpaceRecord?.name || "");
            state.selectedId = (!preferredIsHistory && preferredSpaceRecord?.id)
                || state.spaces.find(space => !/历史内容/.test(space.name || ""))?.id
                || state.spaces[0]?.id || "";
            state.profileDirty = false;
        }
        renderSpaces();
        if (state.selectedId) await loadDetail();
    }

    async function loadDetail(force = false) {
        if (!state.selectedId || (state.loading && !force)) return;
        state.loading = true;
        const selectedId = state.selectedId;
        const request = ++state.detailRequest;
        try {
            const [detail, rewrites] = await Promise.all([
                api(`/api/operations/spaces/${selectedId}`),
                api("/api/ai/rewrites"),
            ]);
            if (detail.space.id !== state.selectedId || request !== state.detailRequest) return;
            state.detail = detail;
            state.rewriteTasks = rewrites.tasks || [];
            renderDetail();
        } finally {
            if (request === state.detailRequest) state.loading = false;
        }
    }

    async function selectSpace(spaceId) {
        if (spaceId === state.selectedId && state.detail) return;
        state.selectedId = spaceId;
        preferredSpace(spaceId);
        state.profileDirty = false;
        state.detail = null;
        renderSpaces();
        await loadDetail(true);
    }

    async function createSpace(event) {
        event.preventDefault();
        const result = await api("/api/operations/spaces", {
            method: "POST",
            body: JSON.stringify({
                name: el("operationCreateName").value.trim(),
                account_name: el("operationCreateAccountName").value.trim(),
                positioning: el("operationCreatePositioning").value.trim(),
                account_url: "", target_audience: el("operationCreateAudience").value.trim(), tone: "", keywords: [],
            }),
        });
        state.selectedId = result.space.id;
        state.profileDirty = false;
        el("operationSpaceDialog").close();
        await loadSpaces();
        showToast("账号空间已创建，现在可以添加对标和商品");
    }

    async function saveSpace(event) {
        event.preventDefault();
        await api(`/api/operations/spaces/${state.selectedId}`, {
            method: "PUT",
            body: JSON.stringify({
                name: el("operationSpaceName").value.trim(),
                account_name: el("operationAccountName").value.trim(),
                account_url: "",
                positioning: el("operationPositioning").value.trim(),
                target_audience: el("operationAudience").value.trim(),
                tone: el("operationTone").value.trim(),
                keywords: splitKeywords(el("operationKeywords").value),
            }),
        });
        await loadSpaces();
        state.profileDirty = false;
        showToast("账号定位已保存，后续生成会自动带入");
    }

    async function analyzeProfile() {
        const button = el("operationAnalyzeProfile");
        button.disabled = true;
        el("operationAnalyzeState").textContent = "正在读取对标账号、爆款笔记和商品资料…";
        try {
            const result = await api(`/api/operations/spaces/${state.selectedId}/analyze-profile`, { method: "POST" });
            state.detail.space = result.space;
            state.profileDirty = false;
            renderDetail();
            const uncertainties = result.analysis?.uncertainties || [];
            el("operationAnalyzeState").textContent = uncertainties.length
                ? `分析完成；仍需确认：${uncertainties.slice(0, 2).join("；")}`
                : "分析完成，已自动填写卖货方向、受众、调性和关键词";
            showToast("已根据当前对标资料补全账号画像，请核对后保存");
        } catch (error) {
            el("operationAnalyzeState").textContent = error.message;
            showToast(error.message, true);
        } finally {
            button.disabled = false;
        }
    }

    async function deleteSpace() {
        const space = state.detail?.space;
        if (!space || !window.confirm(`确定删除账号空间“${space.name}”及其中的对标、商品和生成索引？已生成的本地媒体文件不会删除。`)) return;
        await api(`/api/operations/spaces/${space.id}`, { method: "DELETE" });
        state.selectedId = "";
        state.detail = null;
        await loadSpaces({ preserve: false });
        showToast("账号空间及其数据库记录已删除");
    }

    async function addAccount(event) {
        event.preventDefault();
        const button = event.submitter;
        button.disabled = true;
        try {
            const created = await api(`/api/operations/spaces/${state.selectedId}/benchmark-accounts`, {
                method: "POST",
                body: JSON.stringify({ url: el("operationBenchmarkUrl").value.trim(), nickname: el("operationBenchmarkName").value.trim(), note: "" }),
            });
            event.currentTarget.reset();
            await loadDetail();
            const result = await api(`/api/operations/spaces/${state.selectedId}/benchmark-accounts/${created.account.id}/sync`, { method: "POST" });
            showToast("已添加对标账号，正在筛选它的低粉爆款笔记");
            await pollSyncJob(result.job.id);
        } finally {
            button.disabled = false;
        }
    }

    async function syncAccount(accountId, button) {
        button.disabled = true;
        try {
            const result = await api(`/api/operations/spaces/${state.selectedId}/benchmark-accounts/${accountId}/sync`, { method: "POST" });
            showToast("已开始同步对标账号");
            await pollSyncJob(result.job.id);
        } catch (error) {
            showToast(error.message, true);
        } finally {
            button.disabled = false;
        }
    }

    async function pollSyncJob(jobId) {
        for (let attempt = 0; attempt < 180; attempt += 1) {
            const result = await api(`/api/operations/sync-jobs/${jobId}`);
            const job = result.job;
            el("operationDiscoveryState").textContent = `${job.phase}${job.total ? ` · ${job.completed}/${job.total}` : ""}`;
            if (!["pending", "processing"].includes(job.state)) {
                await loadDetail();
                if (job.state === "success") showToast(job.phase);
                else showToast(job.error || "账号同步失败", true);
                return;
            }
            await new Promise((resolve) => setTimeout(resolve, 1500));
        }
        showToast("账号仍在后台同步，稍后会自动刷新", true);
    }

    async function deleteAccount(account) {
        if (!window.confirm(`确定移除对标账号“${account.nickname || account.platform_user_id}”？已经同步进笔记池的笔记会保留。`)) return;
        await api(`/api/operations/spaces/${state.selectedId}/benchmark-accounts/${account.id}`, { method: "DELETE" });
        await loadDetail();
    }

    async function addNote(event) {
        event.preventDefault();
        const button = event.submitter;
        button.disabled = true;
        try {
            await api(`/api/operations/spaces/${state.selectedId}/benchmark-notes`, {
                method: "POST",
                body: JSON.stringify({ content: el("operationNoteUrl").value.trim() }),
            });
            event.currentTarget.reset();
            await loadDetail();
            showToast("对标正文、图片、结构数据和挂载商品已加入当前运营账号");
        } finally {
            button.disabled = false;
        }
    }

    async function deleteNote(note) {
        if (!window.confirm(`确定从当前账号空间移除“${note.title || "这篇笔记"}”？`)) return;
        await api(`/api/operations/spaces/${state.selectedId}/notes/${note.id}`, { method: "DELETE" });
        await loadDetail();
    }

    async function discover() {
        const button = el("operationDiscover");
        button.disabled = true;
        el("operationDiscoveryState").textContent = "正在提交同品爆款采集";
        try {
            const result = await api(`/api/operations/spaces/${state.selectedId}/discover`, {
                method: "POST",
                body: JSON.stringify({
                    product_id: el("operationGenerateProduct").value || "",
                    keywords: splitKeywords(el("operationDiscoveryKeywords").value),
                    hours: 72, limit: 20,
                }),
            });
            state.discoveryRunId = result.run.id;
            el("operationDiscoveryState").textContent = `正在按“${result.keywords.join("、")}”采集`;
            await pollDiscovery(result.run.id);
        } catch (error) {
            el("operationDiscoveryState").textContent = error.message;
            showToast(error.message, true);
        } finally {
            button.disabled = false;
        }
    }

    async function pollDiscovery(runId) {
        for (let attempt = 0; attempt < 240; attempt += 1) {
            const run = await api(`/api/viral/runs/${runId}`);
            el("operationDiscoveryState").textContent = `${run.message || "采集中"} · 已核验 ${run.scanned || 0} / 候选 ${run.candidates || 0}`;
            if (!["pending", "processing"].includes(run.state)) {
                if (!["success", "partial"].includes(run.state)) throw new Error(run.message || "同品爆款采集失败");
                const imported = await api(`/api/operations/spaces/${state.selectedId}/discover/${runId}/import`, { method: "POST" });
                el("operationDiscoveryState").textContent = `已加入 ${imported.imported} 篇同品爆款笔记`;
                await loadDetail();
                showToast(`同品爆款池已更新：${imported.imported} 篇`);
                return;
            }
            await new Promise((resolve) => setTimeout(resolve, 1800));
        }
        throw new Error("采集仍在后台运行，请稍后刷新")
    }

    async function importProduct(event) {
        event.preventDefault();
        const index = Number(el("operationCollectedProduct").value);
        const product = state.productCatalog[index];
        if (!product) { showToast("请选择一个已采集商品", true); return; }
        const button = event.submitter;
        button.disabled = true;
        try {
            await api(`/api/operations/spaces/${state.selectedId}/products`, {
                method: "POST",
                body: JSON.stringify({
                    source_platform: product.platform,
                    source_product_id: String(product.product_id || ""),
                    title: product.title || "",
                    url: product.url || "",
                    description: product.description || product.subtitle || "",
                    selling_points: el("operationImportedSellingPoints").value.trim(),
                    target_audience: "", category: "", keywords: [], image_paths: [], image_urls: [], video_paths: [],
                }),
            });
            event.currentTarget.reset();
            await loadDetail();
            showToast("商品原图与视频已复制到当前账号空间");
        } finally {
            button.disabled = false;
        }
    }

    async function addManualProduct(event) {
        event.preventDefault();
        await api(`/api/operations/spaces/${state.selectedId}/products`, {
            method: "POST",
            body: JSON.stringify({
                source_platform: "manual", source_product_id: "",
                title: el("operationManualProductName").value.trim(),
                url: el("operationManualProductUrl").value.trim(),
                description: el("operationManualProductDescription").value.trim(),
                selling_points: el("operationManualProductSelling").value.trim(),
                target_audience: "", category: "", keywords: [], image_paths: [], image_urls: [], video_paths: [],
            }),
        });
        event.currentTarget.reset();
        await loadDetail();
        showToast("商品卡已保存；生成图文前还需要从商品素材库导入原图");
    }

    async function deleteProduct(product) {
        if (!window.confirm(`确定从当前账号空间移除商品“${product.title}”？已复制的本地原图不会删除。`)) return;
        await api(`/api/operations/spaces/${state.selectedId}/products/${product.id}`, { method: "DELETE" });
        await loadDetail();
    }

    async function openProductRemix(product) {
        if (!product.video_paths?.length) {
            showToast("这个商品还没有本地视频素材", true);
            return;
        }
        if (!window.videoRemix?.open) {
            showToast("视频混剪器仍在加载，请稍后再试", true);
            return;
        }
        await window.videoRemix.open(product.video_paths.map((path, index) => ({
            path,
            name: `${product.title} · 素材 ${index + 1}`,
        })));
    }

    function syncGenerateMode() {
        const type = document.querySelector('input[name="operationContentType"]:checked')?.value || "graphic";
        const graphic = type === "graphic";
        el("operationArticleCount").disabled = !graphic;
        el("operationImageCount").disabled = !graphic;
        el("operationImageStyle").disabled = !graphic;
        el("operationGenerateForm").querySelector(".operation-generate-button").lastChild.textContent = graphic ? "一键生成对标图文" : "一键生成脚本并混剪";
    }

    function syncCopywritingMode() {
        const mode = el("operationCopywritingMode").value;
        if (mode === "4" && el("operationArticleCount").value === "1") {
            el("operationArticleCount").value = "3";
        }
        if (mode === "5") el("operationArticleCount").value = "1";
    }

    async function generate(event) {
        event.preventDefault();
        const references = [...el("operationReferencePicker").querySelectorAll("input:checked")].map((input) => input.value);
        if (!references.length) { showToast("请明确选择至少一篇本次对标笔记", true); return; }
        const productId = el("operationGenerateProduct").value;
        if (!productId) { showToast("请选择当前商品", true); return; }
        const type = document.querySelector('input[name="operationContentType"]:checked')?.value || "graphic";
        const button = event.submitter;
        button.disabled = true;
        try {
            const result = await api(`/api/operations/spaces/${state.selectedId}/generate`, {
                method: "POST",
                body: JSON.stringify({
                    product_id: productId,
                    content_type: type,
                    reference_note_ids: references,
                    copywriting_mode: el("operationCopywritingMode").value,
                    article_count: Number(el("operationArticleCount").value),
                    image_count: Number(el("operationImageCount").value),
                    style: el("operationImageStyle").value,
                    instructions: el("operationGenerateInstructions").value.trim(),
                }),
            });
            el("operationGenerateInstructions").value = "";
            await loadDetail();
            showToast(type === "graphic" ? `已开始生成 ${result.rewrite.article_count} 篇图文` : "视频脚本、分镜与混剪初稿已生成");
        } catch (error) {
            showToast(error.message, true);
        } finally {
            button.disabled = false;
        }
    }

    function activateTab(tabName) {
        const panel = document.querySelector(`[data-operation-panel="${tabName}"]`);
        if (!panel) return;
        state.activeTab = tabName;
        el("operationDetail").querySelectorAll("video").forEach(video => video.pause());
        document.querySelectorAll("[data-operation-tab]").forEach((button) => {
            const active = button.dataset.operationTab === tabName;
            button.classList.toggle("active", active);
            button.setAttribute("aria-selected", String(active));
            button.tabIndex = active ? 0 : -1;
        });
        document.querySelectorAll("[data-operation-panel]").forEach((panel) => {
            const active = panel.dataset.operationPanel === tabName;
            panel.hidden = !active;
            panel.classList.toggle("active", active);
        });
    }

    async function start() {
        if (!bridge.currentUser()) return;
        if (!state.initialized) {
            state.initialized = true;
            await Promise.all([loadSpaces({ preserve: false }), loadProductCatalog()]);
        } else {
            await loadSpaces();
        }
        if (!state.timer) state.timer = setInterval(() => {
            if (document.hidden || !bridge.currentUser() || !window.location.hash.startsWith("#operations")) return;
            loadDetail().catch(() => {});
        }, 5000);
    }

    function stop() {
        clearInterval(state.timer);
        state.timer = null;
        state.initialized = false;
        state.spaces = [];
        state.selectedId = "";
        state.detail = null;
        state.profileDirty = false;
    }

    el("operationNewSpace").addEventListener("click", openSpaceDialog);
    el("operationEmptyCreate").addEventListener("click", openSpaceDialog);
    el("operationCloseSpaceDialog").addEventListener("click", () => el("operationSpaceDialog").close());
    el("operationCancelSpace").addEventListener("click", () => el("operationSpaceDialog").close());
    el("operationCreateSpaceForm").addEventListener("submit", (event) => createSpace(event).catch((error) => showToast(error.message, true)));
    el("operationSpaceSettings").addEventListener("submit", (event) => saveSpace(event).catch((error) => showToast(error.message, true)));
    el("operationSpaceSettings").addEventListener("input", () => { state.profileDirty = true; });
    el("operationAnalyzeProfile").addEventListener("click", analyzeProfile);
    el("operationDeleteSpace").addEventListener("click", () => deleteSpace().catch((error) => showToast(error.message, true)));
    el("operationAccountForm").addEventListener("submit", (event) => addAccount(event).catch((error) => showToast(error.message, true)));
    el("operationNoteForm").addEventListener("submit", (event) => addNote(event).catch((error) => showToast(error.message, true)));
    el("operationDiscover").addEventListener("click", discover);
    el("operationProductImportForm").addEventListener("submit", (event) => importProduct(event).catch((error) => showToast(error.message, true)));
    el("operationProductManualForm").addEventListener("submit", (event) => addManualProduct(event).catch((error) => showToast(error.message, true)));
    el("operationGenerateForm").addEventListener("submit", generate);
    document.querySelectorAll("[data-operation-tab]").forEach((button) => button.addEventListener("click", () => activateTab(button.dataset.operationTab)));
    const tabs = [...document.querySelectorAll("[data-operation-tab]")];
    tabs.forEach((button, index) => {
        const panel = document.querySelector(`[data-operation-panel="${button.dataset.operationTab}"]`);
        panel.id ||= `operationPanel-${button.dataset.operationTab}`;
        panel.setAttribute("role", "tabpanel");
        panel.setAttribute("aria-labelledby", button.id);
        button.setAttribute("aria-controls", panel.id);
        button.addEventListener("keydown", event => {
            if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
            event.preventDefault();
            const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
            activateTab(tabs[next].dataset.operationTab); tabs[next].focus();
        });
    });
    activateTab("factory");
    document.querySelectorAll('input[name="operationContentType"]').forEach((input) => input.addEventListener("change", syncGenerateMode));
    el("operationCopywritingMode").addEventListener("change", syncCopywritingMode);
    window.addEventListener("hashchange", () => {
        if (window.location.hash.startsWith("#operations") && bridge.currentUser()) start().catch((error) => showToast(error.message, true));
    });
    syncGenerateMode();
    syncCopywritingMode();
    window.operationWorkspace = { start, stop };
})();
