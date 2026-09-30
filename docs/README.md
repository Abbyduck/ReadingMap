# Reading Map docs

`docs/` 保存来源资料、达人笔记、导入格式、数据统计等**参考材料**。它不是 Reading Map 产品/领域规则的权威来源。

当前产品语义只有一个 canonical source：

- `.codex/skills/reading-map-domain-model/SKILL.md`

项目入口规则见根目录 `AGENTS.md`。

## 使用原则

- 需要判断 Entity / Work / Edition / Structure / Review / Research / ReadingList / Classification / Guide / 推荐等业务语义时，读 Domain Skill，不要在 `docs/` 中寻找旧方案补全需求。
- `docs/` 中的达人资料、读图笔记、原始 category 统计和导入说明可以作为事实/操作参考，但不能覆盖 Domain Skill。
- 旧架构方案、旧数据库快照、旧 handoff、一次性 QA/实施报告不保留在当前工作树；需要追溯时使用 Git history。
- 如果当前规则不清楚，询问用户，不要从历史提交中恢复旧假设。

## 当前仍保留的参考材料

主要包括：

- 达人/作者知识与读图笔记；
- 来源书单整理流程；
- CSV / source data 格式参考；
- raw category 等由来源数据生成的统计。

这些材料用于理解来源，不用于定义产品架构。