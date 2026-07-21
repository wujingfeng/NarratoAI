# Task 3 实施报告：首页与路由元数据翻译

## 状态

已完成。未执行 `git add`、`git commit`。

## TDD：RED / GREEN

### RED

- 先扩展 `scripts/verify-i18n.mjs`：为 `zh-CN`、`en`、`ja` 增加首页标题、Hero 主标题、404 标题、404 Heading 断言。
- 增加首页切换语言前后的 `scrollY` 与 active element 断言，覆盖“切换语言不得触发路由滚动/聚焦副作用”。
- 首次执行 `npm run verify:i18n` 得到预期失败：
  - actual: `影创工坊｜AI 出片工作台`
  - expected: `Narrato | AI Video Workspace`
- 该失败证明测试确实捕获到英文首页仍显示中文标题的缺失行为。

### GREEN

最终执行：

```bash
cd docs/web/homepage-prototype
npm run test:i18n && npm run build && npm run verify:i18n
```

结果：

- `test:i18n`：4/4 通过，0 失败。
- `build`：退出码 0，Vite 构建成功。
- `verify:i18n`：退出码 0，三语言首页/404/标题/滚动/焦点断言通过。

另执行资源结构核对：三个 locale 均为 285 个叶子 key，路径顺序完全一致；英文资源未残留中日韩文字。

## 修改文件

- `docs/web/homepage-prototype/scripts/verify-i18n.mjs`
- `docs/web/homepage-prototype/src/components/CapabilitySection.jsx`
- `docs/web/homepage-prototype/src/components/DemoSection.jsx`
- `docs/web/homepage-prototype/src/components/FaqSection.jsx`
- `docs/web/homepage-prototype/src/components/FinalCtaSection.jsx`
- `docs/web/homepage-prototype/src/components/HeroSection.jsx`
- `docs/web/homepage-prototype/src/components/RouteEffects.jsx`
- `docs/web/homepage-prototype/src/components/SiteFooter.jsx`
- `docs/web/homepage-prototype/src/components/Toast.jsx`
- `docs/web/homepage-prototype/src/components/VideoModal.jsx`
- `docs/web/homepage-prototype/src/pages/HomePage.jsx`
- `docs/web/homepage-prototype/src/pages/NotFoundPage.jsx`
- `docs/web/homepage-prototype/src/i18n/locales/zh-CN.js`
- `docs/web/homepage-prototype/src/i18n/locales/en.js`
- `docs/web/homepage-prototype/src/i18n/locales/ja.js`

`BrandMark.jsx` 已检查但保持不变，以满足品牌名“影创工坊”必须保留原文的要求。

## 主要实现

- 首页 Hero、能力区、Demo 工作台、案例卡片、FAQ、最终 CTA、页脚、Toast、视频弹窗、404 页面全部改为通过 `t(...)` 取文案。
- Demo 中的中文源台词、英文目标台词、叙事示例文本与画面内案例内容保持原文；标签、说明、字幕控件、按钮、图片替代文本和无障碍名称均已翻译。
- `RouteEffects` 改为 pathname 到翻译 key 的映射：
  - 标题 effect 依赖 `[pathname, t]`；
  - 滚动重置与路由 Heading 聚焦 effect 只依赖 `[pathname]`。
- 语言切换只更新 `document.title`，不会触发滚动重置或路由 Heading 抢焦点。
- `home.*`、`errors.notFound.*`、`titles.*` 已在三种语言中完整提供且 key 路径一致。

## 自审

- [x] 品牌名保持原文。
- [x] Demo 源/目标内容示例保持原文。
- [x] 页面可见文案、图片 alt、隐藏标签和弹窗控制名称均进入资源层。
- [x] 三语言 key 路径一致。
- [x] RouteEffects 标题与路由副作用分离。
- [x] 切换语言不改变 pathname、不重置 scrollY、不触发路由 Heading 聚焦。
- [x] `git diff --check` 无空白错误。
- [x] 未执行暂存或提交。

## Concerns

- Vite 构建仍输出既有的大 chunk 警告（主 JS 约 1.25 MB）；不影响本任务构建与 i18n 验证，且不在 Task 3 范围内。
- 工作区存在其他任务的未提交改动；本任务未清理、覆盖或提交这些改动。

## Review Fix：Section Kicker 资源化

### 修复内容

- 将 `CapabilitySection.jsx` 中的 `ALL-IN-ONE WORKSPACE` 改为 `t("home.capabilities.kicker")`。
- 将 `DemoSection.jsx` 中的 `CASE DEMO` 改为 `t("home.demo.kicker")`。
- 在 `zh-CN` 资源中补充上述两个 key；`en`、`ja` 由同一资源树递归本地化，因此三语言均显式产出相同 key 和当前相同英文值。
- 在 `verify-i18n.mjs` 中加入三语言资源审计，逐语言断言两个 kicker key 存在且值正确。

### Review Fix TDD

RED：先加入资源断言并执行 `npm run verify:i18n`，得到预期失败：

```text
AssertionError: zh-CN capability kicker must come from resources
actual: undefined
expected: ALL-IN-ONE WORKSPACE
```

GREEN：完成资源和组件迁移后执行：

```bash
cd docs/web/homepage-prototype
npm run test:i18n && npm run build && npm run verify:i18n
```

结果：

- `test:i18n`：4/4 通过，0 失败。
- `build`：退出码 0，Vite 构建成功。
- `verify:i18n`：退出码 0，资源审计及既有浏览器断言全部通过。
- 额外资源结构检查：`zh-CN`、`en`、`ja` 均为 287 个叶子 key，路径完全一致；两个 kicker 在三语言中均可读取。
- 静态检查确认两个组件不再残留对应 JSX 硬编码；`git diff --check` 通过。

Review fix 未执行 `git add` 或 `git commit`。
