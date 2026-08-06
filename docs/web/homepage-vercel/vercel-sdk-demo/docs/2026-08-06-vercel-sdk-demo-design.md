# vercel-sdk-demo 设计文档

> 对话式短剧解说工作台 · 可演示 prototype
>
> 起草日期：2026-08-06
> 范围：homepage-vercel 下的独立子目录 `vercel-sdk-demo/`
> 目标：验证"对话式 Agent 驱动短剧解说"交互模式的可行性，端到端跑通 5 阶段流程

---

## 0. 决策摘要

| 决策项 | 选择 | 替代选项 |
|---|---|---|
| 范围 | 独立子目录 `vercel-sdk-demo`（0→1 新建） | 改造 homepage-vercel 全部 7 个页面（评估为难度过高） |
| 集成程度 | 前端 + 后端 + LLM 全接 | 纯前端 mock / 仅接 LLM |
| LLM Provider | 任意 OpenAI 兼容 API（用户自配 API Key） | OpenAI / Anthropic / 国内模型单选 |
| 后端业务能力 | 内嵌 Hono Mock Server（Vite 插件同进程） | 对接现有 narratoApi + coreApi / 双模式可切换 |
| 主布局 | 三栏：左 Chat + 中 Preview + 右 Inspector | 左 Chat + 右 Preview / 全屏对话 |
| Inspector 形式 | 分组卡片折叠列表 | Tab 切换详情面板 / 时间线为主 |
| 视觉风格 | 复用 B 风格（深色霓虹），继承现有 design tokens | OpenChatCut 极简专业灰 / Claude.ai 暖白柔光 |
| LLM 行为控制 | 预设剧本演示（system prompt 引导） | 半开放 / 完全开放 |
| Agent 工具数 | 11 个（覆盖 5 阶段，音色无试听） | 12（含 preview_voice 试听）/ 8（最小集） |
| 音色呈现 | 纯文字占位（name+gender+age+tone），无试听音频 | 复用现有 voice-list.txt 真实 sample / TTS mock 生成 |
| LLM 输出语言 | 中文（与界面一致，prompts.ts 显式约束） | 英文 |

---

## 1. 架构总览

### 1.1 三层架构

```
┌────────────────────────────────────────────────────────────────┐
│  浏览器 (Vite dev server :5173)                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  React 19 + Vercel AI SDK 7 + @ai-sdk/react              │  │
│  │                                                          │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐                  │  │
│  │  │  Chat    │ │ Preview  │ │Inspector │   ←  三栏布局      │  │
│  │  │  Panel   │ │  Panel   │ │  Cards   │                  │  │
│  │  └──────────┘ └──────────┘ └──────────┘                  │  │
│  │       ↑           ↑            ↑                          │  │
│  │       └───────────┴────────────┘                          │  │
│  │                  │ useChat + tools                        │  │
│  └──────────────────┼───────────────────────────────────────┘  │
└─────────────────────┼──────────────────────────────────────────┘
                      │ fetch + SSE (tool calls)
┌─────────────────────┼──────────────────────────────────────────┐
│  同进程 Hono Mock Server (Vite plugin)                          │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  /api/projects    (CRUD)                                  │  │
│  │  /api/upload      (multipart)                             │  │
│  │  /api/analyze     (plot analysis)                         │  │
│  │  /api/script      (generate / edit)                       │  │
│  │  /api/voices      (list / preview)                        │  │
│  │  /api/render      (start / status)                        │  │
│  │  /api/export      (jianying draft)                        │  │
│  │                                                          │  │
│  │  /api/chat        (LLM proxy + tool execution)           │  │
│  └──────────────────────────────────────────────────────────┘  │
│  in-memory 数据 + JSON fixtures + 内置任务调度器                  │
└─────────────────────┬──────────────────────────────────────────┘
                      │ HTTPS (OpenAI 兼容协议)
                      ▼
              外部 LLM (用户自配 API Key)
```

### 1.2 关键设计取舍

1. **Hono 通过 Vite 插件同进程跑**：避免双进程启动，1 条 `npm run dev` 跑通全栈。
2. **LLM 走独立 `/api/chat` 端点**：前端不直接持有 LLM API Key，密钥只进 mock server 环境变量。
3. **Mock 数据用 in-memory + JSON fixtures**：重启 demo 数据归零（可接受），演示完不留脏数据。
4. **进度轮询用 SSE**：分析/渲染阶段用 Server-Sent Events 推送进度，前端实时显示。
5. **前端工具执行 + 服务端 mock 协作**：LLM 决策 → 前端 useChat 接 tool_call → 前端 fetch mock API → 订阅 SSE → 写回 store → addToolResult 回 LLM。这样 mock 数据进出完全可观测。

