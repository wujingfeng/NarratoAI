# B 风格官网首页视觉规格

## 0. 实现基准

- **桌面设计宽度：1440px**；内容容器 `max-width: 1344px; margin:auto; padding-inline:48px`。
- **移动设计宽度：390px**；`padding-inline:24px`。
- 视觉基调：`深黑空间 + 青蓝主霓虹 + 紫色次强调 + 橙色混剪语义 + 半透明玻璃面板`。
- 允许真实图片：Logo、人物头像、视频封面/缩略图、三张 3D 工具插画。  
  **四张原型 PNG 仅作参考，不得进入页面或作为背景。**

---

## 1. 页面分区与尺寸

### 01 首页 Hero（桌面）

**首屏高度：** `min-height: 880px`；导航 `80px`，Hero 主体约 `760px`。

| 区域 | 建议尺寸 / 比例 | 间距 |
|---|---:|---:|
| 顶部导航 | `height:80px`，左右 `56px` | Logo / 中部导航 / 登录三段布局 |
| Hero 左文案 | `width: 38%`，约 `440px` | 顶部距导航 `115px` |
| Hero 右工作台 | `width: 62%`，约 `830px` | 与左列间距 `24px`；可向右溢出 `16~32px` |
| 标签 | `height:38px`，圆角 `20px` | 标题上 `34px` |
| 标题组 | 两行，约 `50px + 72px` 字级 | 行间 `10px` |
| 描述 | `20px / 1.65` | 标题后 `22px` |
| CTA 行 | 主次按钮各 `226×64`、`156×64` | 按钮间距 `18px` |
| Hero 底部卖点 | `height:96px`，4 等分 | 顶部距主视觉 `14px` |

**右侧工作台：**
- 外框约 `900×680px`，`transform: perspective(1800px) rotateY(-5deg) rotateX(1deg)`。
- 内部：左 AI 流程 `31%`、中视频 `31%`、右功能卡 `32%`，间距 `12px`；下方时间线独占约 `30%` 高度。
- 整体不可用一张工作台截图；流程、视频容器、功能卡、时间线、波形均需独立 DOM 结构。

---

### 25 案例 Demo（桌面）

**结构：标题区 + 演示工作台 + 案例切换卡。**

```css
.demo-section { padding: 24px 48px 72px; }
.demo-shell { max-width: 1344px; min-height: 580px; padding: 22px; }
```

| 区域 | 比例 / 建议值 |
|---|---|
| 标题区 | 标题距顶部 `26px`；副标题距标题 `10px` |
| 工具 Tab | 三等分，单项高 `58px`，间距 `32px` |
| 主 Demo 工作台 | `height:460px`；内边距 `16px` |
| 左步骤列 | `26%` |
| 中视频对比器 | `44%`，保持 `16 / 9`，画面内部用真实 poster/video |
| 右 AI 摘要列 | `28%` |
| 底部案例卡 | 三列，`height:150px`，间距 `20px` |

中间视频需要真实的“原始素材 / 最终成片”对比结构：`clip-path` 或可拖动 divider；不要把左右对比烘焙进一张图片。

---

### 26 能力、流程、FAQ、CTA（桌面）

```css
.capability-section { padding: 36px 48px 28px; }
.capability-grid { grid-template-columns: repeat(3, 1fr); gap: 24px; }
```

| 区域 | 建议尺寸 |
|---|---|
| 主标题 | `44px/1.2`，底部 `30px` |
| 三能力卡 | 单卡约 `calc((100% - 48px)/3) × 324px` |
| 流程条 | `height:154px`，上方 `26px` |
| FAQ + CTA | 左 `45%` / 右 `55%`，间距 `24px`，上方 `22px` |
| FAQ 行 | `height:46px`，行间 `7px` |
| CTA 面板 | `min-height:264px` |
| Footer | 顶边距 `28px`，高度 `106px` |

三卡内部：
- Icon：`62×62px`；
- 标题：`30px/1.2`；
- 副标题：`19px`；
- 能力点：`14px`；
- 按钮：`154×45px`；
- 右上/右侧 3D 插画占卡片约 `47%`，文字不可被插画遮挡。

流程条采用 5 个真实步骤节点，连接线为 CSS 渐变虚线；不要做成一张流程图。

---

