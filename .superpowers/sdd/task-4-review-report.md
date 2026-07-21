# Task 4 独立审查报告

## Verdict

- **规格符合性：FAIL**
- **代码质量：CHANGES_REQUESTED**

主要阻塞项是侧栏“升级会员”入口被做成了不可交互的 CSS `::after` 文本卡片；它不是 DOM 中的 link/button，键盘、读屏和自动化测试均无法访问，也与参考稿中的明确入口语义不符。除此之外，右上账户区的信息架构没有按参考稿重建，CSS 还依赖多处位置/属性选择器与伪元素业务文案。

## 审查范围与方法

- 阅读：`task-4-brief.md`、`task-4-report.md`、`task-4-review.diff`。
- 原尺寸人工比对：
  - 参考：`docs/web/prototypes/b-style/04-dashboard-desktop.png`（1487×1058）
  - 实现：`docs/web/homepage-prototype/artifacts/task-4/dashboard-1487x1058.png`（1487×1058）
- 静态检查 Task 4 commit `2af3d72` 的文件 ownership、CSS/DOM 语义与验证脚本覆盖。
- 按要求**没有复跑已有测试**。

## Findings

### Critical

1. **侧栏会员入口由不可交互的伪元素伪造，规格与可访问性均不成立。**
   - 位置：`docs/web/homepage-prototype/src/styles/dashboard.css:131-146`
   - `content: "♔  升级会员...›"` 将标题、说明和箭头全部放在 `.dashboard-sidebar::after`，同时设置 `pointer-events: none`。`DashboardSidebar.jsx:17-30` 中没有对应的 link/button。
   - 参考图中该卡片具有明显箭头和入口层级；当前实现既不能点击，也不能获得焦点/可访问名称，读屏与键盘用户完全无法使用。
   - 截图还显示卡片越过 250px 侧栏右边界约 16px：伪元素的 `width: 208px` 加左右 `17px` padding 和边框采用 content-box（全局 `*` 不覆盖伪元素），实际外宽约 244px，从 `left: 22px` 延伸至约 266px；参考稿卡片约在 x=22–230 内。
   - 必须改为真实 DOM 交互元素，并对点击、键盘焦点、可访问名称及未实现态行为增加验证；装饰性皇冠/背景可以继续用 CSS。

### Important

1. **右上“账户区”信息架构未按参考稿还原。**
   - 位置：`docs/web/homepage-prototype/src/styles/dashboard.css:153-185`；对应结构 `DashboardHeader.jsx:5-18`
   - 参考稿右上为“创作点 1,280 / 去充值 / 头像”；当前截图是“通知 / 新建创作”。同时 CSS 直接隐藏已有欢迎区（`dashboard-header > div:first-child`），并未形成 brief 所述的“顶部账户区”。
   - 这不是轻微文案差异，而是主要账户操作层级被另一组操作替换。应使用真实余额、充值按钮和账户/头像入口重建；通知或新建创作可作为次级动作，但不能替代账户区。

2. **业务/说明文本被放入 CSS 伪元素，不是可维护的真实文本节点。**
   - 位置：`dashboard.css:81-101`（“工具/账户”分组标题）、`:312`（“上传素材，跟随引导完成专业出片”）、`:370-371`（“消耗”）。
   - 这些不是纯装饰，承担分组、操作说明和字段标签语义。CSS generated content 对读屏暴露不稳定，也无法被正常检索、国际化或由数据层维护；尤其 `creation-entry-card::after` 是主体说明文案。
   - 应把业务文字放回组件的真实 DOM；伪元素仅保留分隔线、光效、圆点等装饰。

3. **CSS hooks 依赖 DOM 顺序/ARIA 属性，后续结构微调容易静默错样式。**
   - 位置：`dashboard.css:161`（`> div:first-child`）、`:178-184`（`button:first-child`）、`:229-255`（用是否有 `aria-label` 区分两个 Banner 按钮）、`:394-398`（`nth-of-type` 与直接子元素定位）、`:406`（`span:nth-child(2)`）。
   - `aria-label` 应服务无障碍，不应兼任视觉 variant hook；为按钮补/删可访问名称会改变样式。新增同类型兄弟节点也会导致 `first-child`/`nth-of-type` 失效。
   - 应在 Task 3 组件上最小补充语义 class，例如 header notice/primary action、banner CTA/close、credits balance/usage/action、inspiration content，并以这些 class 选样式。

