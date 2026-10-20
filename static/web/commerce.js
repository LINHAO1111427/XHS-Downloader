(() => {
    const $ = id => document.getElementById(id);
    const api = (...args) => window.operationBridge.api(...args);
    const toast = (message, error = false) => window.operationBridge.showToast(message, error);
    const labels = {images:"主图", detail_images:"详情图", sku_images:"SKU 规格图", videos:"商品视频"};
    const states = {draft:"待准备", awaiting_review:"网页待核对", platform_draft:"已保存平台草稿", submitted:"平台审核中", published:"已上架"};
    const editor = $("commerceEditor"), dialog = $("commerceBrowserDialog");
    let tasks = [], task = null, snapshot = null, platform = "1688", busy = false;
    const escape = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

    async function run(fn) {
        if (busy) return;
        busy = true;
        dialog.setAttribute("aria-busy", "true");
        const buttons = [...dialog.querySelectorAll("button"), ...editor.querySelectorAll("button")];
        buttons.forEach(b => b.disabled = true);
        try { return await fn(); }
        catch (error) { toast(error.message, true); $("commerceBrowserStatus").textContent = error.message; }
        finally { busy = false; dialog.removeAttribute("aria-busy"); buttons.forEach(b => b.disabled = false); }
    }

    function renderList() {
        const target = $("commerceTaskList");
        target.replaceChildren();
        if (!tasks.length) target.textContent = "到 1688 商品卡片点击「小红书上品」，创建第一个任务。";
        tasks.forEach(item => {
            const b = document.createElement("button");
            b.type = "button"; b.className = "button secondary";
            b.textContent = `${item.title} · ${states[item.state] || item.state}`;
            b.onclick = () => { if (!busy) renderTask(item); };
            target.append(b);
        });
    }

    async function reload() {
        if (!window.operationBridge.currentUser()) return;
        tasks = (await api("/api/commerce/listings")).items;
        renderList();
    }

    function renderVariants() {
        const target = $("commerceVariants");
        target.replaceChildren();
        if (task.variants.length) {
            const title = document.createElement("p");
            title.textContent = "SKU 名称 / 售价 / 库存（在网页按相同规格逐行填写）";
            target.append(title);
        }
        task.variants.forEach((row, index) => {
            const div = document.createElement("div");
            div.className = "commerce-variant";
            div.innerHTML = `<input aria-label="规格名称 ${index+1}" data-sku-field="name" value="${escape(row.name)}"><input aria-label="规格售价 ${index+1}" data-sku-field="sale_price" value="${escape(row.sale_price)}" placeholder="售价"><input aria-label="规格库存 ${index+1}" data-sku-field="stock" value="${escape(row.stock)}" placeholder="库存"><button type="button" class="button secondary">移除</button>`;
            div.querySelectorAll("input").forEach(input => input.oninput = () => row[input.dataset.skuField] = input.value);
            div.querySelector("button").onclick = () => { task.variants.splice(index,1); renderVariants(); };
            target.append(div);
        });
    }

    function renderTask(value) {
        task = structuredClone(value);
        const completed = ["submitted","published"].includes(task.state);
        editor.hidden = false;
        for (const key of ["title","sale_price","stock","shop_name","category","freight_template","notes"]) editor.elements.namedItem(key).value = task[key] || "";
        $("commerceSource").textContent = JSON.stringify({标题:task.source_title, 链接:task.source_url, 采购价格:task.source_price, 参数:task.source_specs, 规格:task.source_skus}, null, 2);
        $("commerceHistory").textContent = JSON.stringify(task.history, null, 2);
        const evidence = $("commerceEvidence");
        evidence.hidden = !task.last_result?.screenshot;
        if (!evidence.hidden) evidence.href = `/api/commerce/listings/${task.id}/evidence/${task.last_result.screenshot}`;
        editor.querySelector('button[type="submit"]').hidden = completed;
        $("commerceRefreshAssets").hidden = completed;
        $("commerceUseSkus").hidden = completed;
        $("commerceTaskStatus").textContent = `${states[task.state] || task.state} · 主图 ${task.assets.images.length} / 详情图 ${task.assets.detail_images.length} / 规格图 ${task.assets.sku_images.length} / 视频 ${task.assets.videos.length}${task.asset_errors.length ? ` · ${task.asset_errors.length} 项源素材缺失` : ""}`;
        $("commercePackage").href = `/api/commerce/listings/${task.id}/package`;
        renderVariants();
        const assets = $("commerceAssets"); assets.replaceChildren();
        Object.entries(labels).forEach(([group,label]) => {
            const h = document.createElement("h3"); h.textContent = `${label} · 选择本次要上传的素材`;
            const div = document.createElement("div"); div.className = "commerce-assets";
            task.assets[group].forEach((asset,index) => {
                const el = document.createElement("label"); el.className = "commerce-asset";
                const src = `/api/commerce/listings/${task.id}/assets/${group}/${index}`;
                el.innerHTML = `${group === "videos" ? `<video src="${src}" controls preload="metadata"></video>` : `<img src="${src}" loading="lazy" alt="${label} ${index+1}">`}<span><input type="checkbox" data-asset-group="${group}" value="${index}" ${task.selected[group]?.includes(index) ? "checked" : ""}> ${label} ${index+1}</span>`;
                div.append(el);
            });
            if (!task.assets[group].length) div.textContent = "暂无此类素材";
            assets.append(h, div);
        });
        editor.querySelectorAll("input,textarea").forEach(el => { el.readOnly = completed; if (el.type === "checkbox") el.disabled = completed; });
        $("commerceVariants").querySelectorAll("button").forEach(el => el.hidden = completed);
    }

    async function saveTask() {
        if (!task) throw new Error("请先选择上品任务");
        const data = {revision:task.revision, variants:task.variants, selected:{}};
        for (const key of ["title","sale_price","stock","shop_name","category","freight_template","notes"]) data[key] = editor.elements.namedItem(key).value;
        for (const group of Object.keys(labels)) data.selected[group] = [...editor.querySelectorAll(`[data-asset-group="${group}"]:checked`)].map(el => Number(el.value));
        const result = await api(`/api/commerce/listings/${task.id}`, {method:"PUT", body:JSON.stringify(data)});
        renderTask(result.task); await reload(); return task;
    }

    async function create(productId) {
        await run(async () => {
            const result = await api("/api/commerce/listings", {method:"POST", body:JSON.stringify({product_id:productId})});
            window.location.hash = "products/listing";
            await reload(); renderTask(result.task);
            toast("上品任务已保存，可编辑售价、库存和素材");
        });
    }

    const roles = {title:"商品标题", sale_price:"售价", stock:"库存", ...labels};
    const aliases = {title:["商品标题","商品名称","请输入商品名称","请输入商品标题"], sale_price:["销售价","售价","商品售价"], stock:["库存","库存数量"], images:["商品主图","主图"], detail_images:["详情图","商品详情图"], sku_images:["规格图","SKU图片"], videos:["主图视频","商品视频"]};
    function renderSnapshot(value) {
        snapshot = value;
        $("commerceBrowserImage").src = `data:image/jpeg;base64,${value.image}`;
        $("commerceBrowserUrl").value = value.url;
        $("commerceBrowserStatus").textContent = "点击预览操作网页；完成登录、选择类目或等待上传后，刷新预览。";
        const target = $("commerceFieldMap"); target.replaceChildren();
        const variants = document.createElement("select"); variants.id = "commerceVariant";
        variants.setAttribute("aria-label", "本次填写的 SKU");
        variants.innerHTML = '<option value="-1">单规格 / 本次不填 SKU 价格库存</option>';
        (task?.variants || []).forEach((v, i) => { const o = document.createElement("option"); o.value = i; o.textContent = `${v.name} · ¥${v.sale_price || "待填"} · 库存 ${v.stock || "待填"}`; variants.append(o); });
        target.append(variants);
        for (const [role,label] of Object.entries(roles)) {
            const file = Object.hasOwn(labels,role);
            const controls = value.controls.filter(c => file ? c.type === "file" : c.type !== "file");
            const row = document.createElement("label"); row.textContent = label;
            const select = document.createElement("select"); select.dataset.mapRole = role;
            const empty = document.createElement("option"); empty.value = ""; empty.textContent = "跳过此项"; select.append(empty);
            controls.forEach((c,i) => {
                const o = document.createElement("option"); o.value = c.id;
                o.textContent = `${c.label || "未命名控件 " + (i+1)}${file ? (c.multiple ? "（多文件）" : "（单文件）") : ""}${c.row ? ` · ${c.row}` : ""}`;
                select.append(o);
            });
            const candidates = controls.filter(c => aliases[role].includes(c.label.replace(/[＊*：:]/g, "").trim()));
            if (candidates.length === 1 && !(task?.variants.length && ["sale_price","stock"].includes(role))) select.value = candidates[0].id;
            row.append(select); target.append(row);
        }
    }

    async function browserAction(action, extra = {}) {
        $("commerceBrowserStatus").textContent = "正在执行，请稍候…";
        const result = await api(`/api/commerce/browser/${platform}`, {method:"POST", body:JSON.stringify({action,...extra})});
        if (result.image) renderSnapshot(result);
        if (result.snapshot) renderSnapshot(result.snapshot);
        if (result.task) { renderTask(result.task); await reload(); }
        return result;
    }

    async function openBrowser(target, url = "") {
        platform = target; snapshot = null;
        $("commerceBrowserImage").removeAttribute("src");
        $("commerceBrowserTitle").textContent = target === "1688" ? "1688 登录与素材采集" : "小红书千帆 · 模拟人工上品";
        $("commerceCapture").hidden = target !== "1688";
        $("commerceMapping").hidden = target !== "xhs";
        if (!dialog.open) dialog.showModal();
        await browserAction("open", {url});
    }

    $("commerceReload").onclick = () => run(reload);
    editor.onsubmit = event => { event.preventDefault(); run(async () => { await saveTask(); toast("上品任务已保存"); }); };
    $("commerceUseSkus").onclick = () => {
        if (!task) return;
        const names = new Set(task.variants.map(v => v.name));
        for (const row of task.source_skus) if (row.name && !names.has(row.name)) { task.variants.push({name:row.name, sale_price:"", stock:""}); names.add(row.name); }
        renderVariants();
    };
    $("commerceRefreshAssets").onclick = () => run(async () => {
        await saveTask();
        const result = await api(`/api/commerce/listings/${task.id}/refresh-assets`, {method:"POST"});
        renderTask(result.task); await reload(); toast("已同步当前采集素材");
    });
    $("commerceOpen1688").onclick = () => run(() => openBrowser("1688", ($("alibabaUrls").value.match(/https?:\/\/[^\s<>"，。]+/) || [""])[0]));
    $("commerceOpenXhs").onclick = () => run(async () => { if (!["published","submitted"].includes(task?.state)) await saveTask(); await openBrowser("xhs"); });
    $("commerceGo").onclick = () => run(() => browserAction("open", {url:$("commerceBrowserUrl").value}));
    $("commerceSnapshot").onclick = () => run(() => browserAction("snapshot"));
    $("commerceHideBrowser").onclick = () => dialog.close();
    $("commerceCloseBrowser").onclick = () => run(async () => { await browserAction("close"); snapshot = null; dialog.close(); });
    let pointerStart = null;
    const previewPoint = event => {
        const box = $("commerceBrowserImage").getBoundingClientRect();
        return {x:Math.max(0,Math.min(1280,(event.clientX-box.left)*1280/box.width)), y:Math.max(0,Math.min(900,(event.clientY-box.top)*900/box.height))};
    };
    $("commerceBrowserImage").onpointerdown = event => {
        if (busy || event.button !== 0) return;
        pointerStart = previewPoint(event);
        event.target.setPointerCapture(event.pointerId);
    };
    $("commerceBrowserImage").onpointercancel = () => { pointerStart = null; };
    $("commerceBrowserImage").onpointerup = event => {
        if (!pointerStart) return;
        const start = pointerStart, end = previewPoint(event); pointerStart = null;
        run(async () => {
            if (!snapshot) throw new Error("请先刷新网页预览");
            const drag = Math.hypot(end.x-start.x,end.y-start.y) > 5;
            await browserAction("input", {kind:drag ? "drag" : "click", revision:snapshot.revision, ...start, to_x:end.x, to_y:end.y});
        });
    };
    dialog.querySelectorAll("[data-commerce-key]").forEach(b => b.onclick = () => run(() => browserAction("input", {kind:"key", key:b.dataset.commerceKey, revision:snapshot?.revision || ""})));
    dialog.querySelectorAll("[data-commerce-scroll]").forEach(b => b.onclick = () => run(() => browserAction("input", {kind:"scroll", delta:Number(b.dataset.commerceScroll), revision:snapshot?.revision || ""})));
    $("commerceType").onclick = () => run(async () => {
        const text = $("commerceBrowserText").value; $("commerceBrowserText").value = "";
        await browserAction("input", {kind:"text", text, revision:snapshot?.revision || ""});
    });
    $("commerceCapture").onclick = () => run(async () => {
        const result = await browserAction("collect");
        await loadAlibabaProducts();
        $("commerceBrowserStatus").textContent = `已保存 ${result.product.title} · ${result.local_image_count} 张图片 · ${result.product.videos.length} 个视频 · ${result.product.asset_status.state === "ready" ? "已识别素材已保存" : "部分素材待补齐"}`;
    });
    $("commerceFill").onclick = () => run(async () => {
        if (!task || !snapshot) throw new Error("请先选择任务并刷新网页");
        const mapping = Object.fromEntries([...$("commerceFieldMap").querySelectorAll("select[data-map-role]")].filter(s=>s.value).map(s=>[s.dataset.mapRole,s.value]));
        if (!Object.keys(mapping).length) throw new Error("请选择至少一个网页控件");
        const result = await browserAction("fill", {task_id:task.id, revision:snapshot.revision, mapping, variant_index:Number($("commerceVariant").value)});
        $("commerceBrowserStatus").textContent = result.events.map(e => `${roles[e.field]}：${({verified:"已回读核对",upload_selected:"已选择文件，等待网页上传",failed:"操作中断，请核对",mismatch:"页面回读不一致"})[e.state]}`).join("；");
    });
    $("commerceSaveDraft").onclick = () => run(async () => {
        const result = await browserAction("save_draft", {task_id:task?.id || ""});
        $("commerceBrowserStatus").textContent = result.saved ? "网页显示草稿保存成功" : "已点击保存，请检查页面提示与必填项";
    });
    $("commerceVerify").onclick = () => run(() => browserAction("verify", {task_id:task?.id || "", external_id:$("commerceExternalId").value.trim()}));
    window.addEventListener("hashchange", () => { if (location.hash === "#products/listing") run(reload); });
    window.commerceWorkspace = {create, reload, stop:() => { task = null; tasks = []; snapshot = null; dialog.close(); editor.hidden = true; $("commerceTaskList").replaceChildren(); $("commerceBrowserImage").removeAttribute("src"); }};
    if (location.hash === "#products/listing") reload().catch(() => {});
})();
