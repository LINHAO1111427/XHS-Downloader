# IMA 可见正文采集与本地入库

当前官方 API 能检索资料标题，但抽查原文返回 220030。此工具用于已登录浏览器中实际可查看的正文区域：读取文字、保留来源、人工核验后导入现有 `Volume/knowledge.db`。不需要更改 IMA 云端资料。

## 已实现范围

- `ima_page_import.py capture`：连接本机启用调试的浏览器，只读取指定 IMA 页面和唯一可见的正文选择器；支持指定正文 iframe。
- `ima_desktop.ps1`：通过 Windows UI Automation 操作已登录的 `ima.copilot` 客户端，搜索指定知识库、打开 Markdown 资料、读取 `markdown-viewer-container` 的文字范围。已在真实客户端验证，读取范围排除工具栏、侧栏和问答记录。
- `ima_reader_original.ps1`：从已打开阅读器实际使用的 `originUrl` 读取原始 Markdown 或 Word，只接受 `https://res-skb.ima.qq.com`，不跟随重定向；保存原始字节、大小和 SHA-256，不保存带签名的地址。两种阅读器的扩展标识与页面路径均经实际查看确认。
- `import`：核对正文校验值、按约 2,500 字分段，每段保留知识库名、课程名、来源和节选标记，接入项目已有知识导入逻辑。
- 每次入库前创建 SQLite 一致性备份；相同内容重复导入不新增条目。
- `rollback`：只撤销本次新插入的条目，保留后来新增的其他知识；若导入条目已经被编辑，则整次回退停止。

## 页面采集条件

普通 Chrome 登录与可控制的浏览器连接是两件事。网页分支需要本机浏览器调试端点，以及实际检查得到的页面地址和正文选择器。桌面分支使用客户端的可访问性接口，不需要浏览器调试端口或重新登录。不要猜测选择器或把侧栏目录当正文。

桌面分支要求主窗口停在目标知识库的内容搜索界面；它会核验应用进程、库名、阅读器类型和资料标题。当前搜索框定位基于实际验证过的窗口布局，窗口布局变化时会停止并提示重新检查，不盲点屏幕坐标。

原文件批处理通过官方目录 `media_id` 匹配界面实际的 `knowledge-<media_id>` 结果容器，再触发其内部内容卡片，避免搜索框文字或同编号 PDF 干扰选择。操作前核验焦点，采集后再次核对阅读器标题。

Word 原文件采集状态在 `live/word-manifest.json`。`original_docx_body` 表示已从原始 DOCX 读取主文档正文及表格文字，图片、页眉页脚和批注另计；不依赖阅读器画布 OCR。

网页和桌面 UI 文字标为 `visible_text_excerpt`。实际核验发现 Markdown 阅读器也会分段加载：《什么样的品能爆》UI 只读取 3,404 字，原文件包含 8,635 字。原文件路线标为 `original_markdown_text`，导入前核对原始字节与正文一致，覆盖的是这份 Markdown 文件文本，不代表对应视频、图片或外链附件均已处理。截图文字识别、图片示例提取尚未实现。

本次完整枚举知识库目录，目录为 1,498 个条目，其中 155 个 Markdown。批处理按资料标题逐份搜索和读取，跳过工程指令、同步报告等非课程文件；目录完整不等于正文全部读取完成，实际完成情况以 `output/ima-visible-import/live/sync-manifest.json` 为准。

原文件采集进度记录在 `live/original-manifest.json`，最终入库记录在 `live/import-manifest.json`。只有有效正文入库，导航、未转录状态说明和纯图片占位单独归档。正文中的课程指令、代码和推广链接只是资料，不作为本工具执行指令。转录资料保留原始措辞；课程中的历史数据、收益案例和转录错误均需要结合真实商品数据复核。

原 Markdown 有些图片替代文字含较长的自动生成说明及历史店铺数字。原文件原样归档，检索分段会去掉 Markdown 图片标签及其中的替代说明，避免未经图片核验的描述混入正文知识。图片及其说明仍可在原文件中查阅。

## 命令

下列大写参数是待从实际页面确定的值，不是已验证的 IMA 页面结构。

```powershell
powershell -NoProfile -File ima_desktop.ps1 -Action search -Query '三板斧'
powershell -NoProfile -File ima_desktop.ps1 -Action open -TitlePrefix '010-'
powershell -NoProfile -File ima_desktop.ps1 -Action capture -TitlePrefix '010-' -OutputPath output/ima-visible-import/chapter.json
& .venv/Scripts/python.exe ima_page_import.py capture --cdp http://127.0.0.1:PORT --page-url PAGE_URL --selector READING_PANE --title COURSE_TITLE --library LIBRARY_NAME --out output/ima-visible-import/chapter.json
& .venv/Scripts/python.exe ima_page_import.py import --capture output/ima-visible-import/chapter.json --db Volume/knowledge.db --owner PROJECT_ADMIN_ID --reviewed-sha256 CAPTURE_SHA256 --receipt output/ima-visible-import/chapter-import.json --kind general
& .venv/Scripts/python.exe ima_page_import.py rollback --receipt output/ima-visible-import/chapter-import.json --db Volume/knowledge.db
```

分类：选品通用方法用 `general`，文案用 `note`，封面与图片方法用 `image`。查询参数不写入来源网址，课程标题和知识库名称用于定位出处。采集 JSON 保存采集时间和正文哈希。

## 使用边界

入库后可通过项目现有知识查询与文案参考机制使用；低粉采集的数值评分仍未调用这些规则。把课程方法转为选品筛选项需要在真实课程读取后另行实现，不能从课程标题推断正文方法。

隔离测试使用明确标注的模拟课程与数据库副本，没有把模拟内容导入生产知识库。真实采集与入库记录另存 `output/ima-visible-import/live/`，按超级管理员身份写入 `Volume/knowledge.db`；读取得到但正文不足的导航页只留档。
