# Three.js Hero 赛博朋克 3D 视觉设计规格

## 1. 目标

参考用户提供的赛博朋克首页原型，仅增强当前首页 Hero：使用 Three.js 实现工作台的真实 3D 透视、镜面反射、边缘高亮与青紫霓虹光效，使工作台像悬浮在高反射地台之上。现有标题、按钮、工作台卡片、视频预览、流程与时间线继续使用结构化 DOM，不重做其他页面，也不改变现有产品信息架构和业务交互。

成功效果应同时满足：

- 桌面端工作台具有明显但可读的侧向透视和轻微俯视角。
- 工作台外轮廓形成连续的 cyan / violet 高亮边缘，而不是多张背板堆叠。
- Hero 底部形成可见的镜面地台，能够反射程序化工作台代理、霓虹边缘和网格光线。
- Three.js 视觉层失效时，真实 DOM 工作台仍完整、可读、可操作。
- 删除参考图后页面不缺失任何主体内容；参考图和工作台截图均不进入最终组件树或渲染纹理。

## 2. 范围边界

### 本次包含

- 首页 Hero 内的透明 WebGL 装饰层。
- 工作台 3D 姿态、程序化面板代理、边缘光轨、镜面和透视网格。
- Three.js 生命周期、性能降级、响应式与自动化验证。
- 现有 `HeroWorkbench` DOM 与 Three.js 场景的空间对齐。

### 明确不做

- 不把工作台内部 UI 重画成完整 3D UI。
- 不加入鼠标拖拽、相机旋转、视角编辑或 `OrbitControls`。
- 不把参考图、页面截图、工作台截图或局部截图作为纹理。
- 不新增后端、账号、支付、上传、音视频处理或生成能力。
- 不重做 Demo、价格、登录、导航或其他页面区块。

前一轮 Demo 独立工作台改造属于并行范围，不是本 Three.js 场景的核心实现；最终整页验证必须确认三类 Demo 的独立结构、Tab 切换与响应式没有被本次改动破坏。

## 3. 混合渲染架构

采用“Three.js 视觉层 + 结构化 DOM 工作台”的混合方案：

```text
HeroSection
├── ThreeHeroScene（绝对定位、透明 canvas、aria-hidden）
│   └── heroThreeScene（场景创建、渲染、观察器回调与释放）
├── Hero 文案与 CTA（真实 DOM）
├── HeroWorkbench（真实 DOM，可编辑、可交互）
└── 能力卖点条（真实 DOM）
```

- `ThreeHeroScene.jsx` 是 React 生命周期适配层，持有容器和 canvas 引用，负责启动、暂停、尺寸同步、降级标记和卸载。
- `heroThreeScene.js` 是纯 Three.js 场景模块，负责相机、几何体、材质、反射、后期处理、动画和资源销毁。
- WebGL canvas 位于 Hero 的装饰层，使用透明背景，覆盖工作台及镜面区域，但必须设置 `pointer-events: none`、`aria-hidden="true"`，不得阻挡登录、CTA、视频和工具卡交互。
- DOM 工作台始终位于可交互层；Three.js 仅绘制程序化几何、边缘光、反射与环境网格。
- Three.js 不读取 DOM 像素，也不使用 `TextureLoader`、`CanvasTexture`、`VideoTexture` 或截图映射。现有真实内容图仍可由 DOM `<img>` 使用，但不得传入 WebGL。

## 4. 场景设计

### 4.1 渲染器与相机

- 使用 `WebGLRenderer({ alpha: true, antialias: true, powerPreference: "high-performance" })`。
- 清屏色保持透明：`renderer.setClearColor(0x000000, 0)`。
- 使用 `PerspectiveCamera`；相机视锥按 Hero 容器宽高更新，使场景单位可稳定映射到 DOM 工作台包围盒。
- 禁止使用 `OrbitControls`。相机位置只由响应式姿态配置决定，用户滚动或移动指针不得改变视角。

### 4.2 程序化工作台代理

- 使用 `RoundedBoxGeometry`，或使用 `Shape + ExtrudeGeometry` 生成单个圆角薄面板代理。
- 代理面板只表现外壳、厚度、暗色玻璃底和轮廓，不承载工作台截图或文字。
- 代理面板与 DOM 工作台共用同一姿态配置，放置在 DOM 背后；其目的包括建立真实透视轮廓、提供可被镜面反射的几何体，以及承载 emissive 边缘。
- 面板主体采用低透明度深蓝材质，避免遮蔽真实 DOM；深度、透明度和渲染顺序需确保不会出现整块黑色遮罩。

