# Task 6 独立审查报告

## Verdict

- **规格：FAIL**
- **质量：CHANGES_REQUESTED**

Task 6 的扫描范围、六类反贴图规则、路由历史链路、五视口截图、最小 Hero 修复和提交边界总体实现正确；但 favicon 被测试路由统一伪造为 204，直接违反“不得忽略资源 404”，并掩盖了当前真实缺失的 favicon。另有一处聚焦断言可能对错误标题产生假阳性。

## Findings

### [P1 / Major] favicon 夹具掩盖真实资源 404，违反明确验收条件

- `docs/web/homepage-prototype/scripts/verify-routing.mjs:20`
- `docs/web/homepage-prototype/scripts/capture-dashboard.mjs:15`
- `docs/web/homepage-prototype/scripts/verify-dashboard.mjs:76`

三个浏览器脚本都用 `page.route("**/favicon.ico", ...204...)` 在网络层伪造成功响应。因此后续 `response.status() >= 400` 与 console error 监听永远看不到真实 favicon 请求结果。仓库当前既没有 `public/favicon*`，`index.html` 也没有 favicon 声明；Task 6 报告还明确记录截图脚本首轮曾捕获 favicon 404，说明这是当前真实资源问题，而不是理论风险。

这与 brief Step 2 的“不得忽略资源 404”和 Step 3 的“任何 console/page/request error 令脚本退出 1”直接冲突。应提供真实 favicon 资产/声明并删除 204 拦截，或至少增加一条不经过拦截的真实资源检查；不能用测试夹具把失败改写为成功。`documentary-thumb.webp` 的精确 404 注入属于有目的的 fallback 验收，且 capture 会走真实资源，不属于同一问题。

### [P2 / Moderate] 聚焦断言没有验证“匹配预期文本的标题”就是活动元素

- `docs/web/homepage-prototype/scripts/verify-routing.mjs:49-51`

第 50 行只确认某个 `[data-route-heading]` 包含预期文本，第 51 行却独立验证 `document.activeElement === document.querySelector("[data-route-heading]")`。如果页面意外出现两个 route heading，错误的第一个 heading 被 `RouteEffects` 聚焦，而第二个 heading 含预期文本，测试仍会通过；这正是“聚焦标题正确”的假阳性。

建议断言 route heading 唯一，并直接比较活动元素与包含预期文本的那个元素；文本也宜使用精确比较而非 `hasText` 子串匹配。

## 通过项

1. **扫描范围精确**：`verify-dashboard.mjs:11-17` 仅扫描 brief 指定的五个 authored/public target；未扫描 `artifacts/`、`dist/`、`node_modules/` 或 `docs/web/prototypes/b-style/` 参考图目录。
2. **六类机制齐全**：`verify-dashboard.mjs:18-25` 与 brief 给出的六条正则一致。独立运行正常源码得到 `20 files` PASS；在临时 scan root 分别注入参考图文件名、`data:image`、`base64`、canvas、CSS URL 背景、SVG `<image>`，六类均非 0。单项输出包含 `src/pages/DashboardPage.jsx`、规则名和命中 token。
3. **路由链路完整**：`verify-routing.mjs:62-111` 覆盖直达 `/dashboard`、reload、Logo → `/`、back → `/dashboard`、forward → `/`、404、404 两个链接；title 和 route heading focus 都有等待。除上述“匹配元素”假阳性外，链路本身有效。
4. **错误监听齐全**：routing 与 capture 均监听 console error、pageerror、requestfailed、HTTP >=400；favicon 例外是阻塞问题。
5. **截图实现符合接口**：`capture-dashboard.mjs:13-39` 使用单一 `capture()` helper，等待 Dashboard 根节点与字体；`42-46` 生成规定的五个 viewport/fullPage 组合，输出目录为 `artifacts/screenshots/`。
6. **截图证据存在且尺寸正确**：1487×1058、390×844、390×1384 full、768×1396 full、1920×1080 五图均存在。逐张查看后，页面主体均为结构化 UI；390/768 fullPage 图存在已记录的 fixed 底栏合成覆盖现象，但运行态遮挡另有 verifier 检查。
7. **Hero 修复最小且合理**：`HeroSection.jsx:172` 只给既有唯一 `h1` 增加 `data-route-heading` 与 `tabIndex="-1"`，使 RouteEffects 可聚焦，未改变 DOM 结构或样式。
8. **无贴图交付**：截图仅在 `artifacts/screenshots/`，被 `.gitignore:4` 忽略；commit `1892747` 未包含任何截图或参考图。页面允许保留的项目/灵感缩略图是内容资产，不是参考图贴图。
9. **ownership 正确**：commit 仅包含 3 个 Task 6 脚本和获授权的最小 `HeroSection.jsx` 修复。当前其他 Hero/Three/Demo 样式与脚本 dirty changes 均未被纳入该 commit；暂存区为空。
10. **diff 卫生**：`git diff --check 6a2a546..1892747` 与当前 `git diff --check` 均通过。

