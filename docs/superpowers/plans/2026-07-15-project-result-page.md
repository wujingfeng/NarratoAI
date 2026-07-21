# Project Result Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增结构化、响应式且可交互的项目结果页，并把已完成项目入口连接到该路由。

**Architecture:** 沿用现有 React Router 工作台壳层，新增数据、结果页组件和独立 CSS；项目列表仅把指定已完成项目的查看动作升级为链接。专项 Playwright 脚本同时承担结构、交互、响应式和禁止贴图检查。

**Tech Stack:** React 19、React Router、Phosphor Icons、原生 HTML Video、CSS、Playwright、Vite

## Global Constraints

- 结果路由固定为 `/dashboard/projects/overlord/result`。
- 必须复用 `DashboardSidebar`、`DashboardHeader`、`DashboardMobileNav`。
- 允许使用 `public/media/narration-editor/` 的真实媒体；禁止将参考图及其局部作为页面资产。
- 交付媒体为 `public/media/project-result/overlord-narration-result-85s.mp4`，实际 1080×1920、85 秒，并配套 WebVTT 字幕。
- 删除参考图后，最终结果不能缺失任何主体内容。
- 不提交 Git，不改动无关脏文件。

---

### Task 1: 专项验收脚本（RED）

**Files:**
- Create: `docs/web/homepage-prototype/scripts/verify-project-result.mjs`
- Modify: `docs/web/homepage-prototype/package.json`

**Interfaces:**
- Consumes: Vite preview 地址 `BASE_URL`，Chrome 可执行路径 `CHROME_PATH`。
- Produces: `npm run verify:project-result` 命令。

- [ ] **Step 1: 写入专项脚本**，检查结果路由、直接访问和刷新、唯一焦点标题、复用组件、导航选中态、真实 `<video>`、85 秒 metadata、媒体 2xx/MIME、全屏调用、任务步骤、日志、摘要、链接入口、控制交互、桌面/移动溢出及禁止贴图规则。
- [ ] **Step 2: 运行 `PROJECT_RESULT_SCAN_ONLY=1 npm run verify:project-result`**，预期因结果页源文件不存在而失败。

### Task 2: 路由、数据和页面骨架（GREEN）

**Files:**
- Create: `src/data/projectResultData.js`
- Create: `src/pages/ProjectResultPage.jsx`
- Create: `src/components/projects/ProjectResultPlayer.jsx`
- Create: `src/components/projects/ProjectResultDetails.jsx`
- Create: `src/styles/project-result.css`
- Modify: `src/App.jsx`
- Modify: `src/main.jsx`
- Modify: `src/components/RouteEffects.jsx`

**Interfaces:**
- Consumes: `dashboardNavItems`、`dashboardCredits` 和工作台共享组件。
- Produces: `ProjectResultPage`、`ProjectResultPlayer`、`ProjectResultDetails` 以及 `/dashboard/projects/overlord/result`。

- [ ] **Step 1: 定义 `projectResult` 数据**，包含成片媒体、任务步骤、日志、消耗和摘要。
- [ ] **Step 2: 实现原生视频播放器**，通过 `onTogglePlay`、`onToggleMute`、`onFullscreen` 暴露控制行为。
- [ ] **Step 3: 实现详情组件**，用真实 DOM 组织步骤轴、日志、创作点消耗与项目摘要。
- [ ] **Step 4: 组合页面壳层和 Toast**，提供导出/字幕下载与未接入操作反馈。
- [ ] **Step 5: 注册路由、页面标题和样式入口**。

### Task 3: 项目列表入口与完整 GREEN

**Files:**
- Modify: `src/components/projects/ProjectTable.jsx`
- Modify: `src/pages/ProjectsPage.jsx`

**Interfaces:**
- Consumes: 项目 `id` 和可选 `resultPath`。
- Produces: 第一条已完成项目的“查看结果”路由链接。

- [ ] **Step 1: 为 `ProjectTable` 增加结果链接渲染**，其他状态和操作保持现状。
- [ ] **Step 2: 运行 `npm run verify:project-result`**，预期专项检查全部通过。
- [ ] **Step 3: 运行 `npm run verify:projects`、`npm run verify:routing`、`npm run build`**，预期全部退出码为 0。

### Task 4: 视觉检查与禁止贴图自检

**Files:**
- Create: `docs/web/homepage-prototype/artifacts/project-result/project-result-desktop-1487.png`

**Interfaces:**
- Consumes: 本地 Vite preview。
- Produces: 1487×1058 桌面验收截图，仅存放在 artifacts。

- [ ] **Step 1: 启动本地服务并用 Playwright 截图**，核对布局、密度、层级、文本溢出和播放器显示。
- [ ] **Step 2: 根据视觉检查微调 CSS 后重新运行专项验证和构建**。
- [ ] **Step 3: 执行禁止贴图扫描**，确认无参考图、`data:image`、canvas、CSS `background-image:url()`、SVG bitmap 残留。
