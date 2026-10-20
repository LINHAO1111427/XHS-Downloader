# 小红书 MCP 与抖音 DouK 采集

工作台「采集 → 多平台选品线索」提供两个入口。管理员配置登录并发起任务，已登录成员可以查看结果、完整正文、评论样本和导出 CSV。结果属于候选样本，不自动加入“已验证爆款”榜单。

## 小红书

1. 在项目虚拟环境运行 `.venv\Scripts\python.exe scripts/install_xhs_mcp.py`。安装器下载上游 `xpzouying/xiaohongshu-mcp` 的 `v2.5.0` Windows AMD64 发布文件，核对 GitHub 发布资产 SHA256，保留 Apache-2.0 许可证。文件位于 `Volume/tools/xhs-mcp/`。
2. 在采集页展开「数据源连接与登录」，点击「启动服务」。首次启动，上游可能需要准备浏览器；进程日志位于 `Volume/xhs-mcp/service.log`。
3. 点击「检查连接」「扫码登录」，用小红书 App 确认，再检查连接。MCP 与原有 Edge 登录状态独立。
4. 选择关键词搜索，或粘贴带 `xsec_token` 的完整笔记链接。搜索使用 MCP 返回的当前搜索页，不提供不存在的翻页能力。

应用托管的 MCP 监听 `127.0.0.1:18060`，使用本地生成的鉴权 Token。程序只调用登录状态、二维码、搜索、详情与作者查询。关闭应用时终止其启动的 MCP 进程；外部服务由外部部署管理。

其他系统或已有独立服务可设置 `XHS_MCP_URL`、`XHS_MCP_TOKEN`；地址由服务端环境配置。外部服务的版本应兼容上述 HTTP 接口。

## 抖音

复用 `vendor/douk_downloader` 中的 DouK-Downloader（GPL-3.0），通过原有参数签名与 HTTP 请求代码接入综合搜索、指定作品详情、首屏评论和抖音热榜。

- 在抖音官网登录后，从浏览器开发者工具 Network 中选中请求，复制 Request Headers 的 Cookie 到工作台并保存。凭证只写入服务端，前端仅显示是否已配置。也可使用已有 `DOUYIN_COOKIE` / `DY_COOKIE` 环境变量。
- 每次搜索最多 3 页、最多 30 条结果，每条最多 30 条首屏评论；默认 1 页、10 条作品、10 条评论。
- 热榜保存热词、榜位和热度，类型为 `topic`；热度不映射成点赞或销量。热词可复制到搜索框继续寻找作品。
- 登录、验证、网络及响应格式错误记录为失败或部分完成，不以“0 条优质商品”解释。

## 存储及数据口径

- `Volume/market_discovery.db`：`discovery_runs` 保存完整批次，`discovery_snapshots` 按 `平台:类型:作品ID` 和批次保存观察快照。同批去重，跨批保留多次快照。
- `Volume/discovery-settings.json`：本地连接凭证，界面和查询接口不返回凭证正文；已被现有 `/Volume/` Git 忽略规则覆盖。
- 标题、正文、平台链接、作者、粉丝数、互动字段、返回的指标原文、采集时间、来源、评论文本一起保存。缺失数字为 `null`，与真实 `0` 分开；缩略数字原文保留在 `metrics_raw`。
- 小红书记录返回页面内的评论样本，抖音记录首屏评论样本；数量上限不代表完整评论覆盖。作者数据缺失时保留正文并标注该批部分完成。
- 两个入口当前没有商品销量和近 24 小时加购数据接口，也不以内容热度估算这两个字段。
- 本次新增采集入口不生成文案。后续将候选用于创作时，继续沿用账号商品关联、本地知识库检索、实际来源引用及账号草稿保存流程。

## API 与验证

`GET /api/discovery` 查询配置状态和历史摘要；`POST /api/discovery/runs` 发起后台采集；`GET /api/discovery/runs/{id}` 查询完整结果；`DELETE /api/discovery/runs/{id}` 请求停止；`GET /api/discovery/runs/{id}/export` 导出含完整正文和评论 JSON 的 UTF-8 BOM CSV。启动与凭证写入沿用管理员会话、CSRF 校验。

```powershell
.venv\Scripts\python.exe -m unittest tests.test_market_discovery tests.test_discovery_web tests.test_platform_sources tests.test_viral_web tests.test_viral_notes -q
.venv\Scripts\python.exe -m tests.check_discovery_browser
node --check static/web/discovery.js
```

自动化测试使用隔离数据库和平台响应。浏览器检查覆盖两数据源选择、正文、评论、复制、CSV、刷新后历史与手机布局；平台真实采集结果需与服务连接和登录状态一起核验。

## 采集中的本地选品方法

采集页增加“查看本次选品计划”和账号、商品、同款、同类、需求、场景输入。`POST /api/discovery/plan` 预览；`POST /api/discovery/runs` 在任务开始时重新读取本地知识，并保存 `selection_plan`。计划中的关键词按钮只填写下一批搜索词，保留单批规模上限。

选品过程按本地课程的广选、严筛、多测组织：小红书优先，抖音结果回小红书核验；结合功能、颜值、情绪、性价比等购买理由。`selection_strategy.py` 对当前启用的本地方法检索依据原文关键词，记录条目 ID、更新时间、内容摘要和原文哈希；未命中则明确显示方法依据待补充。活跃的 note/general 长期用户要求单独保留，不被相关性排序挤掉。相关已确认经验、历史商品分析、当前账号对标及反馈分别展示。评分、实际填写的运营数据和问题案例各自保留。

每条结果保留 `selection`：笔记条件、词语相关性、评论样本中的购买意向/疑虑/场景词、购买理由假设和待核验项。词语标记需要结合原文复核。热榜只进“热词灵感”；抖音不会直接进入小红书优先核验结果；全部原始样本可随时查看。

可选笔记条件为“广选”“7天且粉丝<1000”“北京时间今日且粉丝<1000、点赞≥500”。后者与真实24h加购严格>200预设来自此前用户需求记录 `docs/xhs-product-collection-research.md`。加购门槛可调整，独立于笔记条件；当前 MCP 和 DouK 没有已验证的商品加购/销量字段，所以商品状态始终待核验。缺失不作零，不将点赞、问链接或历史案例加购当作当前销量。人工补齐成本、售价、供应和素材能力，再进行小批量测品。

关联账号的计划、历史批次和 CSV 仅所属用户可读取；查询与保存时校验商品所属账号。未关联账号的公共采集保持既有可见范围。旧批次没有选品快照时显示旧记录提示，不追溯重写旧结果。CSV 保存完整计划和逐条评价，便于按当时来源复核。