## Cannot verify

- 本轮在受限环境尝试 `npm run preview -- --host 127.0.0.1 --port 4173`，因 `listen EPERM` 无法启动服务器，所以未独立重跑 `verify:routing`、完整 `verify:dashboard` 与 `screenshot:dashboard`。运行通过结论仅能依据 Task 6 报告；静态扫描、六类临时注入、Git 边界与五张既有截图已独立核验。
- 未独立复现报告中的生产 build 4627 modules 与 chunk warning；这不影响上述确定性代码问题。

## 收口要求

1. 移除 favicon 204 伪造并提供真实 favicon，确保三套浏览器检查在不吞资源错误的情况下通过。
2. 将 focus 断言绑定到匹配预期文本的唯一 route heading。
3. 在 production preview 上重跑 build、routing、dashboard 与五图 capture，并更新报告证据。

---

## 修复复审（commit `742a59b`）

### Verdict

- **规格：PASS**
- **质量：APPROVED**

原审查的 P1、P2 均已解决，未发现新增阻塞问题。

### 修复确认

1. **真实 favicon 已提供**
   - `docs/web/homepage-prototype/index.html:8` 声明 `<link rel="icon" type="image/svg+xml" href="/favicon.svg" />`。
   - `docs/web/homepage-prototype/public/favicon.svg:1-15` 是有效 SVG；独立 `xmllint --noout` 通过。
   - production build 会把它原样复制为 `dist/favicon.svg`，构建后的 `dist/index.html` 仍正确引用 `/favicon.svg`。

2. **favicon 错误不再被拦截或豁免**
   - `capture-dashboard.mjs:13-25` 直接安装完整 browser issue listeners，没有 `page.route()` 资源拦截。
   - `verify-routing.mjs:16-32` 同样没有 favicon 拦截，所有 HTTP >=400 仍进入 failures。
   - `verify-dashboard.mjs:76-96` 仅保留为缩略图 fallback 验收而精确注入的 `documentary-thumb.webp` 404；全仓浏览器脚本中已无 favicon route/忽略逻辑。

3. **favicon 是纯矢量内容资产**
   - `favicon.svg:12-14` 只使用三个真实 `<path>` 与 SVG gradient。
   - 独立扫描确认无 `<image>`、`data:image`、base64、`xlink:href` 或外链位图；Dashboard authored/public 扫描因新增 favicon 从 20 files 增至 21 files 并 PASS。

4. **focus 断言已精确绑定预期元素**
   - `verify-routing.mjs:47-50` 先等待 route heading 并要求全页恰好一个。
   - `verify-routing.mjs:51-55` 对该同一 locator 的 `textContent` 做精确相等检查。
   - `verify-routing.mjs:56-57` 获取该 locator 的 `ElementHandle`，再直接断言 `document.activeElement === element`；原先“预期文本元素与被聚焦元素可能不是同一个”的假阳性已消除。

5. **验证与提交边界**
   - 独立运行 `DASHBOARD_SCAN_ONLY=1 node scripts/verify-dashboard.mjs` → `21 files` PASS。
   - 独立运行 `npm run build` → 4627 modules、build PASS；仅保留既有 >500 kB chunk warning。
   - `git diff --check 1892747..742a59b` PASS。
   - 修复提交只包含 `index.html`、纯矢量 favicon 和三个测试脚本的针对性改动；现有其他 dirty files 未纳入提交。

### Cannot verify（复审）

- 本复审环境仍不允许监听本地 preview 端口，因此没有再次独立运行三条 Playwright 浏览器命令；更新后的 Task 6 报告记录 production preview 上 `verify:routing`、完整 `verify:dashboard`、`screenshot:dashboard` 均 PASS。静态实现、真实 build、资源复制、SVG 合规和扫描器均已独立验证。
