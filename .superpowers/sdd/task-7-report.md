# Task 7：i18n 覆盖审计、响应式 QA 与最终验证报告

## 结论

- **最终状态：GREEN。** 资源 parity、raw-copy audit、9 路由 × 3 语言 × 3 视口矩阵、完整回归、禁贴图审计与参考资源移除验证均通过。
- 未执行 `git add`、`git commit` 或 `git push`；保留工作区原有大量脏改动。
- 唯一非 i18n 邻接修复：Dashboard 侧栏的“短剧解说”在 `/dashboard/narration/analysis`、`/dashboard/narration/editor` 等兄弟子路由原先不会保持 `aria-current="page"`。经主任务明确授权后，以最小路由前缀判断修复，并保留 `verify-narration-analysis.mjs` 原 active-state 断言。

## 1. TDD / 审计发现与修复

### RED：raw-copy audit

先扩展 `src/i18n/locale.test.js`，新增：

1. 递归 leaf-key 收集器，要求 `en`、`ja` 与 `zh-CN` 的 key 集合完全相等。
2. 扫描全部 `*.jsx` 与 `*Data.js` 的 Han 字面量；项目名、文件名、剧本/字幕/对白、语言自称等内容以带类别注释的显式 allowlist 管理。

首次执行 `npm run test:i18n`：5 项通过，raw-copy 项按文件与行号精确失败，命中：

- `components/BrandMark.jsx`：品牌名硬编码。
- `components/DemoSection.jsx`：三类 Demo preview 的标题/说明硬编码。

### GREEN：漏译修复

- 新增三语 `common.brand`，`BrandMark` 使用真实 `t()` 文本。
- 将 narration / translation / remix preview 的 `titleLine1/2`、`detailLine1/2` 补入三语资源；`DemoSection` 只消费资源 key。
- 最终 `npm run test:i18n`：**6 tests，6 pass，0 fail**。
- 最终三套资源 leaf key 完全一致；未以 fallback 掩盖缺 key。

### RED → GREEN：narration 子路由 active

- RED：`node scripts/verify-narration-analysis.mjs` 在 `.dashboard-sidebar a[aria-current='page']` 超时；根因是 navigation 目标为 `/dashboard/narration/settings`，默认 `NavLink` 无法把 `/analysis` 与 `/editor` 视为其子路由。
- GREEN：`DashboardSidebar.jsx` 仅对 narration 项使用 `/dashboard/narration/` 前缀生成 `aria-current="page"`，其他导航逻辑不变。
- 复验输出：`Narration analysis route and video interactions passed`。

### 旧验证脚本语言稳定性

- 对含中文行为断言的既有 `verify-*.mjs` 页面在导航前写入 `narrato.locale=zh-CN`；不删除、不改弱原交互、布局、active、ARIA 或错误断言。
- `verify-i18n.mjs` 仍通过真实语言切换 handler；对菜单项使用 `role=menuitem + 自身语言名` 稳定定位，在可见后调用 DOM click，避免持续动画导致 Playwright actionability 稳定性误报。键盘、焦点恢复、Escape、外部点击关闭等原行为覆盖保留。

## 2. 9 路由 × 3 语言 × 3 视口

`scripts/verify-i18n.mjs` 覆盖 81 个组合：

- 路由：`/`、`/dashboard`、`/dashboard/create`、`/dashboard/projects`、`/dashboard/projects/overlord/result`、`/dashboard/narration/settings`、`/dashboard/narration/analysis`、`/dashboard/narration/editor`、`/missing-route`。
- 语言：`zh-CN`、`en`、`ja`。
- 视口：`1487×1058`、`768×1024`、`390×844`。

每个组合均断言：document response 成功、localized title、`html[lang]`、localized route heading、0 console/page error、无页面级横向溢出。最终输出：

```text
i18n verification passed: 9 routes × 3 locales × 3 viewports
```

## 3. 代表截图证据

截图仅用于 QA，未被 `src/` 导入：

- `docs/web/homepage-prototype/artifacts/i18n/en-desktop.png`（1487×3006）
- `docs/web/homepage-prototype/artifacts/i18n/en-tablet.png`（768×4981）
- `docs/web/homepage-prototype/artifacts/i18n/en-mobile.png`（390×5508）
- `docs/web/homepage-prototype/artifacts/i18n/ja-desktop.png`（1487×3006）
- `docs/web/homepage-prototype/artifacts/i18n/ja-tablet.png`（768×4981）
- `docs/web/homepage-prototype/artifacts/i18n/ja-mobile.png`（390×5530）

六张均为 8-bit RGB PNG。

## 4. 最终命令与结果

工作目录：`docs/web/homepage-prototype/`。

