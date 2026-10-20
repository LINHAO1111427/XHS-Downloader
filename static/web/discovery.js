(() => {
    const el = (name) => document.getElementById(`discovery${name}`);
    const platforms = { xiaohongshu: "小红书 MCP", douyin: "抖音 DouK" };
    const states = { pending: "等待中", processing: "采集中", success: "已完成", partial: "部分完成", failed: "失败", cancelled: "已停止", interrupted: "已中断" };
    const date = (value) => value ? new Date(value * 1000).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false }) : "未取得";
    const count = (value) => value === null || value === undefined ? "未取得" : String(value);
    let timer, selected = "", active = null, revision = 0, loading = false, opened = null;
    let currentRun = null, products = [], spaceRevision = 0;
    let dailyConfig = null, dailyDay = "", dailyLoaded = false;
    const paragraph = (text) => { const p = document.createElement("p"); p.textContent = text; return p; };

    function renderDaily(data, report) {
        const cfg = data.config;
        el("DailyControls").disabled = currentUser?.role !== "admin";
        if (cfg && !dailyLoaded) {
            dailyConfig = cfg; dailyLoaded = true;
            el("DailyEnabled").checked = cfg.enabled;
            el("DailyAt").value = cfg.at;
            el("DailyKeywords").value = cfg.keywords.join("，");
            el("DailyLimit").value = cfg.limit;
            el("DailyMinimum").value = cfg.min_interactions;
        }
        const dailyWindow = cfg?.window_days ? `近 ${cfg.window_days} 天` : ({ recent: "近 7 天", today: "北京时间今日", broad: "广选" }[cfg?.selection?.preset || "recent"]);
        const productScope = cfg?.require_attached_product ? "，必须有明确挂载商品" : "，商品挂载待核验";
        const mediaScope = cfg?.image_text_only ? "，仅图文笔记" : "";
        el("DailyRules").textContent = `${dailyWindow}，粉丝严格少于 ${cfg?.max_followers ?? 1000}${productScope}${mediaScope}；互动合计门槛 ${cfg?.min_interactions ?? 500}，商品加购、销量和利润单独核验。`;
        el("DailyResume").hidden = !data.paused;
        el("DailyRun").disabled = Boolean(data.paused) || Boolean(active) || currentUser?.role !== "admin";
        el("DailyStatus").textContent = data.paused ? `已暂停：${data.paused.message}` : data.last_error || (cfg?.enabled ? `每日 ${cfg.at}（北京时间）自动执行 · 下次检查 ${date(data.next_run_at)}。电脑与后台服务需保持运行。` : "每日自动选品尚未启用");
        const names = { processing: "进行中", success: "已完成", needs_attention: "待处理", interrupted: "已中断" };
        el("DailyHistory").replaceChildren(...data.reports.map(r => new Option(`${r.day} · ${names[r.state] || r.state} · ${r.recommended_count || 0} 条优先核验`, r.day)));
        if (!data.reports.length) el("DailyHistory").add(new Option("暂无日报", ""));
        el("DailyHistory").value = dailyDay;
        const scope = report?.knowledge_scope?.effective;
        const scopeText = scope ? `；知识库实际条件：${scope.days ?? "不限"}天、粉丝 < ${scope.followers_lt ?? "不限"}、点赞 ≥ ${scope.likes_gte ?? "不限"}` : "";
        el("DailySummary").textContent = report ? `${report.day} · ${names[report.state] || report.state} · ${report.sample_count || 0} 条去重样本 · ${report.product_sample_count || 0} 条挂商品 · ${report.recommended_count || 0} 条优先核验 · ${report.counts?.missing || 0} 条数据待补${scopeText}。${report.message || ""}` : "每天完成后在这里查看推荐、知识库依据和原始批次。";
        el("DailyResults").replaceChildren();
        for (const item of report?.recommendations || []) {
            const card = document.createElement("article"); card.className = "discovery-card";
            const title = document.createElement("button"); title.type = "button"; title.textContent = item.title || item.note_id;
            title.addEventListener("click", () => showNote(item));
            const batch = document.createElement("button"); batch.type = "button"; batch.className = "button secondary"; batch.textContent = "查看原始采集批次";
            batch.addEventListener("click", () => { selected = item.run_id; refresh(); });
            card.append(title, paragraph(`${item.author || "作者"} · 粉丝 ${count(item.followers)} · ${date(item.published_at)}`), paragraph(item.daily_selection.reason), evidence(item), batch);
            el("DailyResults").append(card);
        }
        if (report && !report.recommendations?.length) el("DailyResults").append(paragraph(report.state === "success" ? "本次样本没有符合全部笔记筛选条件的线索；原始记录保留在下方历史批次。" : "采集尚未完成，已取得的正文与数据保留在下方历史批次。"));
    }

    function requestPayload() {
        return {
            platform: el("Platform").value, mode: el("Mode").value, query: el("Query").value,
            sort: el("Sort").value, days: Number(el("Days").value), pages: Number(el("Pages").value),
            limit: Number(el("Limit").value), comments: Number(el("Comments").value),
            selection: { space_id: el("Space").value, product_id: el("ProductId").value,
                product: el("Product").value, category: el("Category").value, need: el("Need").value,
                scene: el("Scene").value, preset: el("Preset").value, cart_min: Number(el("CartMin").value) },
        };
    }

    function renderPlan(target, plan, editable = false) {
        target.hidden = !plan;
        if (plan && target.dataset.planStamp === String(plan.created_at)) return;
        target.dataset.planStamp = plan ? String(plan.created_at) : "";
        target.replaceChildren();
        if (!plan) return;
        target.append(paragraph(`广选 → 严筛 → 多测 · 小红书优先，抖音补充 · 计划时间 ${date(plan.created_at)}`));
        target.append(paragraph(`账号：${plan.context.space_name || "未关联"} · 商品：${plan.focus.product || "按搜索词探索"} · 人群：${plan.focus.audience || "待明确"}`));
        target.append(paragraph(`已检索：${plan.coverage.methods} 类方法、${plan.coverage.cases} 个历史商品分析、${plan.coverage.lessons} 条相关已确认经验、${plan.benchmarks.length} 篇本地对标。`));
        for (const rule of plan.rules) target.append(paragraph(`${rule.label} · ${rule.grounded ? "有本地方法依据" : "未检索到对应本地方法，待补充"}`));
        const c = plan.criteria;
        target.append(paragraph(`本批条件：${{ recent: "近7天、粉丝严格少于1000", today: "北京时间今日、粉丝严格少于1000、点赞至少500", broad: "广选，不设笔记数值门槛" }[c.preset]}；真实24h加购 > ${c.cart_gt}，独立待核验。`));
        for (const direction of plan.directions) {
            const row = document.createElement("div"); row.className = "discovery-keywords";
            row.append(document.createTextNode(`${direction.relation}：`));
            if (!direction.keywords.length) row.append(document.createTextNode("补充方向后可扩展"));
            for (const keyword of direction.keywords) {
                if (editable) {
                    const button = document.createElement("button"); button.type = "button"; button.className = "button secondary"; button.textContent = keyword;
                    button.addEventListener("click", () => { el("Query").value = keyword; el("Mode").value = "search"; modeChanged(); target.hidden = true; el("Query").focus(); });
                    row.append(button);
                } else row.append(document.createTextNode(`${keyword}　`));
            }
            target.append(row);
        }
        for (const note of plan.notes) target.append(paragraph(note));
        if (plan.related_keywords?.length) target.append(paragraph(`商品资料中的其他相关词：${plan.related_keywords.join("、")}`));
        const details = document.createElement("details"), summary = document.createElement("summary");
        summary.textContent = "查看实际引用、对标和反馈"; details.append(summary);
        const types = { user_requirement: "长期要求", local_method: "本地方法", confirmed_lesson: "已确认经验", historical_product_analysis: "历史商品分析（非当前销售证据）" };
        for (const source of plan.sources) {
            const block = document.createElement("details"), label = document.createElement("summary"), text = document.createElement("pre");
            label.textContent = `${types[source.type] || source.type}${source.reference_relation ? ` · ${source.reference_relation}` : ""} · ${source.title}`;
            text.textContent = `${source.excerpt}\n来源ID：${source.id}\n记录时间：${date(source.updated_at)}${source.historical_metrics ? `\n历史快照：${JSON.stringify(source.historical_metrics)}` : ""}`;
            block.append(label, text); details.append(block);
        }
        for (const note of plan.benchmarks) details.append(paragraph(`本地对标 [${note.source_kind}] ${note.title}\n${note.body}\n历史互动：${JSON.stringify(note.metrics)} · ${date(note.updated_at)}`));
        for (const feedback of plan.account_feedback) details.append(paragraph(`${feedback.usage} · 评分 ${count(feedback.rating)} · ${feedback.lesson}\n已填运营数据：${JSON.stringify(feedback.metrics)} · ${date(feedback.updated_at)}`));
        target.append(details);
    }

    function evidence(item) {
        const box = document.createElement("div"); box.className = "discovery-evidence";
        const data = item.selection;
        if (!data) { box.append(paragraph("旧批次未保存选品依据，可重新采集")); return box; }
        const title = document.createElement("strong"); title.textContent = `${data.label} · 商品${data.product_status}`; box.append(title);
        for (const check of data.checks) box.append(paragraph(`${{ pass: "符合", fail: "未符合", unknown: "待核验" }[check.status]}：${check.label}`));
        box.append(paragraph(`评论样本 ${data.comment_sample_size} 条；${data.comment_signals.length} 条命中意向、疑虑或场景词，需复核原文。`));
        for (const signal of data.comment_signals) box.append(paragraph(`[${signal.labels.join(" / ")}] ${signal.text}`));
        for (const reason of data.buying_hypotheses || []) box.append(paragraph(`购买理由假设：${reason.dimension}（${reason.matched_words.join("、")}）；${reason.status}`));
        for (const product of item.products || []) box.append(paragraph(`关联商品：${product.title} · 页面价格 ${product.price || "待核验"} · ${product.url || "商品链接待补"}`));
        box.append(paragraph(`待补：${data.gaps.join("；")}`), paragraph(`下一步：${data.next_step}`));
        return box;
    }

    function modeChanged() {
        const xhs = el("Platform").value === "xiaohongshu";
        el("Mode").querySelector('[value="hot"]').disabled = xhs;
        if (xhs && el("Mode").value === "hot") el("Mode").value = "search";
        const mode = el("Mode").value;
        el("Query").disabled = mode === "hot";
        el("Query").required = mode !== "hot";
        el("Query").maxLength = mode === "search" ? 100 : 4096;
        el("QueryLabel").textContent = mode === "detail" ? "作品链接" : "搜索关键词";
        el("Query").placeholder = mode === "detail" ? xhs ? "完整小红书链接，包含 xsec_token" : "抖音作品链接或分享短链接" : "例如：拼豆工具";
        for (const name of ["Sort", "Days"]) el(name).disabled = mode !== "search";
        el("Pages").disabled = xhs || mode !== "search";
        el("Comments").disabled = mode === "hot";
    }

    function showNote(item) {
        opened = item;
        el("NoteTitle").textContent = item.title || item.note_id;
        el("NoteMeta").textContent = `${platforms[item.platform]} · ${item.author || "热榜词"} · 采集于 ${date(item.collected_at)}`;
        el("NoteBody").textContent = item.body || "本条未取得正文";
        el("NoteDialog").querySelector(".discovery-evidence")?.remove();
        el("NoteBody").after(evidence(item));
        el("CommentScope").textContent = `${item.comments_scope || "未取得评论"} · 已保存 ${(item.comment_items || []).length} 条`;
        el("NoteComments").replaceChildren(...(item.comment_items || []).map((comment) => {
            const node = document.createElement("li");
            node.textContent = `${comment.text}\n点赞：${count(comment.likes)} · ${date(comment.published_at)}`;
            return node;
        }));
        el("NoteLink").removeAttribute("href");
        try {
            const url = new URL(item.url);
            if (url.protocol === "https:" && ["www.xiaohongshu.com", "xiaohongshu.com", "www.douyin.com"].includes(url.hostname)) el("NoteLink").href = url.href;
        } catch (_) { /* Incomplete source URLs are not links. */ }
        el("NoteDialog").showModal();
    }

    function render(run) {
        currentRun = run;
        el("Results").replaceChildren();
        el("Export").hidden = !run;
        if (run) el("Export").href = `/api/discovery/runs/${encodeURIComponent(run.id)}/export`;
        const notes = run?.items || [];
        el("RunPlan").hidden = !run?.selection_plan;
        renderPlan(el("PlanSnapshot"), run?.selection_plan);
        el("RunSummary").textContent = run ? `${platforms[run.request.platform]} · ${states[run.state]} · ${notes.length} 条 · ${date(run.created_at)}` : "暂无多平台采集记录";
        const issues = [...(run?.errors || []), ...(run?.warnings || [])];
        el("Errors").hidden = !issues.length;
        el("Errors").replaceChildren(...issues.map((text) => {
            const p = document.createElement("p"); p.textContent = text; return p;
        }));
        for (const item of notes) {
            if (el("Stage").value && item.selection?.stage !== el("Stage").value) continue;
            const card = document.createElement("article");
            card.className = "discovery-card";
            const title = document.createElement("button");
            title.type = "button"; title.textContent = item.title || item.note_id;
            title.addEventListener("click", () => showNote(item));
            const stats = document.createElement("p");
            stats.textContent = item.kind === "topic" ? `热榜第 ${item.rank} 位 · 热度 ${count(item.hot_value)}` : `${item.author || "作者未取得"} · 粉丝 ${count(item.followers)}\n点赞 ${count(item.likes)} · 收藏 ${count(item.collects)} · 评论 ${count(item.comments)} · 分享 ${count(item.shares)}`;
            const body = document.createElement("p");
            body.className = "discovery-excerpt";
            body.textContent = item.body ? item.body.slice(0, 120) + (item.body.length > 120 ? "…" : "") : "点击查看详情";
            const meta = document.createElement("p");
            meta.textContent = `发布时间：${date(item.published_at)} · 已采评论 ${(item.comment_items || []).length} 条`;
            card.append(title, stats, body, meta, evidence(item)); el("Results").append(card);
        }
        if (notes.length && !el("Results").children.length) el("Results").append(paragraph("本批没有此类结果；可切换“全部”查看样本。"));
    }

    async function openBoardBatch(id) {
        selected = id;
        for (const name of ['Stage', 'Kind', 'ResearchState']) if (el(name)) el(name).value = '';
        if (el('LowFanOnly')) el('LowFanOnly').checked = false;
        el('History').value = id;
        const stamp = revision;
        try {
            const run = await api(`/api/discovery/runs/${encodeURIComponent(id)}`);
            if (stamp !== revision || selected !== id) return;
            render(run);
            el('History').scrollIntoView({behavior:'smooth', block:'center'});
        } catch (error) { if (stamp === revision) el('Status').textContent = error.message; }
    }

    async function refresh() {
        if (loading || !currentUser) return;
        loading = true;
        const stamp = revision;
        try {
            const [data, daily] = await Promise.all([api("/api/discovery"), api("/api/discovery/daily")]);
            if (stamp !== revision) return;
            const admin = currentUser?.role === "admin";
            active = data.active_id;
            if (!daily.reports.some(r => r.day === dailyDay)) dailyDay = daily.latest?.day || "";
            const dailyChosen = dailyDay;
            const report = dailyDay && dailyDay !== daily.latest?.day ? await api(`/api/discovery/daily/${encodeURIComponent(dailyDay)}`) : daily.latest;
            if (stamp !== revision || dailyChosen !== dailyDay) return;
            renderDaily(daily, report);
            window.discoveryBoard?.update(data, daily, {
                openNote: showNote, openBatch: openBoardBatch, refresh,
            }).catch(error => { if (stamp === revision) window.discoveryBoard?.error(error.message); });
            for (const name of ["Controls", "XhsControls", "DyControls"]) el(name).disabled = !admin;
            el("Collect").disabled = Boolean(active) || !admin;
            el("Cancel").hidden = !active || !admin;
            el("Status").textContent = active ? "正在采集，结果逐条保存" : "可选择数据源开始采集";
            el("DyStatus").textContent = data.sources.douyin.cookie_configured ? "Cookie 已配置；实际有效性以采集结果为准" : "尚未配置抖音 Cookie";
            if (!data.runs.some((run) => run.id === selected)) selected = data.runs[0]?.id || "";
            el("History").replaceChildren(...data.runs.map((run) => new Option(`${date(run.created_at)} · ${platforms[run.request.platform]} · ${states[run.state]} · ${run.count} 条`, run.id)));
            if (!data.runs.length) el("History").add(new Option("暂无记录", ""));
            el("History").value = selected;
            const chosen = selected;
            const run = chosen ? await api(`/api/discovery/runs/${encodeURIComponent(chosen)}`) : null;
            if (stamp === revision && chosen === selected) render(run);
        } catch (error) {
            if (stamp === revision) { el("Status").textContent = error.message; window.discoveryBoard?.error(error.message); }
        } finally {
            if (stamp === revision) loading = false;
        }
    }

    async function action(button, target, callback) {
        const stamp = revision;
        button.disabled = true;
        target.textContent = "正在处理，请稍候…";
        try {
            const result = await callback();
            if (stamp === revision) target.textContent = result;
        } catch (error) {
            if (stamp === revision) target.textContent = error.message;
        } finally {
            if (stamp === revision) button.disabled = currentUser?.role !== "admin";
        }
    }

    el("Form").addEventListener("submit", async (event) => {
        event.preventDefault();
        const stamp = revision;
        el("Collect").disabled = true;
        try {
            const data = await api("/api/discovery/runs", { method: "POST", body: JSON.stringify(requestPayload()) });
            if (stamp !== revision) return;
            selected = data.run.id; active = data.run.id;
            render(data.run); await refresh();
        } catch (error) {
            if (stamp === revision) el("Status").textContent = error.message;
        } finally {
            if (stamp === revision) el("Collect").disabled = Boolean(active) || currentUser?.role !== "admin";
        }
    });
    el("DailyForm").addEventListener("submit", async (event) => {
        event.preventDefault();
        const stamp = revision;
        try {
            const cfg = { ...(dailyConfig || {}), enabled: el("DailyEnabled").checked, at: el("DailyAt").value,
                keywords: el("DailyKeywords").value.split(/[,，、\n]/).map(v => v.trim()).filter(Boolean),
                limit: Number(el("DailyLimit").value), min_interactions: Number(el("DailyMinimum").value) };
            await api("/api/discovery/daily", { method: "PUT", body: JSON.stringify(cfg) });
            if (stamp !== revision) return;
            dailyLoaded = false; await refresh(); showToast("每日选品计划已保存");
        } catch (error) { if (stamp === revision) el("DailyStatus").textContent = error.message; }
    });
    for (const [name, path] of [["DailyRun", "run"], ["DailyResume", "resume"]]) {
        el(name).addEventListener("click", event => action(event.currentTarget, el("DailyStatus"), async () => {
            await api(`/api/discovery/daily/${path}`, { method: "POST" }); await refresh();
            return path === "resume" ? "已请求恢复，将继续未完成的方向" : "已执行今日计划检查，结果会自动更新";
        }));
    }
    el("DailyQuickRun").addEventListener("click", event => action(event.currentTarget, el("DailyStatus"), async () => {
        await api("/api/discovery/daily/quick-run", { method: "POST" });
        dailyLoaded = false;
        await refresh();
        return "已启动近 48 小时挂商品低粉图文采集；请保持小红书 MCP 登录和后台服务运行";
    }));
    el("DailyHistory").addEventListener("change", () => { dailyDay = el("DailyHistory").value; refresh(); });
    el("Preview").addEventListener("click", (event) => action(event.currentTarget, el("Status"), async () => {
        if (!el("Form").reportValidity()) return "请补充选品方向和采集参数";
        const stamp = revision;
        const payload = JSON.stringify(requestPayload());
        const plan = await api("/api/discovery/plan", { method: "POST", body: payload });
        if (stamp === revision && payload === JSON.stringify(requestPayload())) renderPlan(el("PlanPreview"), plan, true);
        return "已读取当前本地知识与账号资料；开始采集时会重新检索并保存快照";
    }));
    el("Form").addEventListener("input", () => { el("PlanPreview").hidden = true; });
    el("Stage").addEventListener("change", () => render(currentRun));
    el("Space").addEventListener("change", async () => {
        const stamp = ++spaceRevision, rev = revision;
        products = []; el("ProductId").replaceChildren(new Option("自行填写方向", ""));
        el("Product").value = ""; el("Category").value = "";
        if (!el("Space").value) return;
        try {
            const data = await api(`/api/operations/spaces/${encodeURIComponent(el("Space").value)}`);
            if (stamp !== spaceRevision || rev !== revision) return;
            products = data.products || [];
            el("ProductId").append(...products.map((p) => new Option(p.title, p.id)));
        } catch (error) { if (stamp === spaceRevision && rev === revision) el("Status").textContent = error.message; }
    });
    el("ProductId").addEventListener("change", () => {
        const product = products.find((p) => p.id === el("ProductId").value);
        el("Product").value = (product?.title || "").slice(0, 100); el("Category").value = (product?.category || "").slice(0, 100);
        if (product) { el("Query").value = (product.keywords?.[0] || product.title).slice(0, 100); el("Mode").value = "search"; modeChanged(); }
    });
    el("Preset").addEventListener("change", () => {
        if (el("Preset").value !== "broad") el("Days").value = el("Preset").value === "today" ? "1" : "7";
    });
    el("StartMcp").addEventListener("click", (event) => action(event.currentTarget, el("McpStatus"), async () => (await api("/api/discovery/xiaohongshu/start", { method: "POST" })).message));
    el("CheckMcp").addEventListener("click", (event) => action(event.currentTarget, el("McpStatus"), async () => {
        const result = await api("/api/discovery/xiaohongshu/check", { method: "POST" });
        if (result.logged_in) { el("Qr").hidden = true; el("Qr").removeAttribute("src"); }
        if (result.logged_in === null) return result.message;
        return result.logged_in ? "小红书 MCP 已连接且已登录" : "服务已连接，请扫码登录";
    }));
    el("QrMcp").addEventListener("click", (event) => action(event.currentTarget, el("McpStatus"), async () => {
        const stamp = revision;
        const result = await api("/api/discovery/xiaohongshu/qrcode", { method: "POST" });
        if (stamp !== revision) return "";
        el("Qr").hidden = !result.img;
        if (result.img) el("Qr").src = result.img;
        return result.logged_in ? "小红书 MCP 已登录" : "请使用小红书 App 扫码，确认后点击检查连接";
    }));
    el("SaveCookie").addEventListener("click", (event) => action(event.currentTarget, el("DyStatus"), async () => {
        const result = await api("/api/discovery/douyin/cookie", { method: "PUT", body: JSON.stringify({ cookie: el("DyCookie").value }) });
        el("DyCookie").value = "";
        return result.configured ? "Cookie 已保存，可开始抖音采集" : "Cookie 已清除";
    }));
    el("Cancel").addEventListener("click", (event) => action(event.currentTarget, el("Status"), async () => {
        if (active) await api(`/api/discovery/runs/${encodeURIComponent(active)}`, { method: "DELETE" });
        return "已提交停止请求，当前请求结束后保存结果";
    }));
    el("History").addEventListener("change", () => { selected = el("History").value; refresh(); });
    el("Refresh").addEventListener("click", refresh);
    for (const name of ["Platform", "Mode"]) el(name).addEventListener("change", modeChanged);
    el("NoteClose").addEventListener("click", () => el("NoteDialog").close());
    el("Copy").addEventListener("click", async () => {
        if (!opened) return;
        try { await navigator.clipboard.writeText(`${opened.title || ""}\n\n${opened.body || ""}`); showToast("标题与完整正文已复制"); }
        catch (_) { showToast("复制失败，请选中正文手动复制", true); }
    });
    window.discoveryWorkspace = {
        async start() {
            this.stop(); modeChanged(); const stamp = revision; await refresh();
            if (stamp !== revision || !currentUser) return;
            timer = poll(refresh, 5000);
            try {
                const data = await api("/api/operations/spaces");
                if (stamp === revision) el("Space").append(...(data.spaces || []).map((s) => new Option(s.name, s.id)));
            } catch (error) { if (stamp === revision) el("Status").textContent = error.message; }
        },
        stop() {
            window.discoveryBoard?.reset();
            clearInterval(timer); revision += 1; loading = false; active = null; selected = ""; opened = null;
            dailyConfig = null; dailyDay = ""; dailyLoaded = false;
            el("DailyKeywords").value = ""; el("DailyEnabled").checked = false;
            renderDaily({ config: null, reports: [], latest: null }, null);
            el("Qr").hidden = true; el("Qr").removeAttribute("src"); el("DyCookie").value = "";
            el("NoteDialog").close(); el("History").replaceChildren(); render(null);
            products = []; spaceRevision += 1; el("Stage").value = "";
            el("Space").replaceChildren(new Option("不关联账号", "")); el("ProductId").replaceChildren(new Option("自行填写方向", ""));
            for (const field of ["Product", "Category", "Need", "Scene"]) el(field).value = "";
            renderPlan(el("PlanPreview"), null);
            el("McpStatus").textContent = "尚未检查连接";
        },
    };
})();