4. **桌面指标测试覆盖了“能排下”，但没有覆盖导致本次 FAIL 的信息架构与关键视觉比例。**
   - 位置：`docs/web/homepage-prototype/scripts/verify-dashboard.mjs:49-100,102-151`
   - 已覆盖 1487/1280/1025/1024 的页面宽度、侧栏避让、工具卡最小宽度、移动导航隐藏，以及既有 Toast/404/Banner 交互，基础价值明确。
   - 但没有断言：真实“升级会员”交互元素存在；顶部余额/充值/账户入口存在；Banner 高度约 154px；首排四卡与下排三模块的列关系；会员卡不越过侧栏。因而当前实现即使缺失关键账户信息、用伪元素伪造会员入口，仍可通过。
   - 另外，`creationWidth >= 280` 与 `minimumToolWidth >= 120` 过宽松，不能证明 1025/1024 的文本没有不合理换行/遮挡；建议至少校验关键文本可见、卡片 rect 不相交及分栏数量。

### Minor

1. **1487 视觉比例整体接近，但首排主卡偏宽、工具卡偏窄。**
   - 位置：`dashboard.css:187-192`
   - 参考稿新建创作卡约 x=284–694（约 410px），当前约 x=283–736（约 453px）；当前三张工具卡均约 220px，使主卡/工具卡的视觉权重比参考稿更强。brief 给定的 grid 公式已使用，因此这是视觉微调项，不单独构成规格失败。

2. **参考稿底部有分隔线与居中品牌 footer，当前截图完全缺失。**
   - 当前主体卡片在约 y=942 结束后直接进入空白；参考稿约 y=979 有横线和“影创工坊 · 让 AI 创作更简单”。若 footer 属于后续任务，应明确记录；否则应补真实 DOM。

3. **Token 已定义，但核心样式仍散落大量硬编码色值。**
   - 位置示例：`dashboard.css:56-59,90,114,126-128,171-176,204-208,238,265-269,291-293`。
   - 这削弱了 brief 中语义 Token 的收益。装饰性渐变可以保留局部色值，但常用边框、文字、交互紫色和 surface 应优先落到已有或新增 token。

4. **`display: contents` 用在具名 section 上存在语义稳定性风险。**
   - 位置：`dashboard.css:321-323`
   - `.tool-quick-start` 是带 `aria-labelledby` 的 `<section>`，被设为 `display: contents`；不同浏览器/辅助技术组合对其可访问树保留情况并不完全一致。可用 grid subgrid/显式 placement 或将视觉容器与语义 section 分离。

## 视觉比对结论

### 接近参考的部分

- 1487×1058 画布完全一致；侧栏约 250px，Banner 起点、宽度和约 156px 高度接近参考。
- Banner、首排四卡、下排“最近项目 + 创作点 + 灵感”的纵向层级与整体暗色霓虹风格成立。
- 下排宽度关系较接近：最近项目仍为主列，Credits 与 Inspiration 为右侧双列。
- 晶体、轨道、光束和 Credits 环均为 CSS 结构化装饰；静态扫描未见 `url()`、base64、canvas 或参考图文件名。唯一 `<img>` 位于 `DashboardThumbnail.jsx`，用于 Mock 内容缩略图，属于允许的图片资产。

### 明显差异

- 顶部账户区被“通知 + 新建创作”替代，缺少余额、充值和头像。
- 侧栏会员卡越界且不可交互；侧栏主导航还比参考稿少一个位于主分组的“新建创作”入口，文案也从“工作台概览”缩为“概览”。
- 主创建卡宽约多 43px，三张工具卡相应更窄；输出的创建标题换成两行，参考稿单行“新建创作”层级更简洁。
- 输出缺失参考稿底部品牌 footer。