### 1.3 不做的事

- ❌ 不接现有 narratoApi / coreApi 后端
- ❌ 不做用户认证
- ❌ 不做计费
- ❌ 不做多项目/多会话管理
- ❌ 不做撤销/重做
- ❌ 不做多语言 UI（仅中文）
- ❌ 不做 OpenChatCut 风格的视频精修时间线

---

## 2. 目录结构

```
docs/web/homepage-vercel/vercel-sdk-demo/
├── .env.example                       # OPENAI_API_KEY / BASE_URL / MODEL
├── .gitignore
├── README.md
├── package.json
├── tsconfig.json
├── vite.config.mjs                    # Vite + React + Hono 插件
├── index.html
│
├── public/
│   ├── favicon.svg
│   └── media/                         # 演示用视频/音频
│       ├── episode-1.mp4
│       ├── episode-2.mp4
│       └── episode-3.mp4
│
├── src/                               # 客户端
│   ├── main.tsx
│   ├── App.tsx
│   ├── pages/
│   │   └── WorkbenchPage.tsx          # 单页工作台（承载三栏）
│   ├── components/
│   │   ├── chat/                      # 左栏
│   │   │   ├── ChatPanel.tsx
│   │   │   ├── ChatMessage.tsx
│   │   │   ├── ToolCallCard.tsx       # Agent 调工具的卡片
│   │   │   ├── ScriptSegmentCard.tsx  # 脚本段落内联编辑
│   │   │   ├── ChatComposer.tsx       # 输入框（+附件+建议提示）
│   │   ├── preview/                   # 中栏
│   │   │   ├── PreviewPanel.tsx
│   │   │   ├── VideoPlayer.tsx
│   │   │   ├── RenderProgress.tsx     # SSE 进度条
│   │   │   └── ArtifactList.tsx       # 产物清单
│   │   ├── inspector/                 # 右栏（折叠卡片列表）
│   │   │   ├── InspectorPanel.tsx
│   │   │   ├── ProjectInfoCard.tsx
│   │   │   ├── PlotAnalysisCard.tsx
│   │   │   ├── ScriptSegmentsCard.tsx
│   │   │   ├── VoiceSelectionCard.tsx # 纯文字音色卡，无 audio 元素
│   │   │   └── RenderStatusCard.tsx
│   │   └── shared/
│   │       ├── Card.tsx
│   │       ├── CollapsibleCard.tsx
│   │       ├── Button.tsx
│   │       └── EmptyState.tsx
│   ├── features/
│   │   ├── agent/
│   │   │   ├── tools.ts               # 工具 schema 定义
│   │   │   ├── prompts.ts             # system prompt + 剧本
│   │   │   └── useWorkbench.ts        # useChat + 工具客户端执行
│   │   └── project/
│   │       ├── types.ts
│   │       └── store.ts               # Zustand 状态
│   ├── styles/
│   │   ├── tokens.css                 # 复用 B 风格 tokens
│   │   ├── workbench.css
│   │   └── chat.css
│   └── lib/
│       └── api.ts                     # fetch 封装 + SSE 订阅
│
├── server/                            # Hono mock server (Vite 插件)
│   ├── index.ts                       # Vite 插件入口
│   ├── routes/
│   │   ├── chat.ts                    # /api/chat (LLM 代理 + tool 路由)
│   │   ├── projects.ts
│   │   ├── upload.ts
│   │   ├── analyze.ts
│   │   ├── script.ts
│   │   ├── voices.ts
│   │   ├── render.ts
│   │   └── export.ts
│   ├── store/
│   │   ├── memoryStore.ts             # in-memory 数据
│   │   └── jobRunner.ts               # 模拟异步任务（SSE 推送）
│   └── fixtures/
│       ├── sampleAnalysis.json
│       ├── sampleScript.json
│       ├── voiceList.json
│       └── progressScenarios.json
│
├── tests/                             # Vitest
│   ├── tools.test.ts
│   ├── jobRunner.test.ts
│   ├── scriptEditor.test.ts
│   └── components/                    # Testing Library
│       ├── ChatPanel.test.tsx
│       ├── InspectorPanel.test.tsx
│       └── ToolCallCard.test.tsx
│
└── docs/
    ├── 2026-08-06-vercel-sdk-demo-design.md   # 本文件
    └── demo-script.md                 # 5 阶段对话剧本台词
```

