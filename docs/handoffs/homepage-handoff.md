# 首页原型开发交接文档

> 更新时间：2026-07-14  
> 工作目录：`/Users/wujingfeng/project/ai/codex/NarratoAI`  
> 原型目录：`docs/web/homepage-prototype/`  
> 当前分支：`wjf/v0.01`  
> 当前约束：本轮已按用户要求停止实现，仅保留现场供后续继续。

## 1. 当前目标

首页正在按已选定的 **B 风格赛博朋克方案**还原，核心产品定位为面向自媒体小白的 AI 视频工具集合，主推短剧解说，兼顾视频翻译和短剧混剪。

最新实现方向已经确定为：

- 使用 **Three.js 视觉层 + 结构化 DOM 工作台**的混合方案。
- Three.js 只负责 Hero 的真实 3D 面板代理、镜面反射、透视网格、青紫霓虹边缘和辉光。
- 标题、按钮、流程、卡片、视频预览、时间线等仍然是可编辑、可交互的真实 DOM。
- 禁止把参考图、页面截图或工作台截图映射到 Canvas/纹理中伪造效果。
- Three.js 不可用时进入 CSS fallback，页面主体和交互仍需完整。

设计规格和实施计划：

- `docs/superpowers/specs/2026-07-14-threejs-hero-design.md`
- `docs/superpowers/plans/2026-07-14-threejs-hero-implementation.md`

## 2. 已完成内容

### 2.1 首页基础原型

- 已有完整 React + Vite 首页原型。
- 首页包含导航、Hero、案例 Demo、产品能力、FAQ、CTA、弹层和移动菜单等结构。
- Hero 标题已有 5 秒一次的扫光动画。
- Hero 工作台、流程节点、卡片、时间线、波形和按钮均为真实 DOM/CSS。
- 内容图片仅作为剧情海报、视频帧和案例封面，不承载 UI 结构。

### 2.2 Hero 的 CSS 基础效果

- 工作台已使用较明显的倾斜姿态。
- 已有 CSS 霓虹边框、右侧高亮、投影和镜面地台 fallback。
- Hero 底部已有整区赛博朋克网格、地平线光、文案/CTA 光痕和工作台反射占位层。
- CSS fallback 会在 Three.js 不可用或 `?threeFallback=1` 时保留。

### 2.3 三类 Demo 已拆成不同产品流程

`DemoSection.jsx` 已不再使用同一套三栏 UI 仅替换文字，而是包含三个独立组件：

- `NarrationStudio`
  - 5 步：上传剧集、ASR/剧情拆解、筛选高光、生成/润色解说词、配音字幕合成。
  - 包含素材队列、剧情/文案编辑、前后对比和输出评分。
- `TranslationLocalizer`
  - 4 步：识别中文对白、翻译与本地化、角色声线映射、英文配音与双语字幕。
  - 包含语言对、双语字幕、对白编辑和角色声线映射。
- `RemixConsole`
  - 3 步：导入多集、选择高光、卡点拼接与混音。
  - 包含高光片段池、多轨时间线、原声/BGM 和节拍控制。
  - 不包含解说词或字幕编辑语义。

已新增 `src/styles/demo-workbenches.css`，为三种工作台提供不同布局，并包含 1023px、767px 和 390px 响应式规则。

### 2.4 Three.js 依赖和核心场景

- 已安装并精确锁定 `three@0.185.1`。
- 已增加 npm 脚本：`verify:three-hero`。
- 已新增 `heroThreeScene.js`，包含：
  - `HERO_PANEL_POSES`
  - `resolveHeroPose()`
  - `getHeroPoseStyle()`
  - `createHeroThreeScene()`
  - 透明 `WebGLRenderer`
  - `PerspectiveCamera`
  - `RoundedBoxGeometry` 程序化面板代理
  - cyan / violet 双霓虹边轨
  - `Reflector` 镜面
  - `GridHelper`、暗色地面和地平线光
  - `EffectComposer`、`RenderPass`、`UnrealBloomPass`、`OutputPass`
  - Bloom/透明合成异常时的直接渲染降级
  - 桌面 DPR 上限 1.5、移动端 DPR 1
  - 静态/减少动效模式、离屏暂停和完整资源释放

共享姿态目前为：

| Pose | rotateX | rotateY | rotateZ | depth |
| --- | ---: | ---: | ---: | ---: |
| desktop | 2° | -11° | -1° | 30px |
| compact | 1.5° | -8° | -0.5° | 22px |
| tablet | 1° | -5° | 0° | 14px |
| mobile | 0.5° | -3° | 0° | 8px |

