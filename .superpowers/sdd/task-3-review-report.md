# Task 3 独立审查报告

## Verdict

- **规格符合性：PASS**
- **代码质量：CHANGES_REQUESTED**

实现本身满足 Task 3 的主要规格：集中数据中的固定值与字段正确；仅概览导航到 `/dashboard`；Logo 使用 React Router `Link` 返回 `/`；`DashboardPage` 是 Toast/Banner 唯一状态 owner；重复触发通过递增 `toast.id` 更新并重置 3.2 秒计时；Banner 关闭后卸载；处理中项目同时提供原生 `progress` 与 `处理中 66%` 文本；图片失败时卸载 `<img>` 并显示可访问 fallback；页面仅实现一个 `h1`；入口均为真实 link/button；未发现贴图作弊或 ownership 越界。

代码质量未批准的原因是验收脚本对多个明确规格缺少有效回归保护，并存在一个明显可假阳性的“三态”断言。产品实现未发现 Critical 缺陷。

## Critical

无。

## Important

### 1. Dashboard 验收脚本没有真正证明三态、唯一 h1、图片降级和 Toast 计时语义

- 文件：`docs/web/homepage-prototype/scripts/verify-dashboard.mjs:38-54`
- 问题：
  - 第 41 行仅断言 `[data-project-status]` 数量为 3；即使三个项目全是 `complete` 也会通过，属于明显假阳性，不能证明 `complete / processing / draft` 三态。
  - 第 44 行只验证原生 `progress` 属性，没有验证相邻的可见文本 `处理中 66%`。
  - 第 38 行只等待一个匹配标题，没有断言 Dashboard 中 `h1` 恰好为 1。
  - 脚本没有制造图片加载失败并验证破图被移除、fallback 的 `role=img` 与 `aria-label` 出现。
  - 第 47-54 行验证了 Toast 文案切换与手动关闭，但没有验证同一入口重复触发会重置生命周期，也没有验证约 3200ms 自动关闭。计时器被删掉、时长写错或同文案重复点击不重置时，当前脚本仍可通过。
- 影响：报告中的“结构与交互验收通过”覆盖面被高估；上述显式需求未来回归时 CI 不会阻止。
- 建议：
  1. 读取三个 `data-project-status` 值并与 `complete,processing,draft` 精确比较，同时断言 `处理中 66%` 可见。
  2. 增加 `page.locator("h1").count() === 1`。
  3. 拦截一个缩略图请求返回 404，断言对应 `<img>` 消失且 `${fallbackLabel}缩略图不可用` 出现。
  4. 对同一入口连续点击，确认 Toast 仍更新/重新开始生命周期；再等待计时窗口验证自动卸载。可使用 Playwright clock 降低真实等待和抖动。

## Minor

### 1. 灵感数据包含未消费的 icon 字段与 import

- 文件：`docs/web/homepage-prototype/src/data/dashboardData.js:2,9,74,82`
- 问题：`BookOpenText`、`Sparkle` 及两个 `icon` 字段未被 `InspirationPanel` 使用，也超出 brief 给出的基础 inspirations 形状。
- 建议：如果后续视觉任务不需要图标，删除这些 import/字段；如果需要，则在组件中明确渲染，避免集中 Mock 出现无效字段。

## 已核对通过

