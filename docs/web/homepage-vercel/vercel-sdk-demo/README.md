# vercel-sdk-demo

> NarratoAI 短剧解说的「对话式工作台」原型：左侧 Chat、中间 Preview、右侧 Inspector，三栏布局 + Dark Neon 风格，AI Agent 通过 Vercel AI SDK 7 工具调用驱动 5 阶段工作流。

本目录是 NarratoAI 前端 `homepage-prototype` 的**独立原型**：在保留既有视觉语言（暗色霓虹）的条件下，把短剧解说从「分步表单 + 时间轴」改造为「ChatCut 式对话 + 实时预览 + 状态卡片」三栏工作台。

## 与 `homepage-prototype` 的关系

- `homepage-prototype` 是**先于方案 Y 的多页应用原型**（首页 / 上传 / 配置 / 脚本 / 配音 / 渲染），保持不动；
- `homepage-vercel/vercel-sdk-demo` 是**方案 Y 的独立验证原型**，自包含、零历史包袱：1 个 `WorkbenchPage` 直接承载完整短剧解说工作流；
- 本目录**不**回写 `homepage-prototype`，验收通过后再统一回写；
- 设计背景见 `docs/2026-08-06-vercel-sdk-demo-design.md`（与本目录同级上层的设计稿）。

## 核心特性

- **三栏工作台**（Chat / Preview / Inspector） + 折叠卡片：1 个工作台页面跑通上传→分析→风格配置→脚本生成/编辑→配音→渲染/导出。
- **Vercel AI SDK 7 对话**：`useChat` 接入任意 OpenAI 兼容 LLM，工具调用通过 Zod schema 强校验。
- **11 个原子工具**：覆盖上传、分析、风格、时长、脚本生成/编辑/重生、音色查询/选择、渲染/状态追踪。
- **Hono Mock Server**：作为 Vite 中间件同进程运行，9 条 REST/SSE 端点，0 外部依赖，刷新即用。
- **SSE 进度推送**：剧情分析、脚本生成、渲染过程通过 Server-Sent Events 实时驱动 Preview/Inspector。
- **Zustand 状态中枢**：项目、剧情、脚本、音色、渲染五大块集中管理，类型严格（TS strict + `exactOptionalPropertyTypes`）。
- **暗色霓虹视觉**：CSS Token 沉淀颜色 / 间距 / 圆角 / 阴影，三栏 1024px 以下 Inspector 自动隐藏。
- **测试 25 个用例**：覆盖 store、API 路由、组件渲染、Agent 工具、内存层、JobRunner；`npm run test:coverage` 出 HTML 报告。

## 快速开始

```bash
# 1. 安装依赖
cd docs/web/homepage-vercel/vercel-sdk-demo
npm install

# 2. （可选）配置 LLM —— 不配也能跑，会自动回退到 Mock 模式
cp .env.example .env.local
# 编辑 .env.local：填入 OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL

# 3. 启动开发服务器（默认 http://localhost:5173）
npm run dev

# 4. 在浏览器打开 http://localhost:5173 ，左侧 Chat 直接开始对话
```

**Mock 模式**：未配置 `OPENAI_API_KEY` 时，Chat 路由会按预制剧本返回固定话术 + 工具调用，所有 5 阶段都能跑通，方便演示和验收。

## 脚本命令

| 脚本 | 作用 |
| --- | --- |
| `npm run dev` | 启动 Vite + Hono Mock Server，端口 5173（`strictPort` 占用即报错，不会自动切端口） |
| `npm run build` | `tsc -b` 类型检查 + Vite 生产构建（产物 `dist/`） |
| `npm run preview` | 本地预览生产构建 |
| `npm run test` | 单跑 Vitest 全部用例（25 个） |
| `npm run test:watch` | Vitest 监听模式 |
| `npm run test:coverage` | 跑用例 + 出 v8 coverage 报告（文本 + HTML） |
| `npm run typecheck` | 仅类型检查（不输出产物） |

## 目录结构

