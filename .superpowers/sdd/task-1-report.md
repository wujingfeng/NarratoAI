# Task 1 Report: Locale Resolution and Translation Runtime

## Status

**DONE_WITH_CONCERNS**

实现与验证均完成。唯一非阻塞 concern 是 Vite 构建继续报告主 JavaScript chunk 超过 500 kB；构建本身退出码为 0，且成功生成 `dist/index.html`。

## 修改文件

- `docs/web/homepage-prototype/src/i18n/locale.js`（新建）
- `docs/web/homepage-prototype/src/i18n/locale.test.js`（新建）
- `docs/web/homepage-prototype/src/i18n/I18nProvider.jsx`（新建）
- `docs/web/homepage-prototype/src/i18n/useI18n.js`（新建）
- `docs/web/homepage-prototype/src/i18n/locales/zh-CN.js`（新建）
- `docs/web/homepage-prototype/src/i18n/locales/en.js`（新建）
- `docs/web/homepage-prototype/src/i18n/locales/ja.js`（新建）
- `docs/web/homepage-prototype/src/main.jsx`（仅加入 Provider import 与包裹）
- `docs/web/homepage-prototype/package.json`（仅加入 `test:i18n` script）

按任务要求另行创建本报告：`.superpowers/sdd/task-1-report.md`。

未修改 `package-lock.json`，未触碰 brief 之外的现有脏文件，未暂存、未提交。

## RED

命令：

```bash
cd docs/web/homepage-prototype && node --test src/i18n/locale.test.js
```

结果：退出码 1，出现预期失败：

```text
Error [ERR_MODULE_NOT_FOUND]: Cannot find module '.../src/i18n/locale.js'
```

失败原因与 brief 一致：纯函数测试已存在，但实现文件尚未创建。

## GREEN

首次纯函数 GREEN 命令：

```bash
cd docs/web/homepage-prototype && node --test src/i18n/locale.test.js
```

结果：退出码 0，4 tests pass，0 fail。

最终运行时验证命令：

```bash
cd docs/web/homepage-prototype && npm run test:i18n && npm run build
```

测试结果：退出码 0，4 tests pass，0 fail。

## 构建结果

- Vite 6.4.2 构建成功，退出码 0。
- 4725 modules transformed。
- 成功生成 `dist/index.html`。
- 构建耗时约 4.72s。
- 构建有既存体量类 warning：主 JS chunk 压缩后约 1,201.62 kB，超过 Vite 500 kB 提示阈值。

## 自审

- `locale.js` 已导出 brief 要求的全部 8 个接口：`SUPPORTED_LOCALES`、`DEFAULT_LOCALE`、`STORAGE_KEY`、`normalizeLocale`、`resolveInitialLocale`、`translate`、`formatNumberForLocale`、`formatDateForLocale`；额外执行导出断言，退出码 0。
- locale 解析顺序符合要求：有效存储值优先，其次按序浏览器语言，最后回退 `zh-CN`。
- 翻译查找支持点路径、`zh-CN` 回退、缺失 key 回显和未提供占位符保留。
- 三份资源具有一致骨架：`common.language`、`common.localeName`、`titles`。
- Provider 初始化捕获 localStorage 读取异常；locale 更新同步 `<html lang>` 并捕获 localStorage 写入异常。
- Provider value 使用 `useMemo`，暴露 `locale`、`setLocale`、`supportedLocales`、`t`、`formatNumber`、`formatDate`。
- `useI18n()` 在 Provider 外调用会抛出清晰错误。
- `I18nProvider` 位于 `BrowserRouter` 外层并包裹应用。
- `git diff --check` 对限定文件通过。
- `git diff --cached --name-only` 为空，确认没有暂存内容；未执行 commit。

## Concerns

1. Vite 报告大 chunk warning；这不属于当前 i18n runtime brief，未扩大范围处理。
2. `package.json` 与 `src/main.jsx` 在任务开始前已处于用户未提交修改状态；本任务只做了上述最小增量，未覆盖或清理既有改动。
