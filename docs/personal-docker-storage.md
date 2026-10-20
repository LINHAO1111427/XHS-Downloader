# 单人、少量运营账号的数据部署

当前方案：SQLite WAL，单个应用容器、单个 worker，D 盘持久目录绑定到 `/data`。Compose 项目为 `xhs-personal`，入口 `personal_app:create_personal_app`。少量运营账号共用个人工作区，保留原有登录权限和 owner_id；各运营空间的商品、对标、稿件和反馈继续按 space_id/product_id 关联。

这套个人部署沿用本地工具的共享素材库，不提供不同客户之间的文件隔离。未来需要独立客户工作区时使用 `server_app.py` 的隔离部署，并专门迁移归属数据。当前无需引入 PostgreSQL、Redis 或第二个调度实例。

## 数据位置与关系

| 内容 | `/data` 内文件/数据表 | 关联与约束 |
| --- | --- | --- |
| 登录和会话 | users.db | users.id，sessions.user_id |
| 知识与来源 | knowledge.db | 知识条目、课程/案例分类、完整稿件、引用和反馈分别保留 |
| 运营空间/商品/对标 | xhs_operations.db | operation_spaces → operation_products / operation_notes |
| 每日计划 | factory_schedules | 每个 space 一条计划，指定商品、开始日期、北京时间、5 图文＋5 视频 |
| 生成队列/成品 | factory_runs | UNIQUE(space_id,day,content_type,slot)，阶段、重试时间、输出和计费凭据持久化 |
| 素材 | factory_assets | 商品关联、SHA256 去重；原片使用区间保存在生成计划中 |
| 实际发布 | factory_publications | run_id 唯一；实际日期、标题、正文、链接；独立于媒体完成状态 |
| 运营数据 | factory_metric_snapshots | PRIMARY KEY(run_id,observed_on)，按日保存累计值；未填写与零区分 |
| 任务记录 | tasks/*.db | 生图、Live、混剪等任务日志，重启恢复结果与扣费状态 |
| 原片/图文/视频/发布包 | Download/、Exports/ | 数据库存相对路径，文件随数据目录整体备份 |
| 计费与配置 | billing.db、ai_config.json、settings.json | 私有数据，不打进镜像；AI 密钥留在数据卷 |

`storage_schema_migrations` 记录存储迁移版本。版本 1 开启 WAL，验证数据库及外键，增加商品历史、可用素材、发布日期、指标日期索引；幂等执行，拒绝用旧程序启动高版本数据。现有业务表的初始化仍由原模块负责。

单个空间目前只能安排一个主商品。扩品可以先建立对应运营空间；如果以后同一空间需要按日分配多个商品，应先把计划升级为独立 schedule_id，并扩展生成任务的唯一键，不能直接塞进现有单商品计划。

## 本机启动与备份

实际数据：`D:\Workspace\XHS-Downloader\DockerData`，原 `Volume` 保留为切换前副本。容器启动后只写 DockerData。`.install/docker-mode.json` 让原启动/停止脚本转交 Docker，避免双调度。

```powershell
.\start-web.ps1 -NoBrowser
.\stop-web.ps1
.\backup-docker.ps1
docker compose -f deploy/compose.personal.yml ps
```

网址：`http://127.0.0.1:5557`。Docker Desktop 运行后，容器按 restart 策略恢复。每日内容任务由容器调度，不依赖网页打开；机器休眠或 Docker 停止期间不执行。时区固定 Asia/Shanghai。

备份脚本先停止应用，使用 SQLite backup API 取得跨库一致的离线快照，再校验每个文件 SHA256、数据库完整性、外键和数据表行数，最后重新启动。备份输出 `Backups/docker-时间`，不覆盖原备份；请定期复制到服务器或另一块磁盘。备份包含登录信息和 AI 配置，按私有数据管理。

```powershell
.\.venv\Scripts\python.exe server_admin.py verify --data-root Backups/<备份名>
.\.venv\Scripts\python.exe server_admin.py restore --data-root Backups/<备份名> --destination DockerRestoreCheck
```

恢复目标必须是新目录，校验失败时停止。不要用 Windows SQLite 工具打开运行中的 DockerData 数据库；运行时通过应用或 `docker compose exec` 查询，离线后再做主机侧操作。

## 迁移到服务器

1. 运行备份，携带代码及完整备份（含媒体）到服务器。保持单实例，先构建镜像：`docker compose -f deploy/compose.personal.yml build app`。
2. 在备份目录之外恢复到仓库 `DockerData`，让容器用户 10001:10001 读写。镜像安装依赖，数据目录不进入镜像。首次桌面导入用 `storage_transfer.py`；已是 `/data` 的 Docker 备份直接 restore，不重复转换。
3. 文案中转使用已保存的 portable 配置；图片走 `host.docker.internal:8088`。服务器需要配置它自身可达的图片中转和对应密钥，不能指向旧电脑的回环地址。Compose 已提供 host-gateway 映射。
4. 先在服务器本机检查 `/api/ready`、登录、素材预览、已保存计划和备份恢复。远程使用通过 HTTPS 反向代理；把 `XHS_ALLOWED_HOSTS` 加入实际域名并启用 `XHS_WEB_SECURE_COOKIE=1`，保留后端回环监听。
5. 停用旧电脑的任务后再启用服务器计划，确保同一计划只有一个调度实例。小规模单机继续 SQLite；需要多容器写入或多节点调度时，再迁移 PostgreSQL 并引入独立任务队列。

恢复代码不等于回退数据：已经在 Docker 产生的新稿和反馈必须先另做备份。切回桌面时从最新备份恢复到新目录，改回 Windows work_path 和本机图片中转地址，再切换数据目录。不要直接把旧 Volume 当作最新数据覆盖回来。
