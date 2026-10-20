# 10 人试运营上线说明

当前发布目标：10 个普通试用账号，管理员单独保留，单服务器、单进程运行。先试用，微信和支付宝正式收款暂未启用。
这是经过自动化验证的试运营版本；外部 AI、采集平台和目标服务器网络仍需实机验收。

## 服务器与默认配置

建议起点：**4 vCPU / 8 GB 内存 / 150 GB SSD / 20 Mbps 带宽**。AI 通过外部 API 调用；此配置不含本地大模型推理。
若多人经常生成视频、转录音频或使用 AI 物品运动，建议从 8 vCPU / 16 GB 开始。

Compose 给应用容器 3 核、6 GB 内存，为系统和 HTTPS 网关留出余量。默认环境配置：

| 项目 | 默认值 |
| --- | --- |
| 普通账号总名额 | 10，停用账号仍占名额，管理员不占名额 |
| 常驻工作区上限 | 12，包含管理员工作区 |
| 同时写请求 | 12，每位用户同时 1 个 |
| AI 请求同时执行 | 4，繁忙超时后提示重试并退回失败步骤点数 |
| 媒体渲染同时执行 | 1，共享排队容量 10 |
| 每工作区每类媒体任务 | 最多 2 个未完成任务 |
| 动态商品浏览器 | 同时 1 个 |
| 最低剩余磁盘空间 | 2 GB；低于该值拒绝新写入 |

前后端放在同一台常驻服务器、同一域名。主要面向中国大陆用户时，优先采用国内服务器和备案域名。
10 人同时操作页面属于此版本的目标；耗时视频任务依次执行。实际生成时间还受片长、模型响应和上游额度影响。

## 部署

在 Linux 服务器安装 Docker Engine 和 Compose 插件，准备域名 DNS，开放 TCP 80/443。
完整发布包为 `output/trial-10/MODIFIED_FILE.zip`，解压到一个新的应用目录后执行：

```bash
cp deploy/server.env.example deploy/server.env
# 将 app.example.com 改成自己的域名；ALLOWED_HOSTS 保留 localhost、127.0.0.1。
docker compose -f deploy/compose.yml build app
docker compose -f deploy/compose.yml run --rm app python server_admin.py init-admin --data-root /data
docker compose -f deploy/compose.yml up -d
docker compose -f deploy/compose.yml ps
docker compose -f deploy/compose.yml logs --tail 100 app
curl --fail https://YOUR_DOMAIN/api/ready
```

最后一条应返回 `{"ok":true}`。密码在交互终端输入，至少 10 位且包含字母、数字。
升级前停止应用并备份；沿用原目录和 Compose 项目名，避免误用新数据卷。
`docker compose down -v` 会删除数据卷，正常停止和升级使用 `stop` / `up -d`。

管理员登录后：

1. 配置服务器可访问的 AI 地址、API 密钥和模型，验证文本与图片生成。
2. 在「用户管理 → 开通试用账号」创建普通账号。默认保持公开注册关闭；用户登录后修改初始密码。
3. 每个用户填写自己的平台 Cookie，完成下载器首次使用确认，上传自己的素材。
4. 普通用户沿用每日 20 点试用额度。管理员可通过已有赠点接口分配试用点数；账本保留操作人和防重记录。
5. 本地继续使用原启动方式和 `Volume`。服务器用独立 `ServerVolume` / `/data`，本地超级管理员无限使用。

镜像包含抖音、快手解析适配器源码和许可证，只初始化空运行目录；本机 Cookie、数据库、密钥与个人素材不随镜像和发布包上传。
Linux Chromium 使用项目提供的 seccomp 配置；目标宿主机需要支持非特权用户命名空间。

## 功能状态与上线验收

| 功能 | 自动化覆盖 | 目标服务器验收 |
| --- | --- | --- |
| 登录、账号开通、权限、用户隔离 | 接口与真实 HTTPS 浏览器测试 | 管理员及两个普通账号登录，互查私有文件应为 404 |
| 文案生成、图片生成、知识库 | 回归与模拟上游；同步生成重试防重扣 | 正式模型完成文本、单图、批量图各一次，核对内容与余额 |
| 批量修图 | 持久化任务、成功图片与计费步骤；重复请求找回原任务 | 刷新查看任务，重启检查历史与退款 |
| 混剪、图片成片、Live Photo、清晰增强 | 任务历史持久化；容器内真实 FFmpeg 与浏览器检查 | 实际素材分别生成、下载播放；AI 物品运动另验外部提供方 |
| 一键改写、内容工厂 | 已有回归；本次补内容工厂中断计费保护 | 真实商品素材生成并检查成品，确认定时计划 |
| 小红书、商品页、抖音、快手采集 | 适配器导入与采集逻辑回归 | 有效 Cookie 和真实链接各测一次，观察外部限流或验证码 |
| 微信支付、支付宝 | 账本、回调验签、金额校验已具备，购买保持关闭 | 正式收费前补下单、查单补偿、退款、对账及商户小额实付验收 |
| 桌面剪贴板、打开文件夹、桌面扫码 | 本地保留 | 网页用上传、下载和 Cookie；服务器版不使用用户电脑桌面功能 |

批量修图及主要媒体任务的已完成记录在重启后保留，执行中的步骤标记失败并说明中断；重新提交剩余内容即可。
本轮未实现所有任务的自动断点续跑。采集下载等其他后台任务仍需观察实际平台反馈。
内容工厂先写恢复凭据再扣点，结果落盘后才清除凭据；工作区重新启动时恢复未结算步骤。
普通批量修图的未完成计费步骤则在整个服务启动时统一恢复，即使对应用户尚未登录。

## 运维

每日观察容器健康、内存、磁盘及任务失败原因，并执行账本对账：

```bash
docker compose -f deploy/compose.yml exec app python server_admin.py audit --data-root /data
docker stats --no-stream
df -h
```

备份示例（安排短暂停机，等待在途任务完成）：

```bash
mkdir -p /srv/xhs-backups
sudo chown 10001:10001 /srv/xhs-backups
docker compose -f deploy/compose.yml stop app
docker compose -f deploy/compose.yml run --rm -v /srv/xhs-backups:/backups app \
  python server_admin.py backup --data-root /data --destination /backups/UNIQUE_BACKUP_NAME
docker compose -f deploy/compose.yml up -d app
```

每次使用新备份名称，将备份复制到另一台机器，并定期在新数据卷中恢复、登录、下载素材及对账。
代码回滚脚本只处理本次源码变更，不恢复账本或删除用户资料；已有任务数据库可留在数据卷中。

## 测试边界

`tests/check_trial_load.py` 使用 10 个模拟普通用户、真实 HTTP 和 SQLite，覆盖 150 个请求。
其中故意注入 30 次 AI 上游失败检查退款，以及 10 次越权访问检查隔离；这些预期响应单独统计。
AI 由测试提供返回，不产生真实模型费用，测试延迟不代表正式模型生成速度。
详细命令、实际结果、原始文件哈希和回滚副本测试见 `output/trial-10/VERIFICATION.txt`。
