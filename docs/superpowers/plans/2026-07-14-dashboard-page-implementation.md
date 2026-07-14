# 工作台首页还原 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `docs/web/homepage-prototype/` 中以结构化 React/HTML/CSS 高保真重建桌面与移动工作台首页，建立 `/`、`/dashboard`、`*` 三类真实客户端路由，并让官网全部创作入口进入工作台。

**Architecture:** `main.jsx` 只负责挂载 `BrowserRouter`，`App.jsx` 只负责路由表与路由副作用；现有官网状态原样迁入 `pages/HomePage.jsx`。工作台由 `pages/DashboardPage.jsx` 协调 Banner/Toast 状态，集中 Mock 数据驱动一组职责单一的 `components/dashboard/` 组件，独立 `dashboard.css` 提供 desktop-first 布局与约 `1024px` 的移动导航切换。Playwright 脚本分别验证路由/官网回归、工作台结构交互和响应式视觉指标，截图只写入 `artifacts/screenshots/`。

**Tech Stack:** React 19.2、React Router DOM 7、Vite 6.4、`@phosphor-icons/react` 2.1、原生 CSS Grid/Flex/媒体查询、Playwright 1.61、Node.js ESM 验证脚本。

## Global Constraints

- 保留官网 `/`；新增工作台 `/dashboard`；未知路径渲染轻量 404，不创建任何空白业务占位路由。
- 站内跳转必须使用 `Link`、`NavLink` 或 `useNavigate`；不得用组件布尔状态或 `window.location` 模拟路由。
- 官网所有“开始创作”“使用相同模板创作”“立即体验”等语义明确的创作入口都进入 `/dashboard`；“查看案例”、锚点、Tab、视频弹窗、登录/价格 Toast 行为保持原样。
- 工作台只有 `/` 与 `/dashboard` 是已实现目标；Logo 返回 `/`，所有其他业务动作保持当前路由并显示可访问的“功能建设中” Toast。
- Mock 固定展示余额 `1,280`、月度消耗 `240`、完成/处理中/草稿三态、处理中 `66%`、三种快捷工具和三条案例灵感；不接后端、持久层、假延迟或假成功状态。
- 参考图 `docs/web/prototypes/b-style/04-dashboard-desktop.png` 与 `28-dashboard-mobile.png` 只能用于人工比对；禁止复制、裁切、导入页面或静态资产。
- 禁止 `data:image`、base64、canvas 截图、`background-image: url(...)` 页面贴图、SVG 内嵌位图、透明热点覆盖；文字、Logo、卡片、导航、进度、统计和 Banner 必须是可编辑 DOM/CSS/纯矢量结构。
- 允许复用的图片仅限现有内容资产 `public/assets/short-drama-thumb.webp`、`film-action-thumb.webp`、`documentary-thumb.webp`；每张必须有 `alt` 和结构化加载失败占位。头像使用结构化图标，不新增参考图裁片。
- 移动端在 `320px` 以上无页面级横向溢出，触控目标不小于 `44 × 44 CSS px`，底部导航不得遮挡内容，并计入 `env(safe-area-inset-bottom)`。
- 路由切换更新 `document.title`、滚动到顶部并将焦点移至主标题；Toast 使用 `role="status"`/`aria-live="polite"`；当前导航使用 `aria-current="page"`；进度同时提供原生 `progress` 与可见 `66%`。
- `prefers-reduced-motion: reduce` 下关闭非必要动画与平滑滚动；所有交互提供可见 `:focus-visible`。
- 交付前必须确认：**删除参考图后，最终结果不能缺失任何主体内容。**
- 当前工作区已有未提交改动，基线为：`scripts/verify-hero.mjs`、`scripts/verify-three-hero.mjs`、`src/components/ThreeHeroScene.jsx`、`src/components/heroThreeScene.js`、`src/styles/demo-workbenches.css`、`src/styles/home.css`，以及未跟踪的 `scripts/verify-demo.mjs`。实施时禁止 `git restore`、`git checkout --`、`git reset`、`git clean` 或覆盖这些文件；每次仅显式 `git add` 本任务列出的文件。
- 项目限制：复杂任务最多 2 个 Subagent；禁止 Subagent 再创建 Subagent。各任务实现后必须独立执行测试、规格审查和 commit，不能把无关脏改动带入提交。

---

## 现有结构与改动边界

### 已核对的现有入口

- `src/main.jsx`：当前直接挂载 `<App />`，并全局导入 `tokens.css`、`home.css`。
- `src/App.jsx`：当前承载官网全部状态；Hero 与 Final CTA 的 `onStart` 仍显示旧 Toast；Demo 的 `onTemplate` 显示旧 Toast；Capability 的“立即体验”先选 Tab 再滚到 Demo。
- `src/components/HeroSection.jsx:178`：Hero “开始创作”。
- `src/components/DemoSection.jsx:428`：当前激活工具的案例卡“使用相同模板创作”（每个 Tab 三张）。
- `src/components/CapabilitySection.jsx:59`：三张能力卡“立即体验”。
- `src/components/FinalCtaSection.jsx:9`：底部“开始创作”。
- `src/components/SiteHeader.jsx` 与 `SiteFooter.jsx`：目前没有“开始创作”，其锚点、登录、价格和法律链接不可改成工作台跳转。
- `src/components/Toast.jsx`：官网 Toast 已具备 `role="status"`；工作台使用独立 Toast，避免官网状态跨路由残留。
- `vite.config.mjs`：Vite dev/preview 的 SPA fallback 可服务 `/dashboard`；需要自动化直接访问与刷新验证，而不是额外添加静态 HTML 入口。

### 文件职责图

| 文件 | 动作 | 单一职责 |
| --- | --- | --- |
| `package.json`、`package-lock.json` | Modify | 锁定 `react-router-dom@7`，增加 `verify:routing`、`verify:dashboard`、`screenshot:dashboard` 命令 |
| `src/main.jsx` | Modify | 用 `BrowserRouter` 包裹应用并导入工作台样式 |
| `src/App.jsx` | Modify | 声明 `/`、`/dashboard`、`*` 路由与全局路由变化处理 |
| `src/pages/HomePage.jsx` | Create | 原封不动承接现有官网状态并把创作动作统一接到 `useNavigate` |
| `src/pages/DashboardPage.jsx` | Create | 编排工作台、Banner 状态和重复可重置的 Toast 生命周期 |
| `src/pages/NotFoundPage.jsx` | Create | 轻量 404 及返回官网/进入工作台真实链接 |
| `src/components/RouteEffects.jsx` | Create | 路由切换时更新标题、滚动与主标题焦点 |
| `src/data/dashboardData.js` | Create | 导航、工具、项目、余额、灵感的唯一 Mock 来源 |
| `src/components/dashboard/*.jsx` | Create | 品牌/导航、账户区、Banner、入口卡、工具、项目、余额、灵感、移动导航、Toast、缩略图降级 |
| `src/styles/dashboard.css` | Create | 工作台 Token、桌面/平板/移动布局、状态和 reduced-motion |
| `scripts/verify-routing.mjs` | Create | 路由、全量官网创作入口、历史导航、404、官网行为回归 |
| `scripts/verify-dashboard.mjs` | Create | 工作台结构、交互、可访问性、错误监听、响应式与反贴图检查 |
| `scripts/capture-dashboard.mjs` | Create | 目标视口截图到 `artifacts/screenshots/`，不改页面资源 |

