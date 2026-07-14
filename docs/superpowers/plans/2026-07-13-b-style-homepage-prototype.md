# B 风格官网首页 React 原型实施计划

> **For agentic workers:** 按任务逐项勾选；本计划只覆盖 `docs/web/homepage-prototype` 的独立静态 React/Vite 原型，不接入现有 Streamlit、登录、支付或生成服务。

**目标：** 在新的 Product Design starter + React/Vite 目录中，结构化复刻 B 风格官网首页，桌面以 `1487px` 宽、移动端以 `390x844` 为对齐基准，并完整演示首页交互。

**架构：** 单页 React 通过锚点分区组织 Hero、Demo、能力、FAQ、CTA 和页脚；交互状态仅保存在组件内。视觉层以 CSS token、真实文本、CSS 面板与 `@phosphor-icons/react` 图标重建，真实剧情封面/缩略图可从既有 assets 复制使用。

**技术栈：** Product Design starter、Vite、React、CSS、`@phosphor-icons/react`、Playwright（浏览器验收）。

## 全局约束

- [ ] 仅在实施阶段创建或修改 `docs/web/homepage-prototype/**`；不得回退、覆盖或整理任何既有脏文件。
- [ ] 初始化独立 Vite + React 项目，并安装 `@phosphor-icons/react`；不复用 `docs/c-user-web-prototype` 的应用代码、`baseline/`、`dist/` 或视觉回归脚本。
- [ ] 允许复制 `docs/c-user-web-prototype/public/assets/**` 中本身就是内容图像的资产（剧情海报、缩略图、品牌图）；逐项在 `design-qa.md` 记录来源与用途。禁止复制/引用 `docs/web/prototypes/b-style/*.png`、任何 `baseline/*.png`、截图或参考图到交付目录。
- [ ] 禁止使用参考整图/局部图作为 `<img>`、CSS `background-image`、base64/data URL、canvas 截图、SVG 内嵌位图或 bitmap fill；参考图仅能在开发者本地并排比对，不能被页面运行时请求。
- [ ] 所有标题、正文、按钮、卡片、时间线、波形、地面网格、发光和 UI 面板必须由真实 HTML/CSS/SVG 矢量图形构成；图标统一来自 `@phosphor-icons/react`。
- [ ] 使用语义按钮、键盘可操作的菜单/弹层/FAQ，并支持 `Escape` 关闭弹层与移动菜单；不得为静态视觉牺牲交互可访问性。

## 实施文件图

| 文件 | 职责 |
|---|---|
| `docs/web/homepage-prototype/package.json` | Vite、React、图标库、`dev` / `build` / 浏览器截图脚本。 |
| `docs/web/homepage-prototype/src/main.jsx` | React 入口。 |
| `docs/web/homepage-prototype/src/App.jsx` | 页面数据、锚点/菜单/工具/FAQ/播放弹层/CTA 状态与页面组合。 |
| `docs/web/homepage-prototype/src/components/*.jsx` | `Header`、`HeroWorkbench`、`DemoSection`、`CapabilitySection`、`FaqSection`、`CtaSection`、`VideoModal` 的可维护边界。 |
| `docs/web/homepage-prototype/src/styles/tokens.css` | 颜色、间距、字号、阴影、边框、断点 token。 |
| `docs/web/homepage-prototype/src/styles/home.css` | 首页布局、霓虹、CSS 面板、响应式细节。 |
| `docs/web/homepage-prototype/public/assets/**` | 仅复制允许的真实内容图像，不放任何参考稿/基线图。 |
| `docs/web/homepage-prototype/scripts/capture-home.mjs` | Playwright 生成桌面与移动端截图并采集 console/page error。 |
| `docs/web/homepage-prototype/design-qa.md` | 构建、浏览器、console、视觉与反贴图 gate 的验收记录。 |

## 任务清单

### 1. 初始化与验收骨架

- [ ] 用 Product Design starter 初始化 `docs/web/homepage-prototype` 为独立 React/Vite 项目；配置本地 host、`npm run dev`、`npm run build`、`npm run screenshot`。
- [ ] 安装并锁定 `@phosphor-icons/react`；创建 token 层（近黑背景、青蓝主光、紫色强调、橙色混剪语义、玻璃面板、1440/1024/768/480 断点）。
- [ ] 只复制需要的真实内容图像：主剧情竖版海报、三张 Demo 缩略图、品牌图；在 `design-qa.md` 登记每个路径、页面位置与“内容图像”例外理由。
- [ ] 编写 Playwright 截图脚本：启动后的 `1487x1058` 桌面全页截图和 `390x844` 移动全页截图输出到 `artifacts/screenshots/`，并把 `console` error、`pageerror`、失败请求汇总为非零退出。

### 2. 结构化首屏与顶部导航

- [ ] 实现固定/吸顶 Header：可编辑品牌文字与矢量标识、桌面“产品能力 / 案例 Demo / 价格”、登录按钮；背景从透明逐步过渡为深色玻璃。
- [ ] 构建 Hero 文本列：AI 视频创作标签、“专为自媒体小白打造的 AI 出片工作台”渐变标题、说明、主/次 CTA 和两项能力卖点；文字均为可选择文本。
- [ ] 用 DOM/CSS 重建右侧 AI 工作台：分析步骤、9:16 成片预览、三张工具卡、时间线、字幕/波形/播放指针、倾斜玻璃边框、网格地面与青紫反射；不得把任何参考图切片为面板。
- [ ] 以 CSS 媒体查询重排为移动首屏：Header 仅品牌、登录、汉堡；Hero 居中；CTA 纵向全宽；工作台缩为纵向三列组合；移动端保留两项卖点与继续向下的指示。