---

## 3. Agent 工具集（11 个）

按 5 阶段分组，每工具标注入参、返回、mock 耗时。

| 阶段 | 工具名 | 入参 | 返回 | mock 耗时 |
|---|---|---|---|---|
| **上传** | `upload_video` | `projectId, fileBlob` | `videoId, durationSec, thumbnailUrl` | 1.5s |
| **分析** | `analyze_plot` | `projectId` | `{scenes: [{start,end,summary,keyCharacters}]}` | 4s |
| | `set_narration_style` | `projectId, style: "悬疑\|搞笑\|深情\|冷静"` | `{style}` | 即时 |
| | `set_target_duration` | `projectId, targetSec` | `{targetSec}` | 即时 |
| **脚本** | `generate_script` | `projectId, style, targetSec` | `[{id,start,end,text,tone}]` | 6s |
| | `edit_script_segment` | `projectId, segmentId, newText` | `{segment}` | 2s |
| | `regenerate_segment` | `projectId, segmentId, hint?` | `{segment}` | 3s |
| **音色** | `list_voices` | `language?` | `[{id,name,gender,age,tone}]` | 即时 |
| | `select_voice` | `projectId, voiceId` | `{voiceId}` | 即时 |
| **渲染** | `start_render` | `projectId` | `{renderId}` | 即时 |
| | `track_render_status` | `renderId` | `{stage:"tts\|subtitle\|mixing\|encoding\|done", progress:0-1, artifactUrl?}` | SSE 推送 |

> **不包含 `preview_voice`**：用户选择"纯文字占位"方案，音色候选只显示 name+gender+age+tone，不提供试听音频。

### 3.1 工具设计原则

- **每个工具返回值足够丰富**：前端可基于返回渲染提案卡片（如 `generate_script` 直接返回 5 段脚本）。
- **耗时工具走 SSE 推送进度**：`analyze_plot` / `generate_script` / `start_render`。
- **即时工具直接返回**：配置类、查询类。
- **所有工具都有确定性的 mock 输出**：使用 fixtures 里的固定数据，确保 demo 可重复。
- **所有工具都通过 memoryStore 落地**：前端可观察到状态变化，Inspector 卡片自动重渲染。

---

## 4. 5 阶段对话剧本

每阶段包含：**触发条件**、**Agent 行为**、**建议提示词**、**状态变化**。

### 4.1 阶段 1：上传 → 自动分析

| 项 | 内容 |
|---|---|
| 触发 | 用户拖入视频文件 |
| 用户操作 | 拖入 mp4 文件 或 点 Chat 提示词「帮我分析这 3 集短剧」 |
| Agent 行为 | 调 `upload_video` → 调 `analyze_plot` |
| 工具调用 | `upload_video` (1.5s) → `analyze_plot` (4s) |
| 状态变化 | Inspector 出现「剧情分析」卡片，列出 5-8 个场景分段；中栏视频缩略图出现 |
| 用户可见 | Chat 进度卡片实时显示分析进度 |

### 4.2 阶段 2：配置风格/参数

| 项 | 内容 |
|---|---|
| 触发 | 阶段 1 完成 |
| Agent 主动 | "推荐**悬疑风格**、目标时长 60s，要不要试试？" |
| 建议提示词 | 「改成搞笑风格」/「目标 90 秒」/「目标观众改成中年男性」 |
| Agent 行为 | 调 `set_narration_style` / `set_target_duration` |
| 状态变化 | Inspector「项目信息」卡片实时更新配置 |
| 演示亮点 | 多轮修改可叠加（风格+时长+观众同时设置） |

### 4.3 阶段 3：生成 + 多轮修改脚本

| 项 | 内容 |
|---|---|
| 触发 | 阶段 2 完成 |
| 用户操作 | 点提示词「开始生成脚本」 |
| Agent 行为 | 调 `generate_script` 返回 5 段脚本 |
| 工具调用 | `generate_script` (6s) → SSE 推送 5 段进度 |
| 状态变化 | Inspector 出现「脚本段落」卡片，每段可点击编辑；Chat 中显示 5 段脚本预览 |
| 多轮修改 | 用户：「第 3 段太短了，扩写一下」 → `regenerate_segment` (3s)<br>用户：「把第 1 段第一句改成悬念开场」 → `edit_script_segment` (2s) |
| 演示亮点 | Chat 中的脚本段卡片是**可编辑内联**的，改完自动同步 Inspector |

