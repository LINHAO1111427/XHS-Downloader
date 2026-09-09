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

    function renderRun(run) {
        currentRun = run;
        el("List").replaceChildren();
        const items = run?.items || [];
        el("Table").hidden = !items.length;
        el("Empty").hidden = Boolean(items.length);
        el("Empty").querySelector("span").textContent = !run ? "暂无采集结果" : ["pending", "processing"].includes(run.state) ? "正在搜索和核验数据" : run.state === "failed" ? run.message : "本批次暂无符合条件的笔记";
        el("Export").hidden = !run;
        if (run) el("Export").href = `/api/viral/runs/${encodeURIComponent(run.id)}/export`;
        el("Summary").textContent = run ? `${labels[run.state] || run.state} · 核验 ${run.scanned}/${run.candidates} · 命中 ${run.matched || items.length} · 展示 ${items.length}` : "";
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
                cell.textContent = number.format(note[key]);
                if (key === "score") cell.className = "viral-score";
                row.append(cell);
            }
            const published = document.createElement("td");
            published.className = "viral-published";
            published.textContent = date(note.published_at);
            row.append(published);
            const actions = document.createElement("td");
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
        el("Errors").hidden = !errors.length && !unknown && run?.state !== "failed";
        el("ErrorSummary").textContent = `采集异常 ${errors.length} · 关键字段缺失 ${unknown}`;
        el("ErrorList").replaceChildren();
        const messages = errors.map((error) => `${error.target}：${error.message}`);
        if (unknown) messages.push(`${unknown} 篇笔记的发布时间、互动或作者粉丝数缺失，已排除`);
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
            el("Cancel").hidden = !activeId || !admin;
            if (initial) fillSchedule(status.schedule);
            el("Status").textContent = activeId ? "正在采集" : status.schedule.enabled ? `每日 ${status.schedule.at}（北京时间） · 定时已开启` : "定时未开启";
            if (!status.runs.some((run) => run.id === selectedId)) selectedId = status.runs[0]?.id || "";
            el("History").replaceChildren(...status.runs.map((run) => new Option(`${date(run.created_at)} · ${run.source === "daily" ? "每日" : "手动"} · ${labels[run.state]} · ${run.count} 篇`, run.id)));
            if (!status.runs.length) el("History").add(new Option("暂无采集记录", ""));
            el("History").value = selectedId;
            const run = selectedId ? await api(`/api/viral/runs/${encodeURIComponent(selectedId)}`) : null;
            if (revision === generation && (run?.id || "") === selectedId) renderRun(run);
        } catch (error) {
            if (revision === generation) el("Status").textContent = error.message;
        } finally {
            if (revision === generation) loading = false;
        }
    }

    el("Form").addEventListener("submit", async (event) => {
        event.preventDefault();
        el("Collect").disabled = true;
        try {
            const result = await api("/api/viral/runs", { method: "POST", body: JSON.stringify(rules()) });
            selectedId = result.run.id;
            activeId = result.run.id;
            renderRun(result.run);
            await refresh();
        } catch (error) { showToast(error.message, true); }
        finally { el("Collect").disabled = Boolean(activeId) || currentUser?.role !== "admin"; }
    });
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
    el("NoteClose").addEventListener("click", () => el("NoteDialog").close());
    window.viralWorkspace = {
        async start() {
            this.stop();
            await refresh(true);
            if (currentUser) timer = setInterval(refresh, 3000);
        },
        stop() {
            clearInterval(timer);
            generation += 1;
            loading = false;
            activeId = null;
            selectedId = "";
            currentRun = null;
            renderRun(currentRun);
            el("NoteDialog").close();
        },
    };
})();
