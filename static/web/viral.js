(() => {
    const el = (name) => document.getElementById(`viral${name}`);
    const labels = { pending: "等待中", processing: "采集中", success: "已完成", partial: "部分完成", failed: "失败", cancelled: "已取消", interrupted: "已中断" };
    const number = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 });
    const date = (value) => new Date(value * 1000).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false });
    let timer = null;
    let activeId = null;
    let selectedId = "";
    let generation = 0;
    let loading = false;
    let currentRun = null;

    function rules() {
        const keywords = [...new Set(el("Keywords").value.split(/[,，;；\n]/).map((value) => value.trim()).filter(Boolean))];
        if (!keywords.length || keywords.length > 5 || keywords.some((value) => value.length > 50)) {
            throw new Error("请输入 1 至 5 个关键词，每个不超过 50 个字符");
        }
        return {
            keywords,
            hours: el("Hours").value === "today" ? 24 : Number(el("Hours").value),
            time_range: el("Hours").value === "today" ? "today" : "rolling",
            max_followers: Number(el("Followers").value),
            min_likes: Number(el("Likes").value),
            min_interactions: Number(el("Interactions").value),
            min_ratio: Number(el("Ratio").value),
            pages: Number(el("Pages").value),
            candidate_limit: Number(el("Candidates").value),
            limit: Number(el("Limit").value),
        };
    }

    function fillSchedule(schedule) {
        const values = schedule.rules;
        el("Keywords").value = values.keywords.join("，");
        // API callers can save any supported hour count, including values not in the presets.
        if (![...el("Hours").options].some((option) => Number(option.value) === values.hours)) {
            el("Hours").add(new Option(`近 ${values.hours} 小时`, String(values.hours)));
        }
        el("Hours").value = values.time_range === "today" ? "today" : String(values.hours);
        el("Followers").value = values.max_followers;
        el("Likes").value = values.min_likes ?? 0;
        el("Interactions").value = values.min_interactions;
        el("Ratio").value = values.min_ratio;
        el("Pages").value = values.pages;
        el("Candidates").value = values.candidate_limit;
        el("Limit").value = values.limit;
        el("Daily").checked = schedule.enabled;
        el("Time").value = schedule.at;
    }

    function iconButton(icon, title, action) {
        const button = document.createElement("button");
        button.className = "icon-button subtle";
        button.type = "button";
        button.title = title;
        button.setAttribute("aria-label", title);
        button.innerHTML = `<i data-lucide="${icon}"></i>`;
        button.addEventListener("click", action);
        return button;
    }

    function showNote(note) {
        el("NoteTitle").textContent = note.title || note.note_id;
        el("NoteMeta").textContent = `${note.author} · ${date(note.published_at)} · ${note.tags.join(" / ")}`;
        el("NoteBody").textContent = note.description || "暂无正文";
        el("NoteLink").href = note.url;
        el("NoteDialog").showModal();
    }

    function httpUrl(value) {
        try {
            const url = new URL(String(value || ""));
            return ["http:", "https:"].includes(url.protocol) ? url.href : "";
        } catch (_) { return ""; }
    }

    function renderPlatformProducts(feed) {
        const holder = el("PlatformProducts");
        holder.replaceChildren();
        el("ProductMethod").textContent = feed?.method || "";
        if (!feed) {
            el("ProductStatus").textContent = "正在读取今日平台采集结果";
            return;
        }
        const items = feed.items || [];
        el("ProductStatus").textContent = `${feed.date} · ${feed.source_note_count || 0} 篇低粉爆款笔记提取 · 展示 ${items.length} 个挂载商品`;
        if (!items.length) {
            const message = feed.latest_run?.state === "failed"
                ? `今日平台采集失败：${feed.latest_run.message}`
                : "今日通过低粉规则的笔记暂未提取到挂载商品；完成新一轮平台采集后自动更新";
            const empty = document.createElement("div");
            empty.className = "empty-state";
            const text = document.createElement("span");
            text.textContent = message;
            empty.append(text);
            holder.append(empty);
            return;
        }
        items.forEach((product, index) => {
            const card = document.createElement("article");
            card.className = "viral-platform-product-card";
            const imageUrl = (product.images || []).map(httpUrl).find(Boolean);
            if (imageUrl) {
                const image = document.createElement("img");
                image.src = imageUrl;
                image.alt = "";
                image.loading = "lazy";
                image.referrerPolicy = "no-referrer";
                image.addEventListener("error", () => { image.hidden = true; });
                card.append(image);
            } else card.classList.add("no-image");
            const body = document.createElement("div");
            body.className = "viral-platform-product-body";
            const rank = document.createElement("span");
            rank.className = "viral-platform-product-rank";
            rank.textContent = `TOP ${index + 1}`;
            const title = document.createElement("strong");
            title.textContent = product.title;
            const metric = document.createElement("p");
            metric.className = "viral-platform-product-metric";
            metric.textContent = product.deltas_24h
                ? `近 24 小时：收藏 +${number.format(product.deltas_24h.collects)} · 公开互动 +${number.format(product.deltas_24h.interactions)}`
                : `当前收藏 ${number.format(product.collects)} · ${product.interactions_lower_bound ? "公开互动至少" : "公开互动"} ${number.format(product.interactions)}`;
            const meta = document.createElement("p");
            meta.className = "viral-recommend-meta";
            meta.textContent = `${product.author || "作者"} · 粉丝 ${number.format(product.followers)} · 采集于 ${date(product.observed_at)}`;
            const tags = document.createElement("div");
            tags.className = "viral-platform-product-tags";
            [`来源笔记：${product.note_title}`, product.price ? `价格 ${product.price}` : "", product.shop ? `店铺 ${product.shop}` : "", product.supporting_notes > 1 ? `${product.supporting_notes} 篇低粉笔记挂载` : ""].filter(Boolean).forEach((value) => {
                const tag = document.createElement("span");
                tag.textContent = value;
                tags.append(tag);
            });
            const actions = document.createElement("div");
            actions.className = "viral-platform-product-actions";
            for (const [label, value] of [["查看带货笔记", product.note_url], ["打开商品", product.url]]) {
                const href = httpUrl(value);
                if (!href) continue;
                const link = document.createElement("a");
                link.className = "button secondary";
                link.textContent = label;
                link.href = href;
                link.target = "_blank";
                link.rel = "noopener noreferrer";
                actions.append(link);
            }
            body.append(rank, title, metric, meta, tags, actions);
            card.append(body);
            holder.append(card);
        });
    }

    function renderRecommendations(feed) {
        el("Recommendations").replaceChildren();
        el("RecommendMethod").textContent = feed?.method || "";
        if (!feed) {
            el("RecommendStatus").textContent = "正在读取今日推荐";
            return;
        }
        const last = feed.latest_run;
        const count = feed.items.length;
        let status = `${feed.date} · ${feed.batch_count} 批采集 · ${feed.candidate_count} 篇候选 · 推荐 ${count} 篇`;
        if (last?.state === "failed") status += ` · 最近采集失败：${last.message}`;
        else if (["pending", "processing"].includes(last?.state)) status += " · 采集中，完成后自动更新";
        else if (!count) status += feed.batch_count ? " · 暂无符合条件的笔记，可调整关键词或时间范围" : " · 今天尚未采集，请到「采集」设置每日规则";
        el("RecommendStatus").textContent = status;
        el("Login").hidden = !(last?.login_required || (last?.state === "failed" && /登录|Cookie|code=-100|验证/.test(last.message || "")));
        feed.items.forEach((note, index) => {
            const card = document.createElement("article");
            card.className = "viral-recommend-card";
            const title = document.createElement("button");
            title.type = "button";
            title.className = "viral-note-title";
            title.textContent = `${index + 1}. ${note.title || note.note_id}`;
            title.addEventListener("click", () => showNote(note));
            const meta = document.createElement("p");
            meta.className = "viral-recommend-meta";
            meta.textContent = `${note.author || "作者"} · 采集于 ${date(note.observed_at)}${note.partial ? " · 批次部分完成" : ""}`;
            const reasons = document.createElement("ul");
            note.reasons.forEach((text) => {
                const reason = document.createElement("li");
                reason.textContent = text;
                reasons.append(reason);
            });
            const rewrite = document.createElement("button");
            rewrite.type = "button";
            rewrite.className = "button secondary";
            rewrite.textContent = "用这篇一键改写";
            rewrite.addEventListener("click", () => window.dispatchEvent(new CustomEvent("rewrite-note", { detail: { url: note.url } })));
            card.append(title, meta, reasons, rewrite);
            el("Recommendations").append(card);
        });
    }

    function renderRun(run) {
        currentRun = run;
        el("List").replaceChildren();
        const items = run?.items || [];
        el("Table").hidden = !items.length;
        el("Empty").hidden = Boolean(items.length);
        el("Empty").querySelector("span").textContent = !run ? "暂无采集结果" : ["pending", "processing"].includes(run.state) ? "正在搜索和核验数据" : run.state === "failed" ? run.message : "本批次暂无符合条件的笔记";
        el("Export").hidden = !run;
        if (run) el("Export").href = `/api/viral/runs/${encodeURIComponent(run.id)}/export`;
        el("Summary").textContent = run ? `${labels[run.state] || run.state} · 核验 ${run.scanned}/${run.candidates} · 命中 ${run.matched || items.length} · 展示 ${items.length}${run.irrelevant ? ` · 排除不相关 ${run.irrelevant}` : ""}` : "";
        const rule = run?.rules;
        const timeLabel = rule?.time_range === "today" ? `今日发布（${new Date((run.window_start ?? run.created_at) * 1000).toLocaleDateString("zh-CN", { timeZone: "Asia/Shanghai" })}）` : `近 ${rule?.hours} 小时`;
        el("RunRules").textContent = rule ? `${rule.keywords.join(" / ")} · ${timeLabel} · 粉丝 ≤ ${number.format(rule.max_followers)} · 点赞 ≥ ${number.format(rule.min_likes ?? 0)} · 总互动 ≥ ${number.format(rule.min_interactions)} · 互动/粉丝 ≥ ${rule.min_ratio}${run.truncated ? " · 已达搜索页数或核验上限" : ""}` : "";
        for (const note of items) {
            const row = document.createElement("tr");
            const identity = document.createElement("td");
            const main = document.createElement("div");
            main.className = "viral-note";
            if (note.cover) {
                const image = document.createElement("img");
                image.src = note.cover;
                image.alt = "";
                image.loading = "lazy";
                image.referrerPolicy = "no-referrer";
                image.addEventListener("error", () => { image.hidden = true; });
                main.append(image);
            }
            const text = document.createElement("div");
            const title = document.createElement("button");
            title.type = "button";
            title.className = "viral-note-title";
            title.textContent = note.title || note.note_id;
            title.addEventListener("click", () => showNote(note));
            const author = document.createElement("a");
            author.textContent = note.author || note.author_id;
            author.href = `https://www.xiaohongshu.com/user/profile/${encodeURIComponent(note.author_id)}`;
            author.target = "_blank";
            author.rel = "noopener noreferrer";
            text.append(title, author);
            main.append(text);
            identity.append(main);
            row.append(identity);
            for (const key of ["followers", "likes", "collects", "comments", "shares", "ratio", "score"]) {
                const cell = document.createElement("td");
                cell.textContent = note[key] == null ? "未公开" : number.format(note[key]);
                if (key === "score") cell.className = "viral-score";
                row.append(cell);
            }
            const published = document.createElement("td");
            published.className = "viral-published";
            published.textContent = date(note.published_at);
            row.append(published);
            const actions = document.createElement("td");
            actions.append(iconButton("sparkles", "一键改写这篇笔记", () => {
                window.dispatchEvent(new CustomEvent("rewrite-note", { detail: { url: note.url } }));
            }));
            actions.append(iconButton("download", "下载这篇笔记的素材", async (event) => {
                const button = event.currentTarget;
                button.disabled = true;
                try {
                    const result = await api("/api/tasks", { method: "POST", body: JSON.stringify({ content: note.url }) });
                    showToast(`已创建 ${result.tasks.length} 个下载任务`);
                    await refreshState();
                } catch (error) { showToast(error.message, true); }
                finally { button.disabled = false; }
            }));
            row.append(actions);
            el("List").append(row);
        }
        const errors = run?.errors || [];
        const unknown = run?.unknown || 0;
        const shareHidden = run?.share_hidden || 0;
        el("Errors").hidden = !errors.length && !unknown && !shareHidden && run?.state !== "failed";
        el("ErrorSummary").textContent = `采集异常 ${errors.length} · 关键字段缺失 ${unknown}`;
        el("ErrorList").replaceChildren();
        const messages = errors.map((error) => `${error.target}：${error.message}`);
        const reasons = run?.unknown_reasons || {};
        if (reasons.note_fields) messages.push(`${reasons.note_fields} 篇缺少发布时间、点赞、收藏或评论，已排除`);
        if (reasons.author_id) messages.push(`${reasons.author_id} 篇缺少可核验作者 ID，已排除`);
        if (reasons.followers) messages.push(`${reasons.followers} 篇缺少作者粉丝数，已排除`);
        if (unknown && !Object.values(reasons).some(Boolean)) messages.push(`${unknown} 篇笔记的发布时间、互动或作者粉丝数缺失，已排除`);
        if (shareHidden) messages.push(`${shareHidden} 篇未公开分享数；总互动按已公开数据下限计算，并在榜单中标记`);
        if (run?.state === "failed") messages.unshift(run.message);
        messages.forEach((message) => {
            const item = document.createElement("li");
            item.textContent = message;
            el("ErrorList").append(item);
        });
        refreshIcons();
    }

    async function refresh(initial = false) {
        if (loading || !currentUser) return;
        loading = true;
        const revision = generation;
        try {
            const status = await api("/api/viral");
            if (revision !== generation) return;
            activeId = status.active_id;
            const admin = currentUser?.role === "admin";
            el("Controls").disabled = !admin;
            el("Collect").disabled = Boolean(activeId) || !admin;
            el("CollectNow").hidden = !admin;
            el("CollectNow").disabled = Boolean(activeId) || !admin;
            el("Cancel").hidden = !activeId || !admin;
            if (initial) fillSchedule(status.schedule);
            el("Status").textContent = status.daily_selection?.enabled ? `每日 ${status.daily_selection.at}（北京时间） · 自动选品${status.daily_selection.paused ? "待处理，请查看每日计划" : "已开启"}` : activeId ? "正在采集" : status.schedule.enabled ? `每日 ${status.schedule.at}（北京时间） · 定时已开启` : "定时未开启";
            el("NextRun").textContent = status.timing?.next_run_at ? `下次采集：${date(status.timing.next_run_at)}（北京时间） · 后台运行时执行` : "每日定时未开启，可在「采集」页面保存规则并开启";
            if (status.timing?.readiness_message) el("NextRun").textContent += ` · ${status.timing.readiness_message}`;
            if (status.daily_selection?.enabled) el("NextRun").textContent = "每日自动选品已接入知识库，请在「采集 → 每日自动选品」查看计划和日报；下方保留旧版历史榜单。";
            if (!status.runs.some((run) => run.id === selectedId)) selectedId = status.runs[0]?.id || "";
            el("History").replaceChildren(...status.runs.map((run) => new Option(`${date(run.created_at)} · ${run.source === "daily" ? "每日" : "手动"} · ${run.collector === "browser" ? "Edge 页面" : "旧版接口"} · ${labels[run.state]} · ${run.count} 篇`, run.id)));
            if (!status.runs.length) el("History").add(new Option("暂无采集记录", ""));
            el("History").value = selectedId;
            const run = selectedId ? await api(`/api/viral/runs/${encodeURIComponent(selectedId)}`) : null;
            if (revision === generation && (run?.id || "") === selectedId) renderRun(run);
            const [feed, productFeed] = await Promise.all([
                api("/api/viral/recommendations"),
                api("/api/viral/products"),
            ]);
            if (revision === generation) {
                renderRecommendations(feed);
                renderPlatformProducts(productFeed);
            }
        } catch (error) {
            if (revision === generation) {
                el("Status").textContent = error.message;
                el("RecommendStatus").textContent = `推荐刷新失败：${error.message}`;
            }
        } finally {
            if (revision === generation) loading = false;
        }
    }

    async function startCollection() {
        el("Collect").disabled = true;
        el("CollectNow").disabled = true;
        el("Status").textContent = "正在启动 Edge 页面采集";
        try {
            const result = await api("/api/viral/runs", { method: "POST", body: JSON.stringify(rules()) });
            selectedId = result.run.id;
            activeId = result.run.id;
            renderRun(result.run);
            showToast("Edge 页面采集已开始，请勿关闭自动打开的窗口");
            await refresh();
        } catch (error) {
            el("Status").textContent = `采集启动失败：${error.message}`;
            showToast(error.message, true);
        }
        finally {
            const disabled = Boolean(activeId) || currentUser?.role !== "admin";
            el("Collect").disabled = disabled;
            el("CollectNow").disabled = disabled;
        }
    }
    el("Form").addEventListener("submit", async (event) => {
        event.preventDefault();
        await startCollection();
    });
    el("CollectNow").addEventListener("click", startCollection);
    el("Save").addEventListener("click", async () => {
        if (!el("Form").reportValidity()) return;
        el("Save").disabled = true;
        try {
            await api("/api/viral/schedule", { method: "PUT", body: JSON.stringify({ enabled: el("Daily").checked, at: el("Time").value, rules: rules() }) });
            showToast("采集规则已保存");
            await refresh();
        } catch (error) { showToast(error.message, true); }
        finally { el("Save").disabled = false; }
    });
    el("Cancel").addEventListener("click", async () => {
        if (!activeId) return;
        try {
            await api(`/api/viral/runs/${encodeURIComponent(activeId)}`, { method: "DELETE" });
            showToast("已提交取消请求");
            await refresh();
        } catch (error) { showToast(error.message, true); }
    });
    el("History").addEventListener("change", () => {
        selectedId = el("History").value;
        renderRun(null);
        refresh();
    });
    el("Refresh").addEventListener("click", () => refresh());
    el("Login").addEventListener("click", () => document.getElementById("settingsButton")?.click());
    el("NoteClose").addEventListener("click", () => el("NoteDialog").close());
    window.viralWorkspace = {
        async start() {
            this.stop();
            await refresh(true);
            if (currentUser) timer = poll(refresh, 5000);
        },
        stop() {
            clearInterval(timer);
            generation += 1;
            loading = false;
            activeId = null;
            selectedId = "";
            currentRun = null;
            renderRun(currentRun);
            renderRecommendations(null);
            renderPlatformProducts(null);
            el("Login").hidden = true;
            el("NextRun").textContent = "";
            el("NoteDialog").close();
        },
    };
})();