### 3. Demo、工具切换与播放弹层

- [ ] 实现 `DemoSection`：标题“看见 AI 如何把素材变成成片”、三个工具切换卡、左侧三步进度、中间“原始素材 / 最终成片”对比预览、右侧 AI 输出摘要和三个底部案例卡。
- [ ] 定义单一 `toolId` 数据模型：`narration`（默认）、`translation`、`remix`；切换时同步更新激活色、步骤文案、摘要、案例标题/标签和按钮文本，且保持三类工具语义边界：混剪只露出高光、原声、BGM，不出现配音/字幕功能。
- [ ] “播放完整案例”及任一案例卡打开可关闭的 `VideoModal`：显示允许使用的真实封面、标题、模拟播放进度和关闭按钮；点击播放切换暂停状态，`Escape`/遮罩/关闭按钮均可关闭，并将焦点返回触发按钮。
- [ ] 为三个案例卡提供“使用相同模板创作” CTA 反馈，不跳转真实工作台；以局部 toast 明确展示“已选择：{工具}，正式工作台接入后继续”。

### 4. 能力、流程、FAQ 与收口 CTA

- [ ] 实现三张能力卡：短剧解说（紫）、视频翻译（青）、短剧混剪（橙）；使用 Phosphor 图标与 CSS 3D/矢量装饰，不以插画截图替代；每张“立即体验”触发对应工具选择和 CTA toast。
- [ ] 实现五步流程条（上传素材、AI 分析、用户审核、自动合成、导出发布）与小白引导文案；窄屏改为可读的纵向流程，不发生横向溢出。
- [ ] 实现 FAQ 手风琴：四条问题，单开状态、`aria-expanded`、键盘切换与平滑内容高度过渡；首项默认关闭，避免首屏外无意义占高。
- [ ] 实现最终 CTA 与页脚：点击“开始创作”显示可消失 toast（含默认短剧解说选择）；“查看案例”平滑滚动到 Demo；登录/价格作为原型反馈入口，分别显示“登录流程待接入”“价格页待接入”，不伪造真实业务跳转。

### 5. 锚点、移动菜单与细节收敛

- [ ] 将“产品能力”“案例 Demo”映射到 `#capabilities`、`#demo` 并平滑滚动；滚动时用 `IntersectionObserver` 高亮当前导航项。价格保持显式反馈入口，避免指向不存在的锚点。
- [ ] 实现移动汉堡菜单：打开时显示产品能力、案例 Demo、价格、登录；选中锚点后关闭菜单、滚动到目标；`Escape`、关闭按钮和遮罩都可收起，背景不滚动。
- [ ] 校准桌面 `1487px` 与移动 `390x844`：标题换行、首屏工作台尺度、卡片间距、霓虹强度、底部内容层级与安全区；允许 CSS 近似，不引入重型 3D/动画依赖。
- [ ] 仅保留低成本微交互（hover、focus、工具切换、toast、modal、accordion、平滑滚动）；尊重 `prefers-reduced-motion`，且不实现影响加载/CTA 的炫技动画。

### 6. 构建、浏览器与设计 QA Gate

- [ ] 执行 `npm ci && npm run build`，将命令、退出码、构建产物结论写入 `design-qa.md`。
- [ ] 启动本地预览后执行 `npm run screenshot`；在 `artifacts/screenshots/home-desktop-1487.png` 和 `artifacts/screenshots/home-mobile-390.png` 检查首屏、Demo、能力、FAQ、CTA 和页脚，记录实际截图路径与审阅结论。
- [ ] 用浏览器人工走查：桌面锚点导航、三工具切换、案例弹层和关闭、FAQ、所有 CTA；移动菜单、CTA 点击、无横向滚动；记录每项通过/修复项。
- [ ] 复核浏览器 console、`pageerror` 与失败请求均为零；将原始异常文本（如有）与处理结果写入 `design-qa.md`。
- [ ] 执行反贴图检查：`rg -n "data:image|base64|background-image|/baseline/|b-style/|canvas" docs/web/homepage-prototype/src docs/web/homepage-prototype/public`；仅允许 CSS 渐变/阴影的 `background-image` 结果，任何参考图、基线、canvas、base64 或位图背景命中即 Gate 失败。
- [ ] 在 `design-qa.md` 写入最终 Gate：隐藏/删除所有参考图后页面完整；真实图片资产清单与用途正确；所有文本和交互元素可编辑；build、截图、console、桌面/移动交互均通过。未通过项必须明确列为阻塞项，不能标记完成。

## 完成定义

- [ ] `npm run build` 成功，桌面 `1487x1058` 和移动 `390x844` 浏览器截图已生成且通过人工视觉审查。
- [ ] 首页完整覆盖四张参考图所示的信息架构：Hero 工作台、Demo、三工具能力、五步流程、FAQ、最终 CTA 与页脚。
- [ ] 锚点导航、工具切换、案例播放弹层、FAQ、移动菜单、CTA 反馈可实际操作，且 console 无 error/pageerror。
- [ ] `design-qa.md` Gate 已填写，且证明交付页面未引用 reference/baseline 图片；删除参考图不会让页面缺失任何主体内容。
