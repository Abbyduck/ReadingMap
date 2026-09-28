# Reading Map `/map` 主画布交接（2026-09-24）

## 何时读这份

接手 `/map` 页面中的连续阅读路线、阶段圆、书目在圆内的排布、默认视野、缩放、右上角地图总览窗或调试参数时，先读本文件。这里记录的是**当前前端原型**，不是数据库迁移或达人书单的完整审核流程。

## 用户已明确的方向

- 主画布要有轻柔的地图感、弯曲的连续路径、阶段站点和留白；不要把路径删掉，也不要添加来源书单里不存在的年龄段说明。
- 大圆背景保留，属于该阶段的书放在对应圆内。书目来自“香蕉妈妈牛1-高章泛听泛读书单”的指定 incremental-v2 JSON，不要用此前错误的“牛1-章节”或随意替换书目。
- 主画布**刚进入 `/map` 或刷新时**应看到完整路线、所有阶段圆；右上角小地图只是放大后的定位辅助，不能代替主画布的默认全线路视野。
- 支持连续缩放。小比例以封面为主，放大到阈值才展示书目详情；书的尺寸依据 `importanceScore`，高分书优先靠中间。悬停被遮挡的书时，应能浮到最上层。
- 调试框保留“重叠 / 整齐排列 / 不重叠”和书距调整；当前默认是**重叠**、书距 **0.75×**。“恢复默认”也必须回到这组值。阶段圆尺寸与间距、详情阈值不再作为调试控件。

## 代码与数据入口

| 用途 | 文件 |
| --- | --- |
| `/map` 路由入口 | `frontend/src/ProductApp.tsx` |
| React Flow 主画布、节点/边、书目布局、调试框与小地图 | `frontend/src/pages/ReadingMapPrototype.tsx` |
| 10 个圆的位置、大小和蜿蜒顺序 | `frontend/src/pages/readingMapRoute.mock.ts` |
| 当前页面样式、悬停层级、圆和小地图 | `frontend/src/pages/reading-map-prototype.css` |
| 书目转换为前端阶段及书对象 | `frontend/src/pages/readingMapPrototype.mock.ts` |
| 重要分值、尺寸映射和排序 | `frontend/src/pages/readingMapImportance.ts` |
| 从来源生成前端 JSON 的脚本 | `frontend/scripts/build-reading-map-mock.mjs` |
| 唯一指定的书单来源 | `source_data/drafts/reading_lists/香蕉妈妈__065__2026年香蕉妈妈牛1-高章泛听泛读书单-小红书__incremental-v2.json` |
| 生成物；不要手工改 | `frontend/src/pages/bananaN1Incremental.mock.json` |

`npm run dev` 与 `npm run build` 都会先运行生成脚本。脚本要求来源中有 10 个阶段、111 条书目；若来源条数变化，先检查来源与脚本，不要为通过检查随意丢数据。当前页面使用此本地 mock，不能把它误说成已经接入真实数据库路线。

## 当前实现快照

- `ReadingMapPage` 中 `layout` 初始值为 `"organic"`（调试框显示“重叠”），`DEFAULT_BOOK_SPACING = .75`；“恢复默认”设置为同样的值。
- `STAGE_SPACING = .9`，`BOOK_DETAIL_ZOOM = .85`，这两个值写在代码里，不在调试框中。
- React Flow 使用 `fitView`，初始适配参数为 `padding: .08, minZoom: .06, maxZoom: .18`，而不是固定到前几个圆的 `defaultViewport`。右下角适配视野按钮另有 `fitViewOptions`。
- 路线由 `readingMapRoute.mock.ts` 的 10 个 waypoint 与主画布的 9 条自定义弯曲边构成。阶段编号是 01–10，不能把来源中的“牛”等级硬映射成虚构年龄段。
- `MapNavigator` 使用 React Flow `MiniMap`，用于放大后定位。书节点的封面/详情由当前 zoom 与 `.85` 阈值决定。
- `positionedBooks` 决定三种布局。`organic` 使用按分数排序、中心优先的槽位并带轻微偏移；`spaced` 用拟合槽位降低重叠。修改布局时要同时检查大圆内边界与悬停层级。

## 修改与验收

1. 在 `frontend` 下运行 `npm run build`；生成脚本、TypeScript、Vite 均应通过。Windows 沙箱内若 Vite 写 `node_modules/.vite-temp` 遇到 `EPERM`，这是构建环境权限问题，需按权限流程重试，不能当作代码通过。
2. 打开 `http://127.0.0.1:53180/map` 并刷新：确认主画布 10/10 个圆与 9 条连接路径都可见，而不是只在右上角小地图里看见。上次在 1734×982 视口刷新验证，10 个圆均完整入屏，缩放约 `0.094×`；其他视口需重新检查。
3. 放大与缩小验证路径连续；放大后检查书始终属于对应圆、小地图能定位当前视野、封面到详情的切换、书的大小差异及 hover 层级。
4. 打开左下角“调试参数”：初始选中“重叠”，书距为 `0.75×`；切换布局和间距后点“恢复默认”，应回到重叠 / `0.75×`。再刷新一次，仍应是这组初始值且主画布重新适配完整路线。

## 接手注意

用户对“改错页面”和“删掉路径”非常敏感。改视觉前先确认运行的 `/map` 确实由 `ReadingMapPrototype.tsx` 渲染，并在修改后直接刷新运行页面验证。不要只凭构建成功或小地图的全景判断主画布已符合要求。若需要改变来源数据、路径语义或视觉方向，先与用户对齐，勿自行补造阶段含义。