除 `src/App.jsx`、`src/main.jsx`、包文件外，工作台实现全部使用新文件。不要顺手格式化或修改已有脏文件，尤其不要触碰当前已修改的 `home.css`、`demo-workbenches.css` 和 Three.js 文件。

---

### Task 1: 建立路由失败测试、安装依赖并拆分页面壳

**Files:**
- Create: `docs/web/homepage-prototype/scripts/verify-routing.mjs`
- Create: `docs/web/homepage-prototype/src/components/RouteEffects.jsx`
- Create: `docs/web/homepage-prototype/src/pages/HomePage.jsx`
- Create: `docs/web/homepage-prototype/src/pages/NotFoundPage.jsx`
- Modify: `docs/web/homepage-prototype/src/App.jsx`
- Modify: `docs/web/homepage-prototype/src/main.jsx`
- Modify: `docs/web/homepage-prototype/package.json`
- Modify: `docs/web/homepage-prototype/package-lock.json`

**Interfaces:**
- Produces: `App(): ReactElement`，固定提供 `/`、`/dashboard`、`*` 路由；本任务的 `/dashboard` 先使用可测试的 `DashboardRouteBoundary` 路由边界，Task 3 再接入完整 `DashboardPage`。
- Produces: `HomePage(): ReactElement`，暂时保持原 `App` 的所有 props/状态行为。
- Produces: `RouteEffects(): null`，按 `location.pathname` 设置标题并查找 `[data-route-heading]` 聚焦。
- Produces: `NotFoundPage(): ReactElement`，包含 `Link to="/"` 与 `Link to="/dashboard"`。
- Consumes: Vite history fallback；现有官网组件 API 不变。

- [ ] **Step 1: 记录并保护脏工作区基线**

Run:

```bash
cd docs/web/homepage-prototype
git status --short
git diff -- scripts/verify-hero.mjs scripts/verify-three-hero.mjs src/components/ThreeHeroScene.jsx src/components/heroThreeScene.js src/styles/demo-workbenches.css src/styles/home.css > /tmp/narrato-dashboard-preexisting.patch
test -s /tmp/narrato-dashboard-preexisting.patch
```

Expected: 输出与 Global Constraints 中列出的 6 个已修改文件和 1 个未跟踪脚本一致；`test` 退出码为 0。此补丁只作核对，不应用、不还原。

- [ ] **Step 2: 先写最小路由验证并确认旧实现失败**

在 `scripts/verify-routing.mjs` 写入可独立执行的 Playwright 骨架，至少使用以下断言（完整脚本还需统一收集 `console.error`、`pageerror`、`requestfailed` 和 `>=400` response）：

```js
import { chromium } from "playwright";

const baseUrl = process.env.BASE_URL || "http://127.0.0.1:4173";
const executablePath = process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const browser = await chromium.launch({ executablePath, headless: true });
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });

await page.goto(`${baseUrl}/dashboard`, { waitUntil: "domcontentloaded" });
if ((await page.locator("h1").textContent()) !== "工作台概览") {
  throw new Error("/dashboard 应渲染工作台概览而不是官网");
}
await page.goto(`${baseUrl}/missing-route`, { waitUntil: "domcontentloaded" });
await page.getByRole("heading", { name: "页面未找到" }).waitFor();
await browser.close();
console.log("路由骨架验收通过");
```

Run（终端 A 保持运行）：

```bash
npm run build
npm run preview -- --host 127.0.0.1
```

Run（终端 B）：

```bash
node scripts/verify-routing.mjs
```

Expected: FAIL，错误包含 `/dashboard 应渲染工作台概览而不是官网`，证明测试能识别当前无路由状态。

- [ ] **Step 3: 安装 Router 并更新命令**

Run:

```bash
npm install react-router-dom@7
```

在 `package.json` 的 `scripts` 中加入：

```json
"verify:routing": "node scripts/verify-routing.mjs",
"verify:dashboard": "node scripts/verify-dashboard.mjs",
"screenshot:dashboard": "node scripts/capture-dashboard.mjs"
```

Expected: `package.json` 与 `package-lock.json` 均出现 `react-router-dom`，锁文件固定实际安装版本；不得手工编辑 lockfile。

- [ ] **Step 4: 将当前官网实现迁入 HomePage，不改变官网行为**

复制当前 `src/App.jsx` 全部逻辑到 `src/pages/HomePage.jsx`，只做三项必要变更：相对 import 改为 `../components/...`、导出名改为 `HomePage`、根节点增加 `data-page="home"`。本任务尚未改创作入口，因此核心形态必须是：

```jsx
export function HomePage() {
  // 原 App 的 activeTool/menuOpen/activeSection/modalCase/toast 状态与 effects 全部保留
  return (
    <div className="site-shell" data-page="home">
      {/* 原 SiteHeader、main、SiteFooter、VideoModal、Toast 结构原样迁移 */}
    </div>
  );
}
```

Expected: 现有官网组件文件和 CSS 均无改动；迁移前后首页 DOM 主要 class 与交互一致。

- [ ] **Step 5: 实现路由表、404 与路由副作用**

`src/main.jsx`：

```jsx
import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App.jsx";
import "./styles/tokens.css";
import "./styles/home.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter><App /></BrowserRouter>
  </React.StrictMode>,
);
```

`src/components/RouteEffects.jsx` 的公开行为：

```jsx
import { useEffect } from "react";
import { useLocation } from "react-router-dom";

const titles = {
  "/": "影创工坊｜AI 出片工作台",
  "/dashboard": "工作台概览｜影创工坊",
};

export function RouteEffects() {
  const { pathname } = useLocation();
  useEffect(() => {
    document.title = titles[pathname] || "页面未找到｜影创工坊";
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
    requestAnimationFrame(() => document.querySelector("[data-route-heading]")?.focus());
  }, [pathname]);
  return null;
}
```

`src/App.jsx`：