## Existing dirty ownership

- `2af3d72` commit 只包含：
  1. `scripts/verify-dashboard.mjs`
  2. `src/main.jsx`
  3. `src/styles/dashboard.css`
- 当前工作区另有 `verify-hero.mjs`、`verify-three-hero.mjs`、Three.js 文件、`demo-workbenches.css`、`home.css` 等脏改动；它们没有进入 Task 4 commit，Task 4 的提交 ownership 是窄且可审查的。
- `git diff --check 2af3d72^ 2af3d72` 静态检查无输出。

## Cannot verify

- 未复跑 `npm run build`、`npm run verify:dashboard`，因此报告中声称的最终通过仅有文字记录，没有在本审查中重新确认。
- 没有 RED 阶段命令输出/日志或可定位提交，无法独立确认测试确实先失败再实现；只能确认最终 diff 中测试与 CSS 同在一个 commit。
- 本次只按要求查看 1487×1058 截图，未对 1280、1025、1024 做实时浏览器检查；`dashboard-1025x1058.png` 也未纳入指定的 `view_image` 对比。
- 无法仅凭当前状态证明所有未提交脏改动在 Task 4 开始前就已存在；能确认的是它们没有被包含进 Task 4 commit。

## Required changes before approval

1. 用真实 DOM link/button 重建侧栏会员入口，修复越界并补键盘/读屏/点击测试。
2. 按参考稿补齐真实顶部账户区（余额、充值、头像/账户入口），不要用通知/新建创作替代。
3. 将分组标题、创建说明、字段标签等业务文本从伪元素迁回 DOM；伪元素只做装饰。
4. 为上述区域补稳定的语义 class hooks，移除基于 DOM 顺序和 `aria-label` 的主要样式分派。
5. 扩展桌面验证，覆盖账户区、会员入口、Banner 高度、关键 grid 关系和元素不相交。

---

# Task 4 修复复审（2026-07-14）

## Re-review Verdict

- **规格符合性：PASS**
- **代码质量：APPROVED**

修复提交 `6c87114 fix: address dashboard desktop review` 已解决前次全部 Critical、Important 和 Required changes。更新后的 1487×1058 截图在侧栏、顶部账户区、Banner、首排四卡、下排三模块及 Footer 的信息层级上已形成完整的结构化重建；未发现新的阻塞问题。

## 前次问题逐项复核

### Critical：已解决

1. **侧栏会员入口：RESOLVED**
   - `DashboardSidebar.jsx:40-51` 现为真实 `.dashboard-membership-card` button，包含真实标题、说明、皇冠与箭头节点，并触发“升级会员功能建设中” Toast。
   - `dashboard.css:128-152` 使用侧栏内约束 `width: calc(100% - 44px)`；更新截图中卡片约为 x=22–228，未再越过 250px 侧栏。
   - `verify-dashboard.mjs:53,69,85-90,110,121-123,202` 新增真实 DOM、边界、键盘焦点和点击行为验证。

### Important：全部解决

1. **顶部账户区：RESOLVED**
   - `DashboardHeader.jsx:5-27` 已重建为余额、充值、账户头像三个真实 button；更新截图与参考稿的信息架构一致。
   - 三项均有明确可访问名称/可见文本、焦点能力和 Toast 验证（`verify-dashboard.mjs:111-113,124-130,203-205`）。

2. **CSS 伪元素业务文案：RESOLVED**
   - 工具/账户分组标题已迁入 `DashboardSidebar.jsx:31-33`。
   - 创建说明已迁入 `CreationEntryCard.jsx:9-11`。
   - 项目消耗已迁入 `RecentProjects.jsx:25-28` 的 `.recent-projects__credits`。
   - 当前 CSS 的 `content` 仅用于 Credits 环等纯装饰，没有中文业务内容。

3. **脆弱 CSS hooks：RESOLVED**
   - Banner、Header、Credits、Inspiration、会员入口均补了明确语义 class。
   - 前次 `first-child`、`nth-of-type`、用 `aria-label` 分派样式的选择器已移除；静态复核未发现 `display: contents` 回归。

