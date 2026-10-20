# 服务器部署与收费准备

当前按用户最新要求提供 **10 人试运营版本**，默认配置与上线步骤见 [10 人上线说明](trial-10-launch.md)。
后续仍计划接入微信支付 + 支付宝，本地管理员保持无限使用。下文 100 人以上的配置作为后续扩容参考。

## 已落实的改动

- `server_app.py` 提供独立服务器入口，数据默认在 `ServerVolume`，容器内为 `/data`。
  `start-web.ps1` 和本地 `Volume` 继续用于本地版本；管理员仍免扣点。
- 每个用户有独立素材、Cookie、下载运行实例、知识库、产品库和任务管理器。
  原下载核心的单例现在支持隔离实例，设置、临时文件和下载记录随工作区分开。
- 服务器管理员通过命令行初始化，默认关闭注册；公网首个访客不再自动成为管理员。
  登录 Cookie 强制 HTTPS，增加 Host 校验、私有响应禁止缓存、写操作限流和空间检查。
- 扣点和退款使用事务；幂等标识与用户、操作和金额绑定；已退款请求须重新发起。
  管理员充值核对用户存在、记录操作人并支持重复请求防重。
- 同步文案、单图生成使用持久化请求结果；网络重试可重放结果，失败自动退款。
  服务重启时给未完成的同步请求退点，并明确标记中断，避免自动重复调用上游。
- 支付订单按整数「分」计价；订单状态与发点在同一事务内提交。
  重复通知、金额错误、商户/应用错误、币种错误、交易号重复均有检查。
- 微信 v3 的 RSA 验签、通知解密、密钥标识/时间窗检查，以及支付宝 RSA2 验签已有实现和测试。
  未配置渠道的通知返回失败，网页购买保持关闭，尚未启用真实收款。
- AI 默认最多 4 个请求执行；媒体渲染默认同时 1 个，共享排队容量 10 个。
  动态商品浏览器默认同时 1 个；原有笔记浏览器采集仍串行运行。
  多层渲染调用共享同一并发限制，本地独立进程保留原有使用方式。
- 提供健康检查、独占运行锁、Docker/Caddy HTTPS 配置、账本对账和离线备份恢复验证。

## 需要多大的服务器

「100 人在线浏览」和「100 人同时生成视频」的资源要求差距很大。以下假设文本/图片 AI
通过付费外部 API 调用，服务器负责网页、采集、存储及少量 FFmpeg 视频任务。

| 使用情况 | 建议起点 | 说明 |
| --- | --- | --- |
| 10 人试运营，视频依次执行 | 4 vCPU / 8 GB RAM / 150 GB SSD | 当前默认配置，先完成目标服务器验收 |
| 100–200 人在线，生成错峰，视频并行 1–2 个 | 8 vCPU / 16 GB RAM / 200 GB SSD | 后续扩容参考，需重新配置容量并压测 |
| 视频较多、浏览器采集较多 | 16 vCPU / 32 GB RAM / 300–500 GB SSD | 仍按队列限制并发；浏览器和媒体进程的峰值决定内存 |
| 100 人同时提交持续生成任务、要求不中断服务 | Web 4–8 核 8–16 GB + 独立媒体工作节点 8–16 核 16–32 GB + PostgreSQL/Redis/对象存储 | 需要下一阶段完成分布式任务和数据库迁移后再启用多实例 |

带宽建议起步 **20–50 Mbps**，成品文件走对象存储/CDN 后再按监控调整。
例如 100 人各下载 20 MB 成品，总流量约 2 GB；20 Mbps 理想情况下也需约 13 分钟才能传完，
因此单看 CPU 核数不够。200 GB 磁盘也要预留系统、临时渲染、备份空间和成品保留周期。
AI 费用、对象存储、流量与云服务器费用分开核算。以上配置不含本地大模型/GPU推理需求。

当前生产入口是**单进程、单主机**：`--workers 1`。SQLite WAL 保证本机事务，并不提供跨机高可用。
运行锁会阻止第二个进程使用同一目录，避免重复定时任务及误恢复未完成计费。
默认最多常驻 12 个工作区，普通账号总名额为 10 个，管理员另计。工作区暂未做自动闲置回收；这个上限是
运行期间访问过的工作区数，不等于同时在线人数。超过该规模先做工作区生命周期和分布式迁移，
不要只把 worker 数量调大。