### 4.3 边缘高亮与霓虹

- 圆角外轮廓至少包含两条程序化光轨：主 cyan rail 与右侧/底部 violet rail。
- 光轨由圆角曲线配合 `TubeGeometry`、`Line2` 或等价几何构建，不使用图片光晕。
- 核心光轨使用 emissive 或 `MeshBasicMaterial`；外层柔光使用 additive blending，并关闭不必要的深度写入。
- 高亮强度沿顶部、右边和底边做不对称分布，表现原型中的蓝色迎光边和紫色背光边，而不是平均发光的矩形框。
- 动画仅包含缓慢脉冲和淡入：首次进入 600–900ms 淡入，呼吸周期 3.6–5s，幅度保持克制，不移动工作台内容。

### 4.4 镜面与地台

- Hero 底部使用 `Reflector` 创建水平反射平面，反射程序化面板代理、光轨和场景网格。
- Reflector 反射目标不包含 DOM 内部文字和控件；镜面中出现的是与 DOM 对齐的面板轮廓、厚度和霓虹剪影，从而避免截图纹理，同时维持可信的整体反射。
- 镜面上叠加低透明度暗色地台与 horizon glow，反射在远端逐渐衰减，避免形成无限明亮的整屏镜子。
- 使用 `GridHelper` 或程序化 `LineSegments` 生成透视网格；网格密度、透明度和可见距离按断点降低。
- 镜面不得覆盖 Demo 区域，不得扩大 Hero 的交互盒，也不得引发横向滚动。

### 4.5 后期处理

桌面高质量路径使用：

```text
EffectComposer
├── RenderPass
├── UnrealBloomPass
└── OutputPass
```

- Bloom 仅用于 emissive 轨道、网格交点和地平线，不应让 DOM 文字发糊。
- Composer 与 renderer 均保持 alpha 合成；需要检查 `UnrealBloomPass` 是否产生黑底、方形边界或错误 alpha。
- 若目标浏览器的透明合成与 Bloom 不兼容，则关闭 `UnrealBloomPass`，改用多层 emissive 几何与 additive blending 形成柔光。不得为了保留 Bloom 而牺牲透明背景或遮挡 DOM。
- 移动端默认关闭 Bloom，仅保留核心边缘轨道、简化网格和低分辨率 Reflector。

## 5. DOM 与 Three.js 对齐

工作台姿态只允许一个数据源。`heroThreeScene.js` 导出断点姿态常量和 CSS 变量转换函数，`HeroSection.jsx` 与 `ThreeHeroScene.jsx` 共同使用：

```js
export const HERO_PANEL_POSES = {
  desktop: { rotateX: 2, rotateY: -11, rotateZ: -1, depth: 30 },
  compact: { rotateX: 1.5, rotateY: -8, rotateZ: -0.5, depth: 22 },
  tablet: { rotateX: 1, rotateY: -5, rotateZ: 0, depth: 14 },
  mobile: { rotateX: 0.5, rotateY: -3, rotateZ: 0, depth: 8 },
};
```

- `HeroSection` 将当前姿态写入 `data-hero-pose` 和 `--hero-panel-rotate-x/y/z`、`--hero-panel-depth`。
- DOM 工作台的 CSS transform 使用这些变量；Three.js 面板代理读取同一个姿态对象，不在 CSS 和 JavaScript 中各维护一套角度。
- 场景 resize 时读取 DOM 工作台的 `getBoundingClientRect()`，将宽高、中心点和底边映射到相机视锥；边缘轨道投影后应与 DOM 外壳边缘在视觉上对齐。
- 桌面端保持明显倾斜；1024px 以下逐级减弱，避免透视导致文字过度压缩或内容越界。
- canvas、镜面和发光层全部 `pointer-events: none`，DOM 的层叠顺序、焦点顺序与点击区域保持不变。

## 6. 生命周期与容错

### 初始化