### 2.5 Three.js React 适配器和 Hero 挂载

已新增 `ThreeHeroScene.jsx`：

- WebGL2 能力探测。
- `?threeFallback=1` 强制 fallback。
- `ResizeObserver` 同步 Hero/工作台尺寸。
- `IntersectionObserver` 控制离屏暂停。
- `prefers-reduced-motion` 监听。
- `visibilitychange` 监听。
- 异常降级和 runtime 清理。
- 当前状态属性：
  - `data-three-state`
  - `data-three-reflection`
  - `data-three-rails`
  - `data-three-loop`

`HeroSection.jsx` 已完成：

- 挂载 `ThreeHeroScene`。
- 增加 `heroRef` 和 `workbenchRef`。
- `HeroWorkbench` 外层绑定 `workbenchRef`。
- `section#hero` 设置 `data-hero-pose` 和共享 CSS 变量。
- 监听窗口断点变化并切换姿态。
- 原有 Hero 文案、CTA、工作台 DOM 和业务交互未被替换。

`home.css` 已完成：

- `.three-hero-scene` 和 Canvas 的层级、透明、尺寸及 pointer-events 规则。
- DOM 工作台 transform 改为使用 `--hero-panel-rotate-x/y/z`。
- Three Canvas 位于背景/镜面之上、真实 Hero DOM 之下。
- fallback 时保留原 CSS 霓虹和镜面。

## 3. 改动文件

Git 当前把整个 `docs/web/homepage-prototype/` 识别为未跟踪目录，因此无法依赖普通 `git diff` 还原该目录的逐文件基线。以下为本轮明确新增或修改的文件：

| 文件 | 状态/用途 |
| --- | --- |
| `docs/web/homepage-prototype/package.json` | 新增 `three` 和 `verify:three-hero`；仍包含 `verify:demo` |
| `docs/web/homepage-prototype/package-lock.json` | 锁定 `three@0.185.1` |
| `docs/web/homepage-prototype/src/components/DemoSection.jsx` | 三类独立 Demo 工作台 |
| `docs/web/homepage-prototype/src/styles/demo-workbenches.css` | 三类 Demo 独立布局与响应式 |
| `docs/web/homepage-prototype/src/components/HeroSection.jsx` | Three 场景挂载、共享姿态和 refs |
| `docs/web/homepage-prototype/src/components/ThreeHeroScene.jsx` | React 生命周期适配、观察器和 fallback |
| `docs/web/homepage-prototype/src/components/heroThreeScene.js` | Three.js 核心场景和资源释放 |
| `docs/web/homepage-prototype/src/styles/home.css` | Hero Canvas 层级、共享姿态和 CSS fallback |
| `docs/web/homepage-prototype/scripts/verify-hero.mjs` | 旧 Hero/CSS 回归脚本，Three 最终接入后尚未重新确认 |
| `docs/web/homepage-prototype/scripts/verify-three-hero.mjs` | Three 静态合约、浏览器、fallback 和响应式验证 |
| `docs/web/homepage-prototype/design-qa.md` | 旧版 QA，日期为 2026-07-13，尚未覆盖本轮 Three/Demo 改动 |
| `docs/superpowers/specs/2026-07-14-threejs-hero-design.md` | 已确认的设计规格 |
| `docs/superpowers/plans/2026-07-14-threejs-hero-implementation.md` | TDD 实施计划 |
| `docs/handoffs/homepage-handoff.md` | 本交接文档 |

### 当前缺失文件

- `docs/web/homepage-prototype/scripts/verify-demo.mjs` **当前不存在**。
- 但 `package.json` 仍包含：`"verify:demo": "node scripts/verify-demo.mjs"`。
- 因此当前执行 `npm run verify:demo` 会因脚本缺失失败；后续需要恢复或重建该脚本。

## 4. 当前验证状态