### 4.4 阶段 4：音色选择

| 项 | 内容 |
|---|---|
| 触发 | 阶段 3 完成 |
| Agent 主动 | "根据悬疑风格，我推荐 3 个男声：morgan（中年低沉）、liuchang（青年沉稳）、qingcang（青年磁性），直接选一个？" |
| 建议提示词 | 「换温柔女声」/「这个男声太年轻了」/「直接用 morgan」 |
| Agent 行为 | 调 `list_voices` → 展示候选卡片 → 用户点选 → 调 `select_voice` |
| 状态变化 | Inspector「音色选择」卡片显示当前选中音色（name+gender+age+tone 纯文字） |
| 演示亮点 | 纯文字音色卡片，无试听音频。Agent 推荐能力 + 用户偏好匹配 |

### 4.5 阶段 5：渲染 + 导出

| 项 | 内容 |
|---|---|
| 触发 | 阶段 4 完成 |
| 用户操作 | 「开始生成」 |
| Agent 行为 | 调 `start_render` → SSE 推送 4 个子阶段进度（TTS→字幕→混音→编码） |
| 状态变化 | 中栏 Preview 切换为渲染进度；完成后显示成片播放器 + 产物清单 |
| 后续 | 「导出剪映草稿」→ `export_jianying`（mock 30s 后返回 .zip） |
| 演示亮点 | 进度条、阶段文字、剩余时间估算三合一 |

---

## 5. 数据流

```
┌──────────────────────────────────────────────────────────────┐
│  ChatPanel 发送消息                                            │
│  useChat({ api: '/api/chat', body: { projectId, messages } }) │
└────────────────────────────┬─────────────────────────────────┘
                             │ POST + SSE
┌────────────────────────────▼─────────────────────────────────┐
│  Hono /api/chat                                              │
│  1. 拼 system prompt + 剧本提示 + 历史 messages               │
│  2. 注入 tools schema (12 个)                                │
│  3. 调 LLM (OpenAI 兼容，stream)                              │
└────────────────────────────┬─────────────────────────────────┘
                             │ stream chunks
┌────────────────────────────▼─────────────────────────────────┐
│  LLM 决策                                                     │
│  ├─ 普通文本 → 直接 stream 给前端                              │
│  └─ tool_call(name, args) → 前端 useChat 接收                │
└────────────────────────────┬─────────────────────────────────┘
                             │ onToolCall
┌────────────────────────────▼─────────────────────────────────┐
│  前端 tool 执行 (useWorkbench.ts)                              │
│  ├─ 调 mock API (fetch /api/analyze 等)                       │
│  ├─ 订阅 SSE 进度 (jobRunner 推送)                            │
│  └─ 调 addToolResult 反馈给 LLM                                │
└────────────────────────────┬─────────────────────────────────┘
                             │ tool result
┌────────────────────────────▼─────────────────────────────────┐
│  LLM 继续生成                                                 │
│  (根据工具结果回复用户)                                        │
└────────────────────────────┬─────────────────────────────────┘
                             │ final message
┌────────────────────────────▼─────────────────────────────────┐
│  前端 useChat 收到完整回复                                     │
│  ├─ ChatPanel 追加消息气泡                                    │
│  └─ store 触发 Inspector/Preview 更新（按 toolCall 类型）      │
└──────────────────────────────────────────────────────────────┘
```

---

## 6. 状态管理

所有工具调用结果统一进入 `useProjectStore` (Zustand)：

```ts
useProjectStore = {
  project: {
    id: string,
    title: string,
    style: "悬疑" | "搞笑" | "深情" | "冷静",
    targetDurationSec: number,
    audience: string,
  },
  videos: [{
    id: string,
    name: string,
    durationSec: number,
    thumbnailUrl: string,
  }],
  plotAnalysis: {
    scenes: [{
      start: number,   // 秒
      end: number,
      summary: string,
      keyCharacters: string[],
    }],
  },
  script: {
    segments: [{
      id: string,
      start: number,
      end: number,
      text: string,
      tone: string,
    }],
  },
  voice: {
    candidates: [{ id, name, gender, age, tone }],
    selected: string | null,
  },
  render: {
    renderId: string | null,
    stage: "idle" | "tts" | "subtitle" | "mixing" | "encoding" | "done" | "failed",
    progress: number,    // 0-1
    artifactUrl: string | null,
    artifacts: [{ kind, url, label }],
  },
  messages: [],  // 对话历史（仅用于演示回看，不持久化）
}
```