## Vercel 与中国用户

建议本项目的**前端和后端同源部署在常驻服务器**，不要把当前整个程序直接放入 Vercel Functions。
原因是项目依赖 SQLite 本地持久化、媒体文件、浏览器、FFmpeg、后台线程及长时间任务。
Vercel Functions 的请求/响应体限制与运行时长上限也会影响现有 64 MB 图片和 128 MB 音频上传。

中国大陆用户访问境外服务会受跨境网络、运营商、地区与时间段影响。Vercel 的香港区域
可以缩短部分请求路径，但不等于中国大陆节点，也不是大陆访问稳定性的保证。
如果用户主要在大陆，优先考虑大陆云服务器和域名备案；若先用香港服务器试运营，
应从电信、联通、移动网络分别测试登录、上传、生成和下载。网站可达和服务器访问 AI 上游
是两条不同网络链路，两者都要测。

2026-09-20 已读取的官方资料（上线时再核对套餐限制）：

- https://vercel.com/docs/functions/limitations ：页面当前列出函数请求/响应体 4.5 MB 限制；运行时长因套餐及运行时而异。
- https://vercel.com/docs/regions ：列有香港 `hkg1` 等区域；中国大陆未列为普通 Functions 区域。
- https://vercel.com/docs/functions/runtimes/python

## Linux / Docker 启动

先在目标 Linux 服务器装好 Docker Compose，准备域名 DNS，开放 TCP 80/443；后端 8000 仅在容器网络内访问。

```bash
cp deploy/server.env.example deploy/server.env
# 编辑 server.env 的域名和允许的 Host，保留 localhost、127.0.0.1 供健康检查。
docker compose -f deploy/compose.yml build app
docker compose -f deploy/compose.yml run --rm app python server_admin.py init-admin --data-root /data
docker compose -f deploy/compose.yml up -d
docker compose -f deploy/compose.yml ps
docker compose -f deploy/compose.yml logs --tail 100 app
```

初始化通过交互输入密码，避免命令行历史中留下密码。管理员登录后配置可从服务器访问的 AI 上游，
再按需要开放注册。你的电脑上的 `127.0.0.1:8088` 在容器内代表容器自身，应填写服务器实际可达的地址。
生产 `server.env`、私钥、本地 `Volume` 和现有用户数据均排除在 Docker 构建上下文之外。

容器使用非 root 用户和 Playwright 的 seccomp 配置以支持 Chromium 用户命名空间沙箱；
`deploy/chromium-seccomp.json` 来自 Playwright v1.55.0 官方仓库的 `utils/docker/seccomp_profile.json`。
它保留默认拒绝规则并允许浏览器创建所需的命名空间。目标内核也需允许非特权用户命名空间。

下载器首次使用确认仍由用户完成。服务器没有用户电脑桌面，因此扫码弹窗/打开文件夹/读取剪贴板
会给出提示；用户使用上传、网页下载和自己的 Cookie。将来若提供网页扫码，需实现独立的二维码
传输和会话流程，不能让用户操作服务器桌面。

## 收费前的接入与验收

目前商品包价格沿用既有配置，只完成可靠账务基础，真实购买按钮保持关闭。
支付渠道开启之前还需：微信/支付宝商户开通、正式应用 ID、商户号、签名私钥、平台验签公钥、
HTTPS 通知地址，并实现官方下单/查询订单接口与前端付款码流程。

回调入口已预留：

- `POST /api/payments/callback/wechat`
- `POST /api/payments/callback/alipay`

设置 `XHS_PAYMENTS_CONFIG=/data/payments/config.json` 后可加载验签配置；密钥文件和配置都放在
私有数据目录，微信公钥可同时配置多个标识以支持轮换。此配置只开启验签回调，**不会开启购买**。
正式商户验证之前不要向用户展示付款入口。

```json
{
  "wechat": {
    "app_id": "APP_ID",
    "merchant_id": "MERCHANT_ID",
    "api_v3_key": "32_BYTE_API_V3_KEY",
    "public_keys": {"WECHAT_PAY_PUBLIC_KEY_ID": "wechat-public.pem"}
  },
  "alipay": {
    "app_id": "APP_ID",
    "seller_id": "SELLER_ID",
    "public_key": "alipay-public.pem"
  }
}
```