```jsx
import { Route, Routes } from "react-router-dom";
import { RouteEffects } from "./components/RouteEffects.jsx";
import { HomePage } from "./pages/HomePage.jsx";
import { NotFoundPage } from "./pages/NotFoundPage.jsx";

function DashboardRouteBoundary() {
  return <main><h1 data-route-heading tabIndex="-1">工作台概览</h1></main>;
}

export function App() {
  return <><RouteEffects /><Routes><Route path="/" element={<HomePage />} /><Route path="/dashboard" element={<DashboardRouteBoundary />} /><Route path="*" element={<NotFoundPage />} /></Routes></>;
}
```

`NotFoundPage` 的 `h1` 同样使用 `data-route-heading tabIndex="-1"`，并提供两个真实 `Link`。不要加入自动重定向。

- [ ] **Step 6: 构建、启动 preview 并让路由测试转绿**

Run:

```bash
npm run build
```

Expected: `vite build` 退出码 0。随后重启 preview，执行：

```bash
npm run verify:routing
```

Expected: PASS，打印 `路由骨架验收通过`；直接访问 `/dashboard` 和 `/missing-route` 均无资源 404。

- [ ] **Step 7: 独立审查并提交**

Run:

```bash
git diff --check
git diff -- package.json package-lock.json src/main.jsx src/App.jsx src/components/RouteEffects.jsx src/pages/HomePage.jsx src/pages/NotFoundPage.jsx scripts/verify-routing.mjs
git status --short
git add package.json package-lock.json src/main.jsx src/App.jsx src/components/RouteEffects.jsx src/pages/HomePage.jsx src/pages/NotFoundPage.jsx scripts/verify-routing.mjs
git commit -m "feat: add homepage and dashboard routes"
```

Expected: commit 只包含上述 8 个路径；预存脏文件仍保持未 staged，内容未被恢复或覆盖。

---

### Task 2: 将官网全部创作入口接到 `/dashboard`

**Files:**
- Modify: `docs/web/homepage-prototype/src/pages/HomePage.jsx`
- Modify: `docs/web/homepage-prototype/scripts/verify-routing.mjs`

**Interfaces:**
- Consumes: `HomePage()` 及 React Router `useNavigate(): NavigateFunction`。
- Produces: `startCreation(): void`，统一执行 `navigate("/dashboard")`；Hero、当前 Tab 的 3 张模板卡、3 张能力卡和 Final CTA 都复用此回调。
- Preserves: `scrollTo(id)`、`openCase(caseItem)`、Tab 切换、登录/价格/法律 Toast。

- [ ] **Step 1: 扩充失败测试，枚举每类可见创作入口**

在 `verify-routing.mjs` 增加 `verifyCreationEntries()`。不能只验第一个匹配项；每次点击后用历史返回首页，切换 Demo Tab 以覆盖全部模板数据：

```js
async function expectDashboardAfterClick(page, locator, label) {
  await locator.click();
  await page.waitForURL(`${baseUrl}/dashboard`);
  if ((await page.locator("h1").textContent()) !== "工作台概览") throw new Error(`${label} 未进入工作台`);
  await page.goBack();
  await page.waitForURL(`${baseUrl}/`);
}

await expectDashboardAfterClick(page, page.getByRole("button", { name: /^开始创作/ }).first(), "Hero 开始创作");
for (const toolId of ["narration", "translation", "remix"]) {
  await page.locator(`#tool-tab-${toolId}`).click();
  const templates = page.getByRole("button", { name: /使用相同模板创作/ });
  for (let index = 0; index < await templates.count(); index += 1) {
    await expectDashboardAfterClick(page, templates.nth(index), `${toolId} 模板 ${index + 1}`);
    await page.locator(`#tool-tab-${toolId}`).click();
  }
}
const tryButtons = page.getByRole("button", { name: /立即体验/ });
for (let index = 0; index < await tryButtons.count(); index += 1) {
  await expectDashboardAfterClick(page, tryButtons.nth(index), `能力入口 ${index + 1}`);
}
await expectDashboardAfterClick(page, page.getByRole("button", { name: /^开始创作/ }).last(), "底部开始创作");
```

另加一条源码检查：`HomePage.jsx` 中不得再出现 `正式工作台接入后继续`。

Run: `npm run verify:routing`

Expected: FAIL，至少报告 Hero 仍留在 `/` 或旧文案仍存在。

- [ ] **Step 2: 用唯一导航回调替换旧 Toast 入口**

在 `HomePage.jsx` 增加：

```jsx
import { useNavigate } from "react-router-dom";

const navigate = useNavigate();
const startCreation = useCallback(() => navigate("/dashboard"), [navigate]);
```

绑定必须明确为：

```jsx
<HeroSection onStart={startCreation} onViewDemo={() => scrollTo("demo")} />
<DemoSection {...demoProps} onTemplate={startCreation} />
<CapabilitySection activeTool={activeTool} onChooseTool={startCreation} />
<FinalCtaSection onStart={startCreation} />
```

保留 `chooseTool` 仅用于真正需要的官网内部状态，若替换后无调用则删除该 callback 与 `TOOL_DATA` import；不得修改 `HeroSection.jsx`、`DemoSection.jsx`、`CapabilitySection.jsx` 或 `FinalCtaSection.jsx` 的 DOM。

- [ ] **Step 3: 验证创作入口与官网非创作行为**

在脚本中同时断言：Hero“查看案例”滚到 `#demo` 且 URL 保持 `/`；Tab 仍可切换；案例图片按钮仍打开 `role="dialog"`；登录与价格仍显示原 Toast。

Run:

```bash
npm run build
npm run verify:routing
```

Expected: PASS；所有枚举入口进入 `/dashboard`，非创作行为留在官网且无 browser error。

- [ ] **Step 4: 独立审查并提交**

Run:

```bash
git diff --check
rg -n "正式工作台接入后继续|开始创作|使用相同模板创作|立即体验" src scripts/verify-routing.mjs
git diff -- src/pages/HomePage.jsx scripts/verify-routing.mjs
git add src/pages/HomePage.jsx scripts/verify-routing.mjs
git commit -m "feat: route creation actions to dashboard"
```

Expected: 旧工作台 Toast 文案 0 命中；commit 只含 HomePage 与路由测试。

---

### Task 3: 建立集中 Mock、工作台结构组件与交互状态

