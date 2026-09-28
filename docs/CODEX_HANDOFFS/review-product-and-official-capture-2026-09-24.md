# 审核工作台：购物平台与官方资料采集交接（2026-09-24）

> 范围：`/admin` 审核项顶部的 Amazon／京东商品工具与 Research「搜索官方资料」工具。本文记录当前代码的实际行为，不把搜索成功、页面识别成功、资料采集成功、写入 Catalog 混为一谈。改动前先读 [`review-workflow-contract.md`](../review-workflow-contract.md)。

## 一句话区分

| 链路 | 人工操作 | 采集触发 | 采集结果先到哪里 |
| --- | --- | --- | --- |
| Amazon | 搜索后在辅助 Chrome 中打开正确商品详情页 | 点击「采集当前页」 | Research Subject 草稿 |
| 京东 | 同上，打开正确京东商品详情页 | 点击「采集当前页」 | Research Subject 草稿 |
| 官方资料 | 搜索后在**同一个辅助 Chrome** 中从 Google 进入匹配的出版社／作者页面 | 页面被识别后自动触发；「立即采集」是可用时的手动入口 | Research Subject 草稿 |

搜索只打开页面；采集只补 Research。两者都不直接创建 Catalog Entity，也不把被动发现的结构节点写成当前来源的推荐。最后仍需人工审核并点击「确认结构并写入 Catalog」。

## 页面状态与按钮

前端入口是 `frontend/src/App.tsx` 的 `ReviewView`。客户端 API 定义在 `frontend/src/api/client.ts`，后端路由在 `backend/reviews/urls.py`。

### 商品平台：Amazon／京东

1. 选择平台、必要时修改「商品搜索词」，点击「搜索／重新搜索」。如果 Catalog Draft 有未保存修改，当前实现会**拒绝商品搜索**并要求先保存草稿。
2. 后端启动或复用带调试端口的 Chrome，打开平台搜索页。此时「等待商品详情页」是禁用状态，**不是采集失败**。
3. 人在该辅助 Chrome 中进入正确商品详情页。前端在会话激活后约每 1.5 秒查询一次状态；聚焦审核页时也会再探测。Amazon 要能从 URL 识别 ASIN，京东要能识别 SKU，并通过标题与当前审核项的匹配检查。
4. 状态成为 `capture_ready=true` 后，按钮变为「采集当前页」。点击后 Selenium 连接同一 Chrome，读取当前识别的商品页，下载候选图，写入 Research 草稿，再重新读取当前批次审核数据。此链路**不自动采集**。
5. 页面显示「商品资料已采集…」才表示本次采集 API 成功；只看到搜索页、商品页或启用的采集按钮都不等于保存成功。

「Amazon／京东」切换按钮只选平台，不执行搜索。当前代码中商品搜索／采集遇到 `draftDirty` 会阻止操作；先保存 Catalog Draft。商品搜索框仅作为查询词，实际采集仍按当前 Research Subject 的标题／别名核对商品页，不能用随意搜索词绕过错商品保护。

### 官方资料

1. 点击「搜索官方资料」。搜索词由当前搜索词／对象名、Draft 出版社、作者和 `official publisher` 组成。与商品搜索不同，若 Catalog Draft 有未保存修改，当前实现会**先保存草稿**，再发起搜索；保存失败则停止。
2. 后端在共用的可监测 Chrome 会话中打开 Google 搜索页。复用会话时通过 Chrome 调试接口新建并激活标签页；如果检测不到对应搜索页，应报错，不能假报「已搜索」。
3. 人在**这个辅助 Chrome** 里从 Google 进入对应的官网详情页。审核页约每 1.5 秒轮询 `provider=official`。只要仍显示「等待官网页」，就尚未识别到 `capture_ready`；在 Codex 内置浏览器或另一个不属于该调试会话的 Chrome 中打开官网，不会被这条采集链路看到。
4. 识别到匹配页面后，前端自动调用官方采集 API。「立即采集」在就绪时也可手动触发。前端有进行中标记及已采集 URL 标记，避免同一页面的重复自动提交。
5. 成功时显示「官网资料已采集 · N 个字段已写入 Research 草稿」，更新当前审核项数据并停止本轮官网轮询。失败时显示可见错误；**「已搜索」不等于「已采集」**。