工具执行函数在收到 mock API 返回后 `useProjectStore.setState(partial)`，Inspector 卡片通过 selector 订阅自动重渲染。

---

## 7. 错误处理

按错误源分 4 类：

| 错误源 | 表现 | 处理方式 | UI 反馈 |
|---|---|---|---|
| **网络层** | fetch 失败 / SSE 断流 | 自动重试 1 次，失败后提示 | Chat 顶部黄色横幅"连接中断，正在重试" |
| **LLM 层** | API key 缺失 / 模型 4xx/5xx | 不重试，直接报错 | Chat 顶部红色横幅显示具体错误（如"OPENAI_API_KEY 未配置"），右下角 Toast |
| **工具执行** | mock 路由返回 4xx/5xx | 把错误作为 `toolResult` 反馈给 LLM，让 LLM 自行决定怎么告诉用户 | Chat 中 tool call 卡片显示红色错误，LLM 文字流后续说明 |
| **用户操作** | 上传非视频 / 选音色但无文本 | 前端校验拦截 | Toast 错误提示 + 输入框抖动 |

**特殊处理**：
- LLM 超时（>30s）：前端显示"思考中"动画，超过 60s 提示用户重试
- 工具执行超时（>15s）：自动 cancel 并把超时错误回传给 LLM
- SSE 中断：前端自动 reconnect 1 次，失败后刷新整个对话流

---

## 8. 测试策略

| 层级 | 工具 | 覆盖范围 | 文件 |
|---|---|---|---|
| **单元测试** | Vitest | tool schema 校验、reducer、jobRunner 模拟进度、SSE 解析 | `tests/tools.test.ts`、`tests/jobRunner.test.ts`、`tests/scriptEditor.test.ts` |
| **组件测试** | Vitest + Testing Library | Inspector 卡片状态同步、ChatPanel 消息渲染、ToolCallCard 折叠展开 | `tests/components/*.test.tsx` |
| **集成测试** | Vitest + Hono test client | mock server 端点：上传返回 200、分析返回固定剧情、渲染 SSE 完整流程 | `tests/server/*.test.ts` |

**测试命令**：
```bash
npm test                  # 单元 + 组件
npm run test:server       # 集成
```

端到端 Playwright 留作可选（不在 MVP 验收范围内）。

---

## 9. 演示验证清单

### 9.1 启动检查

- [ ] `npm run dev` 一次启动，无报错
- [ ] 浏览器打开 `http://localhost:5173` 加载完整三栏
- [ ] `.env` 配置 `OPENAI_API_KEY` 后能成功调 LLM
- [ ] 浏览器控制台无 error（warning 可有但需记录）

### 9.2 5 阶段流程必过

- [ ] 拖入 1 个 mp4 → Agent 1.5s 内响应上传
- [ ] 提示「帮我分析这 3 集」 → 4s 内出现剧情分析卡片
- [ ] 「改成搞笑风格」 → 即时生效
- [ ] 「开始生成脚本」 → 6s 内返回 5 段，Inspector 列出
- [ ] 在 Chat 卡片直接改第 3 段文字 → 同步回 Inspector
- [ ] 「换温柔女声」 → 列出 3 个候选（纯文字卡片）
- [ ] 点选一个音色 → Inspector 音色卡片更新
- [ ] 「开始生成」 → SSE 进度 4 阶段，~10s 内完成
- [ ] 完成后中栏显示成片播放器 + 产物清单
- [ ] 「导出剪映草稿」→ 30s 内返回 .zip 下载

### 9.3 响应式验证

- [ ] 1440px 宽：三栏完整并排
- [ ] 1024px 宽：三栏可读，Inspector 折叠态合理
- [ ] 768px / 375px：单栏堆叠，Chat 在最上，Preview 和 Inspector Tab 切换

### 9.4 演示边界（明确不做）

- ❌ 不演示用户登录
- ❌ 不演示多项目切换
- ❌ 不演示撤销/重做
- ❌ 不演示视频精修（OpenChatCut 式时间线）
- ❌ 不演示多语言 UI（仅中文）

---

## 10. 验收标准