| 验证项 | 当前结论 | 说明 |
| --- | --- | --- |
| Three 静态 RED | 已完成 | 实现前正确失败：缺少依赖、核心场景、适配器和 Hero 挂载 |
| `npm run verify:three-hero -- --contract` | 最近一次报告通过 | Three exports、姿态、依赖、生命周期关键字和反贴图扫描通过 |
| Three 核心场景临时 smoke test | 报告通过 | Canvas 透明、状态 ready、dispose 后移除 Canvas；不是最终整页浏览器验收 |
| `npm run build -- --outDir /tmp/narratoai-three-hero-build-final --emptyOutDir` | 通过 | 4598 modules transformed；有 bundle size warning，无构建错误 |
| `npm run verify:three-hero` | **未完成** | 初次因测试脚本 `rectFor is not defined` 中断；该测试代码已改为在 `page.evaluate` 内定义 `rectFor`，但修复后的完整运行被中断，最终结果未知 |
| `npm run verify:hero` | 待重新执行 | CSS-only Hero 版本此前通过；Three 最终接入后未获得新的完整结果 |
| `npm run verify:demo` | 当前不可执行 | `scripts/verify-demo.mjs` 缺失 |
| Demo 响应式 smoke test | 子任务报告通过 | 报告覆盖 1920/1487/1200/1024/768/390，但缺少当前可重复执行的脚本文件 |
| `design-qa.md` | 过期 | 当前内容是 2026-07-13 的 CSS 版本，不能作为最新 Three 版本的通过证据 |
| In-app Browser 最终视觉验收 | 未完成 | 尚未完成参考图与最新实现的并排比较，也未生成最终截图证据 |

本轮停止前，Three 浏览器验证脚本已包含：

- 1920×1080
- 1487×1058
- 1200×900
- 1024×820
- 390×844
- 正常 WebGL 路径
- `?threeFallback=1` 路径
- Canvas 透明度和 pointer-events
- Hero/Demo 重叠和横向溢出
- CTA 可点击
- console/page error 收集

但上述浏览器验收需要重新完整运行后才能视为通过。

## 5. 待办事项

按优先级排序：

1. **恢复 `scripts/verify-demo.mjs`**
   - 保证 `npm run verify:demo` 可重复执行。
   - 验证三类根节点、5/4/3 步骤数、专属 UI 和响应式。

2. **重新启动本地 Vite 服务并运行 Three 浏览器验证**
   - 确认修复后的 `rectFor` 浏览器上下文代码有效。
   - 获得正常路径和 fallback 路径的最终 PASS/FAIL。

3. **检查 Three.js 真实视觉表现**
   - Canvas 是否真的显示，而不是状态 ready 但视觉不可见。
   - 面板代理是否与 DOM 外壳对齐。
   - Reflector 是否形成可信镜面。
   - cyan/violet rails 是否与工作台边缘对齐。
   - Bloom 是否产生黑色矩形、过曝或 alpha 问题。

4. **重点检查可能的双重透视**
   - `getBoundingClientRect()` 返回的是已做 CSS transform 后的工作台包围盒。
   - Three 场景随后又应用同一组 rotateX/Y/Z，存在视觉上重复倾斜或尺寸漂移的可能。
   - 后续应以截图和边缘对齐结果决定是否读取未变换尺寸、抵消 DOM transform，或只让 Three 代理承担厚度/反射。

5. **协调 Three 镜面和 CSS fallback 镜面**
   - 当前两者可能同时可见。
   - 需要在 `data-three-state="ready"` 时降低 CSS 镜面的强度，fallback 时恢复完整 CSS 镜面，避免重复反光或过曝。

6. **重新执行旧 Hero 回归**
   - 验证标题与工作台不重叠。
   - 验证 5 秒扫光。
   - 验证桌面和移动端无横向溢出。

7. **运行 Demo 回归和交互测试**
   - Tab 点击和键盘切换。
   - 案例卡和弹层。
   - 390px 移动端横向滚动仅发生在内部时间线/流程容器，不扩展页面宽度。

8. **更新视觉 QA**
   - 使用最新参考图和最新页面截图做同视口并排比较。
   - 更新 `docs/web/homepage-prototype/design-qa.md`。
   - 只有 P0/P1/P2 均清零时才把 `final result` 更新为 `passed`。

9. **考虑 Three.js bundle 拆分**
   - 当前构建已有 bundle size warning。
   - 后续可以把 Three 场景动态导入，或按 Hero 可见性延迟加载，降低首屏 JS 体积。

10. **Git 收口**
    - 当前原型目录、规格和计划均为未跟踪文件。
    - 尚未暂存、提交或创建分支/PR。
    - 收口前只应加入本次相关文件，避免混入仓库内大量其他未提交改动。

## 6. 建议验证命令

以下命令仅作为后续继续时的执行顺序。本次交接没有继续运行这些命令。

```bash
cd /Users/wujingfeng/project/ai/codex/NarratoAI/docs/web/homepage-prototype
```

### 6.1 安装和依赖确认