「刷新结果」仅调用审核项列表读取接口、重新显示服务器上已有的审核数据。它不会搜索、识别、采集、保存表单或提交 Catalog；有未保存的本地编辑时应先保存草稿。

## 请求与代码定位

| 用途 | HTTP | 前端 | 后端 |
| --- | --- | --- | --- |
| 会话状态 | `GET /api/review/browser-session/status?item_id=…&provider=amazon\|jd\|official` | `App.tsx` 的商品／官网轮询 | `views.BrowserSessionStatus` |
| Amazon 搜索／采集 | `POST /api/review/items/{id}/amazon-search`／`amazon-capture` | `searchProduct`／`captureCurrentProduct` | `views.ItemAmazonSearch`／`ItemAmazonCapture`，`amazon_assist.py` |
| 京东搜索／采集 | `POST /api/review/items/{id}/jd-search`／`jd-capture` | 同上，按平台分支 | `views.ItemJdSearch`／`ItemJdCapture`，`jd_assist.py` |
| 官方搜索／采集 | `POST /api/review/items/{id}/official-search`／`official-capture` | `searchOfficial`／`captureCurrentOfficial` | `views.ItemOfficialSearch`／`ItemOfficialCapture`，`official_assist.py` |
| 刷新结果 | `GET /api/review/items?batch_id=…` | `loadItems` | `views.ItemList` |
| 保存图片选择 | `PUT /api/review/subjects/{id}/product-images` | `persistCatalogDraft` | `views.SubjectProductImages`、`services.update_product_image_selection` |

三种浏览器辅助流程共用 `backend/reviews/amazon_assist.py` 中的 Chrome 定位、调试端口、profile 和互斥锁。默认调试端口是 `9225`（`AMAZON_CHROME_DEBUG_PORT` 可覆盖）；profile 在 `tmp/amazon-research-chrome`。Chrome 可通过 `CHROME_BINARY_PATH` 指定，ChromeDriver 可通过 `CHROMEDRIVER_PATH` 指定。浏览器状态接口读取调试端口的标签页列表；真正采集时 Selenium／ChromeDriver 附着到同一会话。

## 写入与证据边界

- 购物平台采集经 `services.apply_amazon_capture`／`apply_jd_capture`：保存平台商品 URL 为 `ResearchSource`，建立 Subject 与来源的关联，合并有来源 ID 的 `facts_json`，刷新 Catalog 候选，并记录审核动作。Amazon 读取作者、绘者、简介、出版社、出版日期、语言、阅读年龄、页数、ISBN、部分评分／排名信息和候选图片；京东读取类似书目信息、童书类型、商品参数、候选图片。实际字段取决于页面上能读到什么，不保证每项都有值。
- 商品图片最多处理前 16 个 URL，尝试下载到 `research_data/amazon/{ASIN}` 或 `research_data/jd/{SKU}`。即使单张下载失败，Research 图片记录也可能保留来源 URL 而没有 `local_path`。`product_images` 保存候选与选择状态；封面 radio 和详情图 checkbox 是两个独立选择，最终封面／详情图从这些选择派生。
- 同一来源再次采集可刷新该来源自己的值；与另一来源不一致时，平台数据会保存在带平台前缀的事实键中，不能静默覆盖不同来源的既有值。若套装页明确列出成员，可能暂存被动发现的成员 Research Subject 和直接关系；仍不是正式 Catalog 写入。
- 官方采集经 `services.apply_official_capture`：保存官网 URL、标题、来源类型和有来源 ID 的事实；优先读取页面元数据与 JSON-LD，必要时用页面文本。可能得到简介、封面、作者、绘者、出版社、官方年龄／类型、ISBN、页数、发布日期、语言、系列名及对象类型建议。若官网明确列出直接父级或成员，还会暂存 Research 节点与**直接**关系。官方事实与现有事实冲突时保留带 `official_` 前缀的事实，不应假装已自动裁决。
- 上述数据停在 Research 审核区。最终 Catalog Entity、works／collections、`collection_items` 与当前来源的 `reading_list_item` 由审核提交事务处理。`reading_list_item` 只关联真正被来源推荐的主对象。

