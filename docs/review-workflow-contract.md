# 审核工作台稳定行为约定

本文件记录审核工作台已经确认、容易在后续修改中发生回退的具体交互行为与回归约束。

它不是 Reading Map 的最高层领域模型文档，也不表示代码永远不能改。若本文件与用户最新明确确认的需求、Reading Map Domain Model Skill 或当前任务的实施规格冲突，以更高优先级的当前规则为准，并同步修正本文件，避免旧约定继续误导后续实现。

修 bug、优化实现可以进行，但不得悄悄改变下列已确认的用户可见行为。若任务确需改变其中任何一条，动手前明确告诉用户将触及哪条约束、为什么、会产生什么影响，并取得确认。

## 推荐事实

- 一条 `reading_list_item` 就表示来源在该书单/阶段推荐了该 Entity；不再存“弱/普通/强”数字档位。
- 正式表只存 `is_strong_recommendation` 与 `recommendation_emphasis_text`。`recommendation_strength` 和推荐分数不是正式数据库字段；旧导入数据的兼容读取不能被误当成新字段。
- 仅来源明确出现强烈推荐、重点推荐、必读等强调语义时自动勾选强推；人工可修改。不能凭排序、评分、出现次数或视觉需要推测强推。
- `reading_list_item` 只指向当前来源真正推荐的对象。Research 被动发现的父级、同级、成员只用于补齐 Catalog 结构，不能变成这条来源的推荐。
- Research、Structure、Classification 都是可选增强，不是提交 ReviewItem、复用 Catalog Entity 或创建 Catalog Entity 的完成门槛。Catalog 允许不完整。

## Draft 与人工修改保护

- Catalog Draft、推荐语、备注、图片选择、Edition 选择、Guide Draft 等人工修改不能因刷新 Research、采集商品/官网、切换审核项或重新加载数据而被无提示覆盖。
- 表单中的 Ctrl+S 等于“保存草稿”。
- 当 Draft 有未保存修改时，执行 Search 或任何 Capture 前必须先自动保存当前 Draft；自动保存失败时不得继续 Capture，并应给出可见错误。
- Research 候选只用于补充或提示冲突：空 Draft 可被可靠候选预填；与人工 Draft 相同则无需动作；与人工 Draft 冲突时保留人工值并显示候选，不得静默覆盖。
- Catalog 已有值与新 Research 冲突时，也不得静默覆盖 Catalog 当前真相。

## Search 与 Capture

- Amazon、京东、Official 均使用同一类 human-in-the-loop 流程：Search 打开辅助浏览器/当前会话，用户自行浏览并进入目标页面，然后由用户显式点击 Capture。
- Official 不得自动采集。打开官网详情页本身不等于已经 Capture，也不得因为页面可识别就自动写入 Research。
- Search 与 Capture 必须使用可被采集流程监测的同一个浏览器会话，并正确跟踪本次搜索/目标/子标签页，不能误抓旧标签页或无关页面。
- Capture 失败必须给出可见原因，不能静默失败。
- Research 不是审核提交的前置条件；用户可以完全不做 Amazon/JD/Official Research 仍然完成审核。

### 三类 Capture 的语义必须分开

- 顶部 `Capture Current Page`：只用于 Entity / Work Research，例如标题、别名、作者、插画家、译者、AR/Lexile、Work 级 `detail_images` 等。
- Edition 区域 `Capture Current Edition`：只用于当前 Edition Draft，例如封面、ISBN、出版社、装帧、页数、出版日期、尺寸等；不得重新覆盖 Work Draft、重新抓 Work `detail_images` 或触发无关的 Work 冲突。
- Structure 区域 `Capture Structure`：只用于结构发现与 Structure Draft，例如 Collection 身份、直接 parent/member 关系及页面明确提供的顺序；不得修改 Work、Edition、封面、详情图、Classification 或其他通用 Research 字段。
- Capture 的语义由用户点击的业务区域/按钮决定，不由网页上“碰巧还能解析出什么信息”决定。

## Catalog Match 与身份确认

- 系统匹配结果只是候选，不是身份决定。
- 匹配到现有 Catalog Entity 时，不得把该 Entity 的现有字段预填进当前新对象 Draft，以免相似对象发生数据泄漏。
- 点击匹配候选时，应允许以只读方式查看 Catalog 详情，包含足以判断是否为同一 Work 的信息及已有 Edition 封面。
- 只有用户确认“是同一本/同一个 Entity”后，才绑定复用现有 Entity；如果用户判断“不是”，必须干净进入新 Entity / Work 路径，不继承匹配对象数据。
- 确认复用现有 Entity 后，不强制重新 Research；已有 Catalog 数据仍是当前真相，当前审核只补充用户明确要补的内容。

## Structure 与审核交互

