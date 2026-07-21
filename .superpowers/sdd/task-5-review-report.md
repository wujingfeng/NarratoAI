# Task 5 独立审查报告

## Verdict

- **规格：PASS**
- **质量：CHANGES_REQUESTED**

实现覆盖了 Task 5 的书面验收项：1024px 及以下切换移动形态；390/320/768 无页面横溢；信息顺序正确；工具列表内部横滑；最近项目与 66% 状态保留；月耗摘要位于项目后；底栏固定且内容底部留白足够；移动 Logo 是返回 `/` 的具名 Link；reduced-motion、移动导航 `aria-current`、44px 底栏目标和桌面回归均有实现及自动化证据。质量不批准的原因是移动月耗摘要缺失可见操作图标、一个主要移动入口仍只有 34px 高，以及现有验证没有覆盖这两处，因而会给出假绿。

## 阻塞性/重要发现

### 1. [P1] 月耗摘要的操作箭头实际不可见

- 证据：`src/components/dashboard/CreditsOverview.jsx:12` 渲染了 `ArrowUpRight`；但 `src/styles/dashboard.css:406` 给 `.credits-overview__action` 设定 `font-size: 0`，SVG 没有独立宽高；移动覆盖 `src/styles/dashboard.css:604` 只把按钮改为 44×44，没有恢复字体尺寸或给 SVG 指定尺寸。
- 视觉结果：390、320、768 实现截图中的“本月已使用 240 创作点”卡片右侧均没有参考稿中的可见箭头；参考图右侧有明确 chevron。按钮仍在 DOM 中且可被辅助技术命名，但指针/触屏用户看不到这是可操作入口。
- 建议：给 `.credits-overview__action svg` 指定明确的 `width/height`（或在移动端恢复非零图标尺寸），并添加可见性/尺寸断言。

### 2. [P1] 移动“查看全部”触控目标只有 34px 高

- 证据：`src/components/dashboard/RecentProjects.jsx:9` 的“查看全部”是移动端主要入口；`src/styles/dashboard.css:364` 只有 `padding: 6px`，没有 `min-height: 44px`。独立 Playwright DOM 采样在 320、390、768 三种视口均测得 **97×34px**。
- 影响：不满足移动端常用的 44px 触控目标标准，也与本任务“触控完善”的质量目标不一致。
- 测试缺口：`scripts/verify-dashboard.mjs:176-179,212-215` 只遍历底栏内的 `a, button`，因此三种视口测试全部通过但没有覆盖“查看全部”等页面内可见交互项。
- 建议：移动断点为该按钮增加至少 44px 高的目标区域，并将移动可见交互控件的最小 rect 检查纳入验收（如有明确例外，逐项排除并说明）。

## 视觉比对

### 390px

- **信息顺序正确**：Header → Banner → 新建创作 → 快速开始 → 最近项目 → 月耗摘要 → 固定底栏。独立 DOM 采样的 top 值依次为 0、88、308、490、751、1174；底栏固定在视口底部。
- **Banner**：实现为 196px 高的两层结构，符合 brief 的“约 200px”；创建卡为 154px，高度较桌面 251px 明显压缩。
- **横向工具露出**：工具容器 clientWidth 364、scrollWidth 989，页面 scrollWidth 390；只在内部横滑。截图可见下一张卡约一条窄边，露出提示弱于参考稿中同时可见两张以上卡的形态，属于非阻塞的比例/可发现性差异。
- **最近项目**：三条项目均包含缩略图、文案、状态、消耗与箭头；“处理中 66%”可见。第三张业务缩略图请求被测试故意 404，fallback 是既有验证场景，不是贴图缺失。
- **月耗摘要**：文本与图标存在，但右侧操作箭头不可见，见 P1。
- **整体密度差异**：参考图为 852×1846（与 390×844 同纵横比），一屏包含全部模块；实现 390 full-page 为 390×1374，首屏仅到工具区附近。书面 brief 明确要求约 200px Banner，因此不据此判规格失败，但实现相较参考稿明显更松、更长，后续若追求高保真应压缩纵向间距/卡片高度。
- **截图中底栏覆盖项目的观感**：这是 `fullPage` 截取 fixed 元素的绘制位置；独立运行时滚动到底后，最后内容 bottom 小于 nav top，现有遮挡断言也通过，不判运行时遮挡缺陷。