### 27 首页 Hero（移动）

**移动首屏目标高度：** `min-height: 844px`。顺序从“左文右图”改成“文案 → CTA → 工作台 → 2 个卖点”。

| 区域 | 建议值 |
|---|---|
| Header | `height:68px; padding: 16px 24px` |
| Logo | 高 `34px`；名称 `28px` |
| 登录 | `82×42px` |
| 菜单 | `32×32px`；隐藏桌面导航 |
| 标签 | 顶部约 `88px`，`height:30px`，单行省略 |
| 主标题 | 上方 `50px`；第一行 `34px/1.35`，渐变行 `52px/1.1` |
| 描述 | `18px/1.7`，居中，标题后 `22px` |
| CTA | 主按钮 `342×52px`，次按钮同宽，间距 `13px` |
| 工作台 | 顶部 `34px`；宽 `calc(100vw - 28px)`，高约 `340px` |
| 底部卖点 | 仅保留前 2 项，双列；顶距 `28px` |

移动工作台仍保留：左分析列、中竖屏预览、右三张功能卡；隐藏桌面版的时间线、积分、头像、复杂状态。卡片与文案可缩减，**不能直接将桌面工作台等比缩小**。

---

## 2. 字体层级

```css
--font-sans: "PingFang SC", "Noto Sans SC", "Microsoft YaHei", sans-serif;
```

| Token | 桌面 | 移动 | 用途 |
|---|---:|---:|---|
| `--text-hero-lead` | `48px/1.25/700` | `34px/1.35/700` | “专为自媒体…” |
| `--text-hero-display` | `72px/1.1/800` | `52px/1.1/800` | “AI 出片工作台” |
| `--text-section` | `44px/1.2/700` | `32px/1.25/700` | 区块标题 |
| `--text-card-title` | `30px/1.25/700` | `23px/1.3/700` | 工具卡标题 |
| `--text-body` | `18px/1.7/400` | `17px/1.65/400` | Hero 描述 |
| `--text-nav` | `15px/1/500` | — | 导航 |
| `--text-meta` | `13px/1.45/400` | `12px/1.4/400` | 标签、步骤、辅助说明 |

标题使用 `letter-spacing: .01em`；正文 `letter-spacing: .02em`。中文不得使用过紧字距或纯英文 UI 字体替代。

---

## 3. 颜色与表面 Token

```css
:root {
  --bg-page: #02050D;
  --bg-deep: #040914;
  --panel: rgba(7, 16, 31, .78);
  --panel-strong: rgba(8, 19, 38, .92);
  --text-primary: #F5F7FF;
  --text-secondary: #B8C1D2;
  --text-muted: #75839A;

  --cyan: #2FCBFF;
  --blue: #397CFF;
  --violet: #8C3DFF;
  --magenta: #D83DFF;
  --orange: #FF951F;

  --line-subtle: rgba(126, 179, 255, .20);
  --line-cyan: rgba(63, 185, 255, .72);
  --line-violet: rgba(177, 84, 255, .72);
}
```

- 主标题渐变：`linear-gradient(100deg, #D93BFF 0%, #8057FF 38%, #2BCFFF 100%)`。
- 主 CTA：`linear-gradient(100deg, #C53DFF 0%, #5F58FF 48%, #2FCBFF 100%)`。
- 紫 / 蓝 / 橙三工具卡必须保持明确语义，不要将橙色泛化到其他模块。

---

## 4. 边框、玻璃、光晕、3D

```css
.glass-panel {
  background:
    linear-gradient(145deg, rgba(20, 35, 65, .76), rgba(4, 10, 21, .86));
  border: 1px solid rgba(105, 168, 255, .34);
  box-shadow:
    inset 0 1px 0 rgba(225, 243, 255, .10),
    0 24px 60px rgba(0, 0, 0, .42);
  backdrop-filter: blur(14px);
}

.neon-frame {
  box-shadow:
    0 0 0 1px rgba(79, 170, 255, .65),
    0 0 14px rgba(48, 154, 255, .72),
    0 0 42px rgba(92, 65, 255, .36),
    12px 14px 42px rgba(163, 43, 255, .28);
}
```

