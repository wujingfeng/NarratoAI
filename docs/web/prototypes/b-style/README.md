# 影创工坊 B 风格原型设计资产

本目录保存第一版 Web 产品的高保真视觉原型。视觉方向统一为：深黑专业工作台、青蓝主霓虹、紫色辅助强调、克制橙色混剪语义、厚玻璃面板、轻量 3D 与清晰的任务状态。

设计依据：

- `../../docs/ai-video-tools-requirements-v1.md`
- `../../docs/mvp-scope-2-week-validation.md`
- `../../docs/product-page-design-plan-v1.md`

## 1. 完整页面清单

### 1.1 官网与转化

| 编号 | 页面/状态 | 设计稿 |
|---|---|---|
| 01 | 官网 Hero 首屏 | `01-home-hero-desktop.png` |
| 02 | 价格页 | `02-pricing-desktop.png` |
| 31 | 会员订阅价格状态 | `31-membership-pricing-desktop.png` |
| 03 | 登录/注册页 | `03-login-desktop.png` |
| 25 | 首页案例 Demo 区 | `25-home-demo-desktop.png` |
| 26 | 首页能力、流程、FAQ 与最终 CTA | `26-home-capabilities-cta-desktop.png` |
| 27 | 官网移动端首屏 | `27-home-mobile.png` |

### 1.2 工作台公共页面

| 编号 | 页面/状态 | 设计稿 |
|---|---|---|
| 04 | 工作台概览 | `04-dashboard-desktop.png` |
| 05 | 新建创作/上传与排序 | `05-new-creation-desktop.png` |
| 06 | 我的项目 | `06-projects-desktop.png` |
| 13 | 项目结果/导出 | `13-project-result-desktop.png` |
| 14 | 创作点与会员 | `14-credits-membership-desktop.png` |
| 15 | 设置/创作偏好 | `15-settings-desktop.png` |
| 21 | 视频生成中 | `21-rendering-desktop.png` |
| 24 | 生成失败详情 | `24-project-failure-desktop.png` |

### 1.3 短剧解说流程

主路径：上传素材 → 设置参数 → AI 分析 → 编辑片段 → 解说文案 → 配音字幕 → 生成 → 导出。

| 步骤 | 页面/状态 | 设计稿 |
|---|---|---|
| 1 | 上传素材 | `05-new-creation-desktop.png` |
| 2 | 解说风格、比例、配音与字幕默认值 | `07-narration-settings-desktop.png` |
| 3 | 剧情理解与高光分析 | `08-narration-analysis-desktop.png` |
| 4 | 高光片段审核、裁剪与排序 | `16-narration-clips-desktop.png` |
| 5 | 解说文案审核与 AI 改写 | `17-narration-copy-desktop.png` |
| 6 | 配音、字幕与 BGM 设置 | `18-narration-voice-subtitle-desktop.png` |
| 汇总 | 高级编辑器总览状态 | `09-narration-editor-overview-desktop.png` |
| 7 | 生成中 | `21-rendering-desktop.png` |
| 8 | 结果与导出 | `13-project-result-desktop.png` |

### 1.4 视频翻译流程

主路径：上传素材 → 翻译设置 → 字幕校对 → 配音合成 → 生成 → 导出。

| 步骤 | 页面/状态 | 设计稿 |
|---|---|---|
| 1 | 上传素材 | `05-new-creation-desktop.png` |
| 2 | 源语言、目标语言、配音、字幕与原字幕处理 | `10-translation-settings-desktop.png` |
| 3 | 双语字幕逐句校对 | `11-translation-subtitle-editor-desktop.png` |
| 4 | 翻译配音与双语字幕同步 | `19-translation-dubbing-desktop.png` |
| 5 | 生成中 | `21-rendering-desktop.png` |
| 6 | 结果与导出 | `13-project-result-desktop.png` |

### 1.5 短剧混剪流程

主路径：上传素材 → AI 提取高光 → 编辑片段与 BGM → 生成 → 导出。

| 步骤 | 页面/状态 | 设计稿 |
|---|---|---|
| 1 | 上传素材 | `05-new-creation-desktop.png` |
| 2 | AI 高光分析、评分与去重 | `20-remix-analysis-desktop.png` |
| 3 | 片段裁剪、排序、保留原声与 BGM | `12-remix-editor-desktop.png` |
| 4 | 生成中 | `21-rendering-desktop.png` |
| 5 | 结果与导出 | `13-project-result-desktop.png` |

混剪设计中不提供解说文案、AI 配音和字幕轨道。

### 1.6 关键弹窗与异常状态

| 编号 | 页面/状态 | 设计稿 |
|---|---|---|
| 22 | 生成前消耗确认 | `22-generation-confirm-modal-desktop.png` |
| 23 | 创作点不足与购买引导 | `23-insufficient-credits-modal-desktop.png` |
| 24 | 失败原因、步骤、日志与自动退还 | `24-project-failure-desktop.png` |
| 32 | 购买创作点支付确认 | `32-payment-checkout-modal-desktop.png` |
| 33 | 购买成功与返回原项目 | `33-purchase-success-modal-desktop.png` |

### 1.7 移动端代表页面

第一版移动端支持官网浏览、基础创建、项目查看和任务状态；复杂片段编辑建议桌面端完成。

| 编号 | 页面/状态 | 设计稿 |
|---|---|---|
| 27 | 官网首页 | `27-home-mobile.png` |
| 28 | 工作台概览 | `28-dashboard-mobile.png` |
| 29 | 新建创作/上传与排序 | `29-new-creation-mobile.png` |
| 30 | 任务生成状态 | `30-rendering-mobile.png` |

## 2. 核心交互约束

1. 用户可上传一集或多集视频，并在上传后拖动排序。
2. 未上传字幕时自动使用 ASR，页面必须明确显示识别状态。
3. 第一版仅提供高级模式，但所有复杂参数都有默认值和清晰的继续按钮。
4. 短剧解说片段和短剧混剪片段不可发生时间重叠。
5. 视频翻译必须重新配音，翻译字幕自动避让原字幕；检测不到原字幕时默认放底部。
6. 短剧混剪只包含片段、原声和 BGM，不出现解说、配音和字幕功能。
7. 提交生成前透明展示预计创作点消耗；余额不足时保留素材和设置。
8. 任务页展示步骤状态、失败原因与日志；第一版不提供通知功能。
9. 平台原因导致生成失败时，页面展示创作点自动退还结果。
10. 用户购买后，除固定充值入口和权益不足提示外，不再展示额外营销横幅。

## 3. 视觉使用说明

- `00-style-direction-board.png` 是整体视觉方向参考，不作为单独业务页面。
- 桌面稿以 1440 宽产品视口为设计基准；移动端以 390 宽为设计基准。
- 官网允许更强的 3D、霓虹和地面反射；工作台降低装饰光效，优先保证信息密度与可操作性。
- 实施阶段的最终文案、字段和数值以三份需求文档为准，原型图用于布局、层级、状态和视觉语言对齐。

## 4. MVP 覆盖结论

当前 33 张页面/状态稿已经覆盖：官网获客、积分包与会员价格、登录、支付与到账、上传创建、三类工具完整主流程、项目管理、生成进度、结果导出、创作点、设置、额度不足、生成失败与移动端代表场景。