1. `ThreeHeroScene` 首次挂载时检测 `window.WebGL2RenderingContext` 并尝试创建 WebGL2 context。
2. 初始化期间容器标记 `data-three-state="loading"`。
3. 场景首帧成功后标记 `data-three-state="ready"`，同时记录 `data-three-reflector="ready"` 与 `data-three-neon-rails="ready"`，供自动化验证。
4. 不支持 WebGL2、创建 context 失败或初始化抛错时，标记 `data-three-state="fallback"`，释放已创建资源并启用 CSS fallback。

### 观察与动画

- `ResizeObserver` 监听 Hero 场景容器和 DOM 工作台，统一更新 renderer、composer、Reflector render target、相机和几何对齐。
- `IntersectionObserver` 只在 Hero 可见时运行 `requestAnimationFrame`；离屏后立即暂停，重新进入时恢复，不累积时间跳变。
- 监听 `prefers-reduced-motion`：开启时禁用淡入后的持续脉冲，完成一次静态渲染后暂停动画循环。
- 页面隐藏时根据 `document.visibilityState` 暂停；恢复可见后仅在 Hero 位于视口内时继续。
- 自动化测试可通过 `?threeFallback=1` 强制进入 CSS fallback，以稳定验证无 WebGL 路径。

### 销毁

卸载、重建或进入 fallback 时必须：

- 取消 `requestAnimationFrame`。
- 断开 `ResizeObserver`、`IntersectionObserver`、媒体查询与 visibility 监听器。
- 对场景内 geometry、material、render target 和 Reflector 执行 `dispose()`。
- 释放 composer passes、renderer，并调用 `renderer.forceContextLoss()`。
- 从容器移除 canvas，清空对象引用，避免热更新或路由往返产生多个 WebGL context。

## 7. CSS fallback

Fallback 必须保持页面可用，而不是显示空洞：

- 继续使用结构化 DOM 工作台及共享姿态变量完成静态倾斜。
- 使用 CSS 渐变边框、`box-shadow` 和伪元素表现 cyan / violet 边缘。
- 使用 CSS 渐变与低透明度网格表现简化镜面地台；不得引用位图背景。
- fallback 不需要模拟 DOM 内部的镜面内容，但需保留工作台底部轮廓反光和地平线霓虹。
- fallback 下所有 CTA、导航、视频及工具卡交互与正常路径一致。

## 8. 性能预算

- `renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5))`；移动端上限降为 `1.0`。
- Reflector render target 不超过当前场景 CSS 尺寸乘以 DPR，移动端按 0.5–0.75 比例缩放。
- 桌面只保留少量固定光轨和网格；如使用粒子，桌面不超过 160 个，移动端不超过 40 个，且仅用单一共享 geometry/material。
- 移动端关闭 Bloom、减少网格分段和反射分辨率，并在初始静态帧后停止持续动画。
- Hero 离屏、标签页隐藏或 reduced motion 开启时，不得持续占用动画帧。
- 不使用实时阴影、环境贴图、模型加载、视频纹理、OrbitControls 或每帧创建对象。

## 9. 响应式规则

| 视口 | 场景策略 | 工作台姿态与镜面 |
| --- | --- | --- |
| 1920px | 完整 Reflector、Bloom、双边缘轨道与网格 | `desktop` 姿态，明显倾斜，完整宽镜面 |
| 1487px | 与桌面一致，适度降低反射分辨率 | `desktop` 姿态，边缘与 DOM 严格对齐 |
| 1200px | 降低 Bloom 半径和网格密度 | `compact` 姿态，镜面收窄且不碰左侧文案 |
| 1024px | 简化光轨，允许关闭 Bloom | `tablet` 姿态，保证标题和工作台无重叠 |
| 390px | DPR 1、无 Bloom、静态单帧、简化镜面 | `mobile` 轻倾斜，镜面只保留底边反射，不横向溢出 |

所有视口均必须满足：页面 `scrollWidth <= clientWidth`；DOM 工作台可读；Hero 装饰层不改变正常文档高度；镜面不得遮挡下一屏标题或 Demo 操作。

## 10. 文件范围建议

后续实现预计限定在以下文件：

- 修改 `docs/web/homepage-prototype/package.json`
- 修改 `docs/web/homepage-prototype/package-lock.json`
- 新建 `docs/web/homepage-prototype/src/components/ThreeHeroScene.jsx`
- 新建 `docs/web/homepage-prototype/src/components/heroThreeScene.js`
- 修改 `docs/web/homepage-prototype/src/components/HeroSection.jsx`
- 修改 `docs/web/homepage-prototype/src/styles/home.css`
- 新建 `docs/web/homepage-prototype/scripts/verify-three-hero.mjs`
- 修改 `docs/web/homepage-prototype/design-qa.md`