### 320px / 768px

- 独立测得 `documentElement.scrollWidth` 分别等于 320/768，无页面横向溢出；工具列表 scrollWidth 分别为 817/1919，内部横滑成立。
- 320 标题可换行，项目三列没有挤出页面；768 保持单列信息结构并保留工具横滑。
- 两个尺寸均复现“查看全部”34px 高和月耗箭头不可见的问题。

### 1487px 桌面回归

- 截图仍保留 Sidebar、四卡首排、最近项目/完整 Credits ring/Inspiration 三列与 Footer；移动 Header Logo 和底栏均不显示。
- `scripts/verify-dashboard.mjs:49-160,257-268` 对 1487、1280、1025 的桌面结构和内容做了回归断言；本轮 fresh run 通过。

## 可访问性与交互审查

- **通过**：移动 Header Logo 为 `DashboardHeader.jsx:8-10` 的 `Link to="/"`，具有 `aria-label="影创工坊"`。
- **通过**：底栏用原生 Link/button；当前“概览”由 `NavLink` 输出 `aria-current="page"`；独立与内置测试确认底栏各目标至少 44×44。
- **通过**：不可用入口继续使用原生 button；Toast 为 `role="status" aria-live="polite"`，没有主动聚焦代码。
- **通过**：项目状态始终保留文字，66% 还有原生 `<progress>`。
- **通过**：`dashboard.css:682-689` 对动画、过渡和 scroll behavior 提供 reduced-motion 降级；fresh 自动化验证通过。
- **需改**：移动“查看全部”只有 34px 高，见 P1。

## 测试质量

- Fresh `npm run build`：PASS，4627 modules transformed，构建 exit 0；仅有既存 >500kB chunk warning。
- Fresh `BASE_URL=http://127.0.0.1:4174 npm run verify:dashboard`：PASS，输出“工作台结构与交互验收通过”。
- Fresh `BASE_URL=http://127.0.0.1:4174 npm run verify:routing`：PASS，exit 0。
- Fresh `git diff --check`：PASS，0 输出。
- 正向评价：断言覆盖移动/桌面边界、内部滚动、fixed nav 遮挡、隐藏模块、Logo/ARIA、项目状态、reduced-motion 和路由回归。
- 假阳性风险：触控断言只检查底栏；月耗按钮只检查文本存在，没有检查 SVG 可见尺寸；信息顺序仅靠截图/人工报告，没有自动断言各模块 top 顺序。当前测试会在上述两个实际 UI 缺陷存在时仍全绿。
- reduced-motion 使用 `filter(Boolean)`（`scripts/verify-dashboard.mjs:239-253`），若某个目标 selector 意外缺失会被静默跳过；建议同时断言采集结果长度为 3。

## 反贴图与 ownership

- Commit `9416f71` 只包含 brief 允许的 `dashboard.css`、`verify-dashboard.mjs` 和 5 个必要 Dashboard 组件小改；未包含当前工作区的 Hero/Three.js/官网脏改动。
- 对 commit 范围扫描未发现 `background-image`、`data:image`、base64、canvas、参考图文件名或截图嵌入。实现由真实文本、组件、CSS 布局和图标组成。
- 保留的 WebP 是既有项目缩略图业务资产，符合允许图片资产边界；隐藏/删除参考图不会导致主体内容缺失。

## Cannot verify

- 无真实 iPhone safe-area 环境；代码同时在 fixed nav padding 和 main bottom padding 使用 `env(safe-area-inset-bottom)`，但本地 Chromium 的该值为 0，无法实机确认刘海/Home Indicator 区域。
- 未使用屏幕阅读器实测朗读顺序；本轮只验证 DOM/ARIA/原生语义。
- 未进行真实浏览器 200% zoom 操作；320px 窄视口可作为 reflow 近似证据，但不能等同完整缩放验收。
- 未做颜色对比度的数值审计。

