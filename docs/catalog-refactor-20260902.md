# 图书库核心数据结构重构实施说明

实施日期：2026-09-02

## 结果

数据库已从以 `works / content_variants / editions` 为入口的旧模型，迁移为以 `catalog_entities` 为统一入口的模型。旧字段和旧 staging 表暂时保留为兼容层，所有新导入、搜索、ISBN 识别、推荐关系与封面写入均使用新结构。

```text
catalog_entities
├── works (book，1:1)
├── collections (series / level / set，1:1)
│   ├── collections.parent_collection_id
│   └── collection_items → works
├── catalog_title_aliases
├── catalog_identifiers
└── catalog_source_stats

recommendation_sources → reading_lists → reading_list_items → catalog_entities
                                      └→ raw_import_items → import_sources
```

`reading_lists` 和 `reading_list_items` 是原 `recommendation_lists`、`recommendation_items` 的正式表名。API 的旧路径和 Python 类名暂时不变，以避免前端同时发生破坏性升级。

## 数据库备份

正式迁移前已创建：

- `backups/reading_map_20260902_202554.sql`
- `backups/reading_map_20260902_202554.manifest.json`

重构完成后另存恢复点：

- `backups/reading_map_20260902_214200.sql`
- `backups/reading_map_20260902_214200.manifest.json`

manifest 记录 SHA-256、文件大小、26 张原始表及逐表行数。备份还被恢复进临时 MySQL 数据库，并在临时库完整执行所有迁移与 rebuild；校验完成后临时库自动删除。

以后可运行：

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\backup_database.py
.\.venv\Scripts\python.exe scripts\verify_migration.py ..\backups\<backup>.sql
```

## Migration

- `20260902_0005_catalog_entities.py`：建立统一实体、标题别名、ISBN、外部评分、raw import 表；迁移 works、collections 和书单关系。
- `20260902_0006_legacy_catalog_snapshot.py`：将旧 works/collections 保存为可重复 rebuild 的原始书目快照。

当前 Alembic head：`20260902_0006`。

## Rebuild

默认只做 dry-run：

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\rebuild_catalog.py
```

确认统计后正式应用：

```powershell
.\.venv\Scripts\python.exe scripts\rebuild_catalog.py --apply
```

流程按以下优先级处理：

1. `resolve_source=manual`：直接复用人工结论，不运行自动 Resolver。
2. 旧书目快照：复用已迁移 entity，避免对历史事实二次清洗。
3. 非书目资源：保留 raw item，标记 `non_catalog`。
4. 其余条目：Normalizer → Classifier → Resolver → reading list 关系。
5. 级别范围拆成多条 reading list item，共享同一个 raw item。
6. 合并仅有空格/标点差异的确定性重复项，并移除不应成为实体的级别范围。

连续两次 `--apply` 的结构与计数相同。

## Normalizer

- 保存 `raw_title`，永不覆盖原始事实。
- 去除明确的电商语言前缀，如“英文原版绘本”，但不删除“双语”等内容身份信息。
- 统一全角括号和多余空白。
- 识别 `全N册` 并提取 `volume_count`。
- 识别 `第N级`。
- 识别 `1-3级` 并生成级别序列，不创建 set。
- 内置少量确定性常用名映射，例如“小猪小象 / 小猪和小象 / Elephant & Piggie”。

## Classifier

输出 `book / series / level / set / unknown`、置信度和理由：

- 合法 ISBN：book，高置信度。
- 单级或级别范围：level。
- `全N册 / 套装 / 盒装 / 全套 / 礼盒`：set。
- 已知系列名或明确 series 标记：series。
- 旧 collection 目标：series，作为迁移兼容规则。
- 空标题：unknown；不会强制创建 entity。

## Resolver 与 title aliases

匹配顺序：

1. ISBN 精确匹配 `catalog_identifiers`。
2. `display_title / original_title / catalog_title_aliases` 精确规范化匹配。
3. 忽略空格和标点的唯一身份键匹配。
4. 多个候选或低置信度返回 `needs_review`，不自动 merge。

搜索 API 同时覆盖展示名、原名和 aliases。

## ISBN lookup

`catalog_identifiers` 使用 `(identifier_type, identifier_value)` 唯一约束。一个 entity 可关联多个 ISBN；ISBN 不保存装帧、版次或来源。

接口：

```text
GET /api/catalog/isbn/{isbn}
```

返回统一 entity，以及对应的 `work_id` 或 `collection_id`。

## Reading list

`reading_list_items.catalog_entity_id` 可指向 book、series、level 或 set。推荐年龄、AR、Lexile 和 comment 保存在推荐关系上，而不是 catalog entity 上。原 `recommendation_evidence` 仍作为详细证据层保留。

每个 reading list item 都通过 `raw_import_item_id` 回到不可覆盖的原始输入。当前数据中没有缺失 raw link 的 reading item。

## Collection / level / set

- `series`：内容系列或阅读体系。
- `level`：通过 `collections.parent_collection_id` 指向父 series。
- `set`：只表示真实出版/销售套装。
- `collection_items`：只表达 collection 包含哪些可单独阅读的 works。

## CoverResolver

封面脚本现在只在 catalog resolution 之后运行：

```text
ISBN → display/original title + author → title
```

本地封面写入 `catalog_entities.cover_local_path`，远程默认封面写入 `cover_url`。Google Books / Open Library 结果会进行标题相似度校验，非 ISBN 搜索不再无条件采用第一条结果。

## 当前 dry-run 统计

```json
{
  "raw_item_count": 1079,
  "classification_counts": {
    "catalog_snapshot": 526,
    "level": 5,
    "non_catalog": 161,
    "series": 389
  },
  "needs_review_examples": []
}
```

当前数据没有 set/book 类型的达人推荐输入；242 个 book 来自旧书目快照。当前没有 unknown 或 needs_review 样例。未来低置信度条目会保留在 `raw_import_items`，不会强行进入 catalog。

## Work Identity

同一核心阅读正文的精装、平装、重印、换封面、换出版社和仅增加少量附加页版本归为同一 work，并可挂多个 ISBN。不同语言、双语版、简写版、分级改写版或正文有实质调整的版本建立独立 work。不建立 editions 业务体系。

## 验证

- 8 个 catalog pipeline 单元测试通过。
- 原始备份恢复 + 全 migration + rebuild 临时库验证通过。
- works、collections、reading list item 外键完整性检查通过。
- `/works`、`/collections`、`/recommendation-lists`、`/map/recommendations`、`/personal-shelf`、`/imports/{id}` 回归请求均返回 HTTP 200。
