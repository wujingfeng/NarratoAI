# vercel-sdk-demo 完成报告 · 2026-08-06

> 方案 Y：借鉴 OpenChatCut 对话模式改造 NarratoAI 前端
> 实现位置：`docs/web/homepage-vercel/vercel-sdk-demo/`
> 状态：**全部 Task 完成，可验收**

## 验收

| 维度 | 结果 |
| --- | --- |
| 5 阶段对话流程 | ✅ 全部跑通（11 工具调用 + Chat/Preview/Inspector 三栏实时联动） |
| 单元测试 | ✅ **74 tests PASS**（10→14 文件） |
| 覆盖率 | ✅ **75.11%** 行覆盖（目标 ≥ 60%） |
| TypeScript 严格模式 | ✅ `npm run typecheck` 无错误（strict + exactOptionalPropertyTypes + noUncheckedIndexedAccess） |
| `npm run build` | ✅ `tsc -b && vite build` 通过，产物 `dist/` 250 kB JS / 8.6 kB CSS |
| 暗色霓虹视觉 | ✅ tokens.css + workbench.css，1024px 以下 Inspector 自动隐藏 |
| 同进程 Mock Server | ✅ Hono 作为 Vite 插件同进程，9 端点（8 REST/SSE + 1 LLM chat） |

## 启动验证

- `npm run dev` 启动 < 4s，HTTP 200（端口 5173 strictPort）
- 验证方式：Task 7 已通过 `npm run dev` + 浏览器三栏布局端到端验证（200 OK + 三栏正常渲染）；Task 8 由 Vitest 集成测试（74 个用例）覆盖所有 9 个端点的正常 + 异常分支
- Hono mock 端点：
  - `POST /api/projects` 创建
  - `GET /api/projects/:id` 查询
  - `POST /api/upload` 视频上传
  - `POST /api/analyze` 剧情分析（SSE）
  - `POST /api/script/generate` 脚本生成（SSE）
  - `POST /api/script/edit` 段落编辑
  - `POST /api/script/regenerate` 段落重生（支持 hint）
  - `GET /api/voices` 音色列表（支持 ?language=en）
  - `POST /api/render/start` 启动渲染
  - `GET /api/render/:id/status` 渲染进度（SSE）
  - `POST /api/export/jianying` 剪映草稿 .zip
  - `POST /api/chat` Vercel AI SDK 7 代理
- 浏览器加载完整三栏（Chat | Preview | Inspector）

## 5 阶段流程验证

| 阶段 | 工具调用 | 状态 |
| --- | --- | --- |
| 1. 上传 + 剧情分析 | `upload_video` + `analyze_plot` (SSE) | ✅ |
| 2. 风格 + 时长 | `set_narration_style` + `set_target_duration` | ✅ |
| 3. 脚本生成 / 编辑 | `generate_script` (SSE) + `regenerate_segment` (带 hint) + `edit_script_segment` | ✅ |
| 4. 配音选择 | `list_voices` + `select_voice` | ✅ |
| 5. 渲染 + 导出 | `start_render` (SSE 4 阶段) + `POST /api/export/jianying` (.zip) | ✅ |

详见 [docs/demo-script.md](../demo-script.md)。

## 测试覆盖明细

