# 腾讯 IMA 下载与项目接入

本项目已实现腾讯官方 OpenAPI 读取连接，桌面端不是 API 接入的前置条件。当前电脑的安装包已下载并通过签名及 SHA-256 校验；自动启动安装时被 Windows 管理员策略阻止，未记录为安装成功。

## 下载结果

- Windows x64：2.6.10.5128，安装包大小 227,042,584 字节。
- 本地：`.install/ima/ima.copilot_win_x64_1018_2.6.10_5128.exe`。
- 官方下载地址：<https://app-dl.ima.qq.com/win_channel/ima.copilot_win_x64_1018_2.6.10_5128.exe>。
- SHA-256：`37E79B29536B79F0DB0F203CD9135A196F5A9791D446F7B16E2A3C1FE75F9EB9`，与 WinGet 公开清单相符；Authenticode 状态 `Valid`，签名者为 Tencent Technology (Shenzhen) Company Limited。
- Windows 返回：`Access to %1 has been restricted by your Administrator by policy rule %2.`。没有调整应用控制策略。

官网主页内嵌的下载地址仍为较早的 2.3.0.3717；本次另外核实了 WinGet 清单引用的较新腾讯官方地址。

## 配置步骤

1. 在 <https://ima.qq.com/agent-interface> 登录你的 IMA 账号，获取 Client ID 和 API Key。
2. 打开项目工作台顶部云朵按钮「连接 IMA 知识库」，粘贴这两个值，点击「保存凭证并读取知识库」。
3. 按名称查找知识库，最多勾选 3 个。勾选自动检索并点击「保存选择」。知识库列表支持继续加载。
4. 在「试查」输入一个主题，确认返回的来源与内容正确。然后使用普通文案生成或一键图文改写。

推荐把真实产品资料、优秀笔记、好坏文案对照、目标人群描述和图片拆解分别整理清楚。常用检索词可填写「小红书文案，封面优化」等规则主题；每次生成最多使用前两个常用检索词，留空则按本次产品或笔记标题检索。试查始终使用输入的主题。

连接按当前项目账号保存到知识库数据库同目录的 `ima-connections.json`（默认在 `Volume`）。API Key 不通过配置查询接口返回，不进入生成提示词；凭证仅作为请求头发给 `https://ima.qq.com`。断开连接会清除本项目保存的凭证；更换凭证后需要重新选择知识库。

## 实际读取范围

知识检索每次读取各选定库的首批搜索结果，去重后最多使用 4 条资料、总计 8,000 字，每条最多 3,000 字。界面区分「搜索匹配片段」和「笔记原文」，原文节选会单独标注。

- 搜索返回 `highlight_content` 的资料，可以作为匹配片段参与生成。
- 当媒体类型为 IMA 笔记且 API 授权允许时，进一步读取笔记纯文本。
- PDF、Word、网页等资料当前使用搜索返回的匹配片段；没有提取整个原始文件。只有标题、没有文本的条目不进入参考。
- 这不是整库下载或无限量同步。知识库、搜索结果和原文的可读范围取决于 IMA 对当前凭证授予的权限。
- IMA 未匹配到内容时明确显示结果；搜索鉴权或连接失败会在模型调用和扣费前停止，供修正连接后重试。

检索到的内容会作为参考发送给项目当前配置的文案和图片模型。普通生成与一键图文都会记录参考来源，资料中的案例经历、价格、功效等不自动成为本次产品事实。

## 官方协议依据

官方入口：<https://ima.qq.com/agent-interface>。

入口链接的开发文档：<https://skillhub.cn/skills/tencent-adm/ima-skills>。

官方技能文档包：<https://app-dl.ima.qq.com/skills/ima-skills-1.1.10.zip>，已安装到 `C:/Users/Administrator/.codex/skills/ima-skill`，10 个文件与官方包逐一校验一致；下轮对话可用。凭证保存在 `~/.config/ima/client_id` 和 `~/.config/ima/api_key`。

官方 ZIP 名为 1.1.10，但包内 `meta.json` 仍为 1.1.9。重新下载确认内容相同，没有修改供应商版本号。首次每日更新检查提示更新，同日后续正常调用返回 `code=0`，列出 9 个知识库；供应商修正前可能再次出现每日更新提示。

请求为 HTTPS POST + UTF-8 JSON。请求头为 `ima-openapi-clientid` 与 `ima-openapi-apikey`，同时验证 HTTP 状态和 `{code, msg, data}` 业务状态。实现固定官方域名并拒绝重定向，当前只开放以下读取接口：

| 用途 | 官方接口 |
| --- | --- |
| 搜索和分页列出知识库 | `/openapi/wiki/v1/search_knowledge_base` |
| 验证选定知识库并读取名称 | `/openapi/wiki/v1/get_knowledge_base` |
| 搜索知识条目与匹配片段 | `/openapi/wiki/v1/search_knowledge` |
| 识别媒体类型和笔记引用 | `/openapi/wiki/v1/get_media_info` |
| 读取有权限的笔记原文 | `/openapi/note/v1/get_doc_content`，`target_content_format: 0` |

项目连接接口为 `/api/ima/config`、`/api/ima/libraries`、`/api/ima/preview`，沿用登录和 CSRF 校验。没有增加写入、删除 IMA 云端内容的功能。

## 验证状态

协议、中文编码、凭证隔离、分页、匹配片段/原文区分、生成前检索和异常停止通过隔离测试验证。真实接口的知识库列表使用 `kb_id` / `kb_name`，已兼容这两个字段及文档示例字段。

真实账号验证：成功列出 9 个知识库。按用户选择，将连接保存到「超级管理员」，选中「孟哥火火小红书AI电商知识库」，常用检索词为「文案，封面」，自动检索已启用。LIN 账号没有保留本次连接。

搜索「文案」返回 2 个教程标题；「封面」也返回 2 个标题，但摘要为空，原文接口返回 `220030`：`该文件获取失败，请至ima内查看处理`。因此当前试查可用正文为 0 条，没有声称这些资料已经改善生成。项目会显示读取错误和未纳入参考的提示。需在 IMA 内检查相关资料的可读状态，或将可导出的文档通过项目现有知识库导入功能导入，再试查正文。
