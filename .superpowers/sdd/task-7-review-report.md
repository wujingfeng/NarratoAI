# Task 7 独立审查报告

## Verdict

- **规格：FAIL**
- **质量：CHANGES_REQUESTED**

Task 7 的 scoped CSS 修复本身正确，也没有越权修改预存 dirty 官网文件；但新增自动化并未真正证明“隐藏后主体完整”，且最终报告将 `verify:three-hero` 的红项错误归因为“预存 dirty 官网行为”，同时把明确要求既有回归通过的规格第 13/14 节标为 PASS。不要因此修改受保护的 dirty `verify-three-hero.mjs` 或 Three.js 实现；应先把验收结论和归因改准确。

## Findings

### Important 1：隐藏图片测试存在假阳性，未真正验证“主体完整”

- **位置：** `docs/web/homepage-prototype/scripts/verify-dashboard.mjs:73-78,196-225`
- 测试在同一页面先强制 `documentary-thumb.webp` 返回 404，`DashboardThumbnail` 会卸载该 `<img>`；但隐藏阶段只断言图片数 `> 0`，并未证明正常状态的 5 个图片实例都被隐藏。
- `imageHiddenMetrics` 对 Logo/Banner 只做 `querySelector` 存在性检查，对标题、余额、月耗只读取 DOM/textContent；即使它们被 CSS 隐藏、尺寸为 0 或移到视口外，该断言仍会通过。
- brief 要求的按钮、导航、项目标题、统计结构和 Footer 也没有在隐藏状态中被断言。
- `dashboard-images-hidden-1487.png` 的人工查看确实显示当前实现的主体完整，但这不能支撑报告中“`verify-dashboard` 已自动证明主体完整”的表述。

**建议：** 在不注入 404 的独立页面/阶段精确断言 5 个 `<img>`，隐藏后对 brief 列出的主体元素检查可见性和非零几何尺寸，再恢复图片；404 fallback 测试保持独立。

### Important 2：`verify:three-hero` 失败归因不准确，第 13/14 节 PASS 结论不诚实

- **位置：** `.superpowers/sdd/task-7-report.md:5-7,53-57,123-127,145-152`
- patch `cmp` 相同只能证明 Task 7 未写入受保护文件，不能证明失败行为在 Dashboard 任务前已经存在。
- `.superpowers/sdd/task-1-report.md:43-45` 记录 Task 1 时 `verify:three-hero` 仍 PASS。后续 in-scope commit `179864e` 将 Hero 主 CTA 从 Toast 改为路由到 `/dashboard`；而当前 dirty `verify-three-hero.mjs:384-390` 仍在点击后等待 `.toast[role='status']`。
- 独立最小 Playwright 探针点击 `/?threeFallback=1` 的 Hero CTA 后得到 `url=/dashboard`、`toast=0`、Dashboard 标题存在。因此这是“新规格要求的 CTA 路由行为与预存 dirty 验证器的旧 Toast 合约不兼容”，不是报告所称的“预存 dirty 官网行为”。
- 规格 `§§13.2,14` 明确要求官网既有回归与工程验证通过；当 `verify:three-hero` 仍红时，报告可以说 Dashboard/路由业务行为符合新规格，但不能将最终回归、第 13/14 节和整体 1–18 标为 PASS。

**建议：** 不要要求修改不属于 Dashboard 且已受保护的 dirty 文件；仅更正根因和最终验收状态，将该项明确记为旧验证器合约与新路由语义不兼容，并把第 13/14 节及总体规格标为 PARTIAL/FAIL，直到所有者在对应 scope 中更新旧验证合约。

## 已确认正确