- 固定数据：`balance=1280`、`monthlyUsed=240`；三个 recent project 的 id、标题、工具、状态、进度、点数和图片路径与 brief 一致。
- 导航：仅 `overview` 配置 `/dashboard`，其他项为 `to: null` 且消息为 `${label}功能建设中`。
- 组件职责：Sidebar/MobileNav 按 `to` 分派 `NavLink`/button；Toast 不持有 timer；Banner 的关闭与 CTA 是独立按钮。
- Toast：`DashboardPage.jsx:23-32,54` 递增 id、清理旧 timer、手动关闭并重新挂载 Toast，重复/切换入口语义正确。
- Banner：`DashboardPage.jsx:41` 条件渲染，关闭后从 DOM 移除。
- 进度：`RecentProjects.jsx:26-27` 同时存在原生 progress 与可见状态文本。
- 图片：`DashboardThumbnail.jsx:8-24` onError 后移除 `<img>`，显示有 ARIA 名称的 fallback；三张业务缩略图资产在 `public/assets` 存在，属于允许的产品图片资产。
- 标题与 ARIA：Dashboard 实现中仅 `DashboardPage.jsx:36` 有一个 `h1`；主导航、移动导航、Banner、Toast、关闭按钮及图片 fallback 均有对应语义/名称。
- 路由：`App.jsx:13` 接入 `DashboardPage`；`DashboardSidebar.jsx:18-20` 的品牌链接为 React Router `Link to="/"`，没有 `window.location` 或伪链接。
- 禁止贴图：审查范围内未发现 `data:image`、base64、canvas、SVG 内嵌位图、参考稿编号或 `background-image`；唯一 `<img>` 是真实业务缩略图并带降级逻辑。
- Ownership：commit `77fc820` 仅包含 brief 列出的 15 个文件，未包含工作区现有官网脏改动。

## Cannot verify

- 按审查任务要求未重复运行 `npm run build`、`npm run verify:dashboard`、`npm run verify:routing`；其 PASS 状态仅来自 `task-3-report.md`，本次未独立复跑。
- 未提供 RED 阶段日志/提交，无法独立确认测试确实先于实现编写；只能确认当前脚本与实现均存在。
- 本任务未包含 Dashboard 样式文件，无法在本审查包内判断最终视觉布局、响应式显示/隐藏以及 CSS 是否会影响焦点可见性；这些应由后续样式任务验证。
- 未以屏幕阅读器实测动态 Toast 宣告；这里只能静态确认 `role="status"`、`aria-live="polite"` 和可访问按钮名称。

---

# Task 3 修复复审（2026-07-14）

## Verdict

- **规格符合性：PASS**
- **代码质量：APPROVED**

先前提出的 1 项 Important 与 1 项 Minor 均已解决，未发现修复引入的新阻塞问题。

## 先前问题复核

### Important 1：验收脚本覆盖不足与三态假阳性 — RESOLVED

- `scripts/verify-dashboard.mjs:49` 现在精确断言 Dashboard 只有一个 `h1`。
- `scripts/verify-dashboard.mjs:52-55` 读取并排序实际 `data-project-status`，精确比较 `complete,draft,processing`，不再以节点数量冒充三态覆盖。
- `scripts/verify-dashboard.mjs:58-59` 同时验证原生 `progress[value='66'][max='100']` 与可见文本 `处理中 66%`。
- `scripts/verify-dashboard.mjs:61-65` 对指定业务缩略图制造真实 404，验证响应确实发生、具名 fallback 出现且原 `<img>` 被卸载。预期 404 的豁免同时约束 URL 与状态/消息，其余浏览器错误仍进入失败集合。
- `scripts/verify-dashboard.mjs:72-84` 保存旧 Toast 节点、间隔后重复点击同一入口，验证旧节点被替换，并测量新 Toast 在约 3.2 秒后自动卸载；这能覆盖重复触发重置生命周期与自动计时语义。

### Minor 1：未消费的 inspirations icon 数据 — RESOLVED

- `src/data/dashboardData.js:1-10,66-81` 已移除 `BookOpenText`、`Sparkle` import 及对应未使用的 `icon` 字段，数据形状更贴合实际消费方与 brief。

## 修复质量与 ownership

- 修复 commit `2b78685` 仅修改 `scripts/verify-dashboard.mjs` 与 `src/data/dashboardData.js`，范围与审查意见一致。
- 404 测试使用单一、精确业务资源路径，不会吞掉其他资源错误。
- Toast 测试使用旧 DOM 断连而非仅检查相同文案，避免同文案导致的假阳性；2900–4200ms 容差对 3200ms 目标合理。
- 未发现新的 Critical、Important 或 Minor 问题。

## Cannot verify（复审）

- 按复审任务要求未重复运行 `npm run build`、`npm run verify:dashboard`、`npm run verify:routing`；本次对 PASS 证据的确认来自更新后的 `task-3-report.md` 与修复代码静态审查。
- 原报告中关于 RED 编写顺序、视觉样式范围及屏幕阅读器实测的限制仍然成立，不影响本次修复 verdict。