依赖只新增 `three`；`EffectComposer`、`RenderPass`、`UnrealBloomPass`、`OutputPass`、`Reflector` 和 `RoundedBoxGeometry` 均从同版本 `three/examples/jsm/` 导入，避免引入第二套后期处理库。

本设计规格任务自身只新增当前文件，不修改上述实现文件，也不执行 Git 提交。

## 11. 验收与测试

### 自动化验证

`scripts/verify-three-hero.mjs` 使用真实浏览器覆盖正常路径、强制 fallback 和响应式：

1. 页面存在真实 `HTMLCanvasElement`，canvas 透明且 `pointer-events: none`。
2. 正常 WebGL2 环境最终出现 `data-three-state="ready"`。
3. `data-three-reflector="ready"` 与 `data-three-neon-rails="ready"` 存在，场景包含镜面和青紫边缘层。
4. `?threeFallback=1` 下进入 `data-three-state="fallback"`，DOM 工作台仍可见且 CTA 可点击。
5. 1920、1487、1200、1024、390px 均无横向溢出、标题与工作台重叠或镜面遮挡下一屏。
6. Tab、CTA、视频和工具卡交互保持原行为；Three canvas 不截获点击和焦点。
7. 页面加载、切换视口、滚动离屏、恢复可见及 fallback 过程中无 `console.error`、page error 或未处理 Promise。
8. reduced motion 下没有持续 RAF 动画，视觉仍保留静态面板、边缘和镜面。

### 结构化与反贴图检查

- `ThreeHeroScene.jsx` 和 `heroThreeScene.js` 不得出现 `TextureLoader`、`CanvasTexture`、`VideoTexture`、`data:image`、base64、参考图文件名或截图路径。
- Hero 相关 CSS 不得使用 `background-image: url(...)` 模拟面板、霓虹或镜面。
- 文本、按钮、卡片、流程和时间线仍为可编辑 DOM；canvas 只承载装饰几何。
- 隐藏 canvas 或触发 fallback 后，Hero 主体信息和所有交互仍完整。
- 删除参考图后页面主体不缺失任何内容。

### 构建与视觉 QA

- `npm run verify:three-hero` 通过。
- 现有 Hero、Demo 和交互验证脚本继续通过。
- `npm run build` 成功，构建无 Three.js 重复版本。
- `design-qa.md` 记录五个目标视口的截图、WebGL 状态、fallback 状态、console 结果、反贴图检查和最终结论。
- 视觉验收重点为：倾斜角可感知、边缘连续高亮、镜面反射可信、霓虹不过曝、DOM 内容清晰、下一屏未被遮挡。

## 12. 风险与处理

- **DOM 无法被 WebGL Reflector 直接反射：** 使用与 DOM 共姿态的程序化面板代理和边缘光轨形成整体剪影反射，不采集 DOM 像素。
- **Bloom 破坏透明 alpha：** 自动或配置式关闭 Bloom，切换为 additive emissive glow，不接受黑色矩形背景。
- **DOM 与场景边缘漂移：** 以共享姿态常量和实时 `getBoundingClientRect()` 为唯一对齐依据，禁止手写两套角度和偏移。
- **多次挂载导致 WebGL context 泄漏：** 销毁路径统一释放 composer、Reflector、geometry、material、renderer、监听器和 RAF。
- **低性能设备掉帧：** DPR 上限、移动端静态单帧、离屏暂停、低分辨率反射和无 Bloom 共同降级。
- **Three.js 改动破坏 Demo：** 最终整页回归验证工具 Tab、三个独立工作台、案例卡片和响应式，不把 Demo 组件纳入场景层。

## 13. 规格自检

- 已覆盖 3D 透视、镜面、边缘高亮、透明合成、DOM 对齐、生命周期、性能、响应式、fallback 和测试。
- Three.js 职责限定为程序化装饰几何，未包含截图纹理或完整 3D UI。
- 实现文件范围与“不重做其他页面”的边界一致；Demo 仅做回归验证，不纳入核心改造。
- 正常路径、低性能路径、reduced motion 与无 WebGL2 路径均有明确行为。
- 文档不存在待补字段、占位实现或未决架构分支。
