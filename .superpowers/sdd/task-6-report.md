# Task 6 Report — Narration Editor Copy-Only Localization

## 完成内容

- 为解说编辑器补齐 `editor.*` 的简体中文、英文、日文资源。
- 编辑器 topbar 在创作点前挂载稳定的 `<LanguageSwitcher compact />`。
- 本地化 topbar、片段栏、检查器、字幕/BGM 面板、播放器、时间轴、波形标签、Toast、隐藏标题与控件 accessible name。
- 项目名、脚本文本、SRT cue 文本、BGM 文件名、媒体 URL、时间、比例、百分比和评分继续作为内容或技术值展示，不随 locale 翻译。
- locale 只通过 i18n context 触发普通 rerender；未给 video、timeline 或 waveform 添加 locale key，也未把 locale 写入 reducer state。
- 时间轴缩放控件改用稳定 ref 同步 min/value，避免 aria-label 翻译后依赖中文 DOM 查询。
- 响应式改动仅限 topbar 和标签换行/收缩；未更改 workspace、timeline、固定轨道标签列、缩放和 waveform 几何。

## TDD 证据

### RED

命令：

```bash
cd docs/web/homepage-prototype && npm run verify:i18n
```

预期失败：`AssertionError: zh-CN must define Task 6 editor resources`。

### GREEN

`verify-i18n.mjs` 新增真实浏览器断言，覆盖：

- 编辑脚本文本后从 `zh-CN` 切换到 `ja`。
- 路由不变。
- 同一个 `<video>` DOM 节点不变。
- media currentTime 误差不超过 0.25 秒。
- 选中 clip IDs、zoom value、textarea 编辑值不变。
- 日文隐藏标题、保存草稿按钮和 accessible names 生效。
- 项目名与字幕 cue 保持原始内容。
- 1024px 下 compact switcher 位于 viewport 内，且无页面级横向滚动。

## 验证结果

```text
npm run build
✓ built in 5.00s

npm run verify:i18n
i18n public header verification passed

node scripts/verify-narration-editor.mjs
PASS: narration editor data
```

Vite 仅输出既有的 chunk size 提示，无构建失败。

## 约束审计

- 未修改 `editor-reducer.js`。
- 未修改 `timeline-geometry.js`。
- 未修改 `editor-data.js`。
- 未执行 `git add` 或 `git commit`。
- 未使用截图、base64、canvas 或 bitmap fill；本任务没有新增图片资产。

## 残余风险

- 项目当前相关文件整体处于未跟踪/并行开发状态，Git 无可用 HEAD 基线来逐文件展示本任务前后的 diff；本任务只写入 brief 允许的实现/测试文件与本报告。

## Independent Review 修复

- 将 `voiceRole`、`subtitleStyle`、`bgmStyle` 从 preserved-content 白名单移除，改为 `editor.presets.*` UI 预设资源；英文与日文现在展示本地化预设名。
- reducer 中的 `voiceRole` 标识保持原值，仅在渲染已知预设时映射显示文本；未把 locale 写入 reducer。
- 三个设置编辑按钮分别增加配音角色、字幕样式、背景音乐上下文的三语 `aria-label`。
- `verify-i18n.mjs` 新增日文 inspector 预设、三个上下文编辑操作、字幕 cue、BGM 文件面板、播放器按钮、播放速度、时间轴轨道标签及 trim handles 的精确 runtime 断言。
- Review RED：移除错误白名单后，测试按预期失败于 `en Task 6 resource editor.content.voiceRole must not silently remain Chinese`。
- Review GREEN：`npm run build`、`npm run verify:i18n`、`node scripts/verify-narration-editor.mjs` 均重新执行并通过；未提交。
