(() => {
    const el = (id) => document.getElementById(id);
    let libraries = new Map();
    let selected = new Set();
    let cursor = "";
    let busy = false;
    let owner = "";

    function current() { return currentUser?.id === owner && el("imaDialog").open; }
    function renderLibraries() {
        el("imaLibraries").replaceChildren();
        for (const item of libraries.values()) {
            const label = document.createElement("label"); label.className = "check-field";
            const input = document.createElement("input"); input.type = "checkbox"; input.value = item.id; input.checked = selected.has(item.id);
            input.addEventListener("change", () => {
                if (input.checked && selected.size >= 3) { input.checked = false; showToast("最多选择 3 个知识库", true); return; }
                if (input.checked) selected.add(item.id); else selected.delete(item.id);
            });
            label.append(input, document.createTextNode(item.name)); el("imaLibraries").append(label);
        }
    }
    function configView(config) {
        el("imaClientId").value = config.client_id;
        el("imaApiKey").value = "";
        el("imaApiKey").placeholder = config.api_key_configured ? "已保存；留空保留现有密钥" : "填写官方页面提供的 API Key";
        el("imaEnabled").checked = config.enabled;
        el("imaSearchTerms").value = config.search_terms;
        selected = new Set(config.libraries.map((item) => item.id));
        libraries = new Map(config.libraries.map((item) => [item.id, item]));
        renderLibraries();
        el("imaStatus").textContent = config.enabled ? `已启用 ${config.libraries.length} 个知识库` : config.configured ? "凭证已保存，选择知识库后可启用自动检索" : "请先获取并填写官方凭证";
    }
    async function work(action) {
        if (busy) return;
        busy = true;
        const controls = [...el("imaDialog").querySelectorAll("button, input")].filter((node) => !node.classList.contains("dialog-close"));
        controls.forEach((node) => { node.disabled = true; });
        try { await action(); }
        catch (error) { if (current()) { el("imaStatus").textContent = error.message; showToast(error.message, true); } }
        finally { busy = false; controls.forEach((node) => { node.disabled = false; }); }
    }
    async function readLibraries(append = false) {
        const result = await api(`/api/ima/libraries?query=${encodeURIComponent(el("imaLibrarySearch").value.trim())}&cursor=${encodeURIComponent(append ? cursor : "")}`);
        if (!current()) return;
        if (!append) libraries = new Map([...libraries].filter(([id]) => selected.has(id)));
        result.items.forEach((item) => libraries.set(item.id, item));
        cursor = result.next_cursor || "";
        el("imaMoreLibraries").hidden = result.is_end || !cursor;
        renderLibraries();
        el("imaStatus").textContent = `连接成功，当前显示 ${libraries.size} 个知识库。勾选后保存。`;
    }
    el("imaSettingsButton").addEventListener("click", () => {
        owner = currentUser?.id || "";
        el("imaDialog").showModal(); el("imaPreviewResult").replaceChildren();
        el("imaStatus").textContent = "读取本地配置…";
        work(async () => { const config = await api("/api/ima/config"); if (current()) configView(config); });
    });
    el("imaDialog").addEventListener("close", () => {
        el("imaApiKey").value = ""; el("imaClientId").value = "";
        el("imaPreviewResult").replaceChildren(); el("imaLibraries").replaceChildren();
        libraries.clear(); selected.clear(); owner = "";
    });
    el("imaCredentialsForm").addEventListener("submit", (event) => {
        event.preventDefault();
        work(async () => {
            const body = { client_id: el("imaClientId").value.trim() };
            if (el("imaApiKey").value.trim()) body.api_key = el("imaApiKey").value.trim();
            const config = await api("/api/ima/config", { method: "PUT", body: JSON.stringify(body) });
            if (!current()) return;
            configView(config); el("imaStatus").textContent = "正在连接腾讯 IMA…";
            await readLibraries();
        });
    });
    el("imaSearchLibraries").addEventListener("click", () => work(() => readLibraries()));
    el("imaMoreLibraries").addEventListener("click", () => work(() => readLibraries(true)));
    el("imaSelectionForm").addEventListener("submit", (event) => {
        event.preventDefault();
        work(async () => {
            const config = await api("/api/ima/config", { method: "PUT", body: JSON.stringify({
                knowledge_base_ids: [...selected], enabled: el("imaEnabled").checked, search_terms: el("imaSearchTerms").value.trim(),
            }) });
            if (current()) { configView(config); showToast("IMA 知识库选择已保存"); }
        });
    });
    el("imaPreviewButton").addEventListener("click", () => work(async () => {
        const query = el("imaPreviewQuery").value.trim(); if (!query) throw new Error("请填写试查主题");
        el("imaStatus").textContent = "正在检索知识库…";
        const result = await api("/api/ima/preview", { method: "POST", body: JSON.stringify({ query }) });
        if (!current()) return;
        el("imaStatus").textContent = result.status; el("imaPreviewResult").replaceChildren();
        for (const source of result.sources) {
            const article = document.createElement("article");
            const title = document.createElement("strong"); title.textContent = `${source.library} / ${source.title}`;
            const kind = document.createElement("p"); kind.textContent = `${source.kind}${source.truncated ? "（节选）" : ""}`;
            const text = document.createElement("p"); text.textContent = source.excerpt;
            article.append(title, kind, text); el("imaPreviewResult").append(article);
        }
        for (const warning of result.warnings) { const line = document.createElement("p"); line.textContent = warning; el("imaPreviewResult").append(line); }
    }));
    el("imaDisconnect").addEventListener("click", () => work(async () => {
        const config = await api("/api/ima/config", { method: "DELETE" });
        if (current()) { configView(config); el("imaPreviewResult").replaceChildren(); el("imaStatus").textContent = "已断开连接并清除本项目保存的凭证"; }
    }));
})();