`BillingStore.settle_verified_order` 仅允许验签通过的服务端通知/官方查询结果调用。
它不接受浏览器「支付成功」作为证据。接入正式下单时固定订单金额、积分和渠道快照，
用同一订单号重试超时请求，接上订单查询补偿，处理关单与退款/撤销，并完成日对账。

正式收费至少跑通两渠道的小额真实交易、重复通知、通知丢失后查询补账、错误金额、
付款后服务重启、退款以及人工对账。现有自动测试使用本地生成的签名样本，并不替代商户联调。

## 运维、备份与上线验收

```bash
docker compose -f deploy/compose.yml exec app python server_admin.py audit --data-root /data
```

`/api/ready` 检查应用启动、数据库和剩余空间；业务/资金指标还需接入你的监控服务。
至少监控 5xx、任务失败率/等待时间、磁盘、内存、账本差异与上游调用费用。
对账失败时先暂停充值入口、保留账本和通知原文，在备份上定位差异。

备份命令要求暂停应用，确保多个数据库和媒体文件属于同一个时间点。SQLite 通过 backup API
复制并执行完整性检查，而不是仅复制正在写入的 `.db` 文件。示例：

```bash
docker compose -f deploy/compose.yml stop app
mkdir -p /srv/xhs-backups
# 确保备份目录对容器 UID 10001 可写。
sudo chown 10001:10001 /srv/xhs-backups
docker compose -f deploy/compose.yml run --rm -v /srv/xhs-backups:/backups app \
  python server_admin.py backup --data-root /data --destination /backups/RELEASE_DATE
docker compose -f deploy/compose.yml up -d app
```

备份目录应异机保留；定期在新数据卷恢复并执行 `audit` 和登录/素材下载验证。
源码回滚脚本只恢复这次修改的源码，不回滚资金账本或删除运行数据。数据库恢复需保持收款暂停，
并先处理恢复点之后已成功付款的订单，避免丢账。

广泛开放给 100+ 用户前还有明确验收项：

1. 在目标 Linux 机器完成镜像构建、真实浏览器采集/上传/下载/AI/视频链路验证。
2. 进行 120+ 用户混合场景压测，观察 p95、峰值 RAM、队列、磁盘与上游限额；轻量接口压测单独记结果。
3. 长任务统一迁移到持久化工作队列。本次 10 人版本已持久化批量图片与主要媒体任务历史，
   重启后标明中断并恢复批量图片未完成步骤的扣点；跨节点执行和所有任务的自动续跑仍需后续完成。
4. 完成两个支付渠道的下单、补单、退款和日对账，并用正式商户小额交易验收。
5. 对租户媒体总量、保留周期和外部抓取目标做运营配置，接上对象存储/CDN及自动告警。

因此本轮测试通过代表已覆盖的边界成立；外部平台变动、网络波动、进程中断以及未经实测的容量
仍需通过上述验收和监控处理。

## 本轮验证记录

- `python -m unittest discover -s tests -p 'test_*.py'`：284 项通过。
- 最后增加的 3 项容量测试也通过，覆盖跨用户浏览器并发上限、渲染嵌套调用和失败后释放执行名额；
  受影响的服务器接口与动态商品采集测试再次通过。
- `python tests/load_server.py --users 120 --rounds 3`：120 个模拟账号，360 次并发额度查询，
  0 失败，p50 469 ms / p95 703 ms / 最大 750 ms。数据来自本地环境，未调用收费 AI 或媒体任务。
- `python tests/check_server_browser.py`：真实 HTTPS 浏览器登录、普通用户设置入口、响应丢失后刷新重试通过；
  生成调用 1 次、扣点 1 次、页面脚本错误 0 个。
- Linux Docker 镜像构建通过；容器内实测启动、管理员无限额度、真实下载核心工作区隔离、
  FFmpeg 生成 MP4、Chromium 沙箱启动及本地页面读取通过。
- 备份数据恢复、跨日退款、并发扣点、100 次重复支付通知、支付签名与金额校验均包含在自动测试中。
- 源码回滚在额外副本上执行，核对原始 SHA-256；工作目录保留修改后的版本，本地实际账号数据未用于测试。

完整证据放在 `output/server-readiness/VERIFICATION.txt`；部署文件按这份文档使用。