- 大面板圆角：`20px`；中卡：`14px`；按钮：`10~12px`；标签：`999px`。
- 光晕采用**窄边高亮 + 大范围低透明度散射**，不要对整个卡片使用重阴影。
- 背景网格用 CSS：`repeating-linear-gradient`，透视 `perspective(900px) rotateX(62deg)`；透明度 `0.18~0.28`。
- Hero 主工作台、地面网格、倒影必须分层。倒影可用伪元素 + `mask-image` 渐隐，不可贴整图。
- 低端设备禁用 `backdrop-filter` 与持续大面积 blur，保留边框和渐变即可。

---

## 5. 可复用组件清单

1. `SiteHeader`：Logo、桌面导航、登录、移动菜单。
2. `GradientText`：标题渐变字。
3. `PrimaryCTA` / `SecondaryCTA`：带箭头、播放图标两种变体。
4. `GlassPanel`：`default / cyan / violet / orange / elevated`。
5. `ToolTab`、`ToolCapabilityCard`。
6. `NeonWorkbenchFrame`：仅负责外框、透视、光晕。
7. `AnalysisStepList`：步骤、状态、连接线。
8. `VideoPoster` / `BeforeAfterViewer`：真实视频或 poster、进度条、控制按钮。
9. `FeatureShortcutCard`：三色功能入口。
10. `TimelineTrack`：轨道、缩略图、字幕段、波形、播放头。
11. `BenefitItem`：图标、标题、副文案。
12. `ProcessStepper`：五步骤流程节点。
13. `FaqAccordion`。
14. `FinalCtaPanel`。
15. `SiteFooter`。

---

## 6. 真实图像资产清单与边界

| 资产 | 建议规格 | 可否图片 |
|---|---|---|
| 品牌 Logo | SVG，含图标与中文名称 | 可以，矢量 |
| Hero / Demo 主视频封面 | 竖版 `9:16`，至少 `720×1280` | 可以 |
| Demo 对比视频素材 | 左右使用同源原始画面、成片画面 | 可以，视频/图片 |
| 时间线缩略图 | 从同一视频抽帧，`160×90` 或 WebP | 可以 |
| 三张案例卡封面 | `16:9`，至少 `640×360` | 可以 |
| 用户头像 | `80×80` 或更高 | 可以 |
| 三个 3D 工具插画 | 独立透明 WebP/PNG，约 `420×300` | 可以，属于插画资产 |
| 图标、箭头、播放、步骤符号 | SVG / CSS | **不应使用位图** |
| 波形、时间线、网格、面板光边 | CSS / SVG / DOM | **不应使用截图** |

**结构化重建边界：**
- 可使用真实封面、人物、头像、产品插画；这些必须是**独立资产**，不是从原型截图裁切出的面板。
- 所有文字、卡片、按钮、工作台列、Tab、进度条、流程节点、FAQ、页脚均以真实可编辑结构实现。
- 删除全部四张参考原型后，页面主体必须完整可用。

---

## 7. 高保真风险

### P1（必须规避）

1. **把 Hero、Demo 工作台或能力卡整块当背景图。**  
   直接失去可编辑性，也无法响应式重排。

2. **移动端仅缩放桌面工作台。**  
   必须删减时间线和低优先级信息，保持“分析—预览—三能力”层级。

3. **Hero 透视错误。**  
   主面板应是轻微左侧近、右侧远的空间感；旋转超过 `6deg` 会造成文字和卡片不可读。

4. **标题换行偏差。**  
   桌面必须保持“专为自媒体小白打造的 / AI 出片工作台”两层；移动保持首行与渐变大标题分离。

5. **把全部紫蓝光效均匀铺满页面。**  
   光源应集中在 CTA、主工作台边缘、工具卡语义色和地面反射；背景必须保留大面积黑色留白。

### P2（明显拉低质感）

1. 玻璃卡变成不透明纯黑或高透明白玻璃，丢失暗色层次。
2. 使用统一蓝色边框，缺少紫/蓝/橙工具语义。
3. 网格太亮、太密，抢夺标题和 CTA；建议格距 `42~56px`。
4. 所有面板使用同一种发光阴影；需区分常规边框、激活状态、主工作台外框。
5. 视频封面裁切错误，人物脸部和竖屏标题区域被截断。
6. FAQ、Footer、流程条在移动端保留桌面密度，导致首屏后阅读困难。