- 系列父级、同级和成员使用紧凑结构树 + 右侧 Inspector；不得恢复逐节点大卡片和逐个确认弹窗。
- Structure 左侧当前选中的节点，就是右侧 Entity 编辑与 Structure 辅助动作的目标。无需再增加第二套“资料归属对象”选择机制。
- 名称中的系列标记属于 Research 线索，但线索不等于已核实关系；需要可靠证据或人工确认后才建立正式关系。
- `collection_items` 只保存直接 membership，不自动保存祖先/传递关系。
- Collection 允许为空；`volume_count` 表示已知/声明的全集规模，不等于当前已录入 `CollectionItem` 数量，不得被成员数自动覆盖。
- Structure 可通过多次 Capture 逐步补齐；重复 Capture 应合并/去重，而不是要求一次完整识别整棵树。
- 写入 Catalog 应保持事务性：关键步骤失败则回滚，不能留下半提交关系。

## Series 创建时的分类预填

- 从当前 Book 上下文新建 Series 时，可以复制该 Book 当前 Classification 作为 Series Draft 的初始值。
- 这是 creation-time prefill，不是 inheritance，不建立持续同步关系。之后 Book 与 Series 的 Classification 独立修改。
- 其他 Collection 类型不自动复制当前 Book 的 Classification。

## Guide / 手工资料

- Entity 的最终实用指南使用 `guide_markdown`，语义是该 Entity 自身的策展/解释内容，不限定为购买指南。
- 审核主 Entity 和 Structure Inspector 当前选中 Entity 都应能输入原始资料并整理 Guide。
- 原始粘贴资料不能直接成为 Catalog 展示内容；流程应为“原始资料 → 整理后的 Markdown Draft → 人工编辑确认 → `guide_markdown`”。
- Guide 归属当前正在编辑/选中的 Entity，不需要额外的全局归属选择器。

## 图片与来源原图

- 来源原图 / 当前推荐所在原图是只读审核上下文，用于帮助判断来源推荐的具体对象或版本。
- 来源原图本身不是 Catalog 图片候选，不得自动创建 Edition、不得自动设为封面、也不得直接写入 Work `detail_images`。
- 图片可从真正的候选图中切换封面；封面 radio 叠在图片左上角；详情图 checkbox 独立保留。
- 切换图片、封面或详情图选择时，不应导致全部控件短暂禁用、页面滚回顶部或人工选择丢失。
- 外部图片 URL 属于 Research 输入。图片一旦被采纳进入 Catalog，最终应保存到自控存储，不以 Amazon/JD/官网热链作为长期展示资源。

## Edition 审核

- Edition 不是 `CatalogEntity`，也不是新的 Work；它表示同一 Work 下可被识别的出版/物理版本。
- Edition Draft 允许稀疏：仅封面、仅 ISBN/装帧等强版本信息也可以形成候选，不要求补齐所有字段。
- ISBN-10 与 ISBN-13 的兼容表示可以属于同一 Edition；ISBN 数量不能用于推断 Edition 数量。
- 相同 ISBN 默认先视为同一 Edition 候选；出现不同封面时展示封面选择，不应自动拆成两个 Edition。
- 不同 ISBN 只是“可能不同 Edition”的信号，不能自动决定拆分；由人工选择合并或拆分。
- `ReadingListItem` 的版本推荐属于该条推荐关系，通过 `recommended_edition_id` 表达；不存在全局 `Edition.is_recommended`。

## 未明确要求的区域不要顺手重构

- 修改 Review / Research / Catalog 写入逻辑时，只改当前任务明确涉及的区域与行为。
- 现有右侧来源原图、结构树布局、辅助控件或其他未列入任务的工作台区域默认保持不变。
- 不得为了“统一架构”顺手重写已经可用的 Review 辅助能力；若必须重构，应先说明会影响的用户行为。

## 每次改动的回归检查

1. 刷新审核页没有泛化 500；若请求失败，错误至少指出请求方法与路径。
2. Amazon / JD / Official Search 实际打开可监测的浏览器会话；仅打开页面不会自动 Capture，用户点击对应 Capture 后才采集。
3. Draft dirty 时执行 Search / Capture 会先保存；保存失败时 Capture 不继续，且错误可见。
4. 保存/刷新/重新 Research 后人工草稿、推荐事实、Edition 选择、Guide Draft 与图片选择不丢失。
5. Catalog Match 未确认前不会把现有 Catalog 数据预填进当前新对象 Draft；确认或拒绝匹配后分别进入正确路径。
6. 三类 Capture 不串写：Work Capture 不误写 Edition/Structure，Edition Capture 不误写 Work，Structure Capture 不误写 Work/Edition/Classification。
7. Structure 树的推荐对象与被动 Research 对象严格区分，Catalog 只写直接关系，`volume_count` 不被当前成员数覆盖。
8. Research 缺失时仍可完成审核与 Catalog 写入；Research、Structure、Classification 均不得成为无关的强制门槛。
9. 来源原图只作为审核上下文，不会自动创建 Edition 或写入 Catalog 图片。
10. 修改相关模块后运行对应后端与前端回归测试，并在交付说明中列出验证结果。
