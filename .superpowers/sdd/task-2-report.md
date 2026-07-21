# Task 2 实现报告：Shared Accessible Language Switcher

## 状态

已完成 brief 中 Task 2 的实现与验证；未执行 `git add`、`git commit`，也未改动 brief 指定实现文件之外的项目文件（本报告为调度要求的交付文件）。

## TDD 证据

### RED

命令：

```bash
cd docs/web/homepage-prototype && npm run build && npm run verify:i18n
```

结果：退出码 `1`。Vite build 成功，Playwright 在以下断言处按预期超时：

```text
locator.waitFor: Timeout 5000ms exceeded.
- waiting for getByTestId('language-switcher-trigger') to be visible
```

说明：首次在受限沙箱内运行时，动态端口探测因 `listen EPERM` 被环境阻止；随后按权限流程在本机回环地址重跑，得到上述有效 RED，失败原因明确为功能入口不存在。

### GREEN

命令：

```bash
cd docs/web/homepage-prototype && npm run build && npm run test:i18n && npm run verify:i18n
```

结果：退出码 `0`。

- Vite build 成功，4727 modules transformed。
- locale Node tests：4/4 通过。
- Playwright：`i18n public header verification passed`。

清理复核命令：

```bash
cd docs/web/homepage-prototype && npm run verify:i18n && npm run verify:i18n
```

结果：退出码 `0`，连续两轮均通过。脚本每轮动态申请空闲端口、自行启动 Vite preview，并在 `finally` 中关闭 Chromium 与 preview 进程组；连续运行未出现端口占用。

辅助检查：

```bash
git diff --check -- <Task 2 files>
```

结果：通过，无空白错误。

## 修改文件

1. `docs/web/homepage-prototype/src/components/i18n/LanguageSwitcher.jsx`（新增）
   - 三语言常量与公开组件接口。
   - 桌面 popover 和移动端 inline 两种模式。
   - outside pointer、Escape/focus restore、ArrowUp/ArrowDown 循环、Home/End、native button 选择。
   - `menu`/`menuitem`、`aria-current`、`aria-haspopup`、`aria-expanded`、测试标识。
2. `docs/web/homepage-prototype/src/components/SiteHeader.jsx`
   - 桌面登录按钮前挂载默认 switcher。
   - 移动菜单登录入口前挂载 inline switcher。
   - 导航、价格/登录反馈、菜单标签、accessible names 与登录文案接入 `home.header.*` / `common.*`。
3. `docs/web/homepage-prototype/src/styles/home.css`
   - switcher scoped styles、44px 最小触控目标、focus ring、选中 Check 对齐、popover 层级。
   - 390px 移动菜单三列 inline grid。
   - 767px 以下隐藏桌面 switcher，保留移动面板 inline 入口。
4. `docs/web/homepage-prototype/src/i18n/locales/zh-CN.js`
5. `docs/web/homepage-prototype/src/i18n/locales/en.js`
6. `docs/web/homepage-prototype/src/i18n/locales/ja.js`
   - 补齐 SiteHeader 三语言 keys。
7. `docs/web/homepage-prototype/scripts/verify-i18n.mjs`（新增）
   - 自启动/自清理 Vite preview。
   - 验证英文浏览器初始语言、日语切换与持久化、路径不变。
   - 验证键盘移动、Escape 与焦点恢复、外部点击关闭、390px 三语言入口。
8. `docs/web/homepage-prototype/package.json`
   - 新增 `verify:i18n` script。

## 自审

- API 与 brief 一致：`<LanguageSwitcher compact={false} inline={false} className="" />`。
- 未使用截图、bitmap、base64、canvas 或 `background-image` 伪造 UI。
- 关键动作未增加 `text-overflow: ellipsis`。
- 桌面/移动入口顺序符合 brief。
- 所有语言选择均为原生 `button`，键盘焦点与关闭行为由浏览器脚本覆盖。
- preview 使用独立进程组；正常通过、断言失败与异常路径均进入 `finally` 清理。
- 未暂存或提交任何文件，保留工作区既有用户改动。

## Concerns

1. Build 仍输出既有的大 chunk 警告（主 bundle 约 1.21 MB，minified）；不影响本任务通过，且不在 Task 2 文件范围内处理。
2. 工作区在本任务开始前已有大量未提交/未跟踪改动；本实现只触碰 brief 列出的 8 类文件，未清理或覆盖其他改动。
