# 达人书单 CSV 导入格式

这个格式用于用户以后自助导入其它达人的书单。系统内置达人资料由代码种子导入，不要求用户手工整理。

## 目录结构

每个达人建议单独一个文件夹：

```text
booklist/
  达人名/
    profile.md
    list.csv
    images/
      001.jpg
      002.jpg
    order.json
```

`profile.md` 可选，用来写达人简介、路线说明和资料来源。`list.csv` 是推荐条目。`images/` 放原图，CSV 用文件名引用。

`order.json` 可选，用来校准原图顺序。系统会优先按这里的顺序显示图片，识别不到的图片再按文件名排序：

```json
{
  "order": ["001.jpg", "002.jpg", "imgi_72_"]
}
```

`order` 里的值可以是完整文件名，也可以是文件名前缀。

## 核心原则

同一套书如果出现在多个年龄、阶段或达人书单里，不要合并。每一次出现都保留一行推荐记录，这样作品详情才能反查“哪些达人在哪个年龄/阶段推荐过”。

书名尽量保持图片里的原始写法，同时可补充规范书名。拿不准是否同一本书时先分开，后续在后台做归并。

## 字段说明

必填字段：

| 字段 | 说明 | 示例 |
| --- | --- | --- |
| source_name | 达人名 | 香蕉妈妈 |
| list_title | 书单/路线标题 | 2024年度香蕉妈妈2-3岁英文绘本书单 |
| raw_title | 图片或资料里的原始书名 | Spot 系列 |

推荐字段：

| 字段 | 说明 | 示例 |
| --- | --- | --- |
| row_id | 行号，便于回查 | bm-2-3-001 |
| item_type | `work` 单本书，`collection` 套装/系列，`material` 非书架素材；也可用 `animation`、`app`、`audio`、`video`、`resource` | collection |
| canonical_title | 规范书名 | Spot |
| raw_author | 原始作者 | Eric Hill |
| stage_title | 阶段名 | 2-3岁 |
| stage_order | 阶段排序 | 2 |
| position | 在原书单中的顺序 | 1 |
| age_text | 原始年龄文字 | 2.5岁以上 |
| age_min_months | 推荐年龄下限，单位月 | 30 |
| age_max_months | 推荐年龄上限，单位月 | 48 |
| age_semantics | 年龄语义：`recommended`、`advanced`、`minimum` | minimum |
| reading_mode | 阅读方式：`read_aloud`、`independent`、`listening` | listening |
| ar_text | AR 原文 | AR 1.2-1.8 |
| ar_min | AR 下限 | 1.2 |
| ar_max | AR 上限 | 1.8 |
| lexile_text | 蓝思原文 | 300L-450L |
| lexile_min | 蓝思下限 | 300 |
| lexile_max | 蓝思上限 | 450 |
| ort_level_text | 牛津树等级原文 | 牛3-牛5 |
| category | 分类 | 互动绘本 |
| topic_tags | 主题标签，用 `;` 分隔 | 亲子互动;日常生活 |
| emphasis | 强调程度 | 强烈推荐 |
| progression | 进阶提醒 | 进阶+ |
| reading_channel | 点读或资源渠道 | 毛毛虫点读笔 |
| reminder | 加强提醒 | 3.5岁以上 |
| role | 素材在本阶段的角色 | mainline |
| material_type | 素材类型 | bridge_book |
| availability | 平台或资源可得性 | 小小优趣 |
| raw_text | 原图里的完整备注 | 强推，适合 3.5 岁以上进阶 |
| source_image_filename | 对应原图文件名 | 001.jpg |
| source_region_json | 原图区域，可选 JSON | {"x":0.1,"y":0.2,"w":0.3,"h":0.1} |

`item_type=material/animation/app/audio/video` 的条目不会进入作品书架，只作为路线素材和地图条目保存。庆爸这类资料里，动画、APP、训练材料建议用这些类型；“先裸听后回看”“降速 0.9x”这类操作动作不要单独导入为条目，放在 `raw_text`、`reminder` 或阶段说明里。

如果导入的是路线型达人，阶段信息必须能单独整理出来。CSV 里至少用 `stage_title`、`stage_order` 保留阶段；如果原资料有阶段时长、准入、晋级、测试材料、操作动作，先放入 `raw_text` 或 `reminder`，后续会拆到路线阶段资料库。不要把“去字幕观看”“先裸听后回看”这类动作写成 `raw_title`。

`role` 推荐枚举：`mainline` 主线、`supplement` 补充、`fallback` 备选/调整、`test_material` 测试材料、`extension` 兴趣拓展、`prerequisite` 前置条件。

`material_type` 推荐枚举：`picture_book` 绘本、`graded_reader` 分级、`bridge_book` 桥梁书、`early_chapter` 初章、`chapter_book` 章节书、`animation` 动画、`app` APP、`audio` 音频、`resource` 资源/台词本/练习册、`method` 方法说明。

## 阶段和横坐标

英语启蒙地图会从这些字段推导横坐标：

| 地图轴 | 优先读取 |
| --- | --- |
| 年龄 | `age_min_months`、`age_max_months`，其次读 `age_text` |
| 蓝思 | `lexile_min`、`lexile_max`，其次读 `lexile_text` |
| Oxford/牛津树 | `ort_level_text` 或其它等级备注 |
| AR | `ar_min`、`ar_max`，其次读 `ar_text` |

## 最小示例

```csv
source_name,list_title,item_type,raw_title,canonical_title,stage_title,age_text,age_min_months,age_max_months,emphasis,progression,reminder,source_image_filename
香蕉妈妈,2024年度香蕉妈妈2-3岁英文绘本书单,collection,Spot 系列,Spot,2-3岁,2.5岁以上,30,36,强烈推荐,进阶,,001.jpg
庆爸,常规路径 3-4岁2.0版,collection,Oxford Reading Tree,Oxford Reading Tree,阶段5,,36,48,,不要跨难度,听懂优先,003.jpg
```