## 结论

书面规格可以判 PASS，但在修复“月耗操作图标不可见”和“查看全部触控目标不足 44px”并补齐对应自动化之前，质量结论保持 **CHANGES_REQUESTED**。

---

## 复审（2026-07-14，Commit `6a2a546`）

### 最终 Verdict（取代初审质量结论）

- **规格：PASS**
- **质量：APPROVED**

### P1 修复确认

1. **月耗摘要操作箭头：已修复**
   - `src/styles/dashboard.css:407` 现在为 `.credits-overview__action svg` 明确设置 `20×20px`。
   - 更新后的 390 截图中右侧操作箭头清晰可见；独立 Playwright 在 320、390、768 三个视口均实测 SVG 为 `20×20px`。
   - `scripts/verify-dashboard.mjs:198-200,248-251`（当前文件行号）采集并断言月耗 SVG 至少为 18×18，不再只验证月耗文本。

2. **移动“查看全部”44px 触控目标：已修复**
   - `src/styles/dashboard.css:570` 在移动断点为 `.dashboard-section-heading button` 增加 `min-height: 44px`。
   - 独立 Playwright 重新遍历 Header、Main 和底栏的所有实际可见 Link/button，320、390、768 均没有宽或高小于 44px 的目标；初审的 `97×34px` 已不再复现。

3. **触控测试假阳性：已修复**
   - `scripts/verify-dashboard.mjs:180-197,239-247` 将检查从底栏扩展到 Header、Main 与底栏内全部具有非零尺寸且非 `visibility:hidden` 的交互目标。
   - 失败信息包含控件名称与实测宽高，能够直接定位回归。

4. **reduced-motion 缺失 selector 假绿：已修复**
   - `scripts/verify-dashboard.mjs:275-293` 先严格断言三个采样目标全部存在，再读取 animation/transition；原先 `filter(Boolean)` 静默跳过缺失节点的路径已移除。

### 视觉复核

- 390 截图保持 Header → Banner → 新建创作 → 快速开始 → 最近项目 → 月耗摘要 → 底栏的信息顺序。
- 工具卡列宽由 `82vw` 调整为 `78vw`；独立实测 390 容器宽 364px、首卡宽约 304px、轨道宽 943px，下一卡露出比初审更明确，同时页面 `scrollWidth === viewportWidth === 390`。
- 最近项目的三态、66% 进度、项目箭头以及月耗摘要均清晰可读；fixed 底栏的 full-page 截图绘制现象仍只是截图表现，运行时遮挡断言通过。
- 初审记录的整体纵向密度与参考图差异仍存在，但书面 brief 明确要求约 200px Banner；该差异不构成本 Task 的阻塞项。

### Fresh 复审验证

- `npm run build`：PASS，4627 modules transformed，`✓ built in 3.80s`；仅有既有大 chunk warning。
- `BASE_URL=http://127.0.0.1:4174 npm run verify:dashboard`：PASS，输出“工作台结构与交互验收通过”。
- `BASE_URL=http://127.0.0.1:4174 npm run verify:routing`：PASS，exit 0。
- `git diff --check`：PASS，0 输出。
- 独立 DOM 采样：320/390/768 页面均无横溢；全部采样交互目标至少 44×44；月耗 SVG 均为 20×20；工具列表仍只在组件内部横向滚动。

### 复审剩余限制

初审 `Cannot verify` 项保持不变：真实 iPhone safe-area、屏幕阅读器实测、真实浏览器 200% zoom 和颜色对比度数值审计未在本轮执行。这些不是本次修复引入的新风险。

### 复审结论

初审的两个 P1 与两条直接相关的测试假阳性路径均已修复，并有更新截图、代码断言和独立运行证据。Task 5 最终结论为 **规格 PASS / 质量 APPROVED**。