| 维度 | 验收 |
|---|---|
| **功能** | 5 阶段对话流程全部走通，11 个工具调用全部成功 |
| **UI** | 视觉与 B 风格一致；1440/768/375 三档无横向溢出 |
| **性能** | 首屏 < 2s；工具调用体感流畅；SSE 进度无卡顿 |
| **代码** | 单元测试覆盖率 ≥ 60%；TypeScript 严格模式无报错；`npm run build` 通过 |
| **文档** | README 含「快速启动」「演示剧本」；demo-script.md 含完整 5 阶段台词 |

---

## 11. 未来扩展（不做但留接口）

- 接入真实 narratoApi / coreApi（替换 Hono mock 端点）
- 支持多项目切换
- 用户认证
- 撤销/重做
- 多语言 UI
- OpenChatCut 式视频精修时间线（在 Inspector 卡片中嵌入迷你时间线）

---

## 附录 A：实施补充说明

### A.1 演示视频素材来源

直接复用 homepage-prototype 现有的 mp4：

```
docs/web/homepage-prototype/public/media/narration-editor/古墓迷宫震全球1.mp4
docs/web/homepage-prototype/public/media/narration-editor/古墓迷宫震全球2.mp4
docs/web/homepage-prototype/public/media/narration-editor/古墓迷宫震全球3.mp4
```

在 vercel-sdk-demo 自己的 `public/media/` 目录中创建软链或直接复制（实施时二选一）。对应的 srt 字幕文件作为可选辅入。

### A.2 音色方案

8 个内置候选音色（写在 `server/fixtures/voiceList.json`）：

| id | name | gender | age | tone |
|---|---|---|---|---|
| morgan | Morgan | male | 30-50 | 中年低沉 |
| liuchang | 刘畅 | male | 25-35 | 青年沉稳 |
| qingcang | 青苍 | male | 20-30 | 青年磁性 |
| zhiyu | 知予 | male | 40-60 | 长者浑厚 |
| xinyu | 心语 | female | 25-35 | 知性温柔 |
| linyao | 琳瑶 | female | 18-25 | 少女清亮 |
| aiyue | 艾悦 | female | 30-45 | 优雅知性 |
| ronin | Ronin | male | 25-35 | 英文磁性 |

**只显示文字卡片，不提供试听音频**。`list_voices` 工具返回结构不含 `sampleUrl`。

### A.3 剪映草稿 mock 实现

`server/routes/export.ts` 中用 `@zip.js/zip.js` 实时生成占位 .zip，结构：

```
draft.zip
├── manifest.json          # 元信息（项目名、时间戳、Agent 决策历史）
├── draft_content.json     # 模拟剪映草稿内容（含时间线、脚本段、音色 id）
└── README.txt             # "这是 mock 导出，仅用于演示"
```

总大小约 5KB，路由直接返回文件流（`Content-Type: application/zip`），前端触发浏览器下载。

### A.4 prompts.ts 与 demo-script.md 职责分工

| 文件 | 内容 | 写入位置 |
|---|---|---|
| `src/features/agent/prompts.ts` | Agent 角色定义、工具使用约束、回复风格（中文、简洁、<200 字）、错误处理 | 代码 |
| `docs/demo-script.md` | 每阶段用户建议词（建议提示词卡片）+ Agent 预期回答要点 | 文档 |

两者**互不交叉**：prompts.ts 决定"Agent 怎么说话、怎么用工具"，demo-script.md 决定"演示时怎么引导用户点哪个提示词、Agent 应该回答什么要点"。

### A.5 启动环境变量

`.env.example` 内容：

```
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1   # 或国内代理
OPENAI_MODEL=gpt-4o-mini                    # 或其他兼容模型
```

缺少 `OPENAI_API_KEY` 时，server 在启动时打印警告但不报错，LLM 调用时才返回 401，前端会显示红色横幅。

### A.6 范围控制

本项目为 0→1 全新子目录，不修改 homepage-prototype 任何已有文件。完成验收后即作为一个独立 demo 存在，不强制合并回主项目。

---

## 自审记录

| 项 | 结果 |
|---|---|
| 占位符扫描 | 无 TBD / TODO |
| 内部一致性 | 11 工具 = 5 阶段、目录 = 文档引用、三栏 = 卡片清单 |
| 范围检查 | 单 demo 子项目，适中 |
| 歧义检查 | 5 处已修复（演示视频/音色/剪映导出/prompts 分工/LLM 语言） |
| 范围控制 | 不修改 homepage-prototype 任何已有文件 |
