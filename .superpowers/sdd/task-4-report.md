# Task 4 实施报告：Dashboard / Creation / Projects 国际化

## 状态

已完成。严格在 Task 4 brief 指定的实现文件范围内修改；另按任务要求新增本报告。未执行 `git add` 或 `git commit`。

## 完成内容

### 数据与稳定值

- `dashboardData.js`、`createData.js`、`projectsData.js` 的展示字段改为 `labelKey`、`titleKey`、`descriptionKey`、`statusKey`、`subtitleStatusKey`、`unavailableMessageKey` 等翻译键。
- 保留项目标题、上传文件名、字幕文件名、ID、路由、时长、创作点、媒体路径，以及 `type` / `status` 等 machine values。
- 分类和状态筛选继续只使用稳定的 `id`、`type`、`status`，项目搜索继续使用原始项目标题。

### Dashboard

- Dashboard 全部可见文案、导航、响应式移动导航、Toast、图片替代文本和账户可访问名称接入 `useI18n()`。
- `DashboardHeader` 在余额入口之前挂载共享 `<LanguageSwitcher compact />`。
- 余额、月度消耗等数值统一通过 `formatNumber()` 格式化。
- 账户区域增加可收缩/换行布局，语言入口及账户操作保持至少 44px 交互尺寸；390px 下保持单行紧凑布局且无页面级横向溢出。

### Create

- 标题、说明、类型卡、上传区、文件限制、字幕状态、删除/上传字幕的可访问名称、创作小结、按钮及所有错误/不可用 Toast 均已本地化。
- 新上传视频仅写入稳定状态键；实际文件名和字幕文件名保持原值。
- 最大视频数判断继续使用 `creationTypes[].id` 和 `maxVideos`，不依赖渲染标签。

### Projects

- 页面标题、说明、搜索、通知、分类、状态、表头、状态/进度、操作、空状态、分页、Toast 与可访问名称均已本地化。
- 英文、日文切换后，中文项目名 `霸总短剧解说 01` 保持不变且可继续搜索。

### Locale 与自动化验证

- 新增完整的 `dashboard.*`、`create.*`、`projects.*` 三语资源组。
- `verify-i18n.mjs` 新增三条路由 × 三种语言的标题、Header 语言入口、代表性 Toast，以及 1487 / 768 / 390px 页面级 overflow 检查。
- 新增项目名在 English → 日本語切换后的搜索状态与结果持久性检查。

## TDD 证据

### RED

命令：

```bash
cd docs/web/homepage-prototype && npm run verify:i18n
```

首次沙箱内执行因本地端口权限返回 `listen EPERM`，按环境要求使用已批准的本地预览权限重跑。有效 RED 结果：

```text
locator.waitFor: Timeout 5000ms exceeded.
waiting for getByTestId('language-switcher-trigger') to be visible
```

失败原因与预期一致：Dashboard Header 尚未挂载语言切换入口。

### GREEN

最终命令及结果：

```bash
cd docs/web/homepage-prototype && npm run build
```

- PASS，Vite 构建成功（4727 modules transformed）。
- 仅保留既有的大 chunk 提示，不影响退出码。

```bash
cd docs/web/homepage-prototype && npm run verify:i18n
```

- PASS：`i18n public header verification passed`。

```bash
cd docs/web/homepage-prototype && npm run verify:dashboard
```

- PASS：反贴图扫描及工作台结构与交互验收通过。

```bash
cd docs/web/homepage-prototype && npm run verify:create
```

- PASS：反贴图扫描及新建创作页面交互验收通过。

```bash
cd docs/web/homepage-prototype && npm run verify:projects
```

- PASS：anti-paste scan、交互及响应式检查通过。

```bash
cd docs/web/homepage-prototype && npm run test:i18n
```

- PASS：4 tests passed，0 failed。

```bash
git diff --check -- <Task 4 文件范围>
```

- PASS，无空白错误。

## 自审

- [x] Dashboard / Create / Projects 渲染组件与页面中无硬编码中文 UI 文案。
- [x] 三语资源完整，缺失键不会回落为裸 key。
- [x] 项目名和文件名未翻译、未改写。
- [x] 过滤与操作不比较渲染标签。
- [x] Toast 在触发时通过当前 locale 的 `t()` 构造。
- [x] 共享 compact LanguageSwitcher 位于余额入口之前。
- [x] 1487 / 768 / 390px 三条路由、三种语言均通过页面级 overflow 断言。
- [x] 44px 交互目标保持。
- [x] 未引入 screenshot、base64、background-image 贴图、canvas 或 SVG 内嵌位图。
- [x] 未修改项目名/文件名、stable IDs、routes、durations、credits、media paths、type/status machine values。
- [x] 未执行 add / commit。

## 风险与未完成项

- 无功能性未完成项。
- 构建仍输出既有的 `Some chunks are larger than 500 kB` 提示；本任务未扩大范围处理 bundle 拆分。

## Review 修复（Medium / Low）

已读取 `.superpowers/sdd/task-4-review.md` 并完成全部 4 项修复：

1. `verify-i18n.mjs` 现在按 locale + route 精确断言代表性 Toast：Dashboard 充值、Create 参数设置、Projects 导出；不再以“非空字符串”作为通过条件。
2. 桌面账户余额与充值按钮的基础命中高度由 40px 提升为至少 44px；新增 1487px computed geometry 断言。
3. `<LanguageSwitcher compact />` 已移动到 `.dashboard-account` 内，成为 `.dashboard-account__balance` 的直接前置兄弟；新增 DOM 邻接断言。
4. 本地化的账户快捷操作容器已增加 `role="group"`；新增按三种语言查找具名 group 的 a11y 断言。

### Review TDD RED

在只新增精确 Toast、group、DOM 邻接与 44px 断言后运行：

```bash
cd docs/web/homepage-prototype && npm run verify:i18n
```

得到预期失败：

```text
AssertionError [ERR_ASSERTION]: zh-CN account actions should expose group semantics
actual: 0
expected: 1
```

证明新增断言能够捕获 review 指出的缺失语义。

### Review GREEN 与回归

修复后以下命令全部退出 0：

```bash
cd docs/web/homepage-prototype && npm run build
cd docs/web/homepage-prototype && npm run verify:i18n
cd docs/web/homepage-prototype && npm run verify:dashboard
cd docs/web/homepage-prototype && npm run verify:create
cd docs/web/homepage-prototype && npm run verify:projects
cd docs/web/homepage-prototype && npm run test:i18n
```

- `verify:i18n`：三语、三路由精确 Toast，具名 group，switcher/balance 邻接，44px 桌面命中区及三档 overflow 均通过。
- `verify:dashboard`：反贴图扫描、结构与交互通过。
- `verify:create`：反贴图扫描、交互通过。
- `verify:projects`：anti-paste、交互与响应式通过。
- `test:i18n`：4 passed，0 failed。