```
vercel-sdk-demo/
├── docs/
│   └── 2026-08-06-vercel-sdk-demo-design.md      # 设计稿
├── public/
│   ├── media/                                    # Demo 视频与缩略图（episode-1~3.mp4）
│   └── favicon.svg
├── server/                                       # Hono Mock Server
│   ├── app.ts                                    # 路由聚合（9 个端点）
│   ├── routes/                                   # 8 个 REST/SSE 端点
│   │   ├── projects.ts                           # GET/POST/PATCH /api/projects
│   │   ├── upload.ts                             # POST /api/upload
│   │   ├── analyze.ts                            # POST /api/analyze（剧情分析 + SSE）
│   │   ├── script.ts                             # GET/POST/PATCH /api/script
│   │   ├── voices.ts                             # GET /api/voices
│   │   ├── render.ts                             # POST /api/render（异步 + SSE 进度）
│   │   ├── export.ts                             # GET /api/export
│   │   └── chat.ts                               # POST /api/chat（Vercel AI SDK 7）
│   ├── store/
│   │   ├── memoryStore.ts                        # 内存态项目仓库
│   │   └── jobRunner.ts                          # 异步任务 + SSE 推送
│   ├── llm/
│   │   └── agentPrompt.ts                        # Chat 路由的 system prompt
│   └── fixtures/                                 # 示例数据（剧情 / 脚本 / 音色 / 进度）
├── src/
│   ├── main.tsx                                  # React 19 入口
│   ├── App.tsx                                   # 路由壳：渲染 WorkbenchPage
│   ├── pages/
│   │   └── WorkbenchPage.tsx                     # 三栏布局
│   ├── components/
│   │   ├── chat/                                 # Chat 面板
│   │   │   ├── ChatPanel.tsx
│   │   │   ├── ChatMessage.tsx
│   │   │   ├── ChatComposer.tsx
│   │   │   ├── ToolCallCard.tsx
│   │   │   └── ScriptSegmentCard.tsx
│   │   ├── preview/                              # Preview 面板
│   │   │   ├── PreviewPanel.tsx
│   │   │   ├── VideoPlayer.tsx
│   │   │   ├── RenderProgress.tsx
│   │   │   └── ArtifactList.tsx
│   │   ├── inspector/                            # Inspector 面板（5 张折叠卡片）
│   │   │   ├── InspectorPanel.tsx
│   │   │   ├── ProjectInfoCard.tsx
│   │   │   ├── PlotAnalysisCard.tsx
│   │   │   ├── ScriptSegmentsCard.tsx
│   │   │   ├── VoiceSelectionCard.tsx
│   │   │   └── RenderStatusCard.tsx
│   │   └── shared/
│   │       ├── CollapsibleCard.tsx
│   │       └── EmptyState.tsx
│   ├── features/
│   │   ├── project/
│   │   │   ├── store.ts                          # Zustand store（16 actions）
│   │   │   └── types.ts                          # Project / Scene / Script / Voice / Render
│   │   └── agent/
│   │       ├── useWorkbench.ts                   # useChat 封装 + tool 副作用
│   │       ├── tools.ts                          # 11 个 Zod 工具定义
│   │       └── prompts.ts                        # 客户端 system prompt
│   ├── lib/
│   │   └── api.ts                                # postJSON / getJSON / subscribeSSE
│   └── styles/
│       ├── tokens.css                            # 颜色 / 间距 / 字号 / 圆角 token
│       ├── workbench.css                         # 三栏布局 + 响应式
│       └── chat.css                              # Chat 气泡 / 工具卡片
├── tests/                                        # 25 个 Vitest 用例
│   ├── setup.ts                                  # jsdom scrollIntoView 等 mock
│   ├── features/store.test.ts
│   ├── lib/api.test.ts
│   ├── components/ChatPanel.test.tsx
│   ├── components/InspectorPanel.test.tsx
│   ├── components/ToolCallCard.test.tsx
│   ├── agent/tools.test.ts
│   └── server/                                   # 内存层、JobRunner、Chat 路由、集成
├── .env.example
├── .gitignore
├── index.html
├── package.json
├── tsconfig.json                                 # 已合并 node 配置（单工程模式）
└── vite.config.mjs                               # Hono 中间件 + Vitest 配置
```

## 5 阶段对话工作流

| 阶段 | 用户输入示例 | 触发的 Agent 工具 | Inspector 状态变化 | Preview 变化 |
| --- | --- | --- | --- | --- |
| 1. 上传 | "上传第 1 集" | `upload_video` | ProjectInfoCard 显示视频 | 显示视频播放器 |
| 2. 剧情分析 | "分析一下剧情" | `analyze_plot` | PlotAnalysisCard 出现 5–8 个场景 | 视频 + 分析进度 |
| 3. 风格配置 | "用悬疑风格，目标 90 秒" | `set_narration_style`, `set_target_duration` | ProjectInfoCard 更新 | —— |
| 4. 脚本生成/编辑 | "生成脚本" / "把第 3 段改得更紧张" | `generate_script`, `edit_script_segment`, `regenerate_segment` | ScriptSegmentsCard 出现 5 段 | —— |
| 5. 配音 + 渲染导出 | "用女声" / "开始渲染" | `list_voices`, `select_voice`, `start_render`, `track_render_status` | VoiceSelectionCard + RenderStatusCard 实时更新 | RenderProgress → ArtifactList |

