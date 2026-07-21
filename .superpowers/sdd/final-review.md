# Homepage Prototype I18n 最终修复复审

**复审日期：** 2026-07-16  
**最终结论：** **Ready**

## 复审范围

- 更新后的 `.superpowers/sdd/task-7-report.md`
- `src/i18n/locale.js`、`src/i18n/locale.test.js` 与三套 locale 资源
- `BrandMark`、English 品牌相关文案和 `verify-i18n.mjs` 的品牌断言
- Projects / Project Result 的日期数据、渲染与浏览器断言
- 原最终审查 I1、I2、M1 修复附近代码的快速回归扫描

按要求未重跑完整 suite；本轮以当前代码复审、静态资源对比和已有最新验证证据为准。

## Critical findings

**None.**

## Important findings

**None.**

## Minor findings

**None.**

## 原 findings 关闭情况

### I1：品牌不可翻译 — Closed

- `src/i18n/locales/en.js:4` 现将 `影创工坊` 保持为 `影创工坊`。
- `src/components/BrandMark.jsx:14-20` 继续使用 `common.brand`，因此三语可见品牌文字与 accessible name 都保持一致。
- English 登录、FAQ、titles、Dashboard footer/header 已只翻译品牌周边描述，品牌字面值保持不变。
- `src/i18n/locale.test.js:92-94` 增加三语品牌恒等断言。
- `scripts/verify-i18n.mjs:34-45,204` 已修正 English title 预期，并验证页面中可见品牌为 `影创工坊`，不再将 `Narrato` 固化为正确结果。

### I2：日期与 Intl 无效输入 — Closed

- `src/data/projectsData.js:9-14` 和 `src/data/projectResultData.js:31` 已使用带 `+08:00` 的确定性 ISO 8601 时间值。
- `src/components/projects/ProjectTable.jsx:23-35` 与 `src/components/projects/ProjectResultDetails.jsx:40-47` 已统一使用 `formatDate`，并固定 `Asia/Shanghai`，时间码和日志时刻仍保持原值。
- `src/i18n/locale.js:46-53` 在 number/date 值无效时返回调用方原值，不再输出 `NaN` 或因无效日期抛 `RangeError`。
- `src/i18n/locale.test.js:96-111` 覆盖三语有效日期与 number/date 无效输入。
- `scripts/verify-i18n.mjs:30,45,60,246-247,315` 覆盖 Projects 和 Project Result 的三语日期实际渲染。

### M1：缺键开发 warning once — Closed

- `src/i18n/locale.js:28-43` 在当前语言和中文资源都缺键时，开发环境返回 key、输出 warning，并通过模块级 Set 按 key 去重。
- production 分支不触发开发诊断。
- `src/i18n/locale.test.js:113-126` 验证同一个 key 跨 en / ja 仅 warning 一次。

## 快速回归结论

- 修复未改变初始化优先级、storage 异常处理、中文 fallback 或插值行为。
- 品牌修复没有翻译项目名、文件名、字幕/对白、时间码或其他内容边界。
- 日期格式化只作用于语义为创建日期的字段，没有误处理媒体时长和日志时刻。
- 未引入 locale key/remount；编辑器 reducer、video、timeline 和 waveform 生命周期边界保持不变。
- 资源 leaf parity 仍由单测覆盖；当前 English 与中文相同的 Han 值仅剩品牌和明确内容字段。
- `verify-i18n.mjs` 的品牌与日期断言是加强而非削弱；最新 Task 7 报告记录针对性单测、构建、i18n 浏览器矩阵及相关旧 verifier 均通过。
- 未发现新 screenshot/base64/bitmap/canvas 引用或 QA artifacts 进入生产组件树。

## Verdict

**Ready.**

原最终审查的 I1、I2、M1 均已在当前代码与针对性验证中闭环；快速复扫未发现新的 Critical、Important 或 Minor finding。