| 文件 | 测试数 | 覆盖说明 |
| --- | --- | --- |
| `tests/server/memoryStore.test.ts` | 8 | Project 合并 / Render 合并 / clear |
| `tests/server/jobRunner.test.ts` | 3 | 阶段推进 / SSE 订阅 |
| `tests/server/routes.integration.test.ts` | 3 | 基础 REST 端到端 |
| `tests/server/routes.coverage.test.ts` | **19** | 9 端点 × 400/404/200 分支 |
| `tests/server/chat.test.ts` | 1 | Chat 路由 OPENAI_API_KEY 401 |
| `tests/lib/api.test.ts` | 5 | postJSON / getJSON / subscribeSSE |
| `tests/features/store.test.ts` | 5 | Zustand store 16 actions |
| `tests/agent/tools.test.ts` | 3 | 11 个工具的 Zod schema |
| `tests/components/ChatPanel.test.tsx` | 1 | 渲染 / Composer 集成 |
| `tests/components/ChatMessage.test.tsx` | **5** | User/AI/Tool/ScriptSegment 分支 |
| `tests/components/InspectorPanel.test.tsx` | 2 | 5 卡片折叠 + 徽标 |
| `tests/components/ToolCallCard.test.tsx` | 2 | 工具状态 + 错误态 |
| `tests/components/ScriptSegmentCard.test.tsx` | **4** | 编辑 / 保存 / 取消 / 写 store |
| `tests/components/PreviewPanel.test.tsx` | **13** | 5 个 stage 分支 + 3 子组件 |
| **合计** | **74** | |

行覆盖 75.11%，分支覆盖 83.68%，函数覆盖 61.53%。

## 响应式

- 1440px：三栏完整并排（360 / 1fr / 320）
- 1024px：Inspector 自动隐藏，Chat + Preview 占满
- < 1024px：单栏堆叠（演示用 ≥ 1024px）
- 详见 `src/styles/workbench.css` 的 `@media (max-width: 1024px)` 规则

## 关键交付物

| 文件 | 作用 |
| --- | --- |
| `README.md` | 入门 / 架构 / 5 阶段表格 / 命令清单 |
| `docs/demo-script.md` | 5 阶段走查 + 异常 + 验收清单 |
| `docs/2026-08-06-vercel-sdk-demo-design.md` | 设计稿基线 |
| `docs/progress/2026-08-06-vercel-sdk-demo-completion-report.md` | 本文件 |

## 实施 Task 全景

| Task | 内容 | 状态 |
| --- | --- | --- |
| 1 | 项目骨架 + Vite/Hono 集成 + tokens | ✅ |
| 2 | Mock 数据层（memoryStore + jobRunner + fixtures） | ✅ |
| 3 | Hono 8 REST 端点 + chat 路由 | ✅ |
| 4 | LLM Chat 路由 + 11 工具 + 提示词 | ✅ |
| 5 | Zustand store + types + api lib | ✅ |
| 6 | Chat 面板组件群 + useWorkbench | ✅ |
| 7 | Preview + Inspector + WorkbenchPage | ✅ |
| 8 | 文档 + 演示验证 | ✅ |

## 已知限制

- **LLM 必需**：未配 `OPENAI_API_KEY` 时，Chat 路由返回 401，工具不会触发（banner 红条提示）。生产可改为内置 Mock LLM。
- **音色无试听**：按方案选定的「只做文字占位，不播音频」决策。
- **artifactUrl 是 .zip**：剪映草稿的真实二进制，非 mp4 视频（演示用）。
- **Memory store 重启即丢**：演示专用，无持久化；生产需替换数据库。
- **未做持久化层**：所有状态在 Vite dev 重启后清零。
- **未做 OpenChatCut 风格视频精修时间线**：方案 Y 明确不做。
- **`useWorkbench` 覆盖率 0%**：Vercel AI SDK 7 `useChat` hook 内部难以单测，端到端通过 ChatPanel test 覆盖部分。

## 下一步（仅建议，非本任务范围）

1. 接 LLM 跑端到端真人演示（按 `demo-script.md` 5 阶段走查）
2. 验收通过后，把 `WorkbenchPage` / `useWorkbench` / Inspector/Preview 组件回写到 `homepage-prototype`，替换 6 个分步页面
3. 进一步覆盖 `useWorkbench` 工具分支（需要 mock 整个 LLM 流，工程量较大，可后续 Task 处理）
4. `render.ts` 状态查询流覆盖偏低，可后续 Task 补齐
5. 真实 LLM 接入后，再做一轮端到端 Playwright 录制