完整 5 阶段验收走查脚本见 [docs/demo-script.md](./docs/demo-script.md)。

## 架构概览

```
┌──────────────────────────────────────────────────────────────────┐
│  React 19 + Vite 7 + TypeScript strict                           │
│  ┌──────────────┐  ┌─────────────────┐  ┌──────────────────────┐ │
│  │ ChatPanel    │  │ PreviewPanel    │  │ InspectorPanel       │ │
│  │  - useChat   │  │  - VideoPlayer  │  │  - 5 CollapsibleCards│ │
│  │  - 工具卡片  │  │  - RenderProg.  │  │  - 折叠 / 展开       │ │
│  │  - 脚本卡片  │  │  - ArtifactList │  │  - 状态徽标          │ │
│  └──────┬───────┘  └────────┬────────┘  └──────────┬───────────┘ │
│         └──────┬────────────┴──────────────────────┘             │
│                │                                                 │
│         ┌──────▼──────┐                                          │
│         │ Zustand     │  Project / Plot / Script / Voice / Render│
│         │ store.ts    │                                          │
│         └──────┬──────┘                                          │
│                │                                                 │
│  ┌─────────────▼────────────────┐                                │
│  │ useWorkbench (Vercel AI SDK) │  useChat + onToolCall          │
│  │   tools.ts (11 个 Zod 工具)  │  ↕ POST /api/chat              │
│  └─────────────┬────────────────┘                                │
└────────────────┼─────────────────────────────────────────────────┘
                 │ HTTP / SSE
┌────────────────▼─────────────────────────────────────────────────┐
│  Hono (Vite Middleware, in-process)                              │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │ REST/SSE 路由（8 条）                                     │    │
│  │  /api/projects  /api/upload  /api/analyze  /api/script  │    │
│  │  /api/voices    /api/render   /api/export                │    │
│  └──────────────────────────────────────────────────────────┘    │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │ Chat 路由 /api/chat（Vercel AI SDK streamText + tools）  │    │
│  └──────────────────────────────────────────────────────────┘    │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │ memoryStore + jobRunner + fixtures                       │    │
│  └──────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
```

### 关键设计决策

- **Mock Server 同进程**：Hono 作为 Vite middleware 跑在同一端口，避免「前端 + 后端」双进程开发。
- **Tool = 单一副作用入口**：11 个工具由 `useWorkbench` 的 `onToolCall` 统一调度，对应 1 个 store action / 1 个 SSE 订阅，绝不重复请求。
- **SSE 实时进度**：异步任务（分析 / 渲染）通过 `subscribeSSE` 推送到 Preview / Inspector，UI 与服务解耦。
- **Inspector 折叠卡片**：所有 Inspector 卡片复用 `CollapsibleCard`，徽标 + 标题 + 折叠态，5 张卡片纵列不堆挤。
- **TypeScript strict + `exactOptionalPropertyTypes` + `noUncheckedIndexedAccess`**：所有 store action、tool schema、API 返回均强类型。
- **零外部资源**：唯一外部依赖是 LLM（可选），不接 LLM 也能跑 5 阶段。

## 端到端验收

```bash
# 1. 类型检查 + 单测
npm run typecheck && npm test

# 2. 覆盖率
npm run test:coverage
# → 打开 coverage/index.html 查看 HTML 报告

# 3. 生产构建
npm run build

# 4. Dev 演示（人工走 5 阶段）
npm run dev
# 浏览器打开 http://localhost:5173 ，按 docs/demo-script.md 走查
```

## 已知限制 / 后续工作

- **Memory Store 重启即丢**：演示专用，无持久化；生产需替换为数据库。
- **Mock LLM 兜底**：未配 LLM 时走预制剧本，行为固定；如需换 LLM 改 `.env.local`。
- **音频播放未做**：音色只占位文本卡片（按方案选定的「只做文字占位，不播音频」）。
- **响应式边界**：1024px 以下隐藏 Inspector；375px / 768px 暂未单独优化，演示请用 ≥ 1024px。
- **与 `homepage-prototype` 的关系**：本目录是独立原型，验收通过后再统一回写 `homepage-prototype`。

## License & 归属

本目录为 NarratoAI 内部原型，所属会话在 `/Users/wujingfeng/project/ai/codex/NarratoAI`，不对外发布。