**Files:**
- Create: `docs/web/homepage-prototype/src/data/dashboardData.js`
- Create: `docs/web/homepage-prototype/src/pages/DashboardPage.jsx`
- Create: `docs/web/homepage-prototype/src/components/dashboard/DashboardSidebar.jsx`
- Create: `docs/web/homepage-prototype/src/components/dashboard/DashboardHeader.jsx`
- Create: `docs/web/homepage-prototype/src/components/dashboard/PromotionBanner.jsx`
- Create: `docs/web/homepage-prototype/src/components/dashboard/CreationEntryCard.jsx`
- Create: `docs/web/homepage-prototype/src/components/dashboard/ToolQuickStart.jsx`
- Create: `docs/web/homepage-prototype/src/components/dashboard/RecentProjects.jsx`
- Create: `docs/web/homepage-prototype/src/components/dashboard/CreditsOverview.jsx`
- Create: `docs/web/homepage-prototype/src/components/dashboard/InspirationPanel.jsx`
- Create: `docs/web/homepage-prototype/src/components/dashboard/DashboardMobileNav.jsx`
- Create: `docs/web/homepage-prototype/src/components/dashboard/DashboardToast.jsx`
- Create: `docs/web/homepage-prototype/src/components/dashboard/DashboardThumbnail.jsx`
- Create: `docs/web/homepage-prototype/scripts/verify-dashboard.mjs`
- Modify: `docs/web/homepage-prototype/src/App.jsx`

**Interfaces:**
- `dashboardNavItems: Array<{id:string,label:string,icon:Icon,to:string|null,unavailableMessage:string|null,group:"main"|"tools"|"account"}>`。
- `dashboardTools: Array<{id:string,title:string,description:string,tone:"violet"|"cyan"|"orange",icon:Icon,unavailableMessage:string}>`。
- `recentProjects: Array<{id:string,title:string,tool:string,status:"complete"|"processing"|"draft",statusLabel:string,progress:number|null,credits:number,image:string}>`。
- `dashboardCredits: {balance:number,monthlyUsed:number}`；`inspirations: Array<{id,title,description,image}>`。
- 所有业务入口组件统一接收 `onUnavailable(message: string): void`；Banner 接收 `onClose(): void`；`DashboardThumbnail` 接收 `{src, alt, fallbackLabel}`。
- `DashboardPage(): ReactElement` 是唯一 Toast/Banner 状态 owner；`DashboardToast({message,onClose})` 不管理 timer。

- [ ] **Step 1: 先写工作台结构与交互失败测试**

`verify-dashboard.mjs` 必须沿用现有脚本的错误监听方式，并在 1487×1058 下断言以下真实语义：

```js
await page.goto(`${baseUrl}/dashboard`, { waitUntil: "domcontentloaded" });
await page.getByRole("heading", { name: "工作台概览" }).waitFor();
check(await page.getByRole("navigation", { name: "工作台主导航" }).count() === 1, "桌面主导航存在");
check(await page.getByRole("link", { name: "影创工坊" }).getAttribute("href") === "/", "品牌链接返回官网");
check(await page.locator("[data-project-status]").count() === 3, "最近项目覆盖三态");
check(await page.getByText("1,280", { exact: true }).count() >= 1, "余额为 1,280");
check(await page.getByText(/本月.*240.*创作点/).count() >= 1, "月耗为 240");
check(await page.locator("progress[value='66'][max='100']").count() === 1, "处理中进度有原生语义");

const before = page.url();
await page.getByRole("button", { name: /新建创作/ }).first().click();
await page.getByRole("status").filter({ hasText: "新建创作功能建设中" }).waitFor();
check(page.url() === before, "未实现功能不得改路由");

await page.getByRole("button", { name: "关闭促销信息" }).click();
check(await page.locator("[data-dashboard-banner]").count() === 0, "Banner 关闭后移除 DOM");
```

再验证重复点击两种入口时 Toast 文案更新；点击 Toast 关闭按钮后 `role=status` 消失；品牌链接返回 `/`；history back 返回 `/dashboard`。

Run: `npm run verify:dashboard`

Expected: FAIL，报告当前 `/dashboard` 只有路由边界，缺少导航与模块。

- [ ] **Step 2: 创建唯一 Mock 数据源**

`dashboardData.js` 使用 Phosphor icon component 引用，不存 JSX；关键固定数据如下：

```js
export const dashboardCredits = { balance: 1280, monthlyUsed: 240 };
export const recentProjects = [
  { id: "narration-01", title: "霸总短剧解说 01", tool: "短剧解说", status: "complete", statusLabel: "已完成", progress: null, credits: 120, image: "/assets/short-drama-thumb.webp" },
  { id: "remix-city", title: "都市逆袭 · 混剪", tool: "短剧混剪", status: "processing", statusLabel: "处理中 66%", progress: 66, credits: 80, image: "/assets/film-action-thumb.webp" },
  { id: "translation-mystery", title: "悬疑短剧翻译", tool: "视频翻译", status: "draft", statusLabel: "草稿", progress: null, credits: 150, image: "/assets/documentary-thumb.webp" },
];
```

导航只为概览配置 `to: "/dashboard"`；其他项 `to: null` 且消息精确为 `${label}功能建设中`。工具与灵感也必须带明确 unavailable message，避免组件内重复文案。

- [ ] **Step 3: 实现可复用入口与图片降级组件**

`DashboardThumbnail` 在图片失败时不留下破图图标：

```jsx
import { useState } from "react";

export function DashboardThumbnail({ src, alt, fallbackLabel }) {
  const [failed, setFailed] = useState(false);
  return <span className="dashboard-thumbnail">
    {!failed && <img src={src} alt={alt} loading="lazy" decoding="async" onError={() => setFailed(true)} />}
    {failed && <span className="dashboard-thumbnail__fallback" role="img" aria-label={`${fallbackLabel}缩略图不可用`}>{fallbackLabel}</span>}
  </span>;
}
```

Sidebar/MobileNav 对 `item.to` 使用 `NavLink`，否则使用 `button onClick={() => onUnavailable(item.unavailableMessage)}`。禁止 `<a href="#">` 和按钮内嵌按钮。

- [ ] **Step 4: 实现工作台模块语义**

组件根语义必须固定，供样式和测试使用：

```jsx
<aside className="dashboard-sidebar"><Link to="/" aria-label="影创工坊"><BrandMark /></Link><nav aria-label="工作台主导航">…</nav></aside>
<header className="dashboard-header">…</header>
<section data-dashboard-banner aria-label="促销信息">…<button aria-label="关闭促销信息" /></section>
<section aria-labelledby="recent-projects-title">…</section>
<progress value={66} max={100}>66%</progress><span>处理中 66%</span>
<nav className="dashboard-mobile-nav" aria-label="移动工作台导航">…</nav>
<div className="dashboard-toast" role="status" aria-live="polite">…<button aria-label="关闭提示" /></div>
```

`PromotionBanner` 的晶体、轨道、光束与指示点只用 `span`、伪元素和 CSS；关闭/立即查看为两个独立按钮，立即查看调用 `onUnavailable("优惠活动功能建设中")`。

