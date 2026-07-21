# Task 2 独立审查报告

## Verdict

- **规格符合性：PASS**
- **代码质量：CHANGES_REQUESTED**

实现本身符合 Task 2：所有现有创作入口均复用唯一的 `startCreation` 并导航到 `/dashboard`，非创作行为的生产代码路径保留，提交范围也严格限制在 ownership 的两个文件。但新增验收脚本对入口数量没有做基数断言，存在核心场景假阳性，因此代码质量结论为 `CHANGES_REQUESTED`。

## 规格符合性审查

### 通过项

1. `src/pages/HomePage.jsx:14,29` 使用 `useNavigate()` 并定义唯一的 `startCreation` 回调，目标为 `/dashboard`。
2. `src/pages/HomePage.jsx:81,86,88,91` 将 Hero、当前 Tab 模板卡、3 张能力卡、Final CTA 全部绑定到同一回调。
3. `src/pages/HomePage.jsx:31-41,72-77,82-85,94-96` 保留 `scrollTo`、`openCase`、Tab 状态、登录/价格/法律 Toast 的既有传递链；`chooseTool` 与不再需要的 `TOOL_DATA` import 已删除。
4. 组件 DOM 文件未被本提交修改；commit `179864e` 仅包含：
   - `docs/web/homepage-prototype/src/pages/HomePage.jsx`
   - `docs/web/homepage-prototype/scripts/verify-routing.mjs`
5. `scripts/verify-routing.mjs:46-70` 实际按 3 个 Tab 切换并逐项遍历当前可见模板按钮，也逐项遍历能力入口；每次点击后均返回首页继续枚举。
6. `scripts/verify-routing.mjs:73-94` 覆盖 Hero 查看案例、Tab 切换、案例弹层、登录 Toast、价格 Toast；`scripts/verify-routing.mjs:10-14` 检查旧工作台 Toast 文案不再存在。

## Findings（按严重度）

### [P1 / Important] 入口枚举缺少数量断言，会产生核心验收假阳性

**位置：**

- `docs/web/homepage-prototype/scripts/verify-routing.mjs:48-50,67-69`
- `docs/web/homepage-prototype/scripts/verify-routing.mjs:53-64`

脚本用 `.first()` / `.last()` 区分 Hero 与底部 CTA，却未断言“开始创作”按钮应恰有 2 个；若其中一个入口被删除，唯一剩余按钮会同时成为 first 和 last，两次检查仍可通过。

模板与能力按钮循环也直接以实时 `count()` 为上限，但没有断言每个 Tab 必须有 3 个模板、能力区必须有 3 个按钮。若某一 Tab 的模板全部消失，循环执行 0 次并静默通过；若只剩 1～2 个，也只验证残存项。这使报告所称“共 9 张模板卡、3 张能力卡”并未由自动化测试可靠证明，也削弱了“所有创作入口”回归保护。

**建议修复：** 先获取并断言稳定基数，再循环。例如断言 `startButtons.count() === 2`、每次切换 Tab 后 `templates.count() === 3`、`tryButtons.count() === 3`，并使用捕获的固定 count 作为循环上限。

### [P2 / Minor] 案例弹层测试依赖样式类选择器

**位置：** `docs/web/homepage-prototype/scripts/verify-routing.mjs:84`

`.case-card__image` 是实现/样式类，组件重命名 CSS class 即会让行为测试失败，即使可访问语义和功能完全不变。该按钮已有稳定的 accessible name（`播放案例：${item.title}`），建议改用 `getByRole("button", { name: /^播放案例：/ }).first()`，与同一脚本其他用户语义定位方式保持一致。

## 非创作行为与范围结论

- Hero“查看案例”、Tab 切换、案例弹层、登录及价格 Toast 均有脚本覆盖。
- 法律 Toast 未新增端到端断言，但 `SiteFooter` 未在 commit 中变更，`HomePage.jsx:94` 仍将 `showToast` 作为 `onFeedback` 传入，因此生产代码路径保持原样。
- commit 范围为指定两个 ownership 文件；当前工作区另有预存脏文件，但不属于 commit `179864e`。

## Cannot verify

1. 按任务要求未重复执行实施报告已给出的 `npm run build`、`verify:routing`、`git diff --check`；因此报告中的运行时 PASS、4613 modules transformed、无 browser error 等结论仅基于现有实施报告，未由本审查会话复跑确认。
2. 未审计宿主机 `127.0.0.1:4174` 当时实际服务的构建产物与 commit `179864e` 是否完全一致。

## 最终结论

生产实现可判定为规格符合；在合入下一阶段前，应补齐入口数量断言以消除验收假阳性。该问题不否定现有页面当前确有 2 + 9 + 3 个入口，但会导致未来入口缺失回归无法被测试稳定发现。

---

## 修复复审（2026-07-14）

### Verdict

- **规格符合性：PASS**
- **代码质量：APPROVED**

### 原 Findings 关闭情况

1. **[原 P1 / Important] 已解决。**
   - `scripts/verify-routing.mjs:48-52` 先断言“开始创作”入口严格为 2 个，避免单个按钮同时满足 `.first()` 与 `.last()` 的假阳性。
   - `scripts/verify-routing.mjs:58-68` 对 narration、translation、remix 每个 Tab 分别断言模板入口严格为 3 个，并将捕获的 `templateCount` 作为固定循环上限。
   - `scripts/verify-routing.mjs:71-78` 断言能力入口严格为 3 个，并将捕获的 `tryButtonCount` 作为固定循环上限。
   - 以上修改完整覆盖了原审查指出的 2 + 9 + 3 入口基数缺失问题。
2. **[原 P2 / Minor] 已解决。**
   - `scripts/verify-routing.mjs:97` 已将 `.case-card__image` 改为基于可访问名称的 `getByRole("button", { name: /^播放案例：/ })`，不再依赖样式类。

### 范围与回归复核

- 修复 commit `2eef104` 仅修改 `docs/web/homepage-prototype/scripts/verify-routing.mjs`。
- 完整审查区间 `19d5dc7..2eef104` 仍只包含 Task 2 ownership 的两个文件：`HomePage.jsx` 与 `verify-routing.mjs`。
- 两个目标文件当前无未提交修改。
- 未发现修复引入的新功能性、可维护性或测试可靠性问题。

### Cannot verify（复审）

按复审要求未重复运行实施者已报告的 `verify:routing` 与 `git diff --check`；实施报告所列运行时 PASS 与无 browser error 结果未在本复审会话中复跑确认。

### 复审结论

先前 Important 与 Minor findings 已全部解决，规格与代码质量均达到通过标准，可继续进入后续集成流程。