| 命令 | 最终结果 |
| --- | --- |
| `npm run test:i18n` | PASS；6/6，0 fail |
| `npm run build` | PASS；4727 modules transformed；仅既有 chunk >500 kB warning |
| `npm run verify:i18n` | PASS；9×3×3 全覆盖 |
| `npm run verify:routing` | PASS；`路由骨架验收通过` |
| `npm run verify:hero` | PASS；1920/1487/1200/1024/390 + reduced motion |
| `npm run verify:demo` | PASS；三类根节点、5/4/3 流程、键盘、弹层、响应式 |
| `npm run verify:three-hero` | PASS；最终 `Three.js Hero browser verification is GREEN.` |
| `npm run verify:dashboard` | PASS；31 files 反贴图扫描 + 结构交互 |
| `npm run verify:create` | PASS；7 files 反贴图扫描 + 交互 |
| `npm run verify:projects` | PASS；anti-paste、交互、响应式 |
| `npm run verify:project-result` | PASS；anti-paste、路由、交互、响应式 |
| `node scripts/verify-narration-analysis.mjs` | PASS；结构/anti-paste、active、视频交互 |
| `node scripts/verify-narration-editor.mjs` | PASS；`PASS: narration editor data` |
| `git diff --check` | PASS；无输出 |

最终回归曾暴露两项真实问题并已修复：一是 narration active-state；二是 i18n 菜单项在持续动画页面上被 Playwright 等待 stable 超时。修复后分别重跑对应 RED 场景，再在最终代码状态重跑上述完整命令集合，全部 GREEN。

## 5. 禁贴图与参考资源移除审计

执行：

```bash
rg -n "data:image|background-image|<canvas|<image" src || true
rg -n "artifacts/|comparisons/|screenshots/" src || true
git diff -U0 -- src | rg '^\+.*(data:image|background-image|<canvas|<image|artifacts/|comparisons/|screenshots/)' || true
```

结果：

- `src/` 的 `artifacts/|comparisons/|screenshots/` 无命中。
- 新增行中无 `data:image`、`background-image`、`canvas/image` 或 QA 路径引用。
- 仅 `src/styles/home.css` 有 3 处既有纯 CSS gradient `background-image`，不是 URL/位图，且不是本任务新增。
- 临时将整个 `artifacts/` 移出项目后，用无头 Chrome 加载全部 9 路由，输出 `reference-removal route load passed: 9/9`；随后已恢复 artifacts。

## 6. 自检

1. 删除/隐藏参考图后，9 条路由主体完整：PASS。
2. 无新增截图、base64、bitmap、canvas 截图绘制或 SVG 位图：PASS。
3. 品牌与 Demo preview 为真实文本与资源 key；按钮、布局、编辑器均保持真实 DOM：PASS。
4. 必须保留的图片仍仅为项目原有 logo/缩略图/真实媒体等内容资产；本任务生成的 6 张截图仅为 `artifacts/i18n` QA 证据，不进入生产组件树。
5. 未通过项：无。
6. 残余风险：仅 Vite 大 chunk 既有非阻塞 warning；未在真实物理设备执行屏幕阅读器/触控审计，但指定三视口、键盘与 ARIA 自动化均已通过。

## 7. Final Review Not Ready 整改（I1 / I2 / M1）

依据 `.superpowers/sdd/final-review.md` 再次执行严格 RED → GREEN：

### I1：品牌不可翻译

- RED：新增 `common.brand` 三语恒等断言后，English 实际返回 `Narrato`。
- GREEN：三语 `common.brand` 统一为 `影创工坊`；English 登录、FAQ、titles、Dashboard footer/header 等仅翻译周边描述，不再改写品牌。
- `verify-i18n.mjs` 同步修正 English title 预期，并在首页浏览器断言可见 `.brand-mark__text === "影创工坊"`。

### I2：语义日期与 Intl 无效输入

- RED：有效 ISO 日期传给旧 `formatDateForLocale` 抛 `RangeError`；无效数字输出 `NaN`；无效日期抛错。
- GREEN：projects 与 project result 的 `createdAt` 全部改为带 `+08:00` 的 ISO 8601；`ProjectTable`、`ProjectResultDetails` 统一通过 `formatDate` 和固定 `Asia/Shanghai` 展示。
- `formatNumberForLocale` / `formatDateForLocale` 在输入无效时返回调用方原值。
- 单测覆盖 zh-CN / en / ja 日期格式与 number/date 无效输入；浏览器同时断言项目表与项目结果日期随 locale 显示为：
  - zh-CN：`2024年5月30日 14:30`
  - en：`May 30, 2024, 2:30 PM`
  - ja：`2024/05/30 14:30`

### M1：双重缺键一次性开发 warning

- RED：同一动态 key 在 en / ja 连续双重缺失时 warning 数为 0。
- GREEN：开发环境对当前 locale 与 zh-CN 都缺失的 key 返回 key，并以模块级 Set 去重，`console.warn` 同 key 仅一次；production 不触发该开发诊断分支。

### 整改后验证

| 命令 | 结果 |
| --- | --- |
| `npm run test:i18n` | PASS；10/10，0 fail |
| `npm run build` | PASS；4727 modules transformed；仅既有 chunk warning |
| `npm run verify:i18n` | PASS；9 routes × 3 locales × 3 viewports，含品牌和三语日期浏览器断言 |
| `npm run verify:projects` | PASS |
| `npm run verify:project-result` | PASS |
| `npm run verify:routing` | PASS |
| `npm run verify:dashboard` | PASS |
| `git diff --check` | PASS |

I1、I2、M1 均已关闭；未执行 add/commit。
