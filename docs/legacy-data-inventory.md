# 旧数据资产盘点（2026-09-05）

## 盘点范围与原则

本盘点基于当前 MySQL `reading_map` 的实时只读查询、SQLAlchemy 模型、Alembic 迁移、账单导入脚本及其本地导入报告。导出过程只执行 `SELECT`，不修改数据库，也不进行 Catalog merge/split 或正式实体重建。

当前 Alembic 版本为 `20260902_0006`。数据库已经做过一次 catalog-entity 迁移，因此本文区分“原始推荐事实”“当前旧库解析结果”和“个人书架成员关系”，不把旧库解析结果当作未来 Catalog 的最终事实。

## 1. 达人资料保存位置

达人主记录位于 `recommendation_sources`：

- `name`：内部使用的达人名称。
- `source_type`：blogger、author 等来源类型。
- `platform`、`profile_url`、`notes`、`created_at`：来源补充资料。

达人介绍位于一对一表 `recommendation_source_profiles`：

- `display_name`
- `avatar_url`、`photo_credit_url`
- `short_bio`（导出为 `creator.introduction`）
- `positioning`
- `methodology_summary`
- `route_summary`
- `suitable_for`
- `cautions`
- `source_note`

其他达人资料还分布在：

- `recommendation_source_publications`：达人著作、表格/PDF 等出版物或资料入口。
- `recommendation_source_knowledge`：已整理的 AI 说明书、读图笔记、读书笔记；正文在 `content_markdown`。
- `recommendation_source_documents` / `recommendation_source_pages`：原始图片、PDF、文本资料及页级路径、顺序、尺寸、校验值。

实时数据有 5 位达人、5 条 profile、4 条 publication、8 条 knowledge、12 个 source document 和 115 个 source page。5 位达人均有 profile，导出时每份书单 JSON 都内嵌该达人的完整现有资料，达人介绍不会因数据库删除而丢失。

## 2. 达人与书单的真实关系

当前真实关系为：

```text
recommendation_sources（达人）
  -> reading_lists（16 份书单）
     -> recommendation_stages（66 个阶段）
        -> reading_list_items（555 条推荐事实）
           -> raw_import_items（原始导入值，必有）
           -> catalog_entities（可选的旧库解析结果）
              -> collections（当前大部分书单条目解析到集合）
```

与最初设想的 `item -> work` 不同，当前 555 个书单条目的 `work_id` 均为空；394 个条目带 `catalog_entity_id`，并主要关联到 collection/series/level。其余 161 个是 animation、app、audio、material、resource、video 等非 Catalog 素材。导出不依赖这些外键才能理解推荐事实。

16 份书单全部有一条 `legacy_reading_list` import source。555 个条目全部带非空 `raw_import_item_id` 和非空 `raw_title`。

需要特别记录一个既存旧库现象：原始导入项“体验英语少儿阅读文库 1-3级”已经在旧库中解析为 3 个 `reading_list_items`。因此 16 份书单对应 553 个唯一 raw import item，但对应 555 条现有推荐记录。导出完整保留 555 条记录及共同的 raw provenance，不在本步骤合并或再次拆分。

## 3. 书单条目当前保存的信息

`reading_list_items` 直接保存：

- 阶段、阶段内 `position`
- `raw_title`、`raw_author`、`raw_text`
- `item_type`
- 推荐年龄上下限（年）
- AR、Lexile 的结构化值（如果存在）
- `comment`
- source page、source region
- raw import 和旧 catalog 解析引用

`recommendation_evidence` 保存原始/结构化证据：

- `recommended_age`：461 条
- `ar`：28 条
- `lexile`：14 条
- `ort_level`：2 条
- 同时可保存 `value_text`、数值/范围、单位、年龄语义、阅读模式

`recommendation_item_annotations` 保存 1,715 条注释，类型包括 category、emphasis、material_type、progression、reading_channel、reminder、role。导出将这些完整放进条目的 `extracted.other_info`，不会只保留 Schema 中的少数字段。

数据库中的 `position` 是阶段内顺序，并非全书单唯一顺序。导出数组按 `stage_order -> position -> legacy item id` 排列；同时原样保存 `position`，并添加从 1 开始的确定性 `sequence`，从而既保留原顺序语义，也能在脱离数据库后还原整份书单的线性顺序。

## 4. 个人已购书的判定

个人已购书的可靠判定不是“所有 works”，而是 collection `我的书架`（`collection_type = personal_shelf`）中的成员：

- 240 个唯一书架条目
- 240 个不同的 `work_id`
- `position` 为 1..240，完整且不重复
- 数量合计 422

该书架由 `tmp/import_bookshelf_from_bill.py` 从“👪恩恩的账簿 副本.xlsx”的中文书/英文书账单行创建。`tmp/bill_books.json` 保留了 242 条账单原始记录；导入按标题和语言合并为 240 个书架条目，两个重复组通过每个 purchase item 的 `records` 保留，不丢失购买发生记录。

购书导出以数据库中的 240 个书架成员作为覆盖基线，并用现存账单 JSON 补充数据库未保存的购买日期、金额、平台、截图名和原始订单 OCR 文本。账单中某些年龄文字曾包含外部搜索或推测；这些只作为 `source_record.stated_age` 原样保留，不提升为标准书目事实。

## 5. 不确定来源的 works

当前 `works` 共 242 条：

- 240 条属于“我的书架”，可确定为已购书。
- `The Very Hungry Caterpillar`、`Flubby` 两条既不属于个人书架，也没有任何 `reading_list_items` 关联。

这 2 条导出到 `source_data/unresolved/legacy-works-unresolved.json`，不混入达人书单或购书数据。

`import_sources` 中另有一份 526 项的 `legacy_catalog_snapshot`（242 个 works + 284 个非个人书架 collections）。它是旧目录重建快照，不等同于购买来源；购买身份仍只由个人书架成员关系确定。

## 6. 已知限制

- 部分旧书单本身标注为“首轮读图”“资料入口”或“只覆盖部分主题页”。本次导出完整保存当前数据库成果，但不重新 OCR 或补研究数据。
- 当前旧 catalog 的 book/series/level/set 判断仅作为 `analysis` 辅助信息，未来仍须进入预审核和人工审核。
- 原始文件路径会作为 provenance 保存，但第 30 节要求的达人、书单、条目、顺序、推荐信息和购书事实均直接存在 JSON 中，不依赖这些路径才能读取。