- [ ] **Step 5: 由 DashboardPage 编排状态，并替换初始路由边界**

`DashboardPage` 只管理以下状态和回调：

```jsx
export function DashboardPage() {
  const [bannerVisible, setBannerVisible] = useState(true);
  const [toast, setToast] = useState({ id: 0, message: "" });
  const showUnavailable = useCallback((message) => setToast(({ id }) => ({ id: id + 1, message })), []);
  useEffect(() => {
    if (!toast.message) return undefined;
    const timer = window.setTimeout(() => setToast(({ id }) => ({ id, message: "" })), 3200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  return <div className="dashboard-shell" data-page="dashboard">{/* sidebar/header/main/modules/mobile-nav/toast */}</div>;
}
```

主标题 `h1` 必须是页面唯一 h1，可视觉隐藏但不能删除：`<h1 className="sr-only" data-route-heading tabIndex="-1">工作台概览</h1>`。在 `App.jsx` 删除 `DashboardRouteBoundary`，导入并渲染 `<DashboardPage />`。

- [ ] **Step 6: 运行结构测试并修复到通过**

Run:

```bash
npm run build
npm run verify:dashboard
npm run verify:routing
```

Expected: 全部 PASS；路由、Logo 历史导航、Toast 更新/关闭、Banner 移除、三态、66% 进度和 Mock 数值通过；浏览器无 console/page/request error。

- [ ] **Step 7: 独立审查并提交**

Run:

```bash
git diff --check
rg -n "href=\"#\"|window\.location|data:image|base64|canvas|04-dashboard|28-dashboard" src/pages/DashboardPage.jsx src/components/dashboard src/data/dashboardData.js
git diff -- src/App.jsx src/pages/DashboardPage.jsx src/components/dashboard src/data/dashboardData.js scripts/verify-dashboard.mjs
git add src/App.jsx src/pages/DashboardPage.jsx src/components/dashboard src/data/dashboardData.js scripts/verify-dashboard.mjs
git commit -m "feat: build dashboard structure and interactions"
```

Expected: 禁止项 0 命中；commit 不包含现有官网脏文件。

---

### Task 4: 桌面端高保真视觉还原与桌面指标测试

**Files:**
- Create: `docs/web/homepage-prototype/src/styles/dashboard.css`
- Modify: `docs/web/homepage-prototype/src/main.jsx`
- Modify: `docs/web/homepage-prototype/scripts/verify-dashboard.mjs`

**Interfaces:**
- Consumes: Task 3 固定 class/data attributes 与结构。
- Produces: 工作台 Token、`--dashboard-sidebar-width`、`--dashboard-mobile-nav-height`，1487×1058 侧栏 + 顶部账户区 + 主内容 Grid。
- Preserves: 不修改组件 DOM 来迁就 CSS；确需新增 hook class 时只在 Task 3 新组件中做最小增补并在本任务 commit 显式列出。

- [ ] **Step 1: 先加入桌面视觉指标并确认无样式时失败**

在 `verify-dashboard.mjs` 的 desktop 检查中读取真实 rect/computed styles：

```js
const metrics = await page.evaluate(() => {
  const sidebar = document.querySelector(".dashboard-sidebar").getBoundingClientRect();
  const main = document.querySelector(".dashboard-main").getBoundingClientRect();
  const banner = document.querySelector("[data-dashboard-banner]").getBoundingClientRect();
  return {
    pageWidth: document.documentElement.scrollWidth,
    viewportWidth: innerWidth,
    sidebarWidth: sidebar.width,
    sidebarLeft: sidebar.left,
    mainLeft: main.left,
    bannerWidth: banner.width,
    mobileNavDisplay: getComputedStyle(document.querySelector(".dashboard-mobile-nav")).display,
    bg: getComputedStyle(document.querySelector(".dashboard-shell")).backgroundColor,
  };
});
check(metrics.pageWidth <= metrics.viewportWidth + 1, "桌面不得横向溢出");
check(metrics.sidebarWidth >= 220 && metrics.sidebarWidth <= 280, "1487 桌面侧栏宽度接近参考稿");
check(metrics.mainLeft >= metrics.sidebarWidth, "主内容不得压到侧栏");
check(metrics.bannerWidth >= 900, "促销 Banner 占据主内容主宽度");
check(metrics.mobileNavDisplay === "none", "桌面隐藏移动底栏");
```

Run: `npm run verify:dashboard`

Expected: FAIL，侧栏宽度/布局/背景至少一项不满足。

- [ ] **Step 2: 定义 Dashboard Token 与页面骨架**

在 `src/main.jsx` 的现有 `home.css` import 后加入 `import "./styles/dashboard.css";`。`dashboard.css` 顶部必须使用语义变量而非散落色值：

```css
:root {
  --dashboard-bg: #050812;
  --dashboard-surface: #0a1020;
  --dashboard-surface-raised: #10182a;
  --dashboard-surface-muted: rgba(16, 24, 42, 0.72);
  --dashboard-border: rgba(142, 166, 211, 0.15);
  --dashboard-border-strong: rgba(132, 156, 255, 0.3);
  --dashboard-text: #f5f7ff;
  --dashboard-text-muted: #8e9ab3;
  --dashboard-primary: #6f6cff;
  --dashboard-primary-strong: #8a5cff;
  --dashboard-cyan: #21c7e8;
  --dashboard-orange: #ff9a55;
  --dashboard-success: #38d39f;
  --dashboard-warning: #ffb35c;
  --dashboard-radius-sm: 10px;
  --dashboard-radius-md: 16px;
  --dashboard-radius-lg: 22px;
  --dashboard-shadow: 0 18px 50px rgba(0, 0, 0, 0.28);
  --dashboard-sidebar-width: 250px;
  --dashboard-mobile-nav-height: 76px;
}

.dashboard-shell { min-height: 100vh; color: var(--dashboard-text); background: var(--dashboard-bg); }
.dashboard-sidebar { position: fixed; inset: 0 auto 0 0; width: var(--dashboard-sidebar-width); }
.dashboard-header, .dashboard-main { margin-left: var(--dashboard-sidebar-width); }
.dashboard-main { display: grid; grid-template-columns: minmax(0, 1fr); gap: 28px; padding: 28px 32px 36px; }
```

- [ ] **Step 3: 还原桌面模块层级与结构化装饰**

按参考比例实现：侧栏品牌/分组/会员卡；右上账户区；约 154px 高 Banner；首排 `minmax(360px, 1.65fr) repeat(3, minmax(180px, .8fr))`；下排最近项目主列 + Credits + Inspiration。Credits 环用 CSS：

