(() => {
    const bridge = window.operationBridge;
    const host = document.getElementById("accountFactory");
    if (!bridge || !host) return;
    const { api, showToast } = bridge;
    const escape = value => String(value ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
    const roles = { product_image: "商品原图", product_video: "商品演示视频", reference_image: "爆款参考图", reference_video: "爆款参考视频", archive_image: "历史图文配图", archive_video: "历史视频成片" };
    const statuses = { draft: "文案草稿", queued: "排队中", running: "制作中", ready: "待发布", published: "已发布", failed: "需处理", interrupted: "待继续", needs_review: "待检查", retry_wait: "等待自动重试" };
    const media = path => "/media/" + path.split("/").map(encodeURIComponent).join("/");
    let space = "", detail = null, data = null, loading = false, timer = null, loadSequence = 0;
    let runPage = 1, runPageSize = 10, loadedRunQuery = "", searchTimer = null;
    const node = id => host.querySelector(`#${id}`);
    const base = () => `/api/operations/spaces/${space}/factory`;
    const send = (path, method, body) => api(path, { method, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
    const isPublished = run => run.is_published ?? Boolean(run.publication || run.published_url || run.state === "published");
    function runQuery() {
        const query = new URLSearchParams({ page: runPage, page_size: runPageSize,
            status: node("factoryStatusFilter").value, content_filter: node("factoryContentFilter").value,
            completion: node("factoryCompletionFilter").value, search: node("factorySearch").value.trim() });
        if (node("factoryRunDate").value) query.set("day", node("factoryRunDate").value);
        return query.toString();
    }
    function changeRunFilters() {
        clearTimeout(searchTimer); runPage = 1; runsFingerprint = "";
        act(() => load(false, true));
    }
    const metricNames = { impressions: "曝光", views: "观看 / 阅读", likes: "点赞", saves: "收藏", comments: "评论", product_clicks: "商品点击", orders: "本篇归因订单" };
    const feedbackKinds = { "": "整体感受", copy: "文字不自然", cover: "封面不吸引", media: "选图 / 动作不合适", alignment: "文案与画面对不上", approved: "这个方向可以继续" };
    function alignmentPanel(run) {
        const brief = run.plan.creative_brief, review = run.plan.alignment_review;
        const state = review ? (review.passed ? "已核对" : "需调整") : "待核对";
        return `<details class="factory-alignment"><summary>本篇吸引点与画面对应 · ${state}</summary>
          ${brief ? `<p><b>想打动谁：</b>${escape(brief.audience)} · ${escape(brief.desire)}</p><p><b>为什么点开：</b>${escape(brief.promise)}</p><p><b>第一眼看到：</b>${escape(brief.first_frame)}</p><p><b>这次测试：</b>${escape(brief.changed_variable)}</p>` : ""}
          ${review ? `<div class="factory-alignment-checks">${(review.checks || []).map(c => `<p><b>${{title:"标题承接",body:"正文对应",sequence:"内容递进",appeal:"吸引理由"}[c.target] || escape(c.target)} · ${c.supported ? "通过" : "需调整"}</b><br>${escape(c.supported ? c.evidence : c.suggestion)}</p>`).join("")}</div><ol>${(review.observations || []).map(o => `<li><b>${String(o.index + 1).padStart(2,"0")} · ${o.contributes ? "对应" : "需调整"}</b> ${escape(o.observed)}<br><span>${escape(o.reason)}</span></li>`).join("")}</ol>` : `<p>完成媒体后核对标题、正文和实际动作；历史成品可点击下方按钮重新检查。</p>`}
          ${run.plan.copy_locked ? `<p>已认可的标题和正文保持锁定，检查问题用于调整配图与动作。</p>` : ""}
          ${run.plan.copy_revisions?.length ? `<p>已按实际画面修正文案 ${run.plan.copy_revisions.length} 次，修改记录会随发布数据用于后续复盘。</p>` : ""}
        </details>`;
    }
    const today = () => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());

    let runsFingerprint = "", assetsFingerprint = "";
    const expandedRuns = new Set();
    function mount() {
        runPage = 1; runPageSize = 10; loadedRunQuery = ""; clearTimeout(searchTimer);
        runsFingerprint = "";
        assetsFingerprint = "";
        expandedRuns.clear();
        host.innerHTML = `<div class="factory-topbar"><div><span class="factory-eyebrow">日常运营</span><h2 id="factoryViewTitle">发布内容</h2><p id="factoryViewDescription">先选日期，再查看今天可以发布的图文和混剪。</p></div><span id="factoryState" class="visual-context">读取中</span></div>
          <div class="factory-section-tabs" role="tablist" aria-label="内容工作台区域">
            <button id="factoryTab-workbench" role="tab" type="button" data-factory-nav="workbench" class="active" aria-selected="true">发布内容</button>
            <button id="factoryTab-assets" role="tab" type="button" data-factory-nav="assets" aria-selected="false">素材与参考库 <span id="factoryAssetCount"></span></button>
            <button id="factoryTab-learning" role="tab" type="button" data-factory-nav="learning" aria-selected="false">数据复盘</button>
            <button id="factoryTab-plan" role="tab" type="button" data-factory-nav="plan" aria-selected="false">每日计划</button>
          </div>
          <section id="factoryView-plan" class="factory-view" data-factory-view="plan" hidden>
            <div class="factory-area-heading"><h3>自动制作设置</h3><p id="factoryRecipeSummary"></p></div>
            <div id="factoryPlanPanel" class="factory-plan-panel"><form id="factorySchedule" class="factory-schedule">
            <label class="select-field"><span>本账号商品</span><select id="factoryProduct" required></select></label>
            <label class="select-field"><span>每日 Live 图文</span><select id="factoryGraphics">${Array.from({length:11}, (_,n) => `<option>${n}</option>`).join("")}</select></label>
            <label class="select-field"><span>每日视频</span><select id="factoryVideos">${Array.from({length:11}, (_,n) => `<option>${n}</option>`).join("")}</select></label>
            <label class="select-field"><span>每篇 Live 图数</span><select id="factoryImages">${[1,2,3,4,5,6].map(n => `<option>${n}</option>`).join("")}</select></label>
            <label class="select-field"><span>每篇图文组合</span><select id="factoryRecipe"><option value="auto">自由搭配</option><option value="text_cover_live5">6 张：文字首图＋5 张 Live</option><option value="ai2_video4">6 张：2 张场景＋4 张混剪</option><option value="video6_real_action">6 张：全部真实动作 Live</option></select></label><label class="text-field"><span>北京时间 / 点</span><input id="factoryHour" type="number" min="0" max="23" value="9" required></label>
            <label class="text-field"><span>开始日期</span><input id="factoryStart" type="date" required></label>
            <label class="factory-enable"><input id="factoryEnabled" type="checkbox">每天自动制作</label>
            <button class="button secondary" type="submit">保存每日计划</button>
            <button id="factoryToday" class="button primary" type="button">制作今日内容</button>
          </form></div>
            <p class="factory-help">保存后按北京时间自动安排任务。当天重复制作会复用已有任务；运行期间请保持服务开启。</p>
          </section>
          <section id="factoryView-assets" class="factory-view" data-factory-view="assets" hidden>
            <div class="factory-area-heading"><h3>原素材与参考库</h3><p>保存用于制作的商品原图、演示视频和参考案例。</p></div>
            <div id="factoryAssetsPanel" class="factory-assets-panel">            <div class="factory-toolbar"><select id="factoryRole" aria-label="导入素材类别">${Object.entries(roles).map(([key,label]) => `<option value="${key}">${label}</option>`).join("")}</select>
              <button id="factoryUpload" class="button secondary" type="button">上传图片 / 视频</button><input id="factoryFiles" type="file" accept=".jpg,.jpeg,.png,.webp,.mp4,.mov,.m4v" multiple hidden>
              <select id="factoryFilter" aria-label="筛选素材"><option value="">全部类别</option>${Object.entries(roles).map(([key,label]) => `<option value="${key}">${label}</option>`).join("")}</select>
              <button id="factoryImportProduct" class="button secondary" type="button">整理当前商品已有素材</button></div>
            <form id="factoryReferenceForm" class="factory-toolbar"><input id="factoryReference" aria-label="爆款图文或视频链接" placeholder="粘贴小红书、抖音或快手视频分享链接" required maxlength="5000"><button class="button secondary" type="submit">采集并归入当前商品</button></form>
            <p class="factory-hint">支持小红书、抖音和快手。视频会进入同一个参考素材池，由 AI 分析镜头、卖点和节奏后参与混剪；相同文件自动去重。</p>
            <div id="factoryAssets" class="factory-assets"></div>
          </div>
          </section>
          <section id="factoryView-learning" class="factory-view" data-factory-view="learning" hidden>
            <div class="factory-area-heading"><h3>发布反馈与素材使用</h3><p>登记实际发布后，按日期记录观看、点赞、收藏和本篇归因订单。</p></div>
            <div id="factoryLearningSummary" class="factory-learning-summary" aria-live="polite"></div>
            <div class="factory-feedback-shortcuts"><button type="button" class="button secondary" id="factoryPublishedShortcut">查看已发布内容</button><button type="button" class="button secondary" id="factoryMetricsShortcut">今天待记数据</button></div>
            <p class="factory-help">在内容卡片中登记发布、填写每日数据和创作评分。未填写表示未知，店铺总订单需先核对归因；创作评分与真实运营数据分别保存。</p>
            <section id="factoryMaterialPanel" class="factory-material-panel"><h4>视频素材使用情况</h4><div id="factoryMaterialUsage" class="factory-hint"></div></section>
          </section>
          <section id="factoryView-workbench" class="factory-view" data-factory-view="workbench">
            <div class="factory-workbench-toolbar"><div class="factory-date-toolbar"><label for="factoryRunDate">内容日期<input id="factoryRunDate" type="date" aria-label="内容日期"></label><button id="factoryDateToday" class="button secondary" type="button">今天</button><button id="factoryDateAll" class="button secondary" type="button">全部日期</button></div><button id="factoryRefresh" type="button" class="button secondary">刷新内容</button></div>
            <div id="factoryOverview" class="factory-overview" aria-label="所选日期内容概览"></div>
            <div class="factory-filter-panel"><div class="factory-content-switch" role="group" aria-label="内容类型"><button type="button" data-content-type="" aria-pressed="true" class="active">全部内容</button><button type="button" data-content-type="graphic" aria-pressed="false">图文 / LIVE</button><button type="button" data-content-type="video" aria-pressed="false">视频混剪</button></div>
              <div class="factory-filter-controls"><label>发布状态<select id="factoryStatusFilter"><option value="">全部状态</option><option value="unpublished">未发布</option><option value="published">已发布</option><option value="ready">待发布成品</option><option value="working">制作中 / 待处理</option><option value="draft">文案草稿</option></select></label><label class="factory-search">搜索内容<input id="factorySearch" type="search" placeholder="搜索标题或正文" maxlength="200"></label></div>
              <select id="factoryContentFilter" aria-label="筛选账号内容" hidden><option value="">全部内容</option><option value="draft">文案草稿</option><option value="graphic">图文</option><option value="video">视频</option><option value="published">已发布</option><option value="awaiting_metrics">今天待记数据</option></select>
              <select id="factoryCompletionFilter" aria-label="制作状态" hidden><option value="">全部制作状态</option><option value="finished">已完成成品</option><option value="unfinished">待完成 / 待检查</option></select>
            </div>
            <div class="factory-results-heading"><span id="factoryRunCount" aria-live="polite"></span><button id="factoryClearFilters" class="text-action" type="button">重置筛选</button></div>
            <div id="factoryRuns" class="factory-runs"></div>
            <nav id="factoryPagination" class="factory-pagination" aria-label="内容分页">
              <label>每页 <select id="factoryPageSize" aria-label="每页条数"><option value="10">10 条</option><option value="20">20 条</option><option value="50">50 条</option></select></label>
              <button id="factoryPreviousPage" type="button" class="button secondary">上一页</button><span id="factoryPageInfo" aria-live="polite">第 1 / 1 页</span><button id="factoryNextPage" type="button" class="button secondary">下一页</button>
              <form id="factoryPageJump"><label>跳至 <input id="factoryPageNumber" type="number" min="1" value="1" aria-label="跳转页码" required> 页</label><button class="button secondary" type="submit">跳转</button></form>
            </nav>
          </section>`;
        node("factorySchedule").addEventListener("submit", saveSchedule);
        node("factoryToday").addEventListener("click", () => act(async () => { await saveScheduleValue(); await send(base() + "/today", "POST"); showToast("今日任务已安排，重复点击不会重复制作"); await load(); }));
        node("factoryUpload").addEventListener("click", () => node("factoryFiles").click());
        node("factoryFiles").addEventListener("change", upload);
        node("factoryFilter").addEventListener("change", renderAssets);
        node("factoryImportProduct").addEventListener("click", importProduct);
        node("factoryRefresh").addEventListener("click", () => act(load));
        node("factoryContentFilter").addEventListener("change", changeRunFilters);
        node("factoryCompletionFilter").addEventListener("change", changeRunFilters);
        node("factoryStatusFilter").addEventListener("change", changeRunFilters);
        node("factorySearch").addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(changeRunFilters, 250); });
        node("factoryPageSize").addEventListener("change", () => { runPageSize = Number(node("factoryPageSize").value); changeRunFilters(); });
        const turnPage = page => { runPage = Math.max(1, page); act(() => load(false, true)); };
        node("factoryPreviousPage").addEventListener("click", () => turnPage(runPage - 1));
        node("factoryNextPage").addEventListener("click", () => turnPage(runPage + 1));
        node("factoryPageJump").addEventListener("submit", event => { event.preventDefault(); turnPage(Number(node("factoryPageNumber").value)); });
        node("factoryClearFilters").addEventListener("click", () => {
            ["factoryContentFilter", "factoryCompletionFilter", "factoryStatusFilter", "factorySearch"].forEach(id => { node(id).value = ""; }); changeRunFilters();
        });
        host.querySelectorAll("[data-content-type]").forEach(button => button.addEventListener("click", () => {
            node("factoryContentFilter").value = button.dataset.contentType; changeRunFilters();
        }));
        const tabs = [...host.querySelectorAll("[data-factory-nav]")];
        tabs.forEach((button, index) => {
            const panel = node(`factoryView-${button.dataset.factoryNav}`);
            panel.setAttribute("role", "tabpanel"); panel.setAttribute("aria-labelledby", button.id);
            button.setAttribute("aria-controls", panel.id);
            button.addEventListener("click", () => focusFactorySection(button.dataset.factoryNav));
            button.addEventListener("keydown", event => {
                if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
                event.preventDefault();
                const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length-1 : (index+(event.key === "ArrowRight" ? 1 : -1)+tabs.length)%tabs.length;
                focusFactorySection(tabs[next].dataset.factoryNav); tabs[next].focus();
            });
        });
        focusFactorySection("workbench");
        const openFeedback = (filter) => {
            focusFactorySection("workbench"); node("factoryRunDate").value = "";
            node("factoryContentFilter").value = filter; node("factoryStatusFilter").value = "";
            node("factoryCompletionFilter").value = ""; node("factorySearch").value = "";
            changeRunFilters();
        };
        node("factoryPublishedShortcut").addEventListener("click", () => openFeedback("published"));
        node("factoryMetricsShortcut").addEventListener("click", () => openFeedback("awaiting_metrics"));
        node("factoryRunDate").value = today();
        const changeDate = () => {
            runPage = 1;
            runsFingerprint = "";
            node("factoryRuns").innerHTML = '<p class="factory-hint">正在读取对应日期的内容…</p>';
            node("factoryRunCount").textContent = "正在读取…";
            act(() => load(false, true));
        };
        node("factoryRunDate").addEventListener("change", changeDate);
        node("factoryDateToday").addEventListener("click", () => { node("factoryRunDate").value = today(); changeDate(); });
        node("factoryDateAll").addEventListener("click", () => { node("factoryRunDate").value = ""; changeDate(); });
        node("factoryReferenceForm").addEventListener("submit", event => {
            event.preventDefault(); const button = event.submitter; button.disabled = true;
            act(async () => {
                try {
                    if (!node("factoryProduct").value) throw new Error("请先选择商品");
                    const result = await send(base() + "/references", "POST", { product_id: node("factoryProduct").value, content: node("factoryReference").value.trim() });
                    node("factoryReference").value = ""; await load();
                    showToast(result.media_errors?.length ? "正文已保存，部分媒体待补充，可直接上传" : `正文和${result.assets.length}份媒体已归档`);
                } finally { button.disabled = false; }
            });
        });
        node("factoryGraphics").value = "1";
        node("factoryVideos").value = "1";
        node("factoryImages").value = "6";
        node("factoryRecipe").value = "video6_real_action";
        node("factoryRecipe").addEventListener("change", () => { if (["ai2_video4", "video6_real_action", "text_cover_live5"].includes(node("factoryRecipe").value)) node("factoryImages").value = "6"; });
        node("factoryImages").addEventListener("change", () => { if (node("factoryImages").value !== "6") node("factoryRecipe").value = "auto"; });
        node("factoryStart").value = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
        productOptions();
    }

    function focusFactorySection(section) {
        if (!node(`factoryView-${section}`)) return;
        host.querySelectorAll("video").forEach(video => video.pause());
        const labels = { workbench: ["发布内容", "先选日期，再查看今天可以发布的图文和混剪。"], assets: ["素材与参考库", "商品原图、原视频和参考案例集中管理。"], learning: ["数据复盘", "记录实际发布表现，查看原片使用情况。"], plan: ["每日计划", "设置当前账号的制作数量、图片组合和执行时间。"] };
        node("factoryViewTitle").textContent = labels[section][0];
        node("factoryViewDescription").textContent = labels[section][1];
        host.querySelectorAll("[data-factory-view]").forEach(panel => { panel.hidden = panel.dataset.factoryView !== section; });
        host.querySelectorAll("[data-factory-nav]").forEach(button => {
            const active = button.dataset.factoryNav === section;
            button.classList.toggle("active", active); button.setAttribute("aria-selected", String(active)); button.tabIndex = active ? 0 : -1;
        });
    }

    function productOptions() {
        const select = node("factoryProduct");
        if (!select) return;
        const current = select.value;
        select.innerHTML = (detail?.products || []).map(p => `<option value="${escape(p.id)}">${escape(p.title)}</option>`).join("");
        if ((detail?.products || []).some(p => p.id === current)) select.value = current;
    }
    async function act(action) {
        try { await action(); } catch (error) { showToast(error.message, true); }
    }
    async function saveScheduleValue() {
        if (!node("factoryProduct").value) throw new Error("先给账号添加一个商品");
        await send(base() + "/schedule", "PUT", { product_id: node("factoryProduct").value, enabled: node("factoryEnabled").checked,
            graphic_count: Number(node("factoryGraphics").value), video_count: Number(node("factoryVideos").value),
            image_count: Number(node("factoryImages").value), graphic_recipe: node("factoryRecipe").value, hour: Number(node("factoryHour").value), start_date: node("factoryStart").value });
    }
    function saveSchedule(event) { event.preventDefault(); act(async () => { await saveScheduleValue(); showToast("每日计划已保存"); await load(); }); }
    async function load(initial = false, force = false) {
        if (!space || (loading && !initial && !force) || !bridge.currentUser()) return;
        loading = true;
        const requested = space;
        const requestedDay = node("factoryRunDate").value;
        const requestedQuery = runQuery();
        const sequence = ++loadSequence;
        node("factoryRuns").setAttribute("aria-busy", "true");
        ["factoryPreviousPage", "factoryNextPage"].forEach(id => { node(id).disabled = true; });
        try {
            const result = await api(`/api/operations/spaces/${requested}/factory?${requestedQuery}`);
            if (space !== requested || sequence !== loadSequence || runQuery() !== requestedQuery) return;
            data = result;
            runPage = result.pagination.page; loadedRunQuery = runQuery();
            if (initial && data.schedule) {
                const schedule = data.schedule;
                node("factoryProduct").value = schedule.product_id;
                node("factoryGraphics").value = schedule.graphic_count;
                node("factoryVideos").value = schedule.video_count;
                node("factoryImages").value = schedule.image_count;
                node("factoryRecipe").value = schedule.graphic_recipe || "auto";
                node("factoryHour").value = schedule.hour;
                node("factoryStart").value = schedule.start_date;
                node("factoryEnabled").checked = Boolean(schedule.enabled);
            }
            node("factoryState").textContent = data.schedule?.enabled ? `每天 ${data.schedule.hour}:00 · ${data.scheduler_running ? "运行中" : "服务未运行"}` : "手动制作";
            node("factoryRecipeSummary").textContent = data.schedule ? `· 每日 ${data.schedule.graphic_count} 篇图文＋${data.schedule.video_count} 条混剪 · ${data.schedule.graphic_recipe === "ai2_video4" ? "每篇 2 场景＋4 混剪" : data.schedule.graphic_recipe === "video6_real_action" ? "每篇 6 张真实动作 Live" : `每篇 ${data.schedule.image_count} 张`}` : "";
            renderAssets(); renderRuns(); renderLearning();
        } finally { if (sequence === loadSequence) { loading = false; node("factoryRuns").setAttribute("aria-busy", "false"); renderPagination(); } }
    }
    function renderPagination() {
        const page = data?.pagination || { page: 1, total_pages: 1, total: 0 };
        node("factoryPageInfo").textContent = `第 ${page.page} / ${page.total_pages} 页 · 共 ${page.total} 条`;
        node("factoryPageNumber").max = page.total_pages;
        node("factoryPageNumber").value = page.page;
        node("factoryPreviousPage").disabled = loading || page.page <= 1;
        node("factoryNextPage").disabled = loading || page.page >= page.total_pages;
    }
    function renderLearning() {
        const reports = Object.values(data?.learning || {});
        const published = reports.reduce((n, r) => n + r.published_count, 0);
        const measured = reports.reduce((n, r) => n + r.measured_count, 0);
        const daily = (data?.days || []).find(d => d.day === today());
        const startsLater = data?.schedule?.start_date > today();
        const target = startsLater ? 0 : Number(data?.schedule?.graphic_count || 0) + Number(data?.schedule?.video_count || 0);
        const ready = daily?.scheduled_ready || 0;
        node("factoryLearningSummary").textContent = `${startsLater ? `新计划从 ${data.schedule.start_date} 开始。` : ""}今日自动计划 ${target} 条 · 自动任务成品 ${ready} 条 · 距目标 ${Math.max(0, target-ready)} 条。近期反馈记录中已发布 ${published} 篇，已记每日数据 ${measured} 篇。请按后台累计数填写；未填表示未知，订单仅填写能归因到本篇的数量。`;
        const usage = data?.material_usage || [];
        node("factoryMaterialUsage").innerHTML = usage.length ? usage.map(u => `<p>${escape(u.title)}：原片 ${Number(u.duration).toFixed(1)} 秒，历史覆盖 ${Number(u.used_seconds).toFixed(1)} 秒，未覆盖 ${Number(u.unused_seconds).toFixed(1)} 秒，开场使用 ${u.opening_count} 次。</p>`).join("") + "<p>未覆盖时长不等于可用镜头。制作优先选择少用素材；同一动作需要新的讲解重点，重复检查仍会拦截高度相似的成片。</p>" : "还没有商品或参考视频。";
    }
    function publicationPanel(run) {
        const pub = run.publication;
        const snapshots = run.metric_snapshots || [];
        const current = snapshots.find(s => s.observed_on === today());
        return `<details class="factory-publication"><summary>${pub ? `${isPublished(run) ? "已发布" : "历史发布登记 · 当前未发布"} · ${escape(pub.published_on)}` : isPublished(run) ? "已发布 · 补充实际发布日期" : "登记实际发布"}</summary>
          <form data-publication="${run.id}" class="factory-feedback">
            <label>实际发布日期<input name="published_on" type="date" value="${escape(pub?.published_on || today())}" max="${today()}" required></label>
            <label>发布链接（可后补）<input name="published_url" type="url" value="${escape(pub?.published_url || run.published_url || "")}" maxlength="2048"></label>
            <label>实际发布标题<input name="actual_title" value="${escape(pub?.actual_title || run.plan.title)}" maxlength="120"></label>
            <label class="factory-wide">实际发布正文<textarea name="actual_body" maxlength="8000" rows="4">${escape(pub?.actual_body || run.plan.body)}</textarea></label>
            <button class="button secondary" type="submit">保存发布登记并标为已发布</button></form>
          <p class="factory-hint">只登记实际已发的内容；在外部制作媒体后发布的文案也可以登记，原制作状态保持独立。</p></details>
          ${pub ? `<details class="factory-metrics"><summary>每日数据 · ${snapshots.length} 个日期${current ? " · 今天已记录" : " · 今天待记录"}</summary>
            ${isPublished(run) ? `<form data-metrics="${run.id}" class="factory-feedback">
              <label>数据日期<input name="observed_on" type="date" min="${escape(pub.published_on)}" max="${today()}" value="${today()}" required></label>
              ${Object.entries(metricNames).map(([key,label]) => `<label>${label}<input name="${key}" type="number" min="0" max="10000000000" step="1" value="${current?.metrics[key] ?? ""}"></label>`).join("")}
              <button class="button secondary" type="submit">保存当日累计数据</button></form>` : `<p>当前标为未发布，历史数据保留。重新标为已发布后可继续登记。</p>`}
            <p class="factory-hint">填写截至该日的后台累计值。同一天可补充或更正，不覆盖其他日期；店铺总订单请先核对归因。相邻记录的差额可能跨多天。</p>
            <div class="factory-metric-history">${snapshots.map(s => `<p><strong>${escape(s.observed_on)}</strong> · ${Object.entries(s.metrics).map(([k,v]) => `${metricNames[k] || escape(k)} ${v}`).join(" · ")}${s.previous_on ? `<br>较 ${escape(s.previous_on)}：${Object.entries(s.change_since_previous).map(([k,v]) => `${metricNames[k] || escape(k)} ${v >= 0 ? "+" : ""}${v}`).join(" · ") || "暂无同口径数据"}` : ""}${s.has_correction ? "（累计值减少，请核对更正或统计口径）" : ""}</p>`).reverse().join("") || "尚无记录"}</div></details>` : ""}`;
    }
    function publicationToggle(run) {
        const checked = isPublished(run);
        if (!checked && !["draft", "ready", "published", "needs_review"].includes(run.state)) return "";
        return `<label class="factory-published-toggle ${checked ? "is-published" : "is-unpublished"}" data-published-control="${escape(run.id)}" title="点击修改发布状态"><input type="checkbox" aria-label="发布状态：${checked ? "已发布" : "未发布"}，点击切换" data-published-toggle="${escape(run.id)}" ${checked ? "checked" : ""}><span>${checked ? "已发布" : "未发布"}</span></label>`;
    }
    function renderAssets() {
        const filter = node("factoryFilter").value;
        const fingerprint = JSON.stringify([space, filter, data?.assets]);
        if (fingerprint === assetsFingerprint) return;
        assetsFingerprint = fingerprint;
        const assets = (data?.assets || []).filter(a => !filter || a.role === filter);
        node("factoryAssetCount").textContent = `${data?.assets.length || 0}`;
        const renderAsset = asset => `<article class="factory-asset">
            ${asset.role.endsWith("video") ? `<video src="${escape(media(asset.path))}" controls preload="none"></video>` : `<img src="${escape(media(asset.path))}" alt="${escape(asset.title)}" loading="lazy">`}
            <strong>${escape(asset.title)}</strong><small>${roles[asset.role]}${asset.meta.duration ? ` · ${Number(asset.meta.duration).toFixed(1)}秒` : ""}</small>
            <p>${escape(asset.caption || "可补充画面内容、操作步骤、适合的切口")}</p>
            <div><button data-edit="${asset.id}" class="text-action" type="button">${asset.role.endsWith("video") ? "打开混剪" : "图文修改"}</button>
            <button data-caption="${asset.id}" class="text-action" type="button">写注释</button><button data-remove="${asset.id}" class="text-action" type="button">移出库</button></div></article>`;
        node("factoryAssets").innerHTML = Object.entries(roles).map(([key, label]) => {
            const group = assets.filter(a => a.role === key);
            return group.length ? `<section class="factory-asset-group"><h4>${label} <span>${group.length} 份</span></h4><div class="factory-assets-grid">${group.map(renderAsset).join("")}</div></section>` : "";
        }).join("") || '<p class="factory-hint">这个分类还没有素材。</p>';
        node("factoryAssets").querySelectorAll("[data-edit]").forEach(button => button.addEventListener("click", () => act(async () => {
            const asset = data.assets.find(a => a.id === button.dataset.edit);
            if (asset.role.endsWith("video")) await window.videoRemix.open([{ path: asset.path, name: asset.title }]);
            else await bridge.openImageEditor({ path: asset.path, name: asset.title });
        })));
        node("factoryAssets").querySelectorAll("[data-caption]").forEach(button => button.addEventListener("click", () => act(async () => {
            const asset = data.assets.find(a => a.id === button.dataset.caption);
            const caption = window.prompt("写清画面内容、操作步骤或视频时间点；生成时会参考", asset.caption);
            if (caption === null) return;
            await send(base() + "/assets/" + asset.id, "PUT", { caption, tags: asset.tags }); await load();
        })));
        node("factoryAssets").querySelectorAll("[data-remove]").forEach(button => button.addEventListener("click", () => act(async () => {
            await send(base() + "/assets/" + button.dataset.remove, "DELETE"); await load();
        })));
    }
    function runBucket(run) {
        if (isPublished(run)) return "published";
        if (run.state === "draft") return "draft";
        if (["ready", "published"].includes(run.state) && run.package_path) return "ready";
        return "working";
    }
    function groupRuns(runs, renderRun, selectedDay) {
        if (!runs.length) return '<div class="factory-empty-results"><strong>没有符合条件的内容</strong><p>可以切换日期，或点击“重置筛选”查看该日期的全部内容。</p></div>';
        const days = [...new Set(runs.map(r => r.day))].sort().reverse();
        const buckets = { ready: "待发布成品", published: "已发布", working: "制作中 / 待处理", draft: "文案草稿" };
        return days.map((day, dayIndex) => {
            const daily = runs.filter(r => r.day === day);
            return `<details class="factory-day-group" data-group-day="${escape(day)}" open><summary>${escape(day)} <span>${daily.length} 条内容</span></summary><div class="factory-day-content">${["graphic", "video"].map(kind => {
                const typed = daily.filter(r => r.content_type === kind);
                if (!typed.length) return "";
                return `<section class="factory-kind-group" data-group-kind="${kind}"><h4 class="factory-kind-title">${kind === "graphic" ? "图文" : "视频混剪"} <span>${typed.length} ${kind === "graphic" ? "篇" : "条"}</span></h4>${Object.entries(buckets).map(([key, label]) => {
                    const items = typed.filter(r => runBucket(r) === key);
                    if (!items.length) return "";
                    return `<details class="factory-status-group" data-group-status="${key}" open><summary>${label} <span>${items.length}</span></summary><div class="factory-group-cards">${items.map(renderRun).join("")}</div></details>`;
                }).join("")}</section>`;
            }).join("")}</div></details>`;
        }).join("");
    }
    function renderOutput(o, index, run) {
        const number = String(index + 1).padStart(2, "0");
        const source = o.layout === "text_cover" ? "文字首图" : o.ai_generated ? "场景图" : o.source_run_id ? "混剪选段" : o.kind === "live_photo" ? "Live 图" : o.kind === "video" ? "混剪成品" : "图片";
        const trialDownloads = ["draft", "needs_review"].includes(run.state) && o.kind === "image" && o.path
            ? `<div class="factory-file-downloads"><a class="button secondary" href="${escape(media(o.path))}" download>下载试稿图片</a></div>` : "";
        const visual = o.kind === "live_photo" ? `<video src="${escape(media(o.preview_path || o.motion_path))}" poster="${escape(media(o.path))}" controls muted loop playsinline preload="none" aria-label="${escape(number + " " + (o.role || "Live 动态预览"))}"></video>` : o.kind === "video" ? `<video src="${escape(media(o.path))}" controls preload="none"></video>` : `<img src="${escape(media(o.path))}" alt="${escape(o.role)}" loading="lazy">`;
        return `<figure class="factory-media ${o.kind === "live_photo" ? "factory-live" : ""}" data-media-source="${o.ai_generated ? "ai" : o.source_run_id ? "remix" : "other"}"><div class="factory-media-heading"><strong>${number}</strong><span>${source}</span></div>${visual}<figcaption>${escape(o.role || source)}${o.kind === "live_photo" ? `<br>LIVE · ${Number(o.duration || 2).toFixed(1)} 秒 · ${o.motion_mode === "camera" ? "镜头微动" : "视频选段 · 静音"}` : ""}${o.source_run_id ? `<details class="factory-origin"><summary>来源与时间</summary><p>${escape(o.source_title)}<br>${Number(o.source_start).toFixed(2)}–${Number(o.source_end).toFixed(2)} 秒</p></details>` : ""}</figcaption>${trialDownloads}</figure>`;
    }
    function renderRuns() {
        if ((data?.selected_day || "") !== node("factoryRunDate").value || loadedRunQuery !== runQuery()) return;
        // Do not replace a feedback form while somebody is filling it in.
        if (node("factoryRuns").contains(document.activeElement) && document.activeElement?.closest("form")) return;
        const all = data?.runs || [];
        const filter = node("factoryContentFilter").value;
        const completion = node("factoryCompletionFilter").value;
        const bucket = node("factoryStatusFilter").value;
        const search = node("factorySearch").value.trim().toLocaleLowerCase();
        const selectedDay = data?.selected_day || "";
        const finished = run => ["ready", "published"].includes(run.state) && Boolean(run.package_path);
        const days = (data?.days || []).filter(d => !selectedDay || d.day === selectedDay);
        const nextFingerprint = JSON.stringify([space, selectedDay, filter, completion, bucket, search, all, days, data?.pagination, data?.overview]);
        if (nextFingerprint === runsFingerprint) return;
        runsFingerprint = nextFingerprint;
        const runs = all;
        const bucketLabels = { ready: "待发布成品", published: "已发布", working: "制作中 / 待处理", draft: "文案草稿" };
        node("factoryOverview").innerHTML = Object.entries(bucketLabels).map(([key, label]) => `<button type="button" data-bucket="${key}" class="factory-stat ${bucket === key ? "active" : ""}" aria-pressed="${bucket === key}"><span>${label}</span><strong>${data?.overview?.[key] || 0}<small>条</small></strong><em>${key === "ready" ? "预览素材 · 复制 · 下载" : key === "published" ? "发布记录 · 每日数据" : key === "working" ? "查看进度 · 继续制作" : "完善文案 · 待配媒体"}</em></button>`).join("");
        node("factoryOverview").querySelectorAll("[data-bucket]").forEach(button => button.addEventListener("click", () => { node("factoryStatusFilter").value = bucket === button.dataset.bucket ? "" : button.dataset.bucket; changeRunFilters(); }));
        host.querySelectorAll("[data-content-type]").forEach(button => { const active = button.dataset.contentType === filter; button.classList.toggle("active", active); button.setAttribute("aria-pressed", String(active)); });
        const pagination = data.pagination;
        const first = pagination.total ? (pagination.page - 1) * pagination.page_size + 1 : 0;
        node("factoryRunCount").textContent = `${selectedDay || "全部日期"} · 筛选共 ${pagination.total} 条 · 当前 ${first}–${pagination.total ? first + runs.length - 1 : 0} 条`;
        const renderRun = run => `<article class="factory-run" data-run-id="${escape(run.id)}" data-day="${escape(run.day)}">
            <details class="factory-note" data-note-id="${escape(run.id)}" ${expandedRuns.has(run.id) ? "open" : ""}><summary><span class="factory-note-cover">${run.outputs?.[0]?.kind !== "video" && run.outputs?.[0]?.path ? `<img src="${escape(media(run.outputs[0].path))}" alt="" loading="lazy">` : `<span>${run.content_type === "video" ? "▶" : "文"}</span>`}</span><div class="factory-note-summary">
            <header><div><small>${escape(run.day)} · ${run.content_type === "graphic" ? (["live_photo", "text_cover_live5"].includes(run.plan.graphic_format) ? "Live 图文" : "图文") : "视频"} · ${escape(run.angle)}</small><h4>${escape(run.plan.title || "等待制作")}</h4></div><span class="factory-status" data-state="${run.state}">${isPublished(run) ? (run.state === "draft" ? "已发布 · 文案归档" : run.state === "needs_review" ? "已发布 · 媒体待检查" : "已发布") : run.state === "published" ? "待发布" : statuses[run.state] || escape(run.state)}</span></header>
            <div class="factory-note-meta"><span>${run.content_type === "graphic" ? `${run.outputs?.length || 0} 张配图` : "视频混剪"}${run.error ? " · 有待处理问题" : ""}</span><span class="factory-note-actions">${publicationToggle(run)}${["draft","ready","published","needs_review"].includes(run.state) ? `<button class="factory-inline-feedback" data-open-feedback="${escape(run.id)}" type="button">记录反馈</button>` : ""}<span class="factory-note-open-label">查看素材与文案 <b>⌄</b></span></span></div></div></summary><div class="factory-note-body">
            <p>${escape(run.stage)}</p>
            ${run.error ? `<details class="factory-error-details"><summary>查看完整检查问题</summary><p>${escape(run.error)}</p></details>` : ""}
            ${run.plan.dedupe_report ? `<details class="factory-dedupe"><summary>知识库多重去重 · ${run.plan.dedupe_report.passed ? '检查通过' : '需调整素材'}</summary><p>素材区间、三帧画面、讲话文本、历史镜头复用；比较 ${Number(run.plan.dedupe_report.history_count || 0)} 条历史；已应用 ${run.plan.dedupe_report.layers?.length || 0} 层静音低透明度视频及入场动画。${run.plan.dedupe_report.speech_checked ? '已检查讲话文本。' : '本次未检查讲话文本。'}</p><p>${(run.plan.knowledge_sources || []).map(source => escape(source.title)).join('；')}</p></details>` : ''}
            ${run.plan.visual_brief ? `<details><summary>封面设计与参考</summary><p>首图吸引点：${escape(run.plan.visual_brief.hook)}</p><p>商品呈现：${escape(run.plan.visual_brief.product_visibility)}</p><p>本次测试：${escape(run.plan.visual_brief.test_variable)}</p><p>实际参考：${(run.plan.visual_reference_sources || []).map(s => escape(s.title)).join("；") || "本次未附账号参考图"}</p></details>` : ""}
            ${run.plan.body ? `<div class="factory-copy"><p class="factory-copy-body">${escape(run.plan.body)}</p>${run.plan.topics?.length ? `<p class="factory-copy-topics">${escape(run.plan.topics.join(" "))}</p>` : ""}</div>` : ""}
            ${run.plan.body ? alignmentPanel(run) : ""}
            ${run.content_type === "graphic" && run.outputs?.length ? `<p class="factory-composition">${run.plan.graphic_recipe === "text_cover_live5" ? `文字首图 ${run.outputs.filter(o => o.layout === "text_cover").length} 张＋Live ${run.outputs.filter(o => o.kind === "live_photo").length} 张` : `${run.outputs.length} 张${run.outputs.every(o => o.kind === "live_photo") ? " Live" : "配图"} · 场景图 ${run.outputs.filter(o => o.ai_generated).length} 张 · 混剪选段 ${run.outputs.filter(o => o.source_run_id || o.motion_mode === "source_video").length} 张${run.plan.graphic_recipe === "ai2_video4" ? " · 六张组合" : run.plan.graphic_recipe === "video6_real_action" ? " · 全部真实动作" : ""}`}</p>` : ""}
            ${run.outputs?.length ? `<div class="factory-output ${run.content_type === "video" ? "factory-output-video" : ""}">${run.outputs.map((o, index) => renderOutput(o, index, run)).join("")}</div>` : ""}
            <div class="factory-toolbar">${run.package_path && ["ready","published"].includes(run.state) ? `<a class="button primary" href="${base()}/runs/${run.id}/package">下载发布包</a>` : ""}
              ${run.plan.body ? `<button class="button secondary" data-copy="${run.id}" type="button">复制发布文案</button>` : ""}
              ${!isPublished(run) && !run.publication && !run.published_url && ["ready","needs_review"].includes(run.state) && run.outputs?.length ? `<button class="button secondary" data-check-alignment="${run.id}" type="button">检查文案与画面</button>` : ""}
              ${run.content_type === "video" && run.plan.clips?.length ? `<button class="button secondary" data-editing="${run.id}" type="button">下载剪映编辑包</button>` : ""}
              ${["failed","interrupted","needs_review","retry_wait"].includes(run.state) ? `<button class="button secondary" data-retry="${run.id}" type="button">${run.state === "needs_review" ? (run.plan.alignment_audit_only ? "重新检查" : "修正并重新检查") : "继续未完成部分"}</button>` : ""}</div>
            ${run.content_type === "video" && ["ready","published"].includes(run.state) ? `<details><summary>提取功能 Live 图文</summary><form data-extract-live="${run.id}" class="factory-feedback"><label>选段（每行：起点秒数, 时长秒数, 画面说明）<textarea name="segments" required rows="3" placeholder="例如：3.2, 2.5, 笔尖贴板连续铺豆"></textarea></label><p>先播放上方视频，选清楚完整的动作，每段 0.5–5 秒，最多 6 段。静音截取，沿用本条文案并检查图文对应；另存为同日期的 Live 图文。</p><button class="button secondary" type="submit">生成 Live 图文</button></form></details>` : ""}
            ${["draft","ready","published","needs_review"].includes(run.state) ? `<details data-feedback-panel="${escape(run.id)}"><summary>${run.state === "draft" ? "文案反馈" : "发布反馈"} · ${run.rating ? run.rating + "分" : "未评分"}</summary>
              <form data-feedback="${run.id}" class="factory-feedback"><label>创作评分（可选）<select name="rating"><option value="">未评分</option>${[5,4,3,2,1].map(n => `<option ${run.rating === n ? "selected" : ""}>${n}</option>`).join("")}</select></label>
                <label>反馈重点<select name="issue_type">${Object.entries(feedbackKinds).map(([key,label]) => `<option value="${key}">${label}</option>`).join("")}</select></label>
                <label>对应第几张 / 段（可选）<input name="media_numbers" inputmode="numeric" placeholder="例如：3,4"></label>
                <label>具体哪里好或哪里不对<input name="lesson" maxlength="2000" value="${escape(run.lesson)}" placeholder="例如：标题说补一颗，第3张却在装豆；保留标题，换动作"></label>
                <button class="button secondary" type="submit">记入本账号经验</button></form></details>${publicationPanel(run)}` : ""}</div></details></article>`;
        node("factoryRuns").innerHTML = groupRuns(runs, renderRun, selectedDay);
        node("factoryRuns").querySelectorAll(".factory-note").forEach(note => note.addEventListener("toggle", () => {
            if (note.open) expandedRuns.add(note.dataset.noteId);
            else { expandedRuns.delete(note.dataset.noteId); note.querySelectorAll("video").forEach(video => video.pause()); }
        }));
        node("factoryRuns").querySelectorAll("[data-open-feedback]").forEach(button => button.addEventListener("click", event => {
            event.preventDefault(); event.stopPropagation();
            const note = button.closest(".factory-note");
            const panel = [...(note?.querySelectorAll("[data-feedback-panel]") || [])].find(item => item.dataset.feedbackPanel === button.dataset.openFeedback);
            if (!note || !panel) return;
            note.open = true; panel.open = true;
            panel.querySelector("select, textarea, input")?.focus();
        }));
        node("factoryRuns").querySelectorAll("[data-published-toggle]").forEach(toggle => {
            toggle.addEventListener("click", event => event.stopPropagation());
            toggle.addEventListener("change", event => act(async () => {
                const run = data.runs.find(item => item.id === event.target.dataset.publishedToggle);
                if (!run) return;
                const control = event.target, published = control.checked, requestedSpace = space;
                control.disabled = true;
                try {
                    await send(base() + `/runs/${run.id}/publication-status`, "PUT", { status: published ? "published" : "unpublished" });
                    if (space === requestedSpace) {
                        await load(false, true);
                        showToast(published ? "已标为已发布，实际发布日期可在发布登记中补充" : "已改为未发布，原发布详情和数据仍保留");
                    }
                } catch (error) {
                    control.checked = isPublished(run);
                    throw error;
                } finally { control.disabled = false; }
            }));
        });
        node("factoryRuns").querySelectorAll("[data-published-control]").forEach(control => control.addEventListener("click", event => event.stopPropagation()));
        node("factoryRuns").querySelectorAll("[data-copy]").forEach(button => button.addEventListener("click", () => act(async () => {
            const p = data.runs.find(r => r.id === button.dataset.copy).plan;
            await navigator.clipboard.writeText(`${p.title}\n\n${p.body}\n\n${(p.topics || []).join(" ")}`); showToast("发布文案已复制");
        })));
        node("factoryRuns").querySelectorAll("[data-retry]").forEach(button => button.addEventListener("click", () => act(async () => { await send(base() + `/runs/${button.dataset.retry}/retry`, "POST"); await load(); })));
        node("factoryRuns").querySelectorAll("[data-check-alignment]").forEach(button => button.addEventListener("click", () => act(async () => {
            button.disabled = true;
            try { await send(base() + `/runs/${button.dataset.checkAlignment}/check-alignment`, "POST"); await load(); showToast("已安排逐张检查；已认可的文案保持锁定，具体问题会显示在内容卡片内"); }
            finally { button.disabled = false; }
        })));
        node("factoryRuns").querySelectorAll("[data-editing]").forEach(button => button.addEventListener("click", () => act(async () => {
            button.disabled = true;
            try {
                const result = await send(base() + `/runs/${button.dataset.editing}/editing-package`, "POST");
                const link = document.createElement("a"); link.href = result.download_url; link.download = "";
                document.body.appendChild(link); link.click(); link.remove();
                showToast("剪映编辑包已生成：原片分镜＋独立字幕轨，解压后按使用说明打开");
            } finally { button.disabled = false; }
        })));
        node("factoryRuns").querySelectorAll("[data-extract-live]").forEach(form => form.addEventListener("submit", event => {
            event.preventDefault(); act(async () => {
                const segments = form.elements.segments.value.trim().split(/\n/).filter(s => s.trim()).map(line => {
                    const [start, duration, ...role] = line.split(/[,，]/);
                    return { start: Number(start), duration: Number(duration), role: role.join("，").trim() };
                });
                const button = form.querySelector("button"); button.disabled = true;
                try {
                    await send(base() + `/runs/${form.dataset.extractLive}/live-from-video`, "POST", { segments });
                    document.activeElement?.blur(); await load(); showToast("Live 选段已保存，制作完成后可按原日期查看");
                } finally { button.disabled = false; }
            });
        }));
        node("factoryRuns").querySelectorAll("[data-feedback]").forEach(form => form.addEventListener("submit", event => {
            event.preventDefault(); act(async () => {
                const value = Object.fromEntries(new FormData(form));
                const run = data.runs.find(r => r.id === form.dataset.feedback);
                const media_indexes = value.media_numbers.trim() ? value.media_numbers.split(/[,，、\s]+/).filter(Boolean).map(n => Number(n) - 1) : [];
                if (media_indexes.some(n => !Number.isInteger(n) || n < 0 || n > 7)) throw new Error("请填写有效的图片或片段编号，例如 3,4");
                await send(base() + `/runs/${form.dataset.feedback}/feedback`, "PUT", { rating: value.rating ? Number(value.rating) : null, lesson: value.lesson, issue_type: value.issue_type, media_indexes, published_url: run.published_url, metrics: run.metrics });
                document.activeElement?.blur(); await load(); showToast("经验已保存，下次生成只在本账号内参考");
            });
        }));
        node("factoryRuns").querySelectorAll("[data-publication]").forEach(form => form.addEventListener("submit", event => {
            event.preventDefault(); act(async () => {
                await send(base() + `/runs/${form.dataset.publication}/publication`, "PUT", Object.fromEntries(new FormData(form)));
                document.activeElement?.blur(); await load(); showToast("实际发布已登记，可以按日期记录运营数据");
            });
        }));
        node("factoryRuns").querySelectorAll("[data-metrics]").forEach(form => {
            form.elements.observed_on.addEventListener("change", () => {
                const snapshot = data.runs.find(r => r.id === form.dataset.metrics).metric_snapshots.find(s => s.observed_on === form.elements.observed_on.value);
                Object.keys(metricNames).forEach(k => { form.elements[k].value = snapshot?.metrics[k] ?? ""; });
            });
            form.addEventListener("submit", event => {
                event.preventDefault(); act(async () => {
                    const value = Object.fromEntries(new FormData(form));
                    const metrics = Object.fromEntries(Object.keys(metricNames).filter(k => value[k] !== "").map(k => [k, Number(value[k])]));
                    await send(base() + `/runs/${form.dataset.metrics}/metrics`, "PUT", { observed_on: value.observed_on, metrics });
                    document.activeElement?.blur(); await load(); showToast("当日数据已保存，历史日期保留；下次生成将读取本商品反馈");
                });
            });
        });
    }
    async function upload() {
        const files = [...node("factoryFiles").files];
        const product = node("factoryProduct").value, role = node("factoryRole").value;
        if (!product) { showToast("请先选择商品", true); return; }
        node("factoryUpload").disabled = true;
        await act(async () => {
            for (const file of files) {
                node("factoryUpload").textContent = `正在导入 ${file.name}`;
                await api(base() + "/upload?" + new URLSearchParams({ product_id: product, role, filename: file.name }), {
                    method: "POST", headers: { "Content-Type": file.type || "application/octet-stream" }, body: file,
                });
            }
            await load(); showToast("素材已归入当前账号和商品");
        });
        node("factoryUpload").disabled = false; node("factoryUpload").textContent = "上传图片 / 视频"; node("factoryFiles").value = "";
    }
    function importProduct() { act(async () => {
        const product = detail.products.find(p => p.id === node("factoryProduct").value);
        if (!product) throw new Error("请先选择商品");
        for (const [role, paths] of [["product_image", product.image_paths], ["product_video", product.video_paths]]) {
            if (paths?.length) await send(base() + "/assets", "POST", { product_id: product.id, role, paths, title: product.title, caption: "", tags: product.keywords || [] });
        }
        await load(); showToast("已有商品素材已整理，重复文件会自动合并");
    }); }
    window.addEventListener("operation-space-loaded", event => {
        const changed = space !== event.detail.space.id;
        space = event.detail.space.id; detail = event.detail;
        if (changed) { data = null; mount(); act(() => load(true)); }
        else productOptions();
        if (!timer) timer = setInterval(() => {
            if (!document.hidden && location.hash.startsWith("#operations") && bridge.currentUser()) act(load);
        }, 5000);
    });
})();
