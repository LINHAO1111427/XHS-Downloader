# 小红书全平台商品采集调研记录

记录日期：2026-09-05（北京时间）

## 当前决定

**暂停实现，仅保存调研记录。** 用户原话：“这个你先做好记录吧，暂时先不实现”。

- 本次仅新增此文档，不接入商品采集器，不安装第三方项目，不启动商品采集或定时任务。
- 后续须在用户明确恢复该任务后继续实施。
- 现有程序已具备笔记与作者采集逻辑，商品采集模块尚未实现。
- 当前没有真实商品采集结果；本次调研是远程源码、仓库文件列表和接口文档核查，未运行候选项目或进行安卓实机验证。

## 用户需求

- 平台：小红书。
- 对象：全平台、跨店铺商品，不限于用户自己的店铺。
- 筛选：最近连续 24 小时加购超过 200，比较符为严格大于 `>`。
- 用户目前没有商品数据接口，希望优先研究可自行实现、可借鉴的项目。
- 尚待确认：加购统计指人数还是次数，以及是否接受区间数据。
- 与商品任务并列的笔记需求：北京时间今日发布、作者粉丝少于 1,000、点赞至少 500。笔记互动指标与商品加购指标分别处理。

## 已核查项目

### 1. 小红书监控与采集平台

- 仓库：https://github.com/wu83255-sketch/-
- 已核查版本：`b60ddcd805edcee2d1e9de599c0e2499c0a1c11e`。
- README 与代码包含 FastAPI、React、SQLite、商品监控、快照、网页 Playwright 和 Android ADB 采集路线。
- 商品模型及快照包含标题、链接、价格、销量、评论数、评分等字段，所查模型中没有独立的近 24 小时加购统计字段。
- 手机端使用 UIAutomator 读取页面节点，商品卡片识别条件中出现“加购”文本；这只是识别卡片的条件，不是已实现的加购数量或时间窗解析。
- 可借鉴部分：设备连接、商品发现、页面读取、商品去重、快照和任务管理。实际兼容性尚未实测。

关键证据：

- [商品模型](https://github.com/wu83255-sketch/-/blob/b60ddcd805edcee2d1e9de599c0e2499c0a1c11e/backend/app/models/product.py)
- [商品快照模型](https://github.com/wu83255-sketch/-/blob/b60ddcd805edcee2d1e9de599c0e2499c0a1c11e/backend/app/models/snapshot.py)
- [手机采集器第 313 行](https://github.com/wu83255-sketch/-/blob/b60ddcd805edcee2d1e9de599c0e2499c0a1c11e/backend/app/services/xhs_mobile_crawler.py#L313)
- [网页采集器第 526 行](https://github.com/wu83255-sketch/-/blob/b60ddcd805edcee2d1e9de599c0e2499c0a1c11e/backend/app/services/xhs_live_crawler.py#L526)
- [手机商品卡片识别第 1501 行](https://github.com/wu83255-sketch/-/blob/b60ddcd805edcee2d1e9de599c0e2499c0a1c11e/backend/app/services/xhs_mobile_crawler.py#L1501)

特别注意：所查采集器生成的 `delta_24h` 存在以下固定比例计算：

```python
# 手机采集器
"delta_24h": max(int(max(sales_count, 1) * 0.015), 1)

# 网页采集器
"delta_24h": max(int(item.sales_count * 0.12), 1)
```

这些计算不是实际近 24 小时加购统计，也不是基于两个真实时间点求得的销量变化。后续接入时应排除这些值作为目标指标的依据。

### 2. XHS-Vendor

- 仓库：https://github.com/ItellYouTool/XHS-Vendor
- 项目名称为“小红书商品数据采集工具”。
- 核查时默认分支文件树只有 `Readme.md`、`screenshot/1.png`、`screenshot/2.png`。
- 仓库没有公开采集源码或可核验的近 24 小时加购字段实现，暂不作为可直接集成的代码来源。

### 3. MediaCrawler 与 xiaohongshu-mcp

- https://github.com/NanmiCoder/MediaCrawler
- https://github.com/xpzouying/xiaohongshu-mcp
- 已查看小红书客户端、相关数据模型或仓库文件列表。
- 所查实现主要覆盖笔记、评论、作者及笔记相关操作，没有找到商品近 24 小时加购采集实现。
- 这两项是内容采集或自动化参考，不是已确认的目标商品数据源。

### 4. JustOneAPI 商品搜索服务

- 仓库：https://github.com/justoneapi/data-api
- 文档：https://docs.justoneapi.com/zh/api/xiaohongshu-e-commerce-rednote/product-search-v1
- OpenAPI：https://docs.justoneapi.com/openapi/xiaohongshu-e-commerce-rednote/product-search-v1-zh.json
- 文档列出 `GET /api/xiaohongshu-ec/search-products/v1`，需要该服务的 Token，支持关键词、页码和搜索 ID。
- 它是第三方接口服务，不是本地自建采集源码。
- 核查到的响应定义仅给出通用响应结构，`data` 没有具体商品字段定义，尚未证实包含加购数量或统计时间窗。
- 文档中的“24h 健康值”“24h 平均耗时”描述接口运行状态，与商品加购统计无关。
- 未购买、注册、调用付费数据接口，也没有取得真实商品响应。

## 调研结论

已找到商品采集和安卓页面读取的参考代码，但本次检索尚未找到经验证可直接提供“全平台真实近 24 小时加购量”的开源项目。该结论只针对本次查阅材料，不表示所有项目或渠道都不存在该能力。

跨关键词、类目与店铺搜索可以扩大商品发现范围；搜索采样与全站无遗漏覆盖是不同结果，后续应记录搜索范围、翻页上限和覆盖情况。

## 保留的实现方向（未实施）

优先验证 Android 手机登录小红书后的页面采集路线，不以用户先购买数据接口为前提：

```text
商品发现
-> 读取商品列表及详情页面
-> 保存统计原文、时间窗、数值、单位、来源和截图
-> 核验是否为近 24 小时加购指标
-> 筛选严格超过 200 的商品
-> 入库、去重、导出
```

- 候选技术：ADB + UIAutomator 或 uiautomator2；页面节点缺失时再评估 OCR。
- 优先抽查 10 至 20 个真实商品，先验证指标可见性、统计口径和读取准确率，再决定自动化接入。
- 只有页面或可靠响应明确提供目标时间窗和加购指标时，才将记录列入已核验结果。
- “200+人加购”等文案应保留原文与区间属性；时间窗未明确或区间不足以证明严格超过 200 时，标记为待核验。
- 销量、评论数、收藏数、加入购物车按钮和固定比例估算均不作为实际加购统计。
- 两次当前购物车人数或其他口径不明的累计值之差，也不直接等同于 24 小时加购事件数或去重人数。
- 若实机页面没有目标指标，则如实记录缺失，再重新评估数据来源。

## 恢复任务前待确认

1. 用户明确恢复实现。
2. 是否有可连接本机且已登录小红书的 Android 手机；此前已询问，尚未收到答复。
3. 近 24 小时加购按人数还是次数计量。
4. 是否接受区间统计，以及候选发现的类目、关键词、规模和运行频率。
5. 实机抽样中是否确实出现所需指标，及其来源、时效和完整度。

本机环境核查仅确认 `adb` 不在当时的 PATH 中，没有据此判断设备状态或是否在其他位置安装。恢复后重新检查环境，不沿用这一状态作为永久结论。
