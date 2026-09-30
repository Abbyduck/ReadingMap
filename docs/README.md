# Reading Map docs

`docs/` 只保存**参考材料**，例如达人/作者知识、人工读图笔记、来源数据统计等。它不定义 Reading Map 的产品架构或业务规则。

当前产品语义的 canonical source 只有：

- `.codex/skills/reading-map-domain-model/SKILL.md`

仓库协作与优先级规则见根目录 `AGENTS.md`。

## 使用原则

- 判断 Entity / Work / Edition / Structure / Review / Research / ReadingList / Classification / Guide / 推荐等业务语义时，读 Domain Skill。
- `docs/` 可以帮助理解来源事实，但不能覆盖 Domain Skill。
- 旧架构方案、旧数据库快照、旧 handoff、一次性 QA/实施报告不保留在当前工作树；需要追溯时使用 Git history。
- 如果当前规则不清楚，询问用户，不要从历史提交恢复旧假设。

当前保留的文档主要是达人资料、来源阅读笔记和由来源数据生成的统计。