```css
.credits-ring {
  background: conic-gradient(var(--dashboard-cyan) 0 32%, #2874f0 32% 62%, #7b36dc 62% 82%, rgba(80, 95, 130, .22) 82% 100%);
  border-radius: 50%;
}
.credits-ring::after { content: ""; position: absolute; inset: 11px; border-radius: inherit; background: var(--dashboard-surface); }
```

Banner 装饰不得使用 `url()`；使用 `.promotion-banner__crystal`、伪元素和 `clip-path: polygon(...)`。项目/灵感图片仅使用 Mock 的三张现有 WebP。

- [ ] **Step 4: 完成交互态与中间桌面重排**

所有 button/link/card action 统一写 `:hover`、`:active`、`:focus-visible`；在约 `1280px` 将首排工具降为可容纳列宽，在 `1025px–1199px` 将统计区重排为两列/单列，不允许页面横向滚动。侧栏选中项通过背景、边框和 `aria-current` 共同表达。

- [ ] **Step 5: 验证桌面与人工比对**

Run:

```bash
npm run build
npm run verify:dashboard
```

Expected: 1487、1280、1024/1025 桌面指标通过，无横向溢出，无 console/page/resource error。使用浏览器在 1487×1058 与参考图人工比对信息架构、模块比例、间距、颜色、边框、状态；不要把参考图加载到页面 DOM。

- [ ] **Step 6: 独立审查并提交**

Run:

```bash
git diff --check
rg -n "background-image\s*:\s*url|data:image|base64|canvas|04-dashboard|28-dashboard" src/styles/dashboard.css src/components/dashboard
git diff -- src/main.jsx src/styles/dashboard.css scripts/verify-dashboard.mjs src/components/dashboard
git add src/main.jsx src/styles/dashboard.css scripts/verify-dashboard.mjs
git commit -m "feat: match dashboard desktop layout"
```

Expected: 反贴图命中 0；若本任务确实补了组件 hook class，将具体组件路径加入 `git add`，仍不得全量 `git add .`。

---

### Task 5: 移动端响应式、固定底栏与可访问性完善

**Files:**
- Modify: `docs/web/homepage-prototype/src/styles/dashboard.css`
- Modify: `docs/web/homepage-prototype/scripts/verify-dashboard.mjs`
- Modify only if an accessibility hook is missing: `docs/web/homepage-prototype/src/components/dashboard/*.jsx`

**Interfaces:**
- Consumes: `--dashboard-mobile-nav-height` 与现有 `.dashboard-header--mobile`、`.dashboard-mobile-nav`、`.dashboard-tool-list` hook。
- Produces: `@media (max-width: 1024px)` 移动/平板导航形态；320/390/768 三种无溢出布局；reduced-motion 静态降级。
- Preserves: 移动 Header Logo 仍为 `Link to="/"`；桌面 Sidebar 与 Inspiration/完整 ring 只在移动断点隐藏，不从 DOM 逻辑删除。

- [ ] **Step 1: 先写移动与可访问性失败断言**

扩展 `verify-dashboard.mjs`，至少检查 390×844、320×720、768×1024：

```js
const mobileMetrics = await page.evaluate(() => ({
  pageWidth: document.documentElement.scrollWidth,
  viewportWidth: innerWidth,
  sidebarDisplay: getComputedStyle(document.querySelector(".dashboard-sidebar")).display,
  mobileNavDisplay: getComputedStyle(document.querySelector(".dashboard-mobile-nav")).display,
  toolsClient: document.querySelector(".dashboard-tool-list").clientWidth,
  toolsScroll: document.querySelector(".dashboard-tool-list").scrollWidth,
  toolsOverflow: getComputedStyle(document.querySelector(".dashboard-tool-list")).overflowX,
  bodyPaddingBottom: parseFloat(getComputedStyle(document.querySelector(".dashboard-main")).paddingBottom),
  navHeight: document.querySelector(".dashboard-mobile-nav").getBoundingClientRect().height,
}));
check(mobileMetrics.pageWidth <= mobileMetrics.viewportWidth + 1, "移动页面无横向溢出");
check(mobileMetrics.sidebarDisplay === "none", "移动隐藏桌面侧栏");
check(mobileMetrics.mobileNavDisplay !== "none", "移动显示底部导航");
check(mobileMetrics.toolsScroll > mobileMetrics.toolsClient && ["auto", "scroll"].includes(mobileMetrics.toolsOverflow), "工具只在内部横向滚动");
check(mobileMetrics.bodyPaddingBottom >= mobileMetrics.navHeight, "底部 padding 覆盖固定导航");
```

遍历移动导航按钮/链接检查 rect 宽高均 `>=44`；检查移动“概览”具有 `aria-current="page"`；`InspirationPanel` 与 `.credits-ring` computed display 为 none；项目 66% 文本仍可见。

Run: `npm run verify:dashboard`

Expected: FAIL，当前 desktop-first CSS 未完成移动形态。

- [ ] **Step 2: 实现移动信息重排与内部横向滚动**

`dashboard.css` 加入：

```css
@media (max-width: 1024px) {
  .dashboard-sidebar { display: none; }
  .dashboard-header, .dashboard-main { margin-left: 0; }
  .dashboard-header { position: static; min-height: 76px; padding: 16px 20px; }
  .dashboard-main { display: block; padding: 12px 20px calc(var(--dashboard-mobile-nav-height) + 32px + env(safe-area-inset-bottom)); }
  .dashboard-tool-list { display: grid; grid-auto-flow: column; grid-auto-columns: minmax(250px, 82vw); overflow-x: auto; overscroll-behavior-inline: contain; scroll-snap-type: inline proximity; }
  .dashboard-tool-card { scroll-snap-align: start; }
  .dashboard-inspiration, .credits-ring { display: none; }
  .dashboard-mobile-nav { display: grid; position: fixed; inset: auto 0 0; min-height: var(--dashboard-mobile-nav-height); padding-bottom: env(safe-area-inset-bottom); }
}
```

内容顺序必须是：移动 Header → Banner → 新建创作 → “快速开始”工具横滑 → 最近项目 → 月耗摘要 → 底栏。可用 CSS `order`，不得复制一份重复 Mock DOM。

- [ ] **Step 3: 对齐 390px 参考形态并支持 320px**

390px 下 Banner 变为高约 200px 的两层结构，新建卡纵向压缩，项目卡为缩略图 + 文案 + 状态 + 箭头；320px 下允许标题换行并缩小 gutter 到 14–16px。禁止固定 `width: 390px` 或按截图同比缩放。

- [ ] **Step 4: 完成键盘、焦点、reduced-motion 与缩放检查**

验证所有图标按钮有 `aria-label`；不可用入口是原生 `button`；Toast 不抢焦点；Logo 是有可读名称的 `Link`；项目状态始终含文字。CSS 增加：

