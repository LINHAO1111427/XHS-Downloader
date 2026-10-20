/* Saved observations only: grouping never manufactures followers, sales or links. */
(() => {
    'use strict';
    const number = value => typeof value === 'number' && Number.isFinite(value) && value >= 0;
    const fields = ['likes', 'collects', 'comments', 'shares'];
    const interactions = note => {
        const values = fields.map(key => note[key]).filter(number);
        return { value: values.length ? values.reduce((a, b) => a + b, 0) : null, complete: values.length === 4 };
    };
    const stamp = item => number(item.collected_at) ? item.collected_at : 0;
    const sourceName = platform => ({ huitun: '灰豚公开榜单', xiaohongshu: '小红书', douyin: '抖音' }[platform] || '其他来源');
    const day = value => new Date(value * 1000).toLocaleDateString('en-CA', { timeZone: 'Asia/Shanghai' });
    const accountKey = note => `${note.platform}:${note.author_id || note.source_key}`;
    function inPeriod(value, period, now) {
        if (period === 'today') return value > 0 && day(value) === day(now);
        if (period === 'week') return value > 0 && value <= now && now - value <= 7 * 86400;
        return true;
    }
    function model(runs, filters = {}, now = Date.now() / 1000) {
        const { period = 'all', platform = '', query = '', maximum = 1000, minimum = 500 } = filters;
        const batches = runs.filter(run => (!platform || run.request?.platform === platform) && inPeriod(run.created_at, period, now));
        const latest = new Map();
        for (const run of batches) for (const original of run.items || []) {
            const key = original.source_key || `${original.platform}:${original.kind}:${original.note_id}`;
            const item = { ...original, source_key: key, run_id: run.id };
            if (!latest.has(key) || stamp(item) > stamp(latest.get(key))) latest.set(key, item);
        }
        const all = [...latest.values()];
        const notes = all.filter(item => item.kind === 'note').sort((a, b) => stamp(b) - stamp(a));
        const groups = new Map();
        for (const note of notes) {
            const key = accountKey(note);
            if (!groups.has(key)) groups.set(key, { key, latest: note, notes: [] });
            groups.get(key).notes.push(note);
        }
        const accounts = [...groups.values()].map(group => ({ ...group,
            matching: group.notes.filter(note => number(interactions(note).value) && interactions(note).value >= minimum),
        })).filter(group => number(group.latest.followers) && group.latest.followers < maximum && group.matching.length);
        accounts.sort((a, b) => Math.max(...b.matching.map(n => interactions(n).value)) - Math.max(...a.matching.map(n => interactions(n).value)));
        const eligible = new Set(accounts.flatMap(group => group.matching.map(note => note.source_key)));
        const products = new Map();
        for (const item of all) for (const product of item.products || []) {
            const id = product.product_id || product.url;
            if (!id) continue;
            const key = `${product.source || item.origin_platform || item.platform}:${id}`;
            if (!products.has(key)) products.set(key, { key, product, observed_at: stamp(item), notes: [], pages: [] });
            const group = products.get(key);
            if (stamp(item) > group.observed_at) { group.product = product; group.observed_at = stamp(item); }
            const target = item.kind === 'note' ? group.notes : group.pages;
            if (!target.some(row => row.source_key === item.source_key)) target.push(item);
        }
        const goods = [...products.values()].map(group => ({ ...group,
            matching: group.notes.filter(note => eligible.has(note.source_key)),
        })).sort((a, b) => b.matching.length - a.matching.length || b.observed_at - a.observed_at);
        const search = String(query).trim().toLocaleLowerCase();
        const matches = (...values) => !search || values.flat().join(' ').toLocaleLowerCase().includes(search);
        const result = {
            notes: notes.filter(n => matches(n.title, n.body, n.author, (n.products || []).map(p => p.title))),
            accounts: accounts.filter(g => matches(g.latest.author, g.matching.map(n => [n.title, n.body, ...(n.products || []).map(p => p.title)].join(' ')))),
            products: goods.filter(g => matches(g.product.title, g.product.shop_name, g.notes.map(n => `${n.author} ${n.title}`))),
            batches: batches.filter(r => matches(sourceName(r.request?.platform), r.request?.query, r.errors, r.warnings)).sort((a, b) => b.created_at - a.created_at),
        };
        result.totals = { notes: result.notes.length, accounts: result.accounts.length,
            products: result.products.length,
            errors: result.batches.filter(r => ['failed', 'partial', 'interrupted', 'cancelled'].includes(r.state)).length };
        return result;
    }
    window.discoveryBoardModel = { model, interactions, number, inPeriod };
    const root = document.getElementById('discoveryBoard');
    if (!root) return;
    root.innerHTML = `
      <div class="db-heading"><div><span class="db-eyebrow">采集结果总览</span><h2>先看账号，再看商品</h2><p>把已保存的批次放在一起看，点开笔记就能核对依据。</p></div><div class="db-actions"><button type="button" class="button secondary" id="dbReload">刷新总览</button><button type="button" class="button primary" id="dbConfigure">新建采集 / 调整计划</button></div></div>
      <div id="dbHealth" class="db-health" role="status"></div>
      <div class="db-metrics" aria-label="采集结果统计">
        <button type="button" data-db-view="accounts"><span>低粉高互动账号</span><strong id="dbAccountsCount">—</strong><small>按作者合并，查看关联笔记</small></button>
        <button type="button" data-db-view="products"><span>已采商品</span><strong id="dbProductsCount">—</strong><small>可单独筛选低粉账号关联商品</small></button>
        <button type="button" data-db-view="notes"><span>已采笔记</span><strong id="dbNotesCount">—</strong><small>跨批次去重，保留最新快照</small></button>
        <button type="button" data-db-view="batches"><span>有异常的批次</span><strong id="dbErrorsCount">—</strong><small>点开查看失败或缺失原因</small></button>
      </div>
      <details class="db-explanation"><summary>现在是怎么采集和筛选的？</summary><ol><li><strong>确定方向</strong><span>每日计划读取本地知识、账号商品与已确认反馈；手动采集保存本次选品依据。</span></li><li><strong>获取样本</strong><span>灰豚每榜公开首屏最多10条；小红书走分享链接或已登录搜索；抖音提供搜索和热榜。</span></li><li><strong>核对账号</strong><span>保留正文、作者、粉丝、互动、时间与来源。缺粉丝数不会确认为低粉；搜索结果不等于全站。</span></li><li><strong>关联商品</strong><span>只使用返回的明确商品字段。销量、24小时加购和本篇归因加购分别核验，不由互动推算。</span></li></ol><p>下方总览按采集时间筛选，聚合最近100批可见记录；只表示当时的快照。每日推荐还会检查发布时间、商品方向及计划条件，所以推荐数可能少于总览。</p></details>
      <div class="db-toolbar"><label>采集时间<select id="dbPeriod"><option value="all">全部已采</option><option value="today">北京时间今天</option><option value="week">近7天采集</option></select></label><label>来源<select id="dbPlatform"><option value="">全部来源</option><option value="huitun">灰豚公开榜单</option><option value="xiaohongshu">小红书</option><option value="douyin">抖音</option></select></label><label class="db-search">搜索账号、笔记或商品<input id="dbSearch" type="search" placeholder="如：香薰、拼豆、作者昵称"></label></div>
      <div class="db-thresholds"><label>粉丝少于 <input id="dbMaximum" type="number" min="1" max="1000000" value="1000"></label><label>已知互动至少 <input id="dbMinimum" type="number" min="0" max="100000000" value="500"></label><span>仅调整总览，不修改每日计划。互动 = 赞＋藏＋评＋分享。</span></div>
      <div class="db-tabs" aria-label="结果视图"><button type="button" data-db-tab="accounts">低粉账号</button><button type="button" data-db-tab="products">关联商品</button><button type="button" data-db-tab="notes">全部笔记</button><button type="button" data-db-tab="batches">采集批次</button></div>
      <div class="db-results-heading"><p id="dbScope" role="status"></p><label id="dbProductFilter" hidden><input id="dbLinkedOnly" type="checkbox">仅看低粉高互动账号关联商品</label><label id="dbBatchFilter" hidden><input id="dbErrorsOnly" type="checkbox">仅看异常批次</label></div>
      <div id="dbResults" class="db-grid" aria-live="polite"></div>
      <div class="db-pagination"><button type="button" class="button secondary" id="dbPrevious">上一页</button><span id="dbPage"></span><button type="button" class="button secondary" id="dbNext">下一页</button></div>`;
    const el = id => document.getElementById('db' + id);
    const date = value => number(value) && value > 0 ? new Date(value * 1000).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '时间未取得';
    const count = value => number(value) ? value.toLocaleString('zh-CN') : '未取得';
    const node = (tag, text, cls) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n; };
    const button = (text, action, cls = 'db-link') => { const b = node('button', text, cls); b.type = 'button'; b.addEventListener('click', action); return b; };
    const states = { pending: '等待中', processing: '采集中', success: '已完成', partial: '部分完成', failed: '失败', interrupted: '已中断', cancelled: '已停止' };
    let cache = new Map(), runs = [], callbacks = {}, generation = 0, signature = '', view = 'accounts', page = 0, incomplete = 0, daily = null, busy = false, thresholdEdited = false, statusError = '';
    function filters() {
        return { period: el('Period').value, platform: el('Platform').value, query: el('Search').value,
            maximum: Math.max(1, Math.min(1000000, Number(el('Maximum').value) || 1000)),
            minimum: Math.max(0, Math.min(100000000, Number(el('Minimum').value) || 0)) };
    }
    function provenance(note) {
        return `${sourceName(note.platform)}${note.platform === 'huitun' ? ' · 第三方快照' : ''} · 采集 ${date(note.collected_at)}`;
    }
    function noteButton(note) { return button(note.title || '查看完整笔记', () => callbacks.openNote?.(note), 'db-note-title'); }
    function batchButton(id) { return button('查看原始批次', () => callbacks.openBatch?.(id)); }
    function productLink(product) {
        try {
            const url = new URL(product.url);
            if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) return null;
            if (!['xiaohongshu.com', '1688.com', 'taobao.com', 'tmall.com', 'jd.com', 'douyin.com'].some(host => url.hostname === host || url.hostname.endsWith('.' + host))) return null;
            const a = node('a', '打开商品来源', 'db-link'); a.href = url.href; a.target = '_blank'; a.rel = 'noopener noreferrer'; return a;
        } catch (_) { return null; }
    }
    function cardHeading(title, badge, cls = '') {
        const card = node('article', undefined, 'db-card'), top = node('div', undefined, 'db-card-top');
        top.append(node('h3', title), node('span', badge, 'db-badge ' + cls)); card.append(top); return card;
    }
    function accountCard(group) {
        const n = group.latest, card = cardHeading(n.author || '作者昵称未取得', `粉丝 ${count(n.followers)}`, 'db-positive');
        card.append(node('p', provenance(n), 'db-meta'));
        const products = new Set(group.matching.flatMap(n => (n.products || []).map(p => p.product_id || p.url).filter(Boolean)));
        card.append(node('p', `${group.matching.length} 篇达到互动门槛 · ${products.size} 个关联商品`, 'db-card-summary'));
        const best = [...group.matching].sort((a, b) => (interactions(b).value || 0) - (interactions(a).value || 0));
        for (const note of best.slice(0, 2)) {
            const evidence = node('div', undefined, 'db-note-snippet'), total = interactions(note);
            evidence.append(noteButton(note), node('p', `赞 ${count(note.likes)} · 藏 ${count(note.collects)} · 评 ${count(note.comments)} · 分享 ${count(note.shares)}`, 'db-meta'),
                node('p', `${total.complete ? '互动合计' : '已知互动至少'} ${count(total.value)}${total.complete ? '' : '，有指标未取得'}`, 'db-meta'));
            card.append(evidence);
        }
        if (!products.size) card.append(node('p', '未取得挂载商品；可作为内容与账号参考。', 'db-gap'));
        if (best.length > 2) {
            const details = node('details'); details.append(node('summary', `再看 ${best.length - 2} 篇笔记`));
            best.slice(2).forEach(note => details.append(noteButton(note))); card.append(details);
        }
        card.append(batchButton(best[0].run_id)); return card;
    }
    function productCard(group) {
        const p = group.product, card = cardHeading(p.title || '商品名称未取得', group.matching.length ? '低粉账号关联' : '商品线索');
        card.append(node('p', `${group.notes.length} 篇关联笔记 · ${new Set(group.notes.map(accountKey)).size} 位作者 · ${group.matching.length} 篇达到当前门槛`, 'db-card-summary'),
            node('p', `最近采集 ${date(group.observed_at)} · 商品编号 ${p.product_id || '未取得'}`, 'db-meta'));
        const cart = p.cart_24h;
        card.append(node('p', `页面价格：${p.price === null || p.price === undefined || p.price === '' ? '未取得' : p.price}（以规格为准）`, 'db-meta'),
            node('p', `24小时加购：${cart?.status === 'observed' && number(cart.value) ? `${cart.comparison === 'gte' ? '≥' : ''}${count(cart.value)} · ${date(cart.observed_at)}` : '未取得'}`, 'db-meta'),
            node('p', `销量原文：${p.sales_text || '未取得'}；保留来源口径，不推算真实成交。`, 'db-gap'));
        const details = node('details'); details.open = true; details.append(node('summary', `查看关联笔记（${group.notes.length}）`));
        group.notes.forEach(note => { const row = node('div', undefined, 'db-note-snippet'); row.append(noteButton(note), node('p', `${note.author || '作者未取得'} · 粉丝 ${count(note.followers)} · 点赞 ${count(note.likes)}`, 'db-meta')); details.append(row); });
        if (group.notes.length) card.append(details);
        const link = productLink(p); if (link) card.append(link);
        const first = group.notes[0] || group.pages[0]; if (first) card.append(batchButton(first.run_id));
        return card;
    }
    function noteCard(note) {
        const total = interactions(note), card = cardHeading(note.author || '作者未取得', `粉丝 ${count(note.followers)}`);
        card.append(noteButton(note), node('p', `${total.complete ? '互动' : '已知互动至少'} ${count(total.value)} · 挂载商品 ${(note.products || []).length} 个`, 'db-card-summary'),
            node('p', (note.body || '正文未取得').slice(0, 130), 'db-excerpt'), node('p', provenance(note), 'db-meta'),
            node('p', `发布 ${date(note.published_at)} · ${note.selection?.label || '待核验'}`, 'db-meta'), batchButton(note.run_id));
        return card;
    }
    function batchCard(run) {
        const request = run.request || {}, bad = ['partial', 'failed', 'interrupted', 'cancelled'].includes(run.state);
        const board = { low_fan: '低粉爆文榜', commerce: '带货笔记榜', goods: '商品榜', all: '三个榜单' }[request.huitun_board];
        const card = cardHeading(`${sourceName(request.platform)} · ${board || ({search:'关键词搜索',detail:'笔记详情',product:'商品详情',hot:'热榜'}[request.mode] || '')}`, states[run.state] || run.state, bad ? 'db-warning' : '');
        card.append(node('p', `${date(run.created_at)} · 已保存 ${(run.items || []).length} 条${run.collection_host === 'host_worker' ? ' · 主机补采' : run.collection_host === 'host_cli' ? ' · 主机采集后导入' : run.automation ? ' · 每日任务' : ''}`, 'db-card-summary'));
        if (request.query && request.mode === 'search') card.append(node('p', `关键词：${request.query}`, 'db-meta'));
        for (const error of run.errors || []) card.append(node('p', error, 'db-gap'));
        if (!run.items?.length) card.append(node('p', bad ? '本批未取得数据，不能据此判断没有合格账号或商品。' : '本批没有返回记录。', 'db-meta'));
        if (run.warnings?.length) { const d = node('details'); d.append(node('summary', '查看来源与采集范围')); run.warnings.forEach(w => d.append(node('p', w, 'db-meta'))); card.append(d); }
        card.append(batchButton(run.id)); return card;
    }
    function health() {
        const target = el('Health'); target.replaceChildren();
        if (busy) target.append(node('p', '正在汇总已保存批次…'));
        if (statusError) target.append(node('p', `刷新失败：${statusError}。下面保留上次已加载结果。`));
        if (incomplete) target.append(node('p', `${incomplete} 个批次暂未读到，当前统计不完整；可点击“刷新总览”重试。`));
        const report = daily?.latest;
        if (report) target.append(node('p', `每日自动选品 ${report.day}：${report.state === 'success' ? '已完成' : report.state === 'processing' ? '采集中' : '有数据缺口'} · 日报样本 ${report.sample_count || 0} 条 · 优先核验 ${report.recommended_count || 0} 条。${report.message || ''}`));
        const cfg = daily?.config;
        if (cfg) target.append(node('p', `计划：${cfg.enabled ? `每日 ${cfg.at}` : '未启用自动运行'} · ${cfg.selection?.product || cfg.selection?.category || (cfg.keywords || []).join('、') || '未设置方向'}。手动批次与主机导入也会出现在下方总览。`, 'db-meta'));
        const imported = runs.filter(r => r.collection_host === 'host_cli');
        const worker = runs.find(r => r.collection_host === 'host_worker' && r.items?.length);
        if (worker) target.append(node('p', `最近主机补采 ${date(worker.finished_at)}：已保存 ${worker.items.length} 条；${worker.errors?.length || 0} 条失败。点击“已采商品”查看详情；低粉账号关联条件可单独勾选。`, 'db-meta'));
        if (imported.length) target.append(node('p', `包含 ${imported.length} 个主机采集导入批次；这些成功记录不代表容器自动采集已恢复。`, 'db-meta'));
        target.classList.toggle('db-health-warning', Boolean(statusError || incomplete || report && !['success','processing'].includes(report.state)));
    }
    function render() {
        const result = model(runs, filters());
        for (const [name, key] of [['Accounts','accounts'],['Products','products'],['Notes','notes'],['Errors','errors']]) el(name+'Count').textContent = count(result.totals[key]);
        root.querySelectorAll('[data-db-tab], [data-db-view]').forEach(b => { const active = (b.dataset.dbTab || b.dataset.dbView) === view; b.classList.toggle('active', active); b.setAttribute('aria-pressed', String(active)); });
        el('ProductFilter').hidden = view !== 'products'; el('BatchFilter').hidden = view !== 'batches';
        let rows = result[view];
        if (view === 'products' && el('LinkedOnly').checked) rows = rows.filter(p => p.matching.length);
        if (view === 'batches' && el('ErrorsOnly').checked) rows = rows.filter(r => ['failed','partial','interrupted','cancelled'].includes(r.state));
        page = Math.min(page, Math.max(0, Math.ceil(rows.length / 12) - 1));
        const names = {accounts:'个账号',products:'个商品',notes:'篇笔记',batches:'个批次'};
        el('Scope').textContent = `${rows.length} ${names[view]} · 已读取 ${runs.length} 个批次${incomplete ? '（统计尚不完整）' : ''} · 卡片数据为采集快照${el('Search').value ? ' · 已应用搜索' : ''}`;
        const create = {accounts:accountCard,products:productCard,notes:noteCard,batches:batchCard}[view];
        el('Results').replaceChildren(...rows.slice(page * 12, (page + 1) * 12).map(create));
        if (!rows.length) {
            const empty = node('div', undefined, 'db-empty');
            empty.append(node('h3', busy ? '正在加载保存的记录' : '当前条件下没有可展示的记录'),
                node('p', view === 'products' && el('LinkedOnly').checked ? '低粉高互动笔记可能没有返回商品。可取消“仅看低粉高互动账号关联商品”，或切换采集时间查看历史线索。' : '可清空搜索、选择“全部已采”，或打开采集批次查看数据缺口。'));
            empty.append(button('重置查看条件', resetFilters)); el('Results').append(empty);
        }
        el('Page').textContent = rows.length ? `${page+1} / ${Math.ceil(rows.length/12)} 页` : '0 条';
        el('Previous').disabled = !page; el('Next').disabled = (page+1)*12 >= rows.length;
        health();
    }
    function resetFilters() { el('Period').value='all'; el('Platform').value=''; el('Search').value=''; el('Maximum').value='1000'; el('Minimum').value=String(daily?.config?.min_interactions ?? 500); el('LinkedOnly').checked=false; el('ErrorsOnly').checked=false; thresholdEdited=false; page=0; render(); }
    function setView(next) { view=next; page=0; render(); }
    root.querySelectorAll('[data-db-tab], [data-db-view]').forEach(b => b.addEventListener('click', () => { if (b.dataset.dbView === 'batches') el('ErrorsOnly').checked=true; setView(b.dataset.dbTab || b.dataset.dbView); }));
    for (const id of ['Period','Platform','LinkedOnly','ErrorsOnly']) el(id).addEventListener('change', () => { page=0; render(); });
    for (const id of ['Maximum','Minimum']) el(id).addEventListener('change', () => { thresholdEdited=true; page=0; render(); });
    el('Search').addEventListener('input', () => { page=0; render(); });
    el('Previous').addEventListener('click', () => { page--; render(); }); el('Next').addEventListener('click', () => { page++; render(); });
    el('Configure').addEventListener('click', () => document.getElementById('discoveryTitle')?.scrollIntoView({behavior:'smooth',block:'start'}));
    el('Reload').addEventListener('click', () => { signature=''; cache.clear(); callbacks.refresh?.(); });
    window.discoveryBoard = {
        async update(status, dailyStatus, handlers) {
            callbacks=handlers; daily=dailyStatus; statusError='';
            const minimum = el('Minimum').value;
            if (!thresholdEdited) el('Minimum').value=String(daily?.config?.min_interactions ?? 500);
            const summaries=(status.runs || []).slice(0,100), key=JSON.stringify(summaries.map(r => [r.id,r.state,r.count]));
            if (key === signature) { if (minimum !== el('Minimum').value) render(); else health(); return; }
            signature=key; const epoch=++generation; busy=true; health();
            const pending=[...summaries], found=new Map(); let failures=0;
            async function worker() {
                while (pending.length && epoch === generation) {
                    const summary=pending.shift(), version=`${summary.state}:${summary.count}`;
                    try {
                        const old=cache.get(summary.id);
                        const run=old?.version===version && !['pending','processing'].includes(summary.state) ? old.run : await api(`/api/discovery/runs/${encodeURIComponent(summary.id)}`);
                        if (epoch !== generation) return;
                        found.set(summary.id,{run,version});
                    } catch (_) { failures++; }
                }
            }
            await Promise.all(Array.from({length:Math.min(4,pending.length)},worker));
            if (epoch !== generation) return;
            cache=found; runs=summaries.map(r => found.get(r.id)?.run).filter(Boolean); incomplete=failures; busy=false; render();
        },
        error(message) { statusError=message; health(); },
        reset() { generation++; cache.clear(); runs=[]; signature=''; callbacks={}; daily=null; busy=false; incomplete=0; statusError=''; thresholdEdited=false; view='accounts'; page=0; resetFilters(); },
    };
    render();
})();
