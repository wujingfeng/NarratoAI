# 解说多轨编辑器：设计说明

**日期**：2026-07-15  
**目标项目**：`docs/web/homepage-prototype`（Vite + React 原型）  
**参考**：`docs/web/prototypes/b-style/09-narration-editor-overview-desktop.png`

## 1. 目标与范围

在分析页后新增沉浸式桌面编辑器路由 `/dashboard/narration/editor`，完成可交互的四轨解说剪辑工作台：视频、高光解说文本、配音、背景音乐。分析页的“编辑片段”入口进入该路由。

首期交付的是前端原型：真实占位媒体可播放、音频有真实波形与区段、轨道可选中/拖动/框选/缩放/拖动播放头，文案与字幕片段联动；不做后端持久化、真实 TTS、服务端渲染导出、自由叠层、关键帧或任意轨道增删。

## 2. 结构、视觉与响应式

- **顶部工作台栏**：返回分析、项目名、保存状态、撤销/重做、保存草稿、生成视频（演示反馈）。
- **左侧高光片段栏**：片段编号、缩略图、时长与评分；点击选择、定位播放头和轨道片段。
- **中间预览区**：9:16 视频、播放/暂停、跳转、倍速、音量、当前字幕；播放头为唯一时间源。
- **右侧检查器**：解说文案编辑、字数、配音角色/语速/音量、字幕开关、BGM 音量等固定配置。
- **底部时间轴**：标尺、视频/文案/配音/BGM 四条固定轨、滚动容器、播放头、选区、缩放控制。

视觉延续已有深色蓝黑和紫蓝主操作：面板以深色实色/渐变、细边框和选中紫色光晕构成；视频轨显示可用视频帧缩略图，解说轨使用紫色块，配音使用青色波形，BGM 使用橙色波形。桌面断点 `>=1280px` 为完整三栏；`1024–1279px` 收窄左栏并折叠检查器；小于 `1024px` 显示只读桌面端提示。

**还原约束**：所有文本、轨道、波形、控制器均为 DOM/SVG/CSS 可编辑结构；严禁将参考截图、截图切片、base64/data URL、canvas 绘制截图或 SVG 内嵌位图作为页面主体。删除参考图后页面必须完全可用。

## 3. 交互与同步

- 全局 `playhead`（秒）为唯一时间源；预览 `<video>.currentTime`、标尺竖线、当前字幕和激活片段同步。
- 点击左栏、视频轨、文案轨或配音轨均选择同一 `segmentId` 并跳至片段起点；右侧检查器显示其文案和参数。
- 拖动片段改变 `start`，裁切手柄改变 `start/duration`；保持固定轨、无重叠、吸附到相邻边界/整秒，最小长度设限。
- 使用 `@dnd-kit/core` / `@dnd-kit/sortable` 与 Pointer Events 实现片段拖拽；框选使用 `@dnd-kit` 的选择状态与自研矩形命中，支持 Shift 多选，不跨轨重排。
- 滚轮 + 修饰键调整 `pixelsPerSecond`，以鼠标下时间点为缩放锚点；横向滚动不改变真实时间数据。
- 以 Wavesurfer 的 Regions 插件加载配音/BGM，区段对应时间轴音频 clip；波形点击/区域拖动同步 `playhead`，播放时通过 Wavesurfer/Web Audio 与视频时间对齐。原型只需单路试听和音量 UI，不承诺浏览器多源混音精度。
- 撤销/重做只在拖拽、裁切、文案提交等完成操作入栈；生成视频仅显示原型 toast/状态。

## 4. 数据模型

时间以秒保存，像素只由 `pixelsPerSecond` 推导：`left = start * pixelsPerSecond`、`width = duration * pixelsPerSecond`。

```ts
type TrackId = 'video' | 'script' | 'voice' | 'bgm';
type TimelineClip = {
  id: string; segmentId?: string; trackId: TrackId;
  start: number; duration: number;
  sourceStart?: number; sourceDuration?: number;
  assetId?: string; text?: string;
  volume?: number; rate?: number; regionId?: string;
};
type EditorState = {
  activeClipIds: string[]; playhead: number; isPlaying: boolean;
  pixelsPerSecond: number; clips: TimelineClip[];
  voiceRole: string; bgmVolume: number;
};
```

视频预览映射：定位覆盖 `playhead` 的视频 clip，计算 `sourceStart + (playhead - clip.start)`；无覆盖片段时暂停并显示占位状态。

## 5. 占位素材与处理

允许将下列用户指定、本地可用媒体复制到项目内的受版本控制或明确忽略的原型素材目录（推荐 `public/media/narration-editor/`）：

- `古墓迷宫震全球1.mp4`、`古墓迷宫震全球2.mp4`、`古墓迷宫震全球3.mp4`：三个视频片段；
- `0e5bf3db017e0e593c4eef4144d7c68a.mp3`：配音或 BGM 波形；
- `古墓迷宫震全球3.srt`：解析为结构化字幕 cue，预览和文本轨使用。

复制后用 `ffprobe` 读取时长；以视频帧或 CSS 占位生成缩略图（缩略图属于真实媒体资产例外），不得以参考设计图代替。Wavesurfer 对真实 mp3 直接加载；若音频过长，后续由后端预计算 peaks，首期不阻塞。

## 6. 验收

1. 分析页能进入 `/dashboard/narration/editor`，无控制台错误。
2. 四固定轨、标尺、真实媒体预览、字幕、片段选择与右侧编辑完整可见。
3. 视频/文案/配音/BGM 片段可选择、拖动、裁切、框选；时间轴缩放、横向滚动、播放头同步正确。
4. 配音/BGM 均显示 Wavesurfer 波形；至少一个 Regions 音频区段可点选/拖动并与时间轴同步。
5. 在 `1440px` 宽度截图下视觉结构贴近参考；窄屏按降级策略工作。
6. 自动化验证覆盖路由、关键 DOM、拖拽/框选与播放头同步；构建通过。
7. 交付前检索确认没有参考截图被页面引用、没有 `data:image`、base64、canvas 截图或内嵌 bitmap 伪造主体。