```bash
npm install
npm ls three --depth=0
```

预期：仅一个 `three@0.185.1`。

### 6.2 静态 Three 合约

```bash
npm run verify:three-hero -- --contract
```

预期：`Three.js Hero contract is GREEN.`

### 6.3 构建

```bash
npm run build
```

或避免覆盖当前 `dist`：

```bash
npm run build -- --outDir /tmp/narratoai-three-hero-build --emptyOutDir
```

### 6.4 启动本地服务

```bash
npm run dev -- --host 127.0.0.1 --port 4173 --strictPort
```

### 6.5 Three 浏览器回归

另开终端执行：

```bash
BASE_URL=http://127.0.0.1:4173/ npm run verify:three-hero
```

### 6.6 旧 Hero 回归

```bash
BASE_URL=http://127.0.0.1:4173/ npm run verify:hero
```

### 6.7 Demo 回归

当前脚本缺失；先恢复 `scripts/verify-demo.mjs`，再执行：

```bash
BASE_URL=http://127.0.0.1:4173/ npm run verify:demo
```

### 6.8 反贴图扫描

```bash
rg -n \
  "TextureLoader|CanvasTexture|VideoTexture|data:image|base64|codex-clipboard|background-image\\s*:\\s*url" \
  src/components/HeroSection.jsx \
  src/components/ThreeHeroScene.jsx \
  src/components/heroThreeScene.js \
  src/styles/home.css
```

预期：零命中。

### 6.9 Git 和空白检查

```bash
git -C /Users/wujingfeng/project/ai/codex/NarratoAI status --short -- docs/web/homepage-prototype docs/superpowers docs/handoffs
git -C /Users/wujingfeng/project/ai/codex/NarratoAI diff --check
```

## 7. 当前风险

### 高风险

1. **Three 浏览器验收尚未完成**  
   当前不能确认用户实际看到的镜面、霓虹和 3D 对齐已经达到参考图效果。

2. **`verify-demo.mjs` 缺失**  
   `package.json` 暴露了一个当前无法执行的命令，Demo 回归缺少可重复证据。

3. **Three 与 DOM 可能存在双重透视/边缘漂移**  
   需要视觉对齐检查，不能只依赖状态属性或构建通过。

### 中风险

4. **Reflector + UnrealBloomPass 的透明合成兼容性**  
   某些 GPU/浏览器可能出现黑底、alpha 错误、反射异常或性能下降；代码有降级路径，但尚未在最终页面验证。

5. **CSS 镜面与 Three 镜面可能叠加过度**  
   可能导致 Hero 底部过亮、重影或层级混乱。

6. **Three.js 增大首屏 bundle**  
   最新构建出现 bundle size warning；尚未动态导入或拆包。

7. **移动设备性能**  
   已设计 DPR 1、无 Bloom、静态帧等策略，但尚未用真实移动浏览器验证 GPU 占用、发热和掉帧。

### 低风险/流程风险

8. **状态属性命名与设计规格略有差异**  
   设计规格使用过 `data-three-reflector` / `data-three-neon-rails`，当前实现和测试实际使用 `data-three-reflection` / `data-three-rails`。继续时应统一文档或代码，避免后续测试歧义。

9. **`design-qa.md` 已过期**  
   文件目前仍记录旧 CSS 版本的通过结论，不能代表当前实现。

10. **工作区未收口**  
    整个原型目录是未跟踪状态，仓库同时还有大量与首页无关的未提交改动；后续 Git 操作必须限定文件范围。

## 8. 建议接手顺序

1. 阅读设计规格和实施计划。
2. 恢复 `verify-demo.mjs`。
3. 启动 Vite。
4. 跑 Three 静态合约和构建。
5. 跑 Three 浏览器验证，先修测试问题，再修生产问题。
6. 在 1487×1058 和 1920×1080 对照参考图检查 Hero。
7. 再检查 1200、1024、390 响应式。
8. 跑旧 Hero、Demo、交互和反贴图回归。
9. 更新 `design-qa.md`。
10. 用户确认视觉后再做 Git 收口。

## 9. 本次停止点

- Three.js 核心、React 适配和 Hero 挂载均已写入。
- Three 静态合约和构建最近一次报告通过。
- Three 浏览器脚本中的 `rectFor` 上下文问题已在源文件中修正。
- 修正后的完整浏览器测试在运行过程中被中断，没有最终结论。
- 所有正在运行的 Subagent 已关闭。
- 未继续修改实现文件。