## 当前识别边界与风险（交接时不要省略）

1. 商品状态／采集从调试端口的标签页列表寻找平台商品页，并按标题线索判断是否属于当前审核项；不是单靠「用户刚点击的标签页」。同时开着多个同平台商品页时，可能先命中旧页。若提示标题不匹配，关闭／切回其他商品页后再确认状态，**不要强行采集**。
2. 官网候选识别目前是：排除 Google、Amazon、京东等域名，再检查标题或 URL 路径与审核项名称有词重合。这不是出版社域名白名单，也不证明网页真的是官网；同名第三方页面或旧标签页仍可能被误识别。审核人必须核对来源 URL，开发者不应把 `capture_ready` 描述为「已核实官方」或「已采集」。
3. Google 搜索页需要在可监测的辅助 Chrome 中出现。搜索 API 成功但页面没进入该会话时必须报错；进入官网页之后仍是「等待官网页」通常表示浏览器会话不对、标题／路径不匹配，或页面尚未加载。点击「刷新结果」不会补救识别问题。
4. 官网采集目前只对页面能提取的字段有效；没有读到的官方分类、AR、Lexile 等不能编造。官方无分类时，可用**有来源的简介**做待审核的分类归纳，不得标成官方标注。
5. 采集与草稿保存有不同前置条件：商品搜索／采集要求先手动保存脏 Draft；官网搜索／采集会尝试先保存。改这里时特别防止用户正在编辑的草稿被旧快照覆盖。手动图片选择与页面滚动位置也属于回归范围。

## 故障排查顺序

| 症状 | 先查什么 |
| --- | --- |
| 点击「搜索」没反应／报错 | 请求是否到对应 `*-search`；Chrome／调试端口是否可用；是否有未保存 Draft；当前审核项是否已决议；搜索页是否真的出现在调试会话中 |
| 商品页已打开但仍「等待商品详情页」 | URL 能否识别 ASIN／SKU；是否在辅助 Chrome；当前平台是否正确；标题是否与审核项匹配；`browser-session/status` 的 `message` |
| 商品「采集当前页」失败 | `*-capture` 的返回错误；ChromeDriver；页面标题和结构是否变化；当前商品是否仍为同一 ASIN／SKU；图片下载失败与整次采集失败要分开看 |
| 官网页已打开但仍「等待官网页」 | 是否在搜索按钮打开的辅助 Chrome；页面是否非 Google／非购物平台；标题／URL 是否包含当前对象名称；是否命中了旧标签页；`provider=official` 状态 |
| 官网显示「已搜索」但没有资料 | `official-capture` 是否实际发起并成功；Research Source／facts 是否新增；「已搜索」只是搜索阶段，不能当成采集成功 |
| 采集后 UI 没变化 | 看采集 API 响应、当前 Review Item 的 Subject facts／sources，再用「刷新结果」重读；不要用刷新代替采集 |
| 500 横幅 | 先看具体请求方法和路径；例如以前的 `GET /api/reading-lists` 500 是旧后端进程仍查询已删除的 `recommendation_strength` 字段，与当前商品／官网按钮无关 |

## 接手修改的验证

1. 跑 `backend/.venv/Scripts/python.exe backend/manage.py test reviews.tests --keepdb`，至少覆盖搜索、状态匹配、错误商品拒绝、商品与官网草稿写入、图片选择和结构暂存。
2. 跑前端 `tsc --noEmit`。在开发页分别按 Amazon、京东、官方三条路径做一次人工冒烟：搜索页在**同一采集浏览器**出现 → 正确详情页变为就绪 → 采集成功消息 → Research 来源／事实可见。
3. 验证反例：错商品、同名第三方页、另一浏览器中的官网页、已解决审核项、未保存 Draft、重复采集。不能只测试按钮变亮。
4. 验证没有把 Research 草稿直接写入 Catalog 或 `reading_list_item`；未明确变更约定前，不要改变手动商品采集／自动官网采集的触发方式。

相关回归测试主要在 `backend/reviews/tests.py` 的 `OfficialSearchTests`、`RecommendationEmphasisImportTests` 和 `ResearchReviewTests`。这份交接只记录写入时的状态；后续接手时应以代码、测试和实际浏览器会话重新核对。
