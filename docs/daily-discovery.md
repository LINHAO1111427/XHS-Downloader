# 每日自动选品

2026-09-29 起，个人部署使用「采集 → 每日自动选品」。后台每 15 秒检查一次北京时间，默认每天 09:00 执行。首次接通沿用已保存的选品方向：潮玩、家居、女生精致小物。页面可以修改方向、时间、每批上限和互动门槛。

## 每天执行的工作

1. 每个方向分别采集近两天的高赞和最新搜索页样本；小红书 MCP 对两天只能提供“一周内”粗筛，详情时间会再次按 48 小时精确过滤。启用挂商品图文范围时，每个子批次扩大候选窗口，推荐仍最多 10 条。
2. 每个批次重新读取当前 `/data/knowledge.db` 的课程、已启用用户要求和相关确认反馈；关联账号时读取本地对标与运营反馈。保存完整选品计划和来源摘要。本地方法缺失时暂停，不跳过知识库。
3. 主筛选使用近两天、作者粉丝严格少于 1000、仅图文且必须存在明确商品容器；知识库中更严格的粉丝、点赞、互动和加购门槛会叠加生效。字段缺失保留未知，不填写为零。
4. 保存完整标题、正文、评论样本、链接、采集时间和真实字段。粉丝数据在同一服务内缓存 6 小时并保留观测时间。只有明确商品结构中的字段才作为挂载商品，笔记标题不猜作商品名。
5. 日报按已取得互动和互动/粉丝的可解释排序给出最多 10 条优先核验线索，同作者最多 2 条。商品 24 小时加购、销量、货源成本和利润独立待核验。空结果与采集未完成分别展示。

## 持久化与中断

配置保存在 `/data/discovery-settings.json` 的 `daily_selection` 字段，日报在 `/data/market_discovery.db` 的 `daily_selection_reports` 表。每个关键词/排序的子任务先保存标识，再开始执行；保留每次尝试、正文和互动快照。

每天最多生成一份日报。当天错过时间会补执行，过去停机的日期不伪造报告。正在手动采集时等待，不与每日任务重叠。重启会保留已完成批次；中断、登录失效、验证、限流或连接异常会暂停队列，后续日期也不自动反复重试。处理后点击「处理登录后继续」。跨日恢复保留原报告，新采集归入今日。

关闭网页不影响后台计划；电脑、Docker 和后台服务需要运行。个人部署迁移脚本关闭旧版每日低粉榜调度，避免两套任务重复抓取。

## Linux 服务

安装脚本支持 Windows AMD64、Linux AMD64 和 macOS ARM64，固定上游 v2.5.0 并验证发布文件 SHA256。`McpProcess.binary()` 根据实际系统选择二进制，服务使用已有独立会话文件。每日计划启动时启动本地服务；设置外部 `XHS_MCP_URL` 时连接外部服务。

```powershell
.\.venv\Scripts\python.exe scripts/install_xhs_mcp.py --data-root DockerData --platform linux-amd64
```

Docker 挂载中的二进制需要执行权限。首次运行需要准备上游自带浏览器。每日任务的扫码登录入口在「数据源连接与登录 → 小红书 MCP」，与旧采集 Cookie 分开。

```text
GET  /api/discovery/daily             当前计划、运行状态、最近日报
PUT  /api/discovery/daily             保存计划（管理员、CSRF）
POST /api/discovery/daily/run         提前执行今日计划，不重复已完成日报
POST /api/discovery/daily/resume      清除暂停，从未完成方向继续
GET  /api/discovery/daily/YYYY-MM-DD  完整日报（所属管理员可见）
```

## 验证

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_daily_selection tests.test_market_discovery tests.test_selection_strategy tests.test_discovery_web
.\.venv\Scripts\python.exe -m tests.check_auto_selection_browser
```

隔离测试覆盖定时补执行、去重、知识来源、严格边界、未知指标、服务重启、跨日恢复、权限及页面保存/查看。隔离测试数据不进入运行中的用户数据库；真实平台采集结果单独记录。

## 一键抓取近48小时挂商品低粉图文

- `POST /api/discovery/daily/quick-run`（管理员 + CSRF）会固定近两天、粉丝严格少于1000、必须挂载商品、仅图文，并优先使用账号商品与类目关键词。
- 每次子任务会重新读取 `/data/knowledge.db`；日报记录 `knowledge_scope`、规则来源 ID、实际生效条件与挂商品样本数。
- MCP 返回的一周粗粒度结果会在详情时间戳处再过滤到 48 小时；无商品、视频笔记、粉丝越界或指标缺失不会进入推荐列表，但原始批次仍保留。
- 平台未公开的加购、销量、成本和利润不推算；需要登录、验证或限流时任务暂停并保留已采样本。
