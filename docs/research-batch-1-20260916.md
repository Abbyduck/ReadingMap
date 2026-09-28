# Django 审核批次 1：人工审核交接

日期：2026-09-16。数据库：`reading_map_django`。

## 本轮结果

- 已恢复 5 位达人：Susan教英语、庆爸、廖彩杏、盖兆泉、香蕉妈妈。
- 仅导入 1 份 JSON：`source_data/reading_lists/香蕉妈妈__065__2026年香蕉妈妈牛1-高章泛听泛读书单-小红书.json`。
- 源文件 SHA-256：`a81b04025e58754a36aa3856888f9cd5f17266fb046fee66ccd1ee22f223492e`。
- batch_id=1，target_reading_list_id=1，7 个 review_item，7 个主 Research subject。
- 3 项 ready，4 项 partial；7 项均未作人工决定。正式 Catalog 与正式推荐关系均为 0。
- 另有 13 个被动结构提议：How to Train Your Dragon 的 12 本原系列成员、Out of My Mind 的父系列。它们不是新增达人推荐。
- 本轮主项有 18 个证据关联；事实和 AI 推导分开保存。Research 不调用正式审核决定接口。

## 人工审核入口

打开 `http://127.0.0.1:53180/admin?batch=1`。依次核对来源、身份提议、客观证据、AI 推导及可选结构，然后选择关联已有、新建或忽略。

勾选被动结构时，每个未解决对象必须明确选择新建或匹配已有；只为当前主项建立来源推荐关系。提交成功后有正式实体与推荐关系的 Django 只读详情链接。忽略保留来源与研究记录。

## 特别需要检查

- Asterix、Out of My Mind：现有 6 张原图中未找到对应推荐，不能据此断言达人从未推荐；需补证或人工判断。
- Percy Jackson：JSON 指向的图片实际为第 8 页；推荐出现在现有第 7 页图片中。原五部与当前官方页面七部的系列范围也需判断。
- Because of Winn-Dixie：原 JSON 类型为 series，Research 提议修正为 book。Lexile 存在 660L / 670L 来源值差异，两值并列供核对，没有自动选择正式 Lexile。
- Out of My Mind、Wonder 同样提议由 series 修正为 book。Wonder 原图写明“非获奖作品但推荐”，不能沿用旧解析的奖项分类。
- 无可靠点读笔适配证据时保留未知；未知不等于不支持。Syntax / Cognitive 仅作定性推导，无全文与校准量表时不生成分数。

原 JSON 未改动；原图核查发现的问题保存在 Research 说明及歧义提示中。研究文件 `research_data/django-batch-1-20260916/` 是可重放输入，不替代数据库研究档案。

## 验证与边界

- `manage.py test reviews accounts --settings=config.settings_test`：19 项通过；写入测试均在隔离测试库。
- 前端 TypeScript 检查及 Vite 构建通过；现有 bundle 大小警告不阻断构建。
- Worker skill 格式验证通过。
- 浏览器实查 7 项审核队列、事实引用、Lexile 冲突提示及 Django 的 5 位达人；正式提交与只读结果详情在测试库验证，没有替用户审核真实记录。
- 本轮主要交付流程第 2、3 步及其人工审核入口，不代表整个后续审核产品均已完善。例如 AI 分类/评分的逐字段人工采纳、缺失来源材料补录仍需后续工作。

Research 更新会使旧审核快照失效；已决定的研究记录不能被 Worker 覆盖。正式已有字段冲突不自动覆盖，写入 Conflict 等待人工处理。