```css
@media (prefers-reduced-motion: reduce) {
  .dashboard-shell *, .dashboard-shell *::before, .dashboard-shell *::after {
    scroll-behavior: auto !important;
    animation: none !important;
    transition-duration: 0.01ms !important;
  }
}
```

Playwright 用 `page.emulateMedia({ reducedMotion: "reduce" })` 检查 Banner/Toast/卡片 animationName 为 `none`；在 200% browser zoom 等效窄视口下确认无遮挡。

- [ ] **Step 5: 运行响应式验证**

Run:

```bash
npm run build
npm run verify:dashboard
npm run verify:routing
```

Expected: 320、390、768、1024、1280、1487 全部通过；移动工具内部可滚而页面不横溢；固定底栏不遮挡最后一项；桌面回归仍通过。

- [ ] **Step 6: 独立审查并提交**

Run:

```bash
git diff --check
git diff -- src/styles/dashboard.css scripts/verify-dashboard.mjs src/components/dashboard
git add src/styles/dashboard.css scripts/verify-dashboard.mjs
git commit -m "feat: add responsive dashboard navigation"
```

Expected: commit 只含响应式 CSS、测试及明确需要的可访问性组件小修；预存官网脏改动未 staged。

---

### Task 6: 路由全链路、Dashboard 截图与反贴图自动化

**Files:**
- Create: `docs/web/homepage-prototype/scripts/capture-dashboard.mjs`
- Modify: `docs/web/homepage-prototype/scripts/verify-dashboard.mjs`
- Modify: `docs/web/homepage-prototype/scripts/verify-routing.mjs`
- Modify: `docs/web/homepage-prototype/package.json` only if Task 1 did not already add all scripts

**Interfaces:**
- Produces: `npm run screenshot:dashboard`，输出 `dashboard-desktop-1487.png`、`dashboard-mobile-390.png`、`dashboard-mobile-390-full.png`、`dashboard-tablet-768.png`、`dashboard-wide-1920.png`。
- Produces: 静态扫描只扫描 authored source/public，不扫描允许存在的 `artifacts/`、`dist/`、`node_modules/` 或参考图目录本身。
- Consumes: preview URL `BASE_URL`（默认 `http://127.0.0.1:4173`）与 `CHROME_PATH` fallback。

- [ ] **Step 1: 先添加完整验收检查并确认能发现故意缺口**

把 `verify-dashboard.mjs` 的静态扫描限定为以下范围：`src/pages/DashboardPage.jsx`、`src/components/dashboard/`、`src/styles/dashboard.css`、`src/data/dashboardData.js`、`public/`。禁止模式：

```js
const forbidden = [
  ["参考图文件名", /(?:04-dashboard-desktop|28-dashboard-mobile)\.png/i],
  ["data image", /data:image/i],
  ["base64", /base64/i],
  ["canvas", /<canvas\b|CanvasRenderingContext2D|drawImage\s*\(/i],
  ["CSS url 背景", /background-image\s*:\s*url\s*\(/i],
  ["SVG 内嵌位图", /<image\b|xlink:href\s*=|href\s*=\s*["']data:image/i],
];
```

临时在本地未保存编辑器缓冲或 `/tmp` 副本中注入一个禁词运行扫描，确认脚本失败后撤销临时输入；不得向仓库文件提交故意违规内容。

Expected: 扫描对每类违规返回非 0，并给出文件名与 token；正常源码转为 PASS。

- [ ] **Step 2: 补齐全链路路由行为**

`verify-routing.mjs` 增加：直接 `/dashboard` → reload 仍是 Dashboard；Logo → `/`；`goBack()` → `/dashboard`；`goForward()` → `/`；未知路径 404 两个链接都可达；路由后标题与聚焦标题正确。每个 page 都监听：

```js
page.on("console", message => message.type() === "error" && failures.push(`console: ${message.text()}`));
page.on("pageerror", error => failures.push(`pageerror: ${error.message}`));
page.on("requestfailed", request => failures.push(`requestfailed: ${request.url()}`));
page.on("response", response => response.status() >= 400 && failures.push(`response ${response.status()}: ${response.url()}`));
```

Expected: 历史、刷新、404、标题和焦点均 PASS；不得忽略资源 404。

- [ ] **Step 3: 编写 Dashboard 截图脚本**

`capture-dashboard.mjs` 使用一个 `capture(name, viewport, fullPage)` helper；截图前等待字体与 `[data-page="dashboard"]`，并统一收集 browser issues：

```js
await capture("dashboard-desktop-1487", { width: 1487, height: 1058 }, false);
await capture("dashboard-mobile-390", { width: 390, height: 844 }, false);
await capture("dashboard-mobile-390-full", { width: 390, height: 844 }, true);
await capture("dashboard-tablet-768", { width: 768, height: 1024 }, true);
await capture("dashboard-wide-1920", { width: 1920, height: 1080 }, false);
```

输出目录用 `new URL("../artifacts/screenshots/", import.meta.url)`，不得写入 `public/` 或 `src/`。任何 console/page/request error 令脚本退出 1。

- [ ] **Step 4: 运行自动化与人工视觉 QA**

Run（preview 使用最新 build）：

```bash
npm run build
npm run verify:routing
npm run verify:dashboard
npm run screenshot:dashboard
```

Expected: 全部退出 0，5 张截图存在于 `artifacts/screenshots/`。逐张人工对比对应参考：1487×1058 对桌面图，390×844/长图对移动图，768 检查自然重排，1920 检查最大宽度与留白。发现差异只修结构化 DOM/CSS，不导入参考图。

- [ ] **Step 5: 独立审查并提交**

Run:

```bash
git diff --check
git diff -- package.json scripts/verify-routing.mjs scripts/verify-dashboard.mjs scripts/capture-dashboard.mjs
git add package.json scripts/verify-routing.mjs scripts/verify-dashboard.mjs scripts/capture-dashboard.mjs
git commit -m "test: verify dashboard routes and visuals"
```

Expected: 只提交脚本与必要 package script；截图是否提交遵循项目既有 artifacts 约定，默认作为本地 QA 证据而不 stage，绝不进入页面资产目录。

---

### Task 7: 既有官网回归、最终反贴图自检与交付审查

**Files:**
- Modify only when a verified regression requires it: files introduced by Tasks 1–6
- Do not modify: pre-existing dirty files listed in Global Constraints

**Interfaces:**
- Consumes: Tasks 1–6 的构建、三套新增命令和现有 `verify:hero`、`verify:demo`、`verify:three-hero`。
- Produces: 可审查的最终验证记录；无新运行时代码接口。

