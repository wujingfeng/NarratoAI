# B 风格首页高保真原型｜Design QA

- 验收日期：2026-07-13
- 验收范围：独立 React/Vite 首页原型
- 本地地址：`http://127.0.0.1:4173/`
- 最终结论：P0 无、P1 无、P2 无

## 1. 视觉基准

### 参考源图

- Hero：`../prototypes/b-style/01-home-hero-desktop.png`
- 案例区：`../prototypes/b-style/25-home-demo-desktop.png`
- 能力与 CTA：`../prototypes/b-style/26-home-capabilities-cta-desktop.png`
- 移动首屏：`../prototypes/b-style/27-home-mobile.png`

### 最终实现截图

- `artifacts/screenshots/browser-hero-desktop-1487-final.png`
- `artifacts/screenshots/browser-demo-desktop-1487-final.png`
- `artifacts/screenshots/browser-capabilities-desktop-1487-final.png`
- `artifacts/screenshots/browser-hero-mobile-390-final.png`

### 最终并排比对

- `artifacts/comparisons/final/hero-source-vs-final.png`
- `artifacts/comparisons/final/demo-source-vs-final.png`
- `artifacts/comparisons/final/capabilities-source-vs-final.png`
- `artifacts/comparisons/final/mobile-source-vs-final.png`

比对图均为“左侧参考、右侧实现”。它们只用于 QA，不被运行时代码引用。

## 2. 视口、状态与布局证据

| 场景 | 视口 | 状态 | 最终证据 |
|---|---:|---|---|
| 桌面 Hero | 1487×1058 | `#hero`、默认短剧解说 | 工作台约 `x=506–1444`、`y=84–787`；利益点 `y=805–900`；`scrollWidth=1487` |
| 桌面案例区 | 1487×1058 | `#demo` | 标题、三工具 Tab、工作台与 3 张案例卡均在同一视口完整呈现 |
| 桌面能力区 | 1487×1058 | `#capabilities` | 三能力卡、五步流程、FAQ 与最终 CTA 无裁切、重叠或横向溢出 |
| 移动 Hero | 390×844 | `#hero` | 工作台约 `y=431–726`，利益点约 `y=744–840`；`scrollWidth=390` |

聚焦区域同时检查了：Hero 3D 倾角与霓虹边缘、Demo 三栏工作台、能力卡与流程条、移动端工作台重排。最终对比未发现可执行的视觉 P0/P1/P2。

## 3. 比对与修正历史

1. **初版发现**
   - 桌面工作台偏右且纵向偏短。
   - Demo 与能力区整体偏低，1058px 视口内容不够完整。
   - 移动工作台偏高，利益点行被视口底部截断。
2. **第一轮修正**
   - 提升 Hero 文案层级，恢复完整产品说明。
   - 加强 `rotateY / rotateX / rotateZ` 3D 倾角与青紫霓虹边缘。
   - 压缩 Demo、能力区和移动端首屏间距。
3. **第二轮修正**
   - 桌面工作台左移并增高，保持顶部约 84px、底部约 787px。
   - Demo/能力区上移，使主要内容在 1487×1058 视口完整呈现。
   - 移动工作台压到约 295px 高，利益点完整进入 390×844 视口。
4. **语义与体验收口**
   - 三工具的预览标签、文案、时长和弹窗数据完全隔离。
   - 混剪固定为 `00:45`，仅呈现高光、原声、BGM、节奏与转场，不出现旁白、配音或字幕输出语义。
   - 修复 Tab 键盘模式、弹层背景隔离、焦点循环/恢复与 Toast 隔离。
   - 4 张大内容图转换为 WebP，`dist` 从约 7.9MB 降至 924KB。

## 4. 交互验收

- 三工具 Tab：鼠标切换通过；`ArrowLeft / ArrowRight / Home / End` 通过；roving `tabIndex`、`aria-controls`、`tabpanel` 通过。
- 视频翻译：切换后显示多语言、翻译配音和双语字幕信息。
- 短剧混剪：面板和弹窗均为 `00:45`；禁用语义扫描结果为空；保留原声与 BGM 信息存在。
- before/after 滑杆：值从 `52` 更新到 `67`，受控状态正常。
- 案例弹层：打开、播放/暂停、动态时长、Escape 关闭、焦点循环、关闭后返回触发按钮均通过。
- 弹层背景：Header/Main/Footer 均设置 `inert + aria-hidden`；关闭后属性恢复。
- 移动菜单：首焦点、Tab/Shift+Tab 循环、Escape 关闭、焦点返回菜单按钮通过；Main/Footer 与页头背景隔离通过。
- FAQ：展开状态、`aria-expanded` 与答案内容通过。
- CTA/模板按钮：Toast 文案通过；无消息时 Toast 不渲染；Modal/菜单打开时 Toast 隔离，且 z-index 低于 Modal。
- 最终干净浏览器标签页：console error/warning 为 `[]`。
- 图片资源：所有运行时图片 `complete=true` 且 `naturalWidth>0`，broken image 列表为空。

## 5. 结构化重建与反贴图 Gate

- Logo、导航、Hero 工作台、流程节点、成片预览、工具卡、时间线、波形、Tab、对比滑杆、能力卡、FAQ、CTA 与弹层均为真实 DOM/CSS/语义控件。
- 运行时代码未使用参考截图、局部截图、base64、`canvas`、内嵌位图 SVG 或 `background-image: url(...)` 还原 UI。
- 扫描命令：

```bash
rg -n "data:image|base64|/baseline/|b-style/|canvas|docs/web/prototypes|background-image\\s*:\\s*url" src public index.html
```

- 扫描结果：零命中。
- 删除参考源图后，首页主体与交互不受影响；运行时没有任何参考图依赖。

## 6. 内容图像例外

以下仅作为剧情海报、视频帧或案例封面，不承载按钮、面板、文字或交互结构：

- `public/assets/hero-drama-vertical.webp`
- `public/assets/documentary-thumb.webp`
- `public/assets/film-action-thumb.webp`
- `public/assets/short-drama-thumb.webp`
- `public/assets/d01/sample-urban.png`
- `public/assets/d06/romance.png`

高分辨率 PNG 源文件归档在 `artifacts/content-source-assets/`，不进入运行时构建。

## 7. 构建与最终审查

- `npm run build`：通过，4581 modules，Vite 构建成功。
- `git diff --check -- docs/web/homepage-prototype`：通过。
- 运行时反贴图扫描：通过。
- 最终 `dist`：924KB。
- 独立只读审查：P0 无、P1 无、P2 无，结论 PASS。

final result: passed
