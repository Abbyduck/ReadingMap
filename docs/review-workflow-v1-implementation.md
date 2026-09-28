# Catalog Research 与审核流程 v1：评审结论与实现说明

## 结论

原设计的核心边界成立，可以作为实现基线：来源事实、长期 Research Subject、正式 Catalog 三者分离；客观事实与 AI 推导分区；人工确认 Catalog 身份；被动补齐结构不得冒充来源推荐。

实现前补了六个必要护栏：

1. **导入幂等**：`来源相对路径 + 文件 SHA-256 + source_type + 正式目标` 形成唯一导入键。同一个文件重复提交返回已有批次，不重复生成审核项。
2. **正式目标绑定**：阅读书单批次可显式绑定 `target_reading_list_id`，否则审核身份可以完成，但不会猜测或创建正式来源关系。
3. **审核留痕**：审核项保存 `resolved_at`、`lock_version`、最终关系 ID，并通过 `review_action_logs` 记录操作者、动作和结构补齐选择。
4. **并发保护**：提交使用审核项版本校验；创建 Catalog 前刷新候选；MySQL 下按 Research fingerprint 取得命名锁，结构补齐所涉及的 Subject 按稳定顺序加锁，提交后释放。
5. **共享 Research 的 IGNORE 语义**：忽略只终结当前 `review_item`，不把可能被其他来源复用的 `research_subject` 标记为无效。
6. **现有 Catalog 缺项补齐**：当前代码原本没有设计中引用的 Catalog `description` 与点读笔关系，迁移中补入 `reading_pen_models`、`catalog_entity_reading_pens` 和 `catalog_entities.description`。

## 当前交付

- Review/Research 全部持久化模型与 Alembic 迁移。
- `source_data` 内 JSON 的安全路径导入、原始 payload 保留和标准化 proposal。
- Research Subject fingerprint 查找与复用（不加唯一约束）。
- 客观资料、AI 推导、资料来源、Subject 关系的写入 API。
- Catalog 候选评分与提交前重跑。
- Match Existing、Create New、Ignore。
- Series/Level/Set 结构选择、逐项复用/创建和单事务提交。
- 可靠来源事实只补空字段；不同值生成 conflict，不覆盖正式数据。
- 点读笔并集写入；不会因点读版本创建多个 Catalog Entity。
- 阅读书单正式关系只写 primary Review Item。
- 高置信候选的人工触发批量确认。
- 桌面与移动端审核工作台。
- Codex `catalog-research-worker` Skill：联网查证、客观事实引用、AI 推导分区、结构发现、批量写库与提交边界核验。
- 幂等达人恢复脚本；Research Worker 可按 JSON 的达人身份创建/复用一份待审书单框架。

## 客观 Fact 的写入条件

可自动进入正式 Catalog 的客观字段必须使用下面的结构，并且 `source_ids` 至少有一个确实关联到当前 Research Subject：

```json
{
  "description": {
    "value": "客观简介",
    "source_ids": [12]
  },
  "reading_pens": {
    "value": ["毛毛虫", "童趣"],
    "source_ids": [13]
  }
}
```

无来源、来源 ID 未关联或放在 `ai_inferences_json` 中的值都只展示为 proposal，不会自动写正式库。

## API 入口

- `POST /api/review/batches/import`
- `GET /api/review/batches`
- `GET /api/review/items`
- `GET /api/review/items/{id}`
- `PUT /api/review/subjects/{id}`
- `POST /api/review/subjects/{id}/candidates`
- `POST /api/review/relations`
- `POST /api/review/items/{id}/decision`
- `POST /api/review/items/bulk-match`
- `GET /api/review/conflicts`
- `POST /api/review/conflicts/{id}/resolve`

## 启用

```powershell
cd backend
.\.venv\Scripts\alembic.exe upgrade head
```

迁移后启动后端和前端，在侧栏进入“审核工作台”。导入路径必须是 `source_data` 下的相对路径，例如：

```text
reading_lists/廖彩杏__072__廖彩杏52周有声书计划（资料入口）.json
```

## Codex Research Worker

联网 Research 在 Codex 中通过 [`skills/catalog-research-worker/SKILL.md`](../skills/catalog-research-worker/SKILL.md) 执行，而不是在 FastAPI 进程中后台调用模型。Skill 的写库助手接受使用 `source_keys` 的可重放 manifest，写入时解析成数据库 `source_ids`；无来源的客观 fact 会被拒绝。

助手在每次交付前验证所有审核项仍未决、`reading_list_items` 仍为 0，因此 Research 不会越过人工审核边界。示例实跑 manifest 保存在 `research_data/batch-1`。

## 明确未完成的边界

- 当前 Research Worker 是 Codex Skill 驱动的一次性任务，不是后端常驻队列、定时调度器或无人值守服务。
- 当前正式模型没有 purchase/shelf 关系表，所以购买 JSON 可以进入审核并解析身份，但尚不能提交正式购买关系。需要先确定购买领域模型和目标主键。
- Conflict 已有 API 与独立状态，前端专门的冲突处理列表留到下一迭代。
- Entity Merge、Edition、复杂 AI 推荐、孩子画像联动继续保持在本阶段范围外。