- [ ] **Step 1: 确认预存脏改动仍被保护**

Run:

```bash
git status --short
git diff -- scripts/verify-hero.mjs scripts/verify-three-hero.mjs src/components/ThreeHeroScene.jsx src/components/heroThreeScene.js src/styles/demo-workbenches.css src/styles/home.css > /tmp/narrato-dashboard-postexisting.patch
cmp /tmp/narrato-dashboard-preexisting.patch /tmp/narrato-dashboard-postexisting.patch
```

Expected: `cmp` 退出 0。如果上游在实施期间主动改了这些文件，不得覆盖；改用 `git diff` 人工确认本任务没有向其写入，并在交付中说明并发变化。

- [ ] **Step 2: 运行完整构建与官网回归套件**

Run:

```bash
npm run build
npm run verify:routing
npm run verify:dashboard
npm run verify:hero
npm run verify:demo
npm run verify:three-hero
npm run screenshot:dashboard
```

Expected: 所有命令退出 0。若既有验证因预存未提交改动自身失败，记录精确命令和原始错误，不能把它误报成 Dashboard 通过；先用新增测试与手工路径区分回归来源。

- [ ] **Step 3: 执行仓库级反贴图与资产边界扫描**

Run:

```bash
rg -n "04-dashboard-desktop|28-dashboard-mobile|data:image|base64|<canvas|drawImage\(|background-image\s*:\s*url\(" src public scripts --glob '!artifacts/**' --glob '!dist/**'
find public src -type f \( -iname '*dashboard*.png' -o -iname '*dashboard*.jpg' -o -iname '*dashboard*.webp' \) -print
```

Expected: 第一条对本任务新增 Dashboard 源码 0 个违规命中；如现有官网 Three.js 合法使用 `canvas`，必须由 `verify-dashboard.mjs` 的精确 authored-scope 扫描证明 Dashboard 不依赖它，不能删除或修改现有 Three.js。第二条不得发现参考图复制品。

- [ ] **Step 4: 人工 DOM/图片关闭自检**

在浏览器 DevTools 临时执行：

```js
document.querySelectorAll(".dashboard-shell img").forEach((image) => { image.hidden = true; });
```

Expected: 仅项目/灵感内容缩略图隐藏；Logo、Banner、文字、按钮、导航、项目标题/状态、进度、余额、月耗和统计结构仍完整。刷新恢复后逐项记录允许图片：3 个既有 WebP 仅作为项目/灵感内容图，均有 alt 与失败占位；无其他图片例外。

- [ ] **Step 5: 最终规格逐项审查**

逐项对照 `docs/superpowers/specs/2026-07-14-dashboard-page-design.md` 第 1–18 节，确认：路由、所有官网创作入口、桌面/移动取舍、中间断点、集中 Mock、Logo 返回、Toast/Banner、图片降级、404、标题/焦点/ARIA、reduced-motion、无横溢、截图、反贴图与官网回归均有对应测试证据。重点人工检查 320px、390px、768px、1024px、1487px。

Expected: 无规格缺口；不得以“后续完善”代替本规格内项目。

- [ ] **Step 6: 只在确有最终修复时提交收口 commit**

若本任务发现并修复 Tasks 1–6 引入的缺陷：

```bash
git diff --check
git diff -- src/App.jsx src/main.jsx src/pages/HomePage.jsx src/pages/DashboardPage.jsx src/pages/NotFoundPage.jsx src/components/RouteEffects.jsx src/components/dashboard src/data/dashboardData.js src/styles/dashboard.css scripts/verify-routing.mjs scripts/verify-dashboard.mjs scripts/capture-dashboard.mjs package.json package-lock.json
git add src/App.jsx src/main.jsx src/pages/HomePage.jsx src/pages/DashboardPage.jsx src/pages/NotFoundPage.jsx src/components/RouteEffects.jsx src/components/dashboard src/data/dashboardData.js src/styles/dashboard.css scripts/verify-routing.mjs scripts/verify-dashboard.mjs scripts/capture-dashboard.mjs package.json package-lock.json
git commit -m "fix: resolve dashboard acceptance gaps"
```

Expected: commit 只含经过失败复现与回归验证的 Dashboard/路由文件。若无需修复，不创建空 commit。

---

## 最终执行证据清单

实施者最终一次性交付时必须列出：

1. 完成内容：`/`、`/dashboard`、404、全部官网创作入口、工作台桌面/移动模块与交互。
2. 主要文件：路由壳、HomePage、DashboardPage、集中 Mock、Dashboard components、Dashboard CSS、三份脚本。
3. 验证命令及真实结果：`build`、`verify:routing`、`verify:dashboard`、现有三套官网验证、Dashboard 截图。
4. 视觉证据：5 个目标视口截图的绝对路径及人工对比结论。
5. 结构化自检：静态反贴图扫描结果、隐藏所有内容图片后的主体完整结论。
6. 图片例外：仅列出实际使用的现有 WebP、使用位置、alt 与失败占位；未使用则明确为“无”。
7. 代码审查：每任务独立审查结论，以及最终规格覆盖审查。
8. 风险/未完成项：仅列真实残余问题；不得把规格内缺口包装成后续项。
9. 脏工作区保护：明确预存未提交文件未被恢复、覆盖、stage 或带入 commit。

## 计划自审结果

- **规格覆盖：** Task 1 覆盖 BrowserRouter、直接访问、404、标题/焦点；Task 2 覆盖官网全量创作入口及非创作回归；Task 3 覆盖集中 Mock、组件、Logo、Toast、Banner、图片降级与业务交互；Task 4 覆盖桌面高保真和中间桌面；Task 5 覆盖移动/平板、安全区、触控、ARIA 与 reduced-motion；Task 6 覆盖全链路 Playwright、截图和精确反贴图扫描；Task 7 覆盖既有官网回归、图片隐藏检查、最终验收与脏改动保护。规格第 1–18 节均有实施或验证落点。
- **未决内容扫描：** 文档没有需要实施者自行补写的文件名、命令、接口、测试或实现分支；每个条件性收口命令也已列出完整允许路径集合。
- **接口一致性：** 路由固定为 `/`、`/dashboard`、`*`；统一业务回调名为 `onUnavailable(message)`；Banner 为 `onClose()`；Toast 为 `{message,onClose}`；Mock 字段和 status 枚举在 Task 3 定义后由 Tasks 4–7 原样消费；CSS hook 与测试选择器一致。
- **保护审查：** 计划只要求修改 4 个现有 clean 文件/包文件（`App.jsx`、`main.jsx`、`package.json`、`package-lock.json`）并创建新文件；明确禁止恢复或覆盖 6 个现有修改文件和 1 个未跟踪验证脚本。