4. **测试有效性：RESOLVED**
   - `verify-dashboard.mjs:49-130` 现覆盖会员卡 DOM/边界、账户区、Banner 高度、首排不相交及顶部对齐、下排三列关系、真实业务文本和 Footer。
   - `:200-205` 覆盖会员及账户操作的实际 Toast 行为。
   - 1280、1025、1024 的无横向溢出、侧栏避让和卡片最小可读宽度检查仍保留。

## 前次 Minor 复核

1. **首排比例：RESOLVED**
   - `dashboard.css:325-328` 引入 `.dashboard-primary-grid`。更新截图中主创建卡约 427px、工具卡约 228px，较原实现的约 453/220px 更接近参考稿的约 410/230px。

2. **Footer 缺失：RESOLVED**
   - `DashboardPage.jsx:54` 与 `dashboard.css:416` 增加真实 Footer；更新截图约 y=979 的分隔线和居中文案与参考稿位置接近。

3. **Token 使用不足：IMPROVED / non-blocking**
   - 新增 `--dashboard-nav-text`、`--dashboard-panel`、`--dashboard-panel-hover`、`--dashboard-purple-border`，常用导航、面板、hover 和主边框已收敛。
   - 晶体、Banner、头像和工具卡仍保留局部硬编码渐变色，但这些属于一次性结构化装饰，不再作为阻塞项。

4. **`display: contents` 语义风险：RESOLVED**
   - `.tool-quick-start` 保留真实 section 盒；隐藏标题使用 visually-hidden 技法，工具列表使用真实 grid。

## 更新截图视觉复核

### 已达到

- 顶部余额、充值、头像与参考稿一致，不再由通知/新建按钮替代。
- 侧栏补齐“工作台概览 / 新建创作 / 我的项目”，工具与账户分组标题均为真实 DOM。
- 会员卡真实可交互并完整收在侧栏内。
- Banner 约 156px 高，起点、宽度、晶体/轨道/按钮层级保持接近。
- 首排主卡和三张工具卡比例已显著收敛；下排三模块比例、顶部对齐与参考稿接近。
- Footer 已恢复；更新截图删除参考图后主体仍完整。
- 页面仍仅使用 Mock WebP 作为项目/灵感内容缩略图；未发现参考图、裁片、`url()`、base64 或 canvas 贴图。

### 非阻塞视觉差异

- 参考稿会员卡约位于 y=897–979，更新截图约位于 y=950–1032；当前卡片更贴近视口底部，虽不越界也不影响交互，但后续视觉抛光可将其上移约 50px，使其与 Footer 分隔线关系更贴近参考。
- 主创建卡参考稿是“新建创作”在上、说明在下；当前 DOM 为 eyebrow 在标题上方（`CreationEntryCard.jsx:9-11`）。主标题字号/权重仍明确，属于轻微顺序差异，不影响本次验收。
- 头像采用 CSS 结构化图标而非人物照片；这是可维护且符合禁止贴图作弊要求的占位实现。

## 修复提交 ownership

- `6c87114` 只修改 Dashboard 修复所需的 11 个文件：验证脚本、7 个 Dashboard 组件/页面、Dashboard 数据和 Dashboard CSS；没有纳入当前工作区既有的 Hero、Three.js、demo、`home.css` 脏改动。
- `git diff --check 6c87114^ 6c87114` 静态检查无输出。

## Re-review Cannot verify

- 按要求未复跑 `npm run build`、`npm run verify:dashboard`、`npm run verify:routing`；复审对 PASS 证据的判断来自更新报告、diff 与更新截图，而不是本轮重新执行。
- RED 阶段“侧栏存在真实会员入口”的原始终端输出未随 diff 提供，因此 TDD 顺序仍只能依据报告记录确认。
- 本轮仅按要求原尺寸查看 1487×1058 修复截图；1280、1025、1024 的实际渲染未重新做视觉检查。