- `src/styles/dashboard.css:373` 的 `.dashboard-shell img[hidden] { display: none; }` 是对全局 `img { display: block; }` 级联问题的最小 scoped 修复，不影响官网图片。
- commit `34c984d` 仅包含 `scripts/verify-dashboard.mjs` 和 `src/styles/dashboard.css`，符合 Task 7 允许的收口范围，未越权。
- `/tmp/narrato-dashboard-preexisting.patch` 与 postexisting patch 大小均为 46695 bytes、SHA-256 均为 `3aa1dbc3357d1cb62b627b854d3819e504b33a845e5013cfc7c599625b0bc59c`；当前受保护文件仍是 unstaged dirty，证明 Task 7 没有覆盖或带入提交。
- 仓库级扫描的命中仅来自验证脚本中的禁用 token 规则字符串；Dashboard authored-scope 扫描独立 PASS，`find` 没有 Dashboard 参考图复制品。
- 3 个现有 WebP 内容资产、5 个使用位置、alt 和结构化失败占位的列表与源码一致；Logo/Banner/图标/统计不是图片例外。
- 独立在沙箱外重跑 `npm run verify:dashboard` 得到 authored-scope 扫描和“工作台结构与交互验收通过”。

## Cannot verify

- 完整 `npm run verify:three-hero` 在本次独立重跑中进入 fallback 后未能稳定输出最终汇总，因此无法独立确认报告所述“除 CTA 外所有断言均 PASS”。上述最小探针已独立确认 CTA 语义不兼容的根因。
- 本次未重跑 `build` / `verify:routing` / `verify:hero` / `verify:demo` / `screenshot:dashboard`，对这些项仅核对 Task 7 报告与产物。
- 真实 iPhone safe-area、屏幕阅读器、200% zoom 和对比度数值审计未在本次审查环境中执行；Task 7 报告已将其列为残余风险。

---

## 修复后复审（2026-07-14）

### Verdict

- **规格：PASS**
- **质量：APPROVED**

### Findings

无阻塞性或可操作 finding。首轮审查的两项 Important 均已闭环。

### 复审核对

1. **5 图隐藏验收已去除假阳性：** `verify-dashboard.mjs:109-220` 使用未注入 404 的独立 `imagePage`，在 `networkidle` 后精确断言 5 个 Dashboard `<img>`；隐藏后逐张断言 `hidden=true` 且 computed `display=none`，恢复后再断言 5 张全部重新显示。
2. **主体完整性为真实可见性检查：** 新测试同时校验 `display` / `visibility` / `opacity`、非零 rect 和视口交集，覆盖 Logo、Banner、导航、账户/会员/创建/工具/Banner/项目操作、三项目标题与状态、66% progress、余额、月耗、统计 ring 和 Footer，并校验隐藏后无横向溢出。
3. **404 fallback 已独立：** `documentary-thumb.webp` 的 page-specific 404 route 仅作用于原主验收 `page`，不会污染新建的 `imagePage`；结构化 fallback 仍由后续独立断言覆盖。
4. **Three CTA 合约修正精确：** commit `681a901` 只包含 `verify-three-hero.mjs` 的一个 4 insertions / 3 deletions hunk，将“等待旧 Toast”改为“等待 `/dashboard` URL 与工作台标题挂载”；未提交 Three.js 运行时或其他预存 dirty 测试内容。
5. **dirty patch 保护仍成立：** 当前 `verify-three-hero.mjs` 剩余 dirty diff 仍为 166 insertions / 4 deletions，6 个受保护文件仍全部 unstaged，暂存区为空。更新报告已准确说明 CTA hunk 是 review 授权后的合约修正，不再将其误报为“预存 dirty 官网行为”。
6. **完整回归结论成立：** 独立复跑 `build`、`verify:routing`、`verify:dashboard`、`verify:hero`、`verify:demo`、`verify:three-hero` 全部 exit 0，其中 Three 最终输出 `Three.js Hero browser verification is GREEN.`。首次串行到 `screenshot:dashboard` 时原 4173 preview 中途停止，产生 `ERR_NETWORK_IO_SUSPENDED`；在独立启动的 4174 preview 上立即复跑 exit 0 并生成五张截图，确认这是服务进程中断而非项目回归。
7. **最终报告结论已准确：** 报告现在如实列出三个收口 commit、CTA 旧合约的真实根因、全绿回归、图片例外、反贴图扫描及残余设备级风险。在现有自动化与人工证据下，规格第 1–18 节 PASS 表述合理。

### Cannot verify

- 真实 iPhone safe-area、屏幕阅读器、200% zoom 和对比度数值审计仍未在本次复审环境中执行；它们已被报告正确列为残余风险，不阻塞本规格验收。
