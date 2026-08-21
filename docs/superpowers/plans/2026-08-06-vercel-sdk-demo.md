# vercel-sdk-demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `homepage-vercel/vercel-sdk-demo/` 下从零构建一个对话式短剧解说工作台 demo，端到端跑通 5 阶段对话流程（上传→分析→脚本→音色→渲染导出），验证"对话式 Agent 驱动短剧解说"交互模式的可行性。

**Architecture:** Vite 7 + React 19 单页工作台（左侧 Chat、中间 Preview、右侧 Inspector）；同进程 Hono Mock Server 通过 Vite 插件提供 8 个 REST 端点 + 1 个 LLM 代理端点；11 个 Agent 工具通过 Vercel AI SDK 7 的 `useChat` + `tool` 模式调度；状态用 Zustand 管理；可视化进度用 SSE 推送。

**Tech Stack:** Vite 7、React 19、TypeScript 5、Hono 4、Vercel AI SDK 7 (`ai` + `@ai-sdk/react` + `@ai-sdk/openai-compatible`)、Zod 3、Zustand 5、@zip.js/zip.js 2、Vitest 2、@testing-library/react 16、jsdom。

---

## 全局约束

1. **唯一需求基线**：`docs/web/homepage-vercel/vercel-sdk-demo/docs/2026-08-06-vercel-sdk-demo-design.md`。
2. **目录铁律**：所有新文件在 `docs/web/homepage-vercel/vercel-sdk-demo/` 内；**不修改** `docs/web/homepage-prototype/` 下任何文件。
3. **TDD 铁律**：每个 Task 都按"写失败测试 → 跑测试确认失败 → 写最小实现 → 跑测试确认通过 → commit"循环。Vitest 用 `node` 环境跑 server 测试，`jsdom` 环境跑组件测试。
4. **TypeScript 严格模式**：`tsconfig.json` 启用 `strict: true`、`noUncheckedIndexedAccess: true`、`exactOptionalPropertyTypes: true`。
5. **演示素材**：复用 `docs/web/homepage-prototype/public/media/narration-editor/古墓迷宫震全球{1,2,3}.mp4`，在 vercel-sdk-demo 内 `public/media/` 用文件复制（不用软链，跨平台兼容）。
6. **测试运行前置**：每个测试命令前 `cd docs/web/homepage-vercel/vercel-sdk-demo`。
7. **Port 分配**：Vite dev 端口 `5173`，Hono mock server 通过 Vite 插件挂在同进程，路由前缀 `/api/*`。
8. **依赖安装**：所有 npm 命令用 `npm install --no-audit --no-fund` 减少噪音输出。
9. **Commit 规范**：中文 commit message 描述"为什么"，英文 type 前缀（`feat:` / `chore:` / `test:` / `docs:` / `fix:`）。
10. **演示范围**：仅中文 UI；不做用户认证、不做多项目、不做撤销/重做、不做多语言、不接现有 narratoApi。

---

## Task 1: 项目骨架与 Vite/Hono 集成

**Files:**
- Create: `docs/web/homepage-vercel/vercel-sdk-demo/package.json`
- Create: `docs/web/homepage-vercel/vercel-sdk-demo/tsconfig.json`
- Create: `docs/web/homepage-vercel/vercel-sdk-demo/tsconfig.node.json`
- Create: `docs/web/homepage-vercel/vercel-sdk-demo/vite.config.mjs`
- Create: `docs/web/homepage-vercel/vercel-sdk-demo/.env.example`
- Create: `docs/web/homepage-vercel/vercel-sdk-demo/.gitignore`
- Create: `docs/web/homepage-vercel/vercel-sdk-demo/index.html`
- Create: `docs/web/homepage-vercel/vercel-sdk-demo/src/main.tsx`
- Create: `docs/web/homepage-vercel/vercel-sdk-demo/src/App.tsx`
- Create: `docs/web/homepage-vercel/vercel-sdk-demo/src/styles/tokens.css`
- Create: `docs/web/homepage-vercel/vercel-sdk-demo/src/vite-env.d.ts`
- Create: `docs/web/homepage-vercel/vercel-sdk-demo/public/favicon.svg`
- Create: `docs/web/homepage-vercel/vercel-sdk-demo/public/media/.gitkeep`
- Create: `docs/web/homepage-vercel/vercel-sdk-demo/tests/setup.ts`

**Interfaces:**
- Consumes: 文档基线（设计文档 0-2 节）。
- Produces: 一个能 `npm run dev` 启动并显示"工作台加载成功"的最小可运行项目；能 `npm test` 启动但零测试。

- [ ] **Step 1: 创建 package.json**

```json
{
  "name": "vercel-sdk-demo",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest",
    "typecheck": "tsc -b"
  },
  "dependencies": {
    "@ai-sdk/openai-compatible": "^0.0.10",
    "@ai-sdk/react": "^1.0.0",
    "@zip.js/zip.js": "^2.7.45",
    "ai": "^4.0.0",
    "hono": "^4.6.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "zod": "^3.23.8",
    "zustand": "^5.0.0"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.5.0",
    "@testing-library/react": "^16.0.1",
    "@types/node": "^22.7.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@vitejs/plugin-react": "^4.3.2",
    "jsdom": "^25.0.0",
    "typescript": "^5.6.0",
    "vite": "^7.0.0",
    "vitest": "^2.1.0"
  }
}
```

- [ ] **Step 2: 创建 tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,
    "resolveJsonModule": true,
    "types": ["vite/client", "vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src", "tests"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

- [ ] **Step 3: 创建 tsconfig.node.json**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2023"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true,
    "strict": true,
    "noEmit": true,
    "types": ["node"]
  },
  "include": ["vite.config.mjs"]
}
```

- [ ] **Step 4: 创建 vite.config.mjs（先不含 Hono 插件）**

```js
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
  },
});
```

- [ ] **Step 5: 创建 .env.example**

```
# LLM（任意 OpenAI 兼容协议）
OPENAI_API_KEY=sk-your-key-here
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
```

- [ ] **Step 6: 创建 .gitignore**

```
node_modules
dist
.env
.env.local
*.log
.DS_Store
coverage
```

- [ ] **Step 7: 创建 index.html**

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>vercel-sdk-demo · 对话式短剧解说</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 8: 创建 src/main.tsx**

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles/tokens.css";

const root = document.getElementById("root");
if (!root) throw new Error("Root element #root not found");
createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

- [ ] **Step 9: 创建 src/App.tsx**

```tsx
export default function App() {
  return (
    <main className="app-shell">
      <h1>vercel-sdk-demo</h1>
      <p>工作台加载成功</p>
    </main>
  );
}
```

- [ ] **Step 10: 创建 src/styles/tokens.css**

```css
:root {
  --bg-base: #0a0a14;
  --bg-surface: #14141f;
  --bg-elevated: #1c1c2b;
  --border-subtle: #2a2a3d;
  --text-primary: #f0f0f5;
  --text-secondary: #a0a0b5;
  --text-muted: #6a6a85;
  --accent-neon: #7c3aed;
  --accent-cyan: #06b6d4;
  --accent-pink: #ec4899;
  --success: #10b981;
  --warning: #f59e0b;
  --error: #ef4444;
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-xl: 16px;
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 24px;
  --space-6: 32px;
  --font-xs: 11px;
  --font-sm: 12px;
  --font-base: 14px;
  --font-md: 16px;
  --font-lg: 20px;
  --font-xl: 28px;
  --font-family: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", system-ui, sans-serif;
}

* { box-sizing: border-box; }

html, body, #root {
  height: 100%;
  margin: 0;
  background: var(--bg-base);
  color: var(--text-primary);
  font-family: var(--font-family);
  font-size: var(--font-base);
}

.app-shell {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: var(--space-4);
}
```

- [ ] **Step 11: 创建 src/vite-env.d.ts**

```ts
/// <reference types="vite/client" />
```

- [ ] **Step 12: 创建 public/favicon.svg**

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="6" fill="#7c3aed"/><text x="16" y="22" font-size="18" text-anchor="middle" fill="white" font-family="sans-serif">V</text></svg>
```

- [ ] **Step 13: 创建 public/media/.gitkeep（空文件）**

- [ ] **Step 14: 创建 tests/setup.ts**

```ts
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 15: 复制演示视频**

Run:

```bash
mkdir -p docs/web/homepage-vercel/vercel-sdk-demo/public/media
cp "docs/web/homepage-prototype/public/media/narration-editor/古墓迷宫震全球1.mp4" docs/web/homepage-vercel/vercel-sdk-demo/public/media/episode-1.mp4
cp "docs/web/homepage-prototype/public/media/narration-editor/古墓迷宫震全球2.mp4" docs/web/homepage-vercel/vercel-sdk-demo/public/media/episode-2.mp4
cp "docs/web/homepage-prototype/public/media/narration-editor/古墓迷宫震全球3.mp4" docs/web/homepage-vercel/vercel-sdk-demo/public/media/episode-3.mp4
ls docs/web/homepage-vercel/vercel-sdk-demo/public/media/
```

Expected: 列出 `episode-1.mp4`、`episode-2.mp4`、`episode-3.mp4` 三个文件。

- [ ] **Step 16: 安装依赖**

Run:

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo && npm install --no-audit --no-fund
```

Expected: 安装完成，无 ERR。

- [ ] **Step 17: 启动 dev server 验证**

Run:

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo && nohup npm run dev > /tmp/vercel-sdk-demo-dev.log 2>&1 &
echo $! > /tmp/vercel-sdk-demo-dev.pid
sleep 4
curl -s http://localhost:5173/ | head -20
```

Expected: HTML 输出含 `<title>vercel-sdk-demo · 对话式短剧解说</title>`。

- [ ] **Step 18: 关闭 dev server**

Run:

```bash
kill $(cat /tmp/vercel-sdk-demo-dev.pid) || true
rm -f /tmp/vercel-sdk-demo-dev.pid
```

- [ ] **Step 19: Commit**

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo
git add -A
git commit -m "chore: 初始化 vercel-sdk-demo 项目骨架（Vite + React + Hono）"
```

---

## Task 2: Mock 数据层（memoryStore + jobRunner + fixtures）

**Files:**
- Create: `server/store/memoryStore.ts`
- Create: `server/store/jobRunner.ts`
- Create: `server/fixtures/voiceList.json`
- Create: `server/fixtures/sampleAnalysis.json`
- Create: `server/fixtures/sampleScript.json`
- Create: `server/fixtures/progressScenarios.json`
- Test: `tests/server/jobRunner.test.ts`
- Test: `tests/server/memoryStore.test.ts`

**Interfaces:**
- `memoryStore`：提供 `getProject` / `setProject` / `appendMessage` / `getMessages` / `getRender` / `setRender` 等方法，in-memory 存储 Map。
- `jobRunner.run(jobId, kind, payload, onProgress, options)`：返回 `Promise`，内部按 `progressScenarios` 中的 timing 推送 onProgress 事件，支持 `subscribe(jobId, listener)` 做 SSE 流式订阅。

- [ ] **Step 1: 写 jobRunner 失败测试**

`tests/server/jobRunner.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { jobRunner } from "../../server/store/jobRunner";

describe("jobRunner", () => {
  it("推完所有阶段后完成", async () => {
    const events: Array<{ stage: string; progress: number }> = [];
    const result = await jobRunner.run("render-test-1", "render", { projectId: "p1" }, (e) =>
      events.push({ stage: e.stage, progress: e.progress }),
    );
    expect(events.length).toBeGreaterThanOrEqual(4);
    expect(events.at(-1)?.stage).toBe("done");
    expect(events.at(-1)?.progress).toBe(1);
    expect(result.jobId).toBe("render-test-1");
  });

  it("订阅 SSE 期间能收到全部进度", async () => {
    const received: string[] = [];
    const unsub = jobRunner.subscribe("render-test-2", (e) => received.push(e.stage));
    await jobRunner.run("render-test-2", "render", { projectId: "p1" });
    unsub();
    expect(received.at(-1)).toBe("done");
  });

  it("支持取消", async () => {
    const controller = new AbortController();
    const promise = jobRunner.run("render-test-3", "render", { projectId: "p1" }, undefined, { signal: controller.signal });
    setTimeout(() => controller.abort(), 100);
    await expect(promise).rejects.toThrow();
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

Run:

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo && npm test -- tests/server/jobRunner.test.ts
```

Expected: FAIL with "Cannot find module"。

- [ ] **Step 3: 创建 fixtures - voiceList.json**

`server/fixtures/voiceList.json`:

```json
[
  { "id": "morgan", "name": "Morgan", "gender": "male", "age": "30-50", "tone": "中年低沉" },
  { "id": "liuchang", "name": "刘畅", "gender": "male", "age": "25-35", "tone": "青年沉稳" },
  { "id": "qingcang", "name": "青苍", "gender": "male", "age": "20-30", "tone": "青年磁性" },
  { "id": "zhiyu", "name": "知予", "gender": "male", "age": "40-60", "tone": "长者浑厚" },
  { "id": "xinyu", "name": "心语", "gender": "female", "age": "25-35", "tone": "知性温柔" },
  { "id": "linyao", "name": "琳瑶", "gender": "female", "age": "18-25", "tone": "少女清亮" },
  { "id": "aiyue", "name": "艾悦", "gender": "female", "age": "30-45", "tone": "优雅知性" },
  { "id": "ronin", "name": "Ronin", "gender": "male", "age": "25-35", "tone": "英文磁性" }
]
```

- [ ] **Step 4: 创建 fixtures - sampleAnalysis.json**

`server/fixtures/sampleAnalysis.json`:

```json
{
  "scenes": [
    { "start": 0, "end": 18, "summary": "考古小队进入古墓第一道石门，遭遇机关箭雨。", "keyCharacters": ["林夏", "教授"] },
    { "start": 18, "end": 42, "summary": "主角发现墙上的神秘符号，预示着墓主身份不凡。", "keyCharacters": ["林夏"] },
    { "start": 42, "end": 68, "summary": "队伍进入主墓室，金银财宝映入眼帘，但林夏察觉异常。", "keyCharacters": ["林夏", "教授", "助手"] },
    { "start": 68, "end": 95, "summary": "墓室机关触发，队友陷入危机，林夏用绳索救下教授。", "keyCharacters": ["林夏", "教授"] },
    { "start": 95, "end": 120, "summary": "墓主苏醒，主角逃出古墓，但发现这一切只是更大谜团的开始。", "keyCharacters": ["林夏", "墓主"] }
  ]
}
```

- [ ] **Step 5: 创建 fixtures - sampleScript.json**

`server/fixtures/sampleScript.json`:

```json
[
  { "id": "seg-1", "start": 0, "end": 12, "text": "深夜，考古小队推开尘封千年的石门。门后，传来了令人毛骨悚然的声响。", "tone": "紧张" },
  { "id": "seg-2", "start": 12, "end": 28, "text": "林夏发现墙上的符号，瞳孔骤缩——这符号与传说中的守墓人有关。", "tone": "悬疑" },
  { "id": "seg-3", "start": 28, "end": 48, "text": "满室金碧辉煌，但林夏却看到了不该看到的东西——墓主尸身的眼睛，似乎在动。", "tone": "诡谲" },
  { "id": "seg-4", "start": 48, "end": 68, "text": "千钧一发！林夏抛出的绳索救下了教授，自己却被困在崩塌的墓道中。", "tone": "紧张" },
  { "id": "seg-5", "start": 68, "end": 88, "text": "她爬出古墓时，身后传来低沉的笑声——这一切，只是更大谜局的序章。", "tone": "悬念" }
]
```

- [ ] **Step 6: 创建 fixtures - progressScenarios.json**

`server/fixtures/progressScenarios.json`:

```json
{
  "analyze_plot": {
    "stages": [
      { "stage": "uploading", "durationMs": 800, "progress": 0.2 },
      { "stage": "asr", "durationMs": 1500, "progress": 0.55 },
      { "stage": "summarizing", "durationMs": 1500, "progress": 0.9 },
      { "stage": "done", "durationMs": 200, "progress": 1 }
    ]
  },
  "generate_script": {
    "stages": [
      { "stage": "drafting", "durationMs": 3000, "progress": 0.4 },
      { "stage": "refining", "durationMs": 2000, "progress": 0.8 },
      { "stage": "done", "durationMs": 1000, "progress": 1 }
    ]
  },
  "render": {
    "stages": [
      { "stage": "tts", "durationMs": 2500, "progress": 0.25 },
      { "stage": "subtitle", "durationMs": 2000, "progress": 0.5 },
      { "stage": "mixing", "durationMs": 3000, "progress": 0.8 },
      { "stage": "encoding", "durationMs": 2000, "progress": 0.95 },
      { "stage": "done", "durationMs": 500, "progress": 1 }
    ]
  }
}
```

- [ ] **Step 7: 写 memoryStore 失败测试**

`tests/server/memoryStore.test.ts`:

```ts
import { describe, it, expect, beforeEach } from "vitest";
import { memoryStore } from "../../server/store/memoryStore";

describe("memoryStore", () => {
  beforeEach(() => memoryStore.clear());

  it("set 后能 get 出来", () => {
    memoryStore.setProject("p1", { id: "p1", title: "测试项目", style: "悬疑" });
    expect(memoryStore.getProject("p1")?.title).toBe("测试项目");
  });

  it("appendMessage 按顺序累加", () => {
    memoryStore.appendMessage("p1", { role: "user", content: "你好" });
    memoryStore.appendMessage("p1", { role: "assistant", content: "你好！有什么可以帮你？" });
    const msgs = memoryStore.getMessages("p1");
    expect(msgs).toHaveLength(2);
    expect(msgs[0]?.content).toBe("你好");
    expect(msgs[1]?.content).toBe("你好！有什么可以帮你？");
  });

  it("不存在的项目返回 undefined", () => {
    expect(memoryStore.getProject("nonexistent")).toBeUndefined();
  });
});
```

- [ ] **Step 8: 跑 memoryStore 测试确认失败**

Run:

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo && npm test -- tests/server/memoryStore.test.ts
```

Expected: FAIL。

- [ ] **Step 9: 实现 server/store/memoryStore.ts**

```ts
/**
 * 进程内数据存储。重启后清空。用于 demo 演示，演示完不留脏数据。
 */
export type ProjectData = {
  id: string;
  title: string;
  style?: "悬疑" | "搞笑" | "深情" | "冷静";
  targetDurationSec?: number;
  audience?: string;
  selectedVoiceId?: string;
  createdAt: number;
};

export type MessageData = {
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  timestamp: number;
  toolName?: string;
};

export type RenderData = {
  renderId: string;
  projectId: string;
  stage: string;
  progress: number;
  startedAt: number;
  finishedAt?: number;
  artifactUrl?: string;
};

const projects = new Map<string, ProjectData>();
const messages = new Map<string, MessageData[]>();
const renders = new Map<string, RenderData>();

export const memoryStore = {
  setProject(id: string, data: Partial<ProjectData> & { id?: string; title?: string }): ProjectData {
    const existing = projects.get(id);
    const merged: ProjectData = {
      id,
      title: data.title ?? existing?.title ?? "未命名项目",
      ...(data.style !== undefined ? { style: data.style } : existing?.style !== undefined ? { style: existing.style } : {}),
      ...(data.targetDurationSec !== undefined ? { targetDurationSec: data.targetDurationSec } : existing?.targetDurationSec !== undefined ? { targetDurationSec: existing.targetDurationSec } : {}),
      ...(data.audience !== undefined ? { audience: data.audience } : existing?.audience !== undefined ? { audience: existing.audience } : {}),
      ...(data.selectedVoiceId !== undefined ? { selectedVoiceId: data.selectedVoiceId } : existing?.selectedVoiceId !== undefined ? { selectedVoiceId: existing.selectedVoiceId } : {}),
      createdAt: existing?.createdAt ?? Date.now(),
    };
    projects.set(id, merged);
    return merged;
  },

  getProject(id: string): ProjectData | undefined {
    return projects.get(id);
  },

  appendMessage(projectId: string, msg: Omit<MessageData, "timestamp">): void {
    const list = messages.get(projectId) ?? [];
    list.push({ ...msg, timestamp: Date.now() });
    messages.set(projectId, list);
  },

  getMessages(projectId: string): MessageData[] {
    return messages.get(projectId) ?? [];
  },

  setRender(renderId: string, data: Partial<RenderData> & { projectId: string }): RenderData {
    const existing = renders.get(renderId);
    const merged: RenderData = {
      renderId,
      projectId: data.projectId,
      stage: data.stage ?? existing?.stage ?? "idle",
      progress: data.progress ?? existing?.progress ?? 0,
      startedAt: existing?.startedAt ?? Date.now(),
      ...(data.finishedAt !== undefined ? { finishedAt: data.finishedAt } : existing?.finishedAt !== undefined ? { finishedAt: existing.finishedAt } : {}),
      ...(data.artifactUrl !== undefined ? { artifactUrl: data.artifactUrl } : existing?.artifactUrl !== undefined ? { artifactUrl: existing.artifactUrl } : {}),
    };
    renders.set(renderId, merged);
    return merged;
  },

  getRender(renderId: string): RenderData | undefined {
    return renders.get(renderId);
  },

  clear(): void {
    projects.clear();
    messages.clear();
    renders.clear();
  },
};
```

- [ ] **Step 10: 跑 memoryStore 测试确认通过**

Run:

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo && npm test -- tests/server/memoryStore.test.ts
```

Expected: 3 tests PASS。

- [ ] **Step 11: 实现 server/store/jobRunner.ts**

```ts
import progressScenarios from "../fixtures/progressScenarios.json" with { type: "json" };

export type ProgressEvent = {
  jobId: string;
  stage: string;
  progress: number;
  timestamp: number;
};

type Listener = (e: ProgressEvent) => void;

const subscribers = new Map<string, Set<Listener>>();

function emit(jobId: string, event: ProgressEvent): void {
  const set = subscribers.get(jobId);
  if (!set) return;
  for (const listener of set) listener(event);
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(new Error("aborted"));
    const t = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(t);
      reject(new Error("aborted"));
    };
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

type JobKind = keyof typeof progressScenarios;

export const jobRunner = {
  async run<T = Record<string, unknown>>(
    jobId: string,
    kind: JobKind,
    _payload: unknown,
    onProgress?: (e: ProgressEvent) => void,
    options: { signal?: AbortSignal } = {},
  ): Promise<{ jobId: string } & T> {
    const scenario = progressScenarios[kind];
    if (!scenario) throw new Error(`Unknown job kind: ${kind}`);

    const fire = (e: ProgressEvent) => {
      emit(jobId, e);
      onProgress?.(e);
    };

    fire({ jobId, stage: "queued", progress: 0, timestamp: Date.now() });

    for (const step of scenario.stages) {
      await sleep(step.durationMs, options.signal);
      fire({ jobId, stage: step.stage, progress: step.progress, timestamp: Date.now() });
    }

    return { jobId } as { jobId: string } & T;
  },

  subscribe(jobId: string, listener: Listener): () => void {
    let set = subscribers.get(jobId);
    if (!set) {
      set = new Set();
      subscribers.set(jobId, set);
    }
    set.add(listener);
    return () => {
      set?.delete(listener);
      if (set && set.size === 0) subscribers.delete(jobId);
    };
  },
};
```

- [ ] **Step 12: 跑 jobRunner 测试确认通过**

Run:

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo && npm test -- tests/server/jobRunner.test.ts
```

Expected: 3 tests PASS。

- [ ] **Step 13: 跑全部测试**

Run:

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo && npm test
```

Expected: 6 tests PASS。

- [ ] **Step 14: TypeScript 检查**

Run:

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo && npm run typecheck
```

Expected: 无错误。

- [ ] **Step 15: Commit**

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo
git add -A
git commit -m "feat: 实现 mock 数据层 memoryStore + jobRunner + fixtures"
```

---

## Task 3: Hono Mock Server 与 8 个 REST 路由

**Files:**
- Create: `server/routes/projects.ts`
- Create: `server/routes/upload.ts`
- Create: `server/routes/analyze.ts`
- Create: `server/routes/script.ts`
- Create: `server/routes/voices.ts`
- Create: `server/routes/render.ts`
- Create: `server/routes/export.ts`
- Create: `server/app.ts`
- Modify: `vite.config.mjs`
- Test: `tests/server/routes.integration.test.ts`

**Interfaces:**
- `POST /api/projects` 创建项目；`GET /api/projects/:id` 获取
- `POST /api/upload` multipart；返回 `{videoId, durationSec, thumbnailUrl}`
- `POST /api/analyze` SSE 推送 analyze_plot 进度，最终返回 sampleAnalysis
- `POST /api/script/generate` SSE；`POST /api/script/edit`；`POST /api/script/regenerate`
- `GET /api/voices?language=zh`
- `POST /api/render/start` 启动；`GET /api/render/:id/status` SSE 推送
- `POST /api/export/jianying` 返回 .zip 文件流

- [ ] **Step 1: 写 server 集成测试失败**

`tests/server/routes.integration.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { app } from "../../server/app";

describe("REST 路由集成", () => {
  it("POST /api/projects 创建并返回", async () => {
    const res = await app.request("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "古墓系列" }),
    });
    expect(res.status).toBe(200);
    const json = (await res.json()) as { id: string; title: string };
    expect(json.title).toBe("古墓系列");
    expect(json.id).toBeTruthy();
  });

  it("GET /api/voices 返回 8 个候选", async () => {
    const res = await app.request("/api/voices");
    const json = (await res.json()) as Array<{ id: string }>;
    expect(json.length).toBe(8);
    expect(json[0]?.id).toBe("morgan");
  });

  it("POST /api/script/edit 修改段落", async () => {
    const create = await app.request("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "t" }),
    });
    const { id } = (await create.json()) as { id: string };
    const res = await app.request("/api/script/edit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ projectId: id, segmentId: "seg-1", newText: "新文案" }),
    });
    expect(res.status).toBe(200);
    const json = (await res.json()) as { segment: { text: string } };
    expect(json.segment.text).toBe("新文案");
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

Run:

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo && npm test -- tests/server/routes.integration.test.ts
```

Expected: FAIL（server/app.ts 不存在）。

- [ ] **Step 3: 实现 server/routes/projects.ts**

```ts
import { Hono } from "hono";
import { memoryStore } from "../store/memoryStore";

export const projectsRoute = new Hono();

projectsRoute.post("/", async (c) => {
  const body = (await c.req.json().catch(() => ({}))) as { title?: string };
  const id = `proj-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const project = memoryStore.setProject(id, { id, title: body.title ?? "未命名项目" });
  return c.json(project);
});

projectsRoute.get("/:id", (c) => {
  const id = c.req.param("id");
  const project = memoryStore.getProject(id);
  if (!project) return c.json({ error: "Project not found" }, 404);
  return c.json(project);
});
```

- [ ] **Step 4: 实现 server/routes/upload.ts**

```ts
import { Hono } from "hono";
import { memoryStore } from "../store/memoryStore";

export const uploadRoute = new Hono();

uploadRoute.post("/", async (c) => {
  const body = (await c.req.parseBody()) as Record<string, string | File>;
  const projectId = typeof body["projectId"] === "string" ? body["projectId"] : "";
  const file = body["file"];
  if (!projectId) return c.json({ error: "projectId required" }, 400);
  if (!(file instanceof File)) return c.json({ error: "file required" }, 400);

  const videoId = `vid-${Date.now()}`;
  const durationSec = 120;
  const idx = ((Date.now() % 3) + 1) as 1 | 2 | 3;
  const thumbnailUrl = `/media/episode-${idx}.mp4`;

  memoryStore.setProject(projectId, { id: projectId, title: file.name.replace(/\.[^.]+$/, "") });
  return c.json({ videoId, durationSec, thumbnailUrl });
});
```

- [ ] **Step 5: 实现 server/routes/analyze.ts**

```ts
import { Hono } from "hono";
import { streamSSE } from "hono/streaming";
import { jobRunner } from "../store/jobRunner";
import sampleAnalysis from "../fixtures/sampleAnalysis.json" with { type: "json" };

export const analyzeRoute = new Hono();

analyzeRoute.post("/", async (c) => {
  const body = (await c.req.json()) as { projectId: string };
  if (!body.projectId) return c.json({ error: "projectId required" }, 400);

  return streamSSE(c, async (stream) => {
    const jobId = `analyze-${Date.now()}`;
    await jobRunner.run(
      jobId,
      "analyze_plot",
      { projectId: body.projectId },
      async (e) => {
        await stream.writeSSE({ event: e.stage, data: JSON.stringify({ progress: e.progress }) });
      },
    );
    await stream.writeSSE({ event: "result", data: JSON.stringify(sampleAnalysis) });
    await stream.close();
  });
});
```

- [ ] **Step 6: 实现 server/routes/script.ts**

```ts
import { Hono } from "hono";
import { streamSSE } from "hono/streaming";
import { jobRunner } from "../store/jobRunner";
import sampleScript from "../fixtures/sampleScript.json" with { type: "json" };

export const scriptRoute = new Hono();

scriptRoute.post("/generate", async (c) => {
  const body = (await c.req.json()) as { projectId: string; style: string; targetSec: number };
  if (!body.projectId) return c.json({ error: "projectId required" }, 400);

  return streamSSE(c, async (stream) => {
    const jobId = `script-${Date.now()}`;
    await jobRunner.run(
      jobId,
      "generate_script",
      { projectId: body.projectId, style: body.style, targetSec: body.targetSec },
      async (e) => {
        await stream.writeSSE({ event: e.stage, data: JSON.stringify({ progress: e.progress }) });
      },
    );
    await stream.writeSSE({ event: "result", data: JSON.stringify(sampleScript) });
    await stream.close();
  });
});

scriptRoute.post("/edit", async (c) => {
  const body = (await c.req.json()) as { projectId: string; segmentId: string; newText: string };
  if (!body.projectId || !body.segmentId) return c.json({ error: "missing fields" }, 400);
  return c.json({
    segment: { id: body.segmentId, start: 0, end: 12, text: body.newText, tone: "紧张" },
  });
});

scriptRoute.post("/regenerate", async (c) => {
  const body = (await c.req.json()) as { projectId: string; segmentId: string; hint?: string };
  if (!body.projectId || !body.segmentId) return c.json({ error: "missing fields" }, 400);
  const newText = body.hint
    ? `[重新生成] 根据提示「${body.hint}」扩展后的版本：深夜，墓门开，林夏只觉背后发凉。`
    : "[重新生成] 重新写一版这一段。";
  return c.json({
    segment: { id: body.segmentId, start: 0, end: 12, text: newText, tone: "悬疑" },
  });
});
```

- [ ] **Step 7: 实现 server/routes/voices.ts**

```ts
import { Hono } from "hono";
import voiceList from "../fixtures/voiceList.json" with { type: "json" };

export const voicesRoute = new Hono();

voicesRoute.get("/", (c) => {
  const language = c.req.query("language");
  if (language === "en") {
    return c.json(voiceList.filter((v) => v.id === "ronin"));
  }
  return c.json(voiceList);
});
```

- [ ] **Step 8: 实现 server/routes/render.ts**

```ts
import { Hono } from "hono";
import { streamSSE } from "hono/streaming";
import { memoryStore } from "../store/memoryStore";
import { jobRunner } from "../store/jobRunner";

export const renderRoute = new Hono();

renderRoute.post("/start", async (c) => {
  const body = (await c.req.json()) as { projectId: string };
  if (!body.projectId) return c.json({ error: "projectId required" }, 400);
  const renderId = `render-${Date.now()}`;
  memoryStore.setRender(renderId, { renderId, projectId: body.projectId, stage: "tts", progress: 0 });
  return c.json({ renderId });
});

renderRoute.get("/:id/status", (c) => {
  const id = c.req.param("id");
  const existing = memoryStore.getRender(id);
  if (!existing) return c.json({ error: "render not found" }, 404);

  return streamSSE(c, async (stream) => {
    if (existing.stage === "done") {
      const url = existing.artifactUrl ?? `/api/export/jianying?renderId=${id}`;
      await stream.writeSSE({ event: "done", data: JSON.stringify({ progress: 1, artifactUrl: url }) });
      await stream.close();
      return;
    }

    await jobRunner.run(
      id,
      "render",
      { projectId: existing.projectId },
      async (e) => {
        memoryStore.setRender(id, { projectId: existing.projectId, stage: e.stage, progress: e.progress });
        if (e.stage === "done") {
          const artifactUrl = `/api/export/jianying?renderId=${id}`;
          memoryStore.setRender(id, { projectId: existing.projectId, stage: "done", progress: 1, artifactUrl });
        }
        await stream.writeSSE({ event: e.stage, data: JSON.stringify({ progress: e.progress, ...(e.stage === "done" ? { artifactUrl: `/api/export/jianying?renderId=${id}` } : {}) }) });
      },
    );
    await stream.close();
  });
});
```

- [ ] **Step 9: 实现 server/routes/export.ts**

```ts
import { Hono } from "hono";
import { BlobReader, BlobWriter, ZipWriter } from "@zip.js/zip.js";
import { memoryStore } from "../store/memoryStore";

export const exportRoute = new Hono();

exportRoute.post("/jianying", async (c) => {
  const body = (await c.req.json().catch(() => ({}))) as { projectId?: string; renderId?: string };
  const project = body.projectId ? memoryStore.getProject(body.projectId) : undefined;
  const render = body.renderId ? memoryStore.getRender(body.renderId) : undefined;

  const manifest = {
    project: project ?? null,
    render: render ?? null,
    exportedAt: new Date().toISOString(),
    note: "mock 导出，仅用于演示",
  };
  const draftContent = {
    timeline: [
      { type: "video", source: "episode-1.mp4", start: 0, end: 60 },
      { type: "narration", start: 0, end: 60, text: "[mock] 这里是解说文本" },
      { type: "voiceover", start: 0, end: 60, voiceId: project?.selectedVoiceId ?? "morgan" },
    ],
  };

  const writer = new ZipWriter(new BlobWriter("application/zip"));
  await writer.add("manifest.json", new BlobReader(new Blob([JSON.stringify(manifest, null, 2)])));
  await writer.add("draft_content.json", new BlobReader(new Blob([JSON.stringify(draftContent, null, 2)])));
  await writer.add("README.txt", new BlobReader(new Blob(["这是 mock 剪映草稿，仅用于演示 vercel-sdk-demo。\n"])));
  const blob = await writer.close();

  return new Response(blob.stream(), {
    headers: {
      "Content-Type": "application/zip",
      "Content-Disposition": `attachment; filename="narrato-mock-${Date.now()}.zip"`,
    },
  });
});
```

- [ ] **Step 10: 实现 server/app.ts**

```ts
import { Hono } from "hono";
import { projectsRoute } from "./routes/projects";
import { uploadRoute } from "./routes/upload";
import { analyzeRoute } from "./routes/analyze";
import { scriptRoute } from "./routes/script";
import { voicesRoute } from "./routes/voices";
import { renderRoute } from "./routes/render";
import { exportRoute } from "./routes/export";

export const app = new Hono()
  .route("/api/projects", projectsRoute)
  .route("/api/upload", uploadRoute)
  .route("/api/analyze", analyzeRoute)
  .route("/api/script", scriptRoute)
  .route("/api/voices", voicesRoute)
  .route("/api/render", renderRoute)
  .route("/api/export", exportRoute);
```

- [ ] **Step 11: 更新 vite.config.mjs 集成 Hono**

```js
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

function honoMockServer() {
  return {
    name: "hono-mock-server",
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        if (!req.url?.startsWith("/api/")) return next();
        try {
          const { app } = await import("./server/app.ts");
          const url = `http://${req.headers.host ?? "localhost"}${req.url}`;
          const headers = new Headers();
          for (const [k, v] of Object.entries(req.headers)) {
            if (Array.isArray(v)) v.forEach((vv) => headers.append(k, vv));
            else if (v != null) headers.set(k, String(v));
          }
          const method = req.method ?? "GET";
          let body;
          if (method !== "GET" && method !== "HEAD") {
            const chunks: Buffer[] = [];
            for await (const chunk of req) chunks.push(chunk as Buffer);
            body = Buffer.concat(chunks);
            if (!headers.has("content-type")) headers.set("content-type", "application/octet-stream");
          }
          const webReq = new Request(url, { method, headers, ...(body !== undefined ? { body } : {}) });
          const webRes = await app.request(webReq);
          res.statusCode = webRes.status;
          webRes.headers.forEach((v, k) => res.setHeader(k, v));
          if (webRes.body) {
            const reader = webRes.body.getReader();
            while (true) {
              const { done, value } = await reader.read();
              if (done) break;
              res.write(Buffer.from(value));
            }
          }
          res.end();
        } catch (err) {
          next(err);
        }
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), honoMockServer()],
  server: { port: 5173, strictPort: true },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
  },
});
```

- [ ] **Step 12: 跑 server 集成测试**

Run:

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo && npm test -- tests/server/routes.integration.test.ts
```

Expected: 3 tests PASS。

- [ ] **Step 13: 启动 dev server 端到端验证 mock 端点**

Run:

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo && nohup npm run dev > /tmp/vercel-sdk-demo-dev.log 2>&1 &
echo $! > /tmp/vercel-sdk-demo-dev.pid
sleep 4
curl -s http://localhost:5173/api/voices | head -c 200
echo ""
```

Expected: 输出 JSON 数组，第一个对象含 `"id":"morgan"`。

- [ ] **Step 14: 验证 export 端点返回 zip**

Run:

```bash
curl -s -X POST -H "Content-Type: application/json" -d '{}' http://localhost:5173/api/export/jianying -o /tmp/test-export.zip
file /tmp/test-export.zip
```

Expected: `file` 命令输出包含 `Zip archive data`。

- [ ] **Step 15: 关闭 dev server**

Run:

```bash
kill $(cat /tmp/vercel-sdk-demo-dev.pid) || true
rm -f /tmp/vercel-sdk-demo-dev.pid /tmp/test-export.zip
```

- [ ] **Step 16: TypeScript 检查**

Run:

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo && npm run typecheck
```

Expected: 无错误。

- [ ] **Step 17: Commit**

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo
git add -A
git commit -m "feat: 实现 8 个 mock REST 端点 + Hono Vite 插件"
```

---

## Task 4: LLM Chat 路由 + Agent 工具定义 + 提示词

**Files:**
- Create: `server/routes/chat.ts`
- Create: `server/llm/agentPrompt.ts`
- Modify: `server/app.ts`
- Create: `src/features/agent/tools.ts`
- Create: `src/features/agent/prompts.ts`
- Test: `tests/server/chat.test.ts`
- Test: `tests/agent/tools.test.ts`

**Interfaces:**
- `POST /api/chat` 接受 `{messages, projectId}`，调用 OpenAI 兼容 LLM，stream 转发给前端。
- `tools.ts` 用 `ai` 的 `tool` 函数 + Zod schema 定义 11 个工具，导出 `allTools` / `toolNames`。
- `prompts.ts` 导出 `systemPrompt` 与 `demoStageHints`。

- [ ] **Step 1: 写 tools 失败测试**

`tests/agent/tools.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { allTools, toolNames } from "../../src/features/agent/tools";

describe("Agent 工具集", () => {
  it("导出 11 个工具", () => {
    expect(Object.keys(allTools).length).toBe(11);
  });

  it("包含全部预期工具名", () => {
    const expected = [
      "upload_video",
      "analyze_plot",
      "set_narration_style",
      "set_target_duration",
      "generate_script",
      "edit_script_segment",
      "regenerate_segment",
      "list_voices",
      "select_voice",
      "start_render",
      "track_render_status",
    ];
    for (const name of expected) {
      expect(toolNames).toContain(name);
    }
  });

  it("每个工具都有 description 和 parameters", () => {
    for (const [name, t] of Object.entries(allTools)) {
      expect(t.description, `${name} 缺 description`).toBeTruthy();
      expect(t.parameters, `${name} 缺 parameters`).toBeDefined();
    }
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

Run:

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo && npm test -- tests/agent/tools.test.ts
```

Expected: FAIL。

- [ ] **Step 3: 实现 src/features/agent/tools.ts**

```ts
import { tool } from "ai";
import { z } from "zod";

export const uploadVideoTool = tool({
  description: "上传用户提供的视频文件，返回视频元信息（videoId、时长、缩略图）。",
  parameters: z.object({
    projectId: z.string().describe("项目 ID"),
    fileName: z.string().describe("原始文件名"),
  }),
  execute: async () => ({ ok: true }),
});

export const analyzePlotTool = tool({
  description: "分析剧情，把视频拆分为 5-8 个场景并提取关键人物。",
  parameters: z.object({ projectId: z.string() }),
  execute: async () => ({ ok: true }),
});

export const setNarrationStyleTool = tool({
  description: "设置解说风格：悬疑 / 搞笑 / 深情 / 冷静。",
  parameters: z.object({
    projectId: z.string(),
    style: z.enum(["悬疑", "搞笑", "深情", "冷静"]),
  }),
  execute: async () => ({ ok: true }),
});

export const setTargetDurationTool = tool({
  description: "设置目标解说时长（秒）。",
  parameters: z.object({ projectId: z.string(), targetSec: z.number().int().min(10).max(300) }),
  execute: async () => ({ ok: true }),
});

export const generateScriptTool = tool({
  description: "根据风格与目标时长生成 5 段解说脚本。",
  parameters: z.object({
    projectId: z.string(),
    style: z.string(),
    targetSec: z.number(),
  }),
  execute: async () => ({ ok: true }),
});

export const editScriptSegmentTool = tool({
  description: "直接修改某一段解说文案。",
  parameters: z.object({
    projectId: z.string(),
    segmentId: z.string(),
    newText: z.string(),
  }),
  execute: async () => ({ ok: true }),
});

export const regenerateSegmentTool = tool({
  description: "重新生成某一段（可带 hint）。",
  parameters: z.object({
    projectId: z.string(),
    segmentId: z.string(),
    hint: z.string().optional(),
  }),
  execute: async () => ({ ok: true }),
});

export const listVoicesTool = tool({
  description: "列出可选音色候选。",
  parameters: z.object({ language: z.enum(["zh", "en"]).optional() }),
  execute: async () => ({ ok: true }),
});

export const selectVoiceTool = tool({
  description: "选定一个音色作为本项目的配音。",
  parameters: z.object({ projectId: z.string(), voiceId: z.string() }),
  execute: async () => ({ ok: true }),
});

export const startRenderTool = tool({
  description: "开始渲染（服务端异步任务）。",
  parameters: z.object({ projectId: z.string() }),
  execute: async () => ({ ok: true }),
});

export const trackRenderStatusTool = tool({
  description: "查询渲染任务状态。",
  parameters: z.object({ renderId: z.string() }),
  execute: async () => ({ ok: true }),
});

export const allTools = {
  upload_video: uploadVideoTool,
  analyze_plot: analyzePlotTool,
  set_narration_style: setNarrationStyleTool,
  set_target_duration: setTargetDurationTool,
  generate_script: generateScriptTool,
  edit_script_segment: editScriptSegmentTool,
  regenerate_segment: regenerateSegmentTool,
  list_voices: listVoicesTool,
  select_voice: selectVoiceTool,
  start_render: startRenderTool,
  track_render_status: trackRenderStatusTool,
};

export const toolNames = Object.keys(allTools);
```

- [ ] **Step 4: 跑 tools 测试确认通过**

Run:

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo && npm test -- tests/agent/tools.test.ts
```

Expected: 3 tests PASS。

- [ ] **Step 5: 实现 src/features/agent/prompts.ts**

```ts
export const systemPrompt = `你是一位短剧解说导演 Agent，名叫 Narrato。你的工作是引导用户一步步完成短剧解说的生成。

## 严格约束
1. 所有回复必须使用中文，简洁自然，单次回复不超过 200 字。
2. 必须使用工具推进流程，禁止用纯文字模拟工具行为。
3. 5 阶段流程：上传 → 分析 → 配置 → 生成脚本 → 选音色 → 渲染。
4. 当用户要求进行某项操作时，先调对应工具，再根据工具结果回复。
5. 出现错误时（如 API key 缺失），用文字如实告知用户。
6. 推荐时给出具体建议而非泛泛而谈。

## 推荐策略
- 默认风格：悬疑（适合大多数短剧）
- 默认时长：60 秒
- 默认音色：根据风格匹配 2-3 个候选

## 回复模板
- 工具成功：1 句确认 + 1 句推进建议 + 最多 2 个建议提示词
- 工具失败：直接展示错误，询问是否继续
`;

export const demoStageHints = {
  upload: ["帮我分析这 3 集短剧", "用 60 秒时长", "目标观众改成中年男性"],
  analyze: ["开始生成脚本", "把第 1 集扩写"],
  configure: ["改成搞笑风格", "目标 90 秒", "观众改成 Z 世代"],
  script: ["第 3 段太短了，扩写一下", "把第 1 段第一句改成悬念开场"],
  voice: ["换温柔女声", "直接用 morgan", "这个男声太年轻了"],
  render: ["开始生成", "导出剪映草稿"],
} as const;
```

- [ ] **Step 6: 实现 server/llm/agentPrompt.ts**

```ts
export const SERVER_SYSTEM_PROMPT = `你是一位短剧解说导演 Agent，名叫 Narrato。你的工作是引导用户一步步完成短剧解说的生成。

## 严格约束
1. 所有回复必须使用中文，简洁自然，单次回复不超过 200 字。
2. 必须使用工具推进流程，禁止用纯文字模拟工具行为。
3. 5 阶段流程：上传 → 分析 → 配置 → 生成脚本 → 选音色 → 渲染。
4. 当用户要求进行某项操作时，先调对应工具，再根据工具结果回复。
5. 出现错误时（如 API key 缺失），用文字如实告知用户。
6. 推荐时给出具体建议而非泛泛而谈。

## 推荐策略
- 默认风格：悬疑
- 默认时长：60 秒
- 默认音色：根据风格匹配 2-3 个候选
`;
```

- [ ] **Step 7: 实现 server/routes/chat.ts**

```ts
import { Hono } from "hono";
import { streamText } from "ai";
import { createOpenAICompatible } from "@ai-sdk/openai-compatible";
import { SERVER_SYSTEM_PROMPT } from "../llm/agentPrompt";

export const chatRoute = new Hono();

chatRoute.post("/", async (c) => {
  const apiKey = process.env["OPENAI_API_KEY"];
  if (!apiKey || apiKey === "sk-your-key-here") {
    return c.json({ error: "OPENAI_API_KEY 未配置，请在 .env 中设置后再启动" }, 401);
  }

  const body = (await c.req.json()) as {
    messages: Array<{ role: string; content: string }>;
    projectId?: string;
  };

  const baseURL = process.env["OPENAI_BASE_URL"] ?? "https://api.openai.com/v1";
  const modelName = process.env["OPENAI_MODEL"] ?? "gpt-4o-mini";

  const openai = createOpenAICompatible({ name: "custom", apiKey, baseURL });

  try {
    const result = streamText({
      model: openai(modelName),
      system: SERVER_SYSTEM_PROMPT,
      messages: body.messages as Array<{ role: "user" | "assistant" | "system"; content: string }>,
    });
    return result.toDataStreamResponse();
  } catch (err) {
    const msg = err instanceof Error ? err.message : "LLM 调用失败";
    return c.json({ error: msg }, 500);
  }
});
```

- [ ] **Step 8: 修改 server/app.ts 挂载 chat 路由**

在 `server/app.ts` 末尾追加 import + 挂载：

```ts
import { chatRoute } from "./routes/chat";
// ... 原内容 ...
  .route("/api/export", exportRoute)
  .route("/api/chat", chatRoute);
```

- [ ] **Step 9: 写 chat 路由测试（mock 环境变量失败分支）**

`tests/server/chat.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { app } from "../../server/app";

describe("chat 路由", () => {
  it("无 API key 时返回 401", async () => {
    const oldKey = process.env["OPENAI_API_KEY"];
    delete process.env["OPENAI_API_KEY"];
    try {
      const res = await app.request("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: [{ role: "user", content: "hi" }] }),
      });
      expect(res.status).toBe(401);
      const json = (await res.json()) as { error: string };
      expect(json.error).toContain("OPENAI_API_KEY");
    } finally {
      if (oldKey) process.env["OPENAI_API_KEY"] = oldKey;
    }
  });
});
```

- [ ] **Step 10: 跑 chat 测试确认通过**

Run:

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo && npm test -- tests/server/chat.test.ts
```

Expected: 1 test PASS。

- [ ] **Step 11: 跑全部测试**

Run:

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo && npm test
```

Expected: 13 tests PASS。

- [ ] **Step 12: TypeScript 检查**

Run:

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo && npm run typecheck
```

Expected: 无错误。

- [ ] **Step 13: Commit**

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo
git add -A
git commit -m "feat: 实现 LLM chat 路由 + 11 个 Agent 工具定义 + 提示词"
```

---

## Task 5: 前端状态层（Zustand store + types + API 库）

**Files:**
- Create: `src/features/project/types.ts`
- Create: `src/features/project/store.ts`
- Create: `src/lib/api.ts`
- Test: `tests/features/store.test.ts`
- Test: `tests/lib/api.test.ts`

**Interfaces:**
- `useProjectStore`：Zustand store，包含 6 个状态字段 + 16 个 setter/reducer action。
- `api.ts`：`postJSON` / `getJSON` / `subscribeSSE`。
- `types.ts`：所有状态类型定义。

- [ ] **Step 1: 创建 src/features/project/types.ts**

```ts
export type NarrationStyle = "悬疑" | "搞笑" | "深情" | "冷静";
export type RenderStage = "idle" | "tts" | "subtitle" | "mixing" | "encoding" | "done" | "failed";

export type Project = {
  id: string;
  title: string;
  style: NarrationStyle;
  targetDurationSec: number;
  audience: string;
};

export type Video = {
  id: string;
  name: string;
  durationSec: number;
  thumbnailUrl: string;
};

export type Scene = {
  start: number;
  end: number;
  summary: string;
  keyCharacters: string[];
};

export type PlotAnalysis = { scenes: Scene[] };

export type ScriptSegment = {
  id: string;
  start: number;
  end: number;
  text: string;
  tone: string;
};

export type Script = { segments: ScriptSegment[] };

export type Voice = {
  id: string;
  name: string;
  gender: "male" | "female";
  age: string;
  tone: string;
};

export type Render = {
  renderId: string | null;
  stage: RenderStage;
  progress: number;
  artifactUrl: string | null;
  artifacts: Array<{ kind: "video" | "audio" | "subtitle" | "draft"; url: string; label: string }>;
};

export type InitialState = {
  project: Project;
  videos: Video[];
  plotAnalysis: PlotAnalysis;
  script: Script;
  voice: { candidates: Voice[]; selected: string | null };
  render: Render;
  banner: { kind: "error" | "warning" | "info"; text: string } | null;
};
```

- [ ] **Step 2: 写 store 失败测试**

`tests/features/store.test.ts`:

```ts
import { describe, it, expect, beforeEach } from "vitest";
import { useProjectStore } from "../../src/features/project/store";

describe("useProjectStore", () => {
  beforeEach(() => {
    useProjectStore.getState().reset();
  });

  it("setStyle 更新项目风格", () => {
    useProjectStore.getState().setStyle("搞笑");
    expect(useProjectStore.getState().project.style).toBe("搞笑");
  });

  it("setTargetDuration 更新目标时长", () => {
    useProjectStore.getState().setTargetDuration(90);
    expect(useProjectStore.getState().project.targetDurationSec).toBe(90);
  });

  it("appendScene 累加场景", () => {
    useProjectStore.getState().appendScene({ start: 0, end: 10, summary: "s1", keyCharacters: [] });
    useProjectStore.getState().appendScene({ start: 10, end: 20, summary: "s2", keyCharacters: [] });
    expect(useProjectStore.getState().plotAnalysis.scenes).toHaveLength(2);
  });

  it("updateSegmentText 改写某段文案", () => {
    useProjectStore.getState().setScriptSegments([
      { id: "a", start: 0, end: 5, text: "old", tone: "紧张" },
    ]);
    useProjectStore.getState().updateSegmentText("a", "new");
    expect(useProjectStore.getState().script.segments[0]?.text).toBe("new");
  });

  it("setBanner 设置后能被 clearBanner 清空", () => {
    useProjectStore.getState().setBanner("error", "出错");
    expect(useProjectStore.getState().banner?.text).toBe("出错");
    useProjectStore.getState().clearBanner();
    expect(useProjectStore.getState().banner).toBeNull();
  });
});
```

- [ ] **Step 3: 跑测试确认失败**

Run:

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo && npm test -- tests/features/store.test.ts
```

Expected: FAIL（store.ts 不存在）。

- [ ] **Step 4: 实现 src/features/project/store.ts**

```ts
import { create } from "zustand";
import type {
  InitialState,
  NarrationStyle,
  PlotAnalysis,
  RenderStage,
  Scene,
  ScriptSegment,
  Voice,
} from "./types";

const initial: InitialState = {
  project: { id: "demo-project", title: "新项目", style: "悬疑", targetDurationSec: 60, audience: "通用" },
  videos: [],
  plotAnalysis: { scenes: [] },
  script: { segments: [] },
  voice: { candidates: [], selected: null },
  render: { renderId: null, stage: "idle", progress: 0, artifactUrl: null, artifacts: [] },
  banner: null,
};

export const useProjectStore = create<InitialState & {
  setStyle: (style: NarrationStyle) => void;
  setTargetDuration: (sec: number) => void;
  setAudience: (audience: string) => void;
  setTitle: (title: string) => void;
  addVideo: (v: InitialState["videos"][number]) => void;
  setPlotAnalysis: (a: PlotAnalysis) => void;
  appendScene: (s: Scene) => void;
  setScriptSegments: (segs: ScriptSegment[]) => void;
  updateSegmentText: (id: string, text: string) => void;
  setVoiceCandidates: (vs: Voice[]) => void;
  selectVoice: (id: string) => void;
  setRenderStart: (renderId: string) => void;
  setRenderProgress: (stage: RenderStage, progress: number) => void;
  setRenderArtifact: (url: string) => void;
  setBanner: (kind: "error" | "warning" | "info", text: string) => void;
  clearBanner: () => void;
  reset: () => void;
}>((set) => ({
  ...initial,
  setStyle: (style) => set((s) => ({ project: { ...s.project, style } })),
  setTargetDuration: (sec) => set((s) => ({ project: { ...s.project, targetDurationSec: sec } })),
  setAudience: (audience) => set((s) => ({ project: { ...s.project, audience } })),
  setTitle: (title) => set((s) => ({ project: { ...s.project, title } })),
  addVideo: (v) => set((s) => ({ videos: [...s.videos, v] })),
  setPlotAnalysis: (a) => set({ plotAnalysis: a }),
  appendScene: (s2) => set((s) => ({ plotAnalysis: { scenes: [...s.plotAnalysis.scenes, s2] } })),
  setScriptSegments: (segs) => set({ script: { segments: segs } }),
  updateSegmentText: (id, text) =>
    set((s) => ({
      script: { segments: s.script.segments.map((seg) => (seg.id === id ? { ...seg, text } : seg)) },
    })),
  setVoiceCandidates: (vs) => set((s) => ({ voice: { ...s.voice, candidates: vs } })),
  selectVoice: (id) => set((s) => ({ voice: { ...s.voice, selected: id } })),
  setRenderStart: (renderId) =>
    set({ render: { renderId, stage: "tts", progress: 0, artifactUrl: null, artifacts: [] } }),
  setRenderProgress: (stage, progress) => set((s) => ({ render: { ...s.render, stage, progress } })),
  setRenderArtifact: (url) =>
    set((s) => ({
      render: {
        ...s.render,
        artifactUrl: url,
        artifacts: [...s.render.artifacts, { kind: "draft", url, label: "剪映草稿 zip" }],
      },
    })),
  setBanner: (kind, text) => set({ banner: { kind, text } }),
  clearBanner: () => set({ banner: null }),
  reset: () => set(initial),
}));
```

- [ ] **Step 5: 跑 store 测试确认通过**

Run:

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo && npm test -- tests/features/store.test.ts
```

Expected: 5 tests PASS。

- [ ] **Step 6: 写 api 库失败测试**

`tests/lib/api.test.ts`:

```ts
import { describe, it, expect, vi, afterEach } from "vitest";
import { postJSON } from "../../src/lib/api";

describe("api.postJSON", () => {
  afterEach(() => vi.restoreAllMocks());

  it("成功时返回 JSON", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "content-type": "application/json" } }),
      ),
    );
    const r = await postJSON<{ ok: boolean }>("/api/test", {});
    expect(r.ok).toBe(true);
  });

  it("失败时抛出带状态码的错误", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("bad", { status: 400 })));
    await expect(postJSON("/api/test", {})).rejects.toThrow(/400/);
  });
});
```

- [ ] **Step 7: 跑测试确认失败**

Run:

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo && npm test -- tests/lib/api.test.ts
```

Expected: FAIL。

- [ ] **Step 8: 实现 src/lib/api.ts**

```ts
export async function postJSON<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
  return (await res.json()) as T;
}

export async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
  return (await res.json()) as T;
}

const KNOWN_EVENTS = [
  "queued",
  "uploading",
  "asr",
  "summarizing",
  "drafting",
  "refining",
  "tts",
  "subtitle",
  "mixing",
  "encoding",
  "done",
  "result",
];

/**
 * 订阅 SSE 流。返回 unsubscribe 函数。
 */
export function subscribeSSE(url: string, onEvent: (event: string, data: unknown) => void): () => void {
  const es = new EventSource(url);
  const handle = (e: MessageEvent) => {
    try {
      onEvent(e.type, JSON.parse(e.data));
    } catch {
      onEvent(e.type, e.data);
    }
  };
  for (const name of KNOWN_EVENTS) {
    es.addEventListener(name, handle as EventListener);
  }
  return () => {
    for (const name of KNOWN_EVENTS) es.removeEventListener(name, handle as EventListener);
    es.close();
  };
}
```

- [ ] **Step 9: 跑 api 测试确认通过**

Run:

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo && npm test -- tests/lib/api.test.ts
```

Expected: 2 tests PASS。

- [ ] **Step 10: 跑全部测试**

Run:

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo && npm test
```

Expected: 20 tests PASS。

- [ ] **Step 11: TypeScript 检查**

Run:

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo && npm run typecheck
```

Expected: 无错误。

- [ ] **Step 12: Commit**

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo
git add -A
git commit -m "feat: 实现 Zustand store + types + api 工具（SSE 订阅）"
```

---

## Task 6: Chat 面板组件群（5 个组件 + useWorkbench hook）

**Files:**
- Create: `src/features/agent/useWorkbench.ts`
- Create: `src/components/chat/ChatPanel.tsx`
- Create: `src/components/chat/ChatMessage.tsx`
- Create: `src/components/chat/ToolCallCard.tsx`
- Create: `src/components/chat/ScriptSegmentCard.tsx`
- Create: `src/components/chat/ChatComposer.tsx`
- Create: `src/styles/chat.css`
- Test: `tests/components/ChatPanel.test.tsx`
- Test: `tests/components/ToolCallCard.test.tsx`

**Interfaces:**
- `useWorkbench(projectId)`：包装 `useChat`，配置 `api: '/api/chat'`，onToolCall 中执行 mock API 并 addToolResult。
- `ChatPanel`：列出 messages + composer。
- `ToolCallCard`：展示工具名 + 折叠/展开结果。
- `ScriptSegmentCard`：可点击编辑的脚本段卡片。
- `ChatComposer`：输入框 + 附件 + 建议提示词 chips。

- [ ] **Step 1: 实现 src/features/agent/useWorkbench.ts**

```ts
import { useChat } from "@ai-sdk/react";
import { useProjectStore } from "../project/store";
import { getJSON, postJSON, subscribeSSE } from "../../lib/api";
import type { ScriptSegment, Voice } from "../project/types";

export function useWorkbench(projectId: string) {
  const setStyle = useProjectStore((s) => s.setStyle);
  const setTargetDuration = useProjectStore((s) => s.setTargetDuration);
  const setPlotAnalysis = useProjectStore((s) => s.setPlotAnalysis);
  const setScriptSegments = useProjectStore((s) => s.setScriptSegments);
  const updateSegmentText = useProjectStore((s) => s.updateSegmentText);
  const setVoiceCandidates = useProjectStore((s) => s.setVoiceCandidates);
  const selectVoice = useProjectStore((s) => s.selectVoice);
  const setRenderStart = useProjectStore((s) => s.setRenderStart);
  const setRenderProgress = useProjectStore((s) => s.setRenderProgress);
  const setRenderArtifact = useProjectStore((s) => s.setRenderArtifact);
  const setBanner = useProjectStore((s) => s.setBanner);

  return useChat({
    api: "/api/chat",
    body: { projectId },
    onError: (err) => setBanner("error", `LLM 错误：${err.message}`),
    onToolCall: async ({ toolCall }) => {
      const { toolName, args } = toolCall;
      try {
        switch (toolName) {
          case "set_narration_style": {
            const a = args as { style: "悬疑" | "搞笑" | "深情" | "冷静" };
            setStyle(a.style);
            return { ok: true, style: a.style };
          }
          case "set_target_duration": {
            const a = args as { targetSec: number };
            setTargetDuration(a.targetSec);
            return { ok: true, targetSec: a.targetSec };
          }
          case "analyze_plot": {
            const a = args as { projectId: string };
            return new Promise<{ ok: boolean }>((resolve) => {
              subscribeSSE("/api/analyze", (event, data) => {
                if (event === "result") {
                  const d = data as { scenes: import("../project/types").Scene[] };
                  setPlotAnalysis({ scenes: d.scenes });
                  resolve({ ok: true });
                }
              });
              postJSON("/api/analyze", { projectId: a.projectId }).catch((err) => {
                setBanner("error", `分析失败：${err.message}`);
                resolve({ ok: false });
              });
            });
          }
          case "generate_script": {
            const a = args as { projectId: string; style: string; targetSec: number };
            return new Promise<{ ok: boolean }>((resolve) => {
              subscribeSSE("/api/script/generate", (event, data) => {
                if (event === "result") {
                  setScriptSegments(data as ScriptSegment[]);
                  resolve({ ok: true });
                }
              });
              postJSON("/api/script/generate", a).catch((err) => {
                setBanner("error", `脚本生成失败：${err.message}`);
                resolve({ ok: false });
              });
            });
          }
          case "edit_script_segment": {
            const a = args as { projectId: string; segmentId: string; newText: string };
            updateSegmentText(a.segmentId, a.newText);
            const r = await postJSON<{ segment: ScriptSegment }>("/api/script/edit", a);
            return { ok: true, segment: r.segment };
          }
          case "regenerate_segment": {
            const a = args as { projectId: string; segmentId: string; hint?: string };
            const r = await postJSON<{ segment: ScriptSegment }>("/api/script/regenerate", a);
            updateSegmentText(a.segmentId, r.segment.text);
            return { ok: true, segment: r.segment };
          }
          case "list_voices": {
            const a = (args as { language?: "zh" | "en" }) ?? {};
            const url = a.language ? `/api/voices?language=${a.language}` : "/api/voices";
            const voices = await getJSON<Voice[]>(url);
            setVoiceCandidates(voices);
            return { ok: true, voices };
          }
          case "select_voice": {
            const a = args as { projectId: string; voiceId: string };
            selectVoice(a.voiceId);
            return { ok: true, voiceId: a.voiceId };
          }
          case "start_render": {
            const a = args as { projectId: string };
            const r = await postJSON<{ renderId: string }>("/api/render/start", a);
            setRenderStart(r.renderId);
            subscribeSSE(`/api/render/${r.renderId}/status`, (event, data) => {
              const d = data as { progress: number; artifactUrl?: string };
              if (event === "done") {
                setRenderProgress("done", 1);
                if (d.artifactUrl) setRenderArtifact(d.artifactUrl);
              } else {
                setRenderProgress(event as "tts" | "subtitle" | "mixing" | "encoding", d.progress);
              }
            });
            return { ok: true, renderId: r.renderId };
          }
          case "track_render_status": {
            const a = args as { renderId: string };
            return new Promise<{ ok: boolean }>((resolve) => {
              subscribeSSE(`/api/render/${a.renderId}/status`, (event, data) => {
                const d = data as { progress: number };
                if (event === "done") {
                  setRenderProgress("done", 1);
                  resolve({ ok: true });
                } else {
                  setRenderProgress(event as "tts" | "subtitle" | "mixing" | "encoding", d.progress);
                }
              });
            });
          }
          default:
            return { ok: false, error: `Unknown tool: ${toolName}` };
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : "工具执行失败";
        setBanner("error", `${toolName} 失败：${msg}`);
        return { ok: false, error: msg };
      }
    },
  });
}
```

- [ ] **Step 2: 实现 src/components/chat/ChatMessage.tsx**

```tsx
import type { Message } from "@ai-sdk/react";
import { ToolCallCard } from "./ToolCallCard";
import { ScriptSegmentCard } from "./ScriptSegmentCard";
import type { ScriptSegment } from "../../features/project/types";

type Props = { message: Message };

export function ChatMessage({ message }: Props) {
  const isUser = message.role === "user";
  return (
    <div className={`chat-msg chat-msg--${message.role}`}>
      <div className="chat-msg__avatar">{isUser ? "你" : "AI"}</div>
      <div className="chat-msg__body">
        {message.content && <p className="chat-msg__text">{message.content}</p>}
        {message.toolInvocations?.map((inv) => {
          if (inv.state === "result" && inv.result && Array.isArray((inv.result as { segments?: unknown[] }).segments)) {
            return (
              <ScriptSegmentCard
                key={inv.toolCallId}
                segments={(inv.result as { segments: ScriptSegment[] }).segments}
              />
            );
          }
          return <ToolCallCard key={inv.toolCallId} toolName={inv.toolName ?? "?"} state={inv.state} result={inv.result} />;
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: 实现 src/components/chat/ToolCallCard.tsx**

```tsx
import { useState } from "react";

type Props = {
  toolName: string;
  state: "call" | "partial-call" | "result";
  result?: unknown;
};

const LABEL: Record<string, string> = {
  upload_video: "上传视频",
  analyze_plot: "分析剧情",
  set_narration_style: "设置解说风格",
  set_target_duration: "设置目标时长",
  generate_script: "生成脚本",
  edit_script_segment: "修改段落",
  regenerate_segment: "重新生成段落",
  list_voices: "查询音色",
  select_voice: "选定音色",
  start_render: "开始渲染",
  track_render_status: "查询渲染状态",
};

export function ToolCallCard({ toolName, state, result }: Props) {
  const [open, setOpen] = useState(false);
  const label = LABEL[toolName] ?? toolName;
  const isError = state === "result" && result && typeof result === "object" && "ok" in result && (result as { ok: boolean }).ok === false;
  return (
    <div className={`tool-card ${isError ? "tool-card--error" : ""}`}>
      <button type="button" className="tool-card__head" onClick={() => setOpen((o) => !o)}>
        <span className="tool-card__dot" />
        <span className="tool-card__name">{label}</span>
        <span className="tool-card__state">{state === "result" ? "完成" : "执行中…"}</span>
      </button>
      {open && <pre className="tool-card__body">{JSON.stringify(result ?? null, null, 2)}</pre>}
    </div>
  );
}
```

- [ ] **Step 4: 实现 src/components/chat/ScriptSegmentCard.tsx**

```tsx
import { useState } from "react";
import type { ScriptSegment } from "../../features/project/types";
import { useProjectStore } from "../../features/project/store";

type Props = { segments: ScriptSegment[] };

export function ScriptSegmentCard({ segments }: Props) {
  const update = useProjectStore((s) => s.updateSegmentText);
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");

  return (
    <div className="script-card">
      <div className="script-card__title">解说脚本（{segments.length} 段）</div>
      {segments.map((seg) => (
        <div key={seg.id} className="script-card__row">
          <span className="script-card__idx">{seg.id}</span>
          {editing === seg.id ? (
            <>
              <input className="script-card__input" value={draft} onChange={(e) => setDraft(e.target.value)} />
              <button type="button" onClick={() => { update(seg.id, draft); setEditing(null); }}>保存</button>
              <button type="button" onClick={() => setEditing(null)}>取消</button>
            </>
          ) : (
            <>
              <span className="script-card__text">{seg.text}</span>
              <button type="button" onClick={() => { setEditing(seg.id); setDraft(seg.text); }}>改</button>
            </>
          )}
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 5: 实现 src/components/chat/ChatComposer.tsx**

```tsx
import { useState } from "react";
import { demoStageHints } from "../../features/agent/prompts";

type Props = {
  onSend: (text: string, file?: File) => void;
  disabled?: boolean;
};

const STAGE_HINTS = [
  ...demoStageHints.upload,
  ...demoStageHints.script,
  ...demoStageHints.voice,
  ...demoStageHints.render,
];

export function ChatComposer({ onSend, disabled }: Props) {
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);

  const handleSend = () => {
    if (!text.trim() && !file) return;
    onSend(text, file ?? undefined);
    setText("");
    setFile(null);
  };

  return (
    <div className="composer">
      <div className="composer__hints">
        {STAGE_HINTS.map((h) => (
          <button key={h} type="button" className="composer__chip" onClick={() => onSend(h)}>
            {h}
          </button>
        ))}
      </div>
      <div className="composer__row">
        <input type="file" accept="video/mp4" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <input
          className="composer__input"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="告诉 Narrato 你想做什么…"
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
        />
        <button type="button" onClick={handleSend} disabled={disabled || (!text.trim() && !file)}>发送</button>
      </div>
      {file && <div className="composer__file">已选：{file.name}</div>}
    </div>
  );
}
```

- [ ] **Step 6: 实现 src/components/chat/ChatPanel.tsx**

```tsx
import { useEffect, useRef } from "react";
import { ChatMessage } from "./ChatMessage";
import { ChatComposer } from "./ChatComposer";
import { useWorkbench } from "../../features/agent/useWorkbench";
import { useProjectStore } from "../../features/project/store";

type Props = { projectId: string };

export function ChatPanel({ projectId }: Props) {
  const banner = useProjectStore((s) => s.banner);
  const clearBanner = useProjectStore((s) => s.clearBanner);
  const { messages, status, append } = useWorkbench(projectId);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <section className="chat-panel">
      {banner && (
        <div className={`chat-banner chat-banner--${banner.kind}`}>
          <span>{banner.text}</span>
          <button type="button" onClick={clearBanner}>×</button>
        </div>
      )}
      <div className="chat-panel__list">
        {messages.length === 0 && (
          <div className="chat-empty">
            <p>👋 你好，我是 Narrato。</p>
            <p>告诉我你想做什么，例如"帮我分析这 3 集短剧"。</p>
          </div>
        )}
        {messages.map((m) => <ChatMessage key={m.id} message={m} />)}
        <div ref={bottomRef} />
      </div>
      <ChatComposer
        onSend={(text, file) => {
          if (file) void append({ role: "user", content: `${text}（已上传 ${file.name}）` });
          else void append({ role: "user", content: text });
        }}
        disabled={status !== "ready"}
      />
    </section>
  );
}
```

- [ ] **Step 7: 实现 src/styles/chat.css**

```css
.chat-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-surface);
  border-right: 1px solid var(--border-subtle);
}
.chat-banner {
  display: flex; align-items: center; justify-content: space-between;
  padding: var(--space-2) var(--space-3); font-size: var(--font-sm);
}
.chat-banner--error { background: rgba(239, 68, 68, 0.15); color: var(--error); }
.chat-banner--warning { background: rgba(245, 158, 11, 0.15); color: var(--warning); }
.chat-banner--info { background: rgba(6, 182, 212, 0.15); color: var(--accent-cyan); }
.chat-banner button { background: transparent; border: none; color: inherit; cursor: pointer; }
.chat-panel__list {
  flex: 1; overflow-y: auto; padding: var(--space-3);
  display: flex; flex-direction: column; gap: var(--space-3);
}
.chat-empty {
  color: var(--text-muted); text-align: center;
  margin-top: var(--space-6); font-size: var(--font-sm);
}
.chat-msg { display: flex; gap: var(--space-2); }
.chat-msg__avatar {
  width: 28px; height: 28px; border-radius: 50%;
  background: var(--bg-elevated);
  display: flex; align-items: center; justify-content: center;
  font-size: var(--font-xs); flex-shrink: 0;
}
.chat-msg--user .chat-msg__avatar { background: var(--accent-neon); }
.chat-msg__body { flex: 1; min-width: 0; }
.chat-msg__text { margin: 0; line-height: 1.5; }
.tool-card {
  margin-top: var(--space-2); background: var(--bg-elevated);
  border: 1px solid var(--border-subtle); border-radius: var(--radius-md); overflow: hidden;
}
.tool-card--error { border-color: var(--error); }
.tool-card__head {
  display: flex; align-items: center; gap: var(--space-2);
  width: 100%; padding: var(--space-2) var(--space-3);
  background: transparent; border: none; color: inherit; cursor: pointer; font-size: var(--font-sm);
}
.tool-card__dot { width: 8px; height: 8px; border-radius: 50%; background: var(--accent-cyan); }
.tool-card__name { flex: 1; text-align: left; }
.tool-card__state { color: var(--text-muted); }
.tool-card__body {
  margin: 0; padding: var(--space-2) var(--space-3);
  font-size: var(--font-xs); color: var(--text-secondary);
  border-top: 1px solid var(--border-subtle);
  white-space: pre-wrap; word-break: break-all;
}
.script-card {
  margin-top: var(--space-2); background: var(--bg-elevated);
  border: 1px solid var(--border-subtle); border-radius: var(--radius-md);
  padding: var(--space-3);
}
.script-card__title { font-size: var(--font-sm); color: var(--text-secondary); margin-bottom: var(--space-2); }
.script-card__row {
  display: flex; align-items: center; gap: var(--space-2);
  padding: var(--space-1) 0; font-size: var(--font-sm);
}
.script-card__idx { color: var(--text-muted); min-width: 50px; }
.script-card__text { flex: 1; }
.script-card__input {
  flex: 1; background: var(--bg-base); color: var(--text-primary);
  border: 1px solid var(--border-subtle); border-radius: var(--radius-sm);
  padding: var(--space-1) var(--space-2);
}
.composer {
  border-top: 1px solid var(--border-subtle);
  padding: var(--space-3); background: var(--bg-surface);
}
.composer__hints { display: flex; flex-wrap: wrap; gap: var(--space-1); margin-bottom: var(--space-2); }
.composer__chip {
  padding: 2px var(--space-2); border-radius: var(--radius-sm);
  border: 1px solid var(--border-subtle); background: var(--bg-elevated);
  color: var(--text-secondary); font-size: var(--font-xs); cursor: pointer;
}
.composer__chip:hover { color: var(--accent-cyan); border-color: var(--accent-cyan); }
.composer__row { display: flex; gap: var(--space-2); }
.composer__input {
  flex: 1; background: var(--bg-elevated); color: var(--text-primary);
  border: 1px solid var(--border-subtle); border-radius: var(--radius-md);
  padding: var(--space-2) var(--space-3); font-size: var(--font-sm);
}
.composer__file { font-size: var(--font-xs); color: var(--accent-cyan); margin-top: var(--space-1); }
```

- [ ] **Step 8: 写 ToolCallCard 组件测试**

`tests/components/ToolCallCard.test.tsx`:

```tsx
import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ToolCallCard } from "../../src/components/chat/ToolCallCard";

describe("ToolCallCard", () => {
  it("默认折叠，点击 head 展开", () => {
    render(<ToolCallCard toolName="analyze_plot" state="result" result={{ ok: true, scenes: [] }} />);
    expect(screen.queryByText(/ok/i)).toBeNull();
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText(/"ok":\s*true/)).toBeTruthy();
  });

  it("错误时显示 error 样式", () => {
    const { container } = render(<ToolCallCard toolName="x" state="result" result={{ ok: false }} />);
    expect(container.querySelector(".tool-card--error")).toBeTruthy();
  });
});
```

- [ ] **Step 9: 跑 ToolCallCard 测试**

Run:

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo && npm test -- tests/components/ToolCallCard.test.tsx
```

Expected: 2 tests PASS。

- [ ] **Step 10: 写 ChatPanel 渲染测试（mock useWorkbench）**

`tests/components/ChatPanel.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("../../src/features/agent/useWorkbench", () => ({
  useWorkbench: () => ({
    messages: [
      { id: "1", role: "user", content: "你好", toolInvocations: [] },
      { id: "2", role: "assistant", content: "你好！", toolInvocations: [] },
    ],
    input: "",
    handleInputChange: vi.fn(),
    handleSubmit: vi.fn(),
    status: "ready",
    append: vi.fn(),
  }),
}));

import { ChatPanel } from "../../src/components/chat/ChatPanel";

describe("ChatPanel", () => {
  it("渲染用户与 AI 消息", () => {
    render(<ChatPanel projectId="p1" />);
    expect(screen.getByText("你好")).toBeTruthy();
    expect(screen.getByText("你好！")).toBeTruthy();
  });
});
```

- [ ] **Step 11: 跑 ChatPanel 测试**

Run:

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo && npm test -- tests/components/ChatPanel.test.tsx
```

Expected: 1 test PASS。

- [ ] **Step 12: 跑全部测试**

Run:

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo && npm test
```

Expected: 23 tests PASS。

- [ ] **Step 13: TypeScript 检查**

Run:

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo && npm run typecheck
```

Expected: 无错误。

- [ ] **Step 14: Commit**

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo
git add -A
git commit -m "feat: 实现 Chat 面板 5 个组件 + useWorkbench hook"
```

---

## Task 7: Preview + Inspector + WorkbenchPage + 样式

**Files:**
- Create: `src/components/preview/PreviewPanel.tsx`
- Create: `src/components/preview/VideoPlayer.tsx`
- Create: `src/components/preview/RenderProgress.tsx`
- Create: `src/components/preview/ArtifactList.tsx`
- Create: `src/components/inspector/InspectorPanel.tsx`
- Create: `src/components/inspector/ProjectInfoCard.tsx`
- Create: `src/components/inspector/PlotAnalysisCard.tsx`
- Create: `src/components/inspector/ScriptSegmentsCard.tsx`
- Create: `src/components/inspector/VoiceSelectionCard.tsx`
- Create: `src/components/inspector/RenderStatusCard.tsx`
- Create: `src/components/shared/CollapsibleCard.tsx`
- Create: `src/components/shared/EmptyState.tsx`
- Create: `src/pages/WorkbenchPage.tsx`
- Create: `src/styles/workbench.css`
- Modify: `src/App.tsx`
- Test: `tests/components/InspectorPanel.test.tsx`

- [ ] **Step 1: 实现 src/components/shared/CollapsibleCard.tsx**

```tsx
import { useState, type ReactNode } from "react";

type Props = {
  title: string;
  defaultOpen?: boolean;
  children: ReactNode;
  badge?: string;
};

export function CollapsibleCard({ title, defaultOpen = true, children, badge }: Props) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="c-card">
      <button type="button" className="c-card__head" onClick={() => setOpen((o) => !o)}>
        <span className="c-card__title">{title}</span>
        {badge && <span className="c-card__badge">{badge}</span>}
        <span className="c-card__caret">{open ? "▾" : "▸"}</span>
      </button>
      {open && <div className="c-card__body">{children}</div>}
    </div>
  );
}
```

- [ ] **Step 2: 实现 src/components/shared/EmptyState.tsx**

```tsx
type Props = { icon?: string; text: string };

export function EmptyState({ icon = "📭", text }: Props) {
  return (
    <div className="empty-state">
      <div className="empty-state__icon">{icon}</div>
      <div className="empty-state__text">{text}</div>
    </div>
  );
}
```

- [ ] **Step 3: 实现 src/components/preview/VideoPlayer.tsx**

```tsx
import { useProjectStore } from "../../features/project/store";

export function VideoPlayer() {
  const videos = useProjectStore((s) => s.videos);
  const render = useProjectStore((s) => s.render);
  const first = videos[0];
  const src = render.artifactUrl ? render.artifactUrl : first ? `/media/episode-${(Date.now() % 3) + 1}.mp4` : null;

  if (!src) return <div className="player player--empty">等待视频上传…</div>;
  return (
    <div className="player">
      <video src={src} controls className="player__video" />
      <div className="player__caption">{render.artifactUrl ? "渲染产出" : first?.name ?? "视频"}</div>
    </div>
  );
}
```

- [ ] **Step 4: 实现 src/components/preview/RenderProgress.tsx**

```tsx
import { useProjectStore } from "../../features/project/store";

const STAGE_LABEL: Record<string, string> = {
  idle: "未开始",
  tts: "配音合成",
  subtitle: "字幕烧录",
  mixing: "音视频混流",
  encoding: "编码输出",
  done: "完成",
  failed: "失败",
};

export function RenderProgress() {
  const { stage, progress } = useProjectStore((s) => s.render);
  const pct = Math.round(progress * 100);
  return (
    <div className="render-progress">
      <div className="render-progress__stage">{STAGE_LABEL[stage] ?? stage}</div>
      <div className="render-progress__bar">
        <div className="render-progress__fill" style={{ width: `${pct}%` }} />
      </div>
      <div className="render-progress__pct">{pct}%</div>
    </div>
  );
}
```

- [ ] **Step 5: 实现 src/components/preview/ArtifactList.tsx**

```tsx
import { useProjectStore } from "../../features/project/store";

export function ArtifactList() {
  const artifacts = useProjectStore((s) => s.render.artifacts);
  if (artifacts.length === 0) {
    return <div className="artifact-list artifact-list--empty">渲染完成后这里会列出产物</div>;
  }
  return (
    <ul className="artifact-list">
      {artifacts.map((a) => (
        <li key={a.url} className="artifact-list__row">
          <span>{a.label}</span>
          <a href={a.url} target="_blank" rel="noreferrer">下载</a>
        </li>
      ))}
    </ul>
  );
}
```

- [ ] **Step 6: 实现 src/components/preview/PreviewPanel.tsx**

```tsx
import { useProjectStore } from "../../features/project/store";
import { VideoPlayer } from "./VideoPlayer";
import { RenderProgress } from "./RenderProgress";
import { ArtifactList } from "./ArtifactList";

export function PreviewPanel() {
  const stage = useProjectStore((s) => s.render.stage);
  return (
    <section className="preview-panel">
      {stage === "idle" && <VideoPlayer />}
      {(stage === "tts" || stage === "subtitle" || stage === "mixing" || stage === "encoding") && (
        <>
          <VideoPlayer />
          <RenderProgress />
        </>
      )}
      {stage === "done" && (
        <>
          <RenderProgress />
          <ArtifactList />
        </>
      )}
    </section>
  );
}
```

- [ ] **Step 7: 实现 src/components/inspector/ProjectInfoCard.tsx**

```tsx
import { CollapsibleCard } from "../shared/CollapsibleCard";
import { useProjectStore } from "../../features/project/store";

export function ProjectInfoCard() {
  const { project, videos } = useProjectStore((s) => ({ project: s.project, videos: s.videos }));
  return (
    <CollapsibleCard title="项目信息" badge={videos.length > 0 ? `${videos.length} 个视频` : undefined}>
      <div className="kv"><span>标题</span><b>{project.title}</b></div>
      <div className="kv"><span>风格</span><b>{project.style}</b></div>
      <div className="kv"><span>目标时长</span><b>{project.targetDurationSec} 秒</b></div>
      <div className="kv"><span>目标观众</span><b>{project.audience}</b></div>
    </CollapsibleCard>
  );
}
```

- [ ] **Step 8: 实现 src/components/inspector/PlotAnalysisCard.tsx**

```tsx
import { CollapsibleCard } from "../shared/CollapsibleCard";
import { EmptyState } from "../shared/EmptyState";
import { useProjectStore } from "../../features/project/store";

export function PlotAnalysisCard() {
  const scenes = useProjectStore((s) => s.plotAnalysis.scenes);
  return (
    <CollapsibleCard title="剧情分析" badge={scenes.length > 0 ? `${scenes.length} 段` : undefined}>
      {scenes.length === 0 ? (
        <EmptyState icon="🎬" text="上传视频后开始分析" />
      ) : (
        <ul className="scene-list">
          {scenes.map((s, i) => (
            <li key={`${s.start}-${i}`} className="scene-list__row">
              <div className="scene-list__time">{s.start}–{s.end}s</div>
              <div className="scene-list__summary">{s.summary}</div>
              {s.keyCharacters.length > 0 && (
                <div className="scene-list__chars">人物：{s.keyCharacters.join("、")}</div>
              )}
            </li>
          ))}
        </ul>
      )}
    </CollapsibleCard>
  );
}
```

- [ ] **Step 9: 实现 src/components/inspector/ScriptSegmentsCard.tsx**

```tsx
import { CollapsibleCard } from "../shared/CollapsibleCard";
import { EmptyState } from "../shared/EmptyState";
import { useProjectStore } from "../../features/project/store";

export function ScriptSegmentsCard() {
  const segments = useProjectStore((s) => s.script.segments);
  return (
    <CollapsibleCard title="解说脚本" badge={segments.length > 0 ? `${segments.length} 段` : undefined}>
      {segments.length === 0 ? (
        <EmptyState icon="📝" text="先生成脚本" />
      ) : (
        <ul className="insp-seg-list">
          {segments.map((seg) => (
            <li key={seg.id} className="insp-seg-list__row">
              <div className="insp-seg-list__head">
                <span>{seg.id}</span>
                <span>{seg.start}–{seg.end}s · {seg.tone}</span>
              </div>
              <p>{seg.text}</p>
            </li>
          ))}
        </ul>
      )}
    </CollapsibleCard>
  );
}
```

- [ ] **Step 10: 实现 src/components/inspector/VoiceSelectionCard.tsx**

```tsx
import { CollapsibleCard } from "../shared/CollapsibleCard";
import { EmptyState } from "../shared/EmptyState";
import { useProjectStore } from "../../features/project/store";

export function VoiceSelectionCard() {
  const { candidates, selected } = useProjectStore((s) => s.voice);
  const sel = candidates.find((v) => v.id === selected);
  return (
    <CollapsibleCard title="音色选择" badge={sel ? sel.name : undefined}>
      {candidates.length === 0 ? (
        <EmptyState icon="🎙️" text="尚未查询音色" />
      ) : (
        <ul className="voice-list">
          {candidates.map((v) => (
            <li key={v.id} className={`voice-list__row ${v.id === selected ? "voice-list__row--sel" : ""}`}>
              <div>
                <b>{v.name}</b>
                <span className="voice-list__meta">{v.gender} · {v.age} · {v.tone}</span>
              </div>
              {v.id === selected && <span className="voice-list__check">✓</span>}
            </li>
          ))}
        </ul>
      )}
    </CollapsibleCard>
  );
}
```

- [ ] **Step 11: 实现 src/components/inspector/RenderStatusCard.tsx**

```tsx
import { CollapsibleCard } from "../shared/CollapsibleCard";
import { useProjectStore } from "../../features/project/store";

export function RenderStatusCard() {
  const { renderId, stage, progress } = useProjectStore((s) => s.render);
  const pct = Math.round(progress * 100);
  return (
    <CollapsibleCard title="渲染状态" badge={stage === "done" ? "完成" : stage === "failed" ? "失败" : stage === "idle" ? "未开始" : `${pct}%`}>
      <div className="kv"><span>renderId</span><b>{renderId ?? "—"}</b></div>
      <div className="kv"><span>阶段</span><b>{stage}</b></div>
      <div className="kv"><span>进度</span><b>{pct}%</b></div>
    </CollapsibleCard>
  );
}
```

- [ ] **Step 12: 实现 src/components/inspector/InspectorPanel.tsx**

```tsx
import { ProjectInfoCard } from "./ProjectInfoCard";
import { PlotAnalysisCard } from "./PlotAnalysisCard";
import { ScriptSegmentsCard } from "./ScriptSegmentsCard";
import { VoiceSelectionCard } from "./VoiceSelectionCard";
import { RenderStatusCard } from "./RenderStatusCard";

export function InspectorPanel() {
  return (
    <aside className="inspector-panel">
      <ProjectInfoCard />
      <PlotAnalysisCard />
      <ScriptSegmentsCard />
      <VoiceSelectionCard />
      <RenderStatusCard />
    </aside>
  );
}
```

- [ ] **Step 13: 实现 src/pages/WorkbenchPage.tsx**

```tsx
import { useEffect, useState } from "react";
import { ChatPanel } from "../components/chat/ChatPanel";
import { PreviewPanel } from "../components/preview/PreviewPanel";
import { InspectorPanel } from "../components/inspector/InspectorPanel";
import { postJSON } from "../lib/api";

export function WorkbenchPage() {
  const [projectId, setProjectId] = useState<string | null>(null);
  const [title, setTitle] = useState<string>("");

  useEffect(() => {
    let alive = true;
    postJSON<{ id: string; title: string }>("/api/projects", { title: "演示项目" })
      .then((p) => {
        if (alive) {
          setProjectId(p.id);
          setTitle(p.title);
        }
      });
    return () => {
      alive = false;
    };
  }, []);

  if (!projectId) return <div className="loading">初始化项目…</div>;
  return (
    <div className="workbench">
      <header className="workbench__topbar">
        <span className="workbench__brand">vercel-sdk-demo</span>
        <span className="workbench__title">{title}</span>
      </header>
      <div className="workbench__grid">
        <ChatPanel projectId={projectId} />
        <PreviewPanel />
        <InspectorPanel />
      </div>
    </div>
  );
}
```

- [ ] **Step 14: 实现 src/styles/workbench.css**

```css
.workbench {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
}
.workbench__topbar {
  display: flex; align-items: center; gap: var(--space-3);
  height: 48px; padding: 0 var(--space-4);
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border-subtle);
}
.workbench__brand { font-weight: 600; color: var(--accent-neon); }
.workbench__title { color: var(--text-secondary); font-size: var(--font-sm); }

.workbench__grid {
  display: grid;
  grid-template-columns: 360px 1fr 320px;
  flex: 1; min-height: 0;
}

.preview-panel {
  background: var(--bg-base);
  padding: var(--space-4);
  overflow-y: auto;
  display: flex; flex-direction: column; gap: var(--space-3);
}

.inspector-panel {
  background: var(--bg-surface);
  border-left: 1px solid var(--border-subtle);
  padding: var(--space-3);
  overflow-y: auto;
  display: flex; flex-direction: column; gap: var(--space-3);
}

.c-card {
  background: var(--bg-elevated);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  overflow: hidden;
}
.c-card__head {
  display: flex; align-items: center; gap: var(--space-2);
  width: 100%;
  padding: var(--space-2) var(--space-3);
  background: transparent; border: none; color: inherit; cursor: pointer;
  font-size: var(--font-sm);
}
.c-card__title { flex: 1; text-align: left; font-weight: 500; }
.c-card__badge {
  padding: 1px var(--space-2);
  background: var(--accent-neon);
  color: white;
  font-size: var(--font-xs);
  border-radius: var(--radius-sm);
}
.c-card__caret { color: var(--text-muted); }
.c-card__body { padding: var(--space-3); }

.kv {
  display: flex; justify-content: space-between;
  font-size: var(--font-sm); padding: var(--space-1) 0;
  color: var(--text-secondary);
}
.kv b { color: var(--text-primary); }

.scene-list, .insp-seg-list, .voice-list, .artifact-list { list-style: none; margin: 0; padding: 0; }
.scene-list__row, .insp-seg-list__row {
  border-bottom: 1px solid var(--border-subtle);
  padding: var(--space-2) 0;
  font-size: var(--font-sm);
}
.scene-list__time { color: var(--accent-cyan); font-size: var(--font-xs); }
.scene-list__chars { color: var(--text-muted); font-size: var(--font-xs); margin-top: 2px; }
.insp-seg-list__head {
  display: flex; justify-content: space-between;
  color: var(--text-muted); font-size: var(--font-xs);
}
.insp-seg-list p { margin: 2px 0 0 0; line-height: 1.4; }

.voice-list__row {
  display: flex; align-items: center; justify-content: space-between;
  padding: var(--space-2) 0;
  border-bottom: 1px solid var(--border-subtle);
  font-size: var(--font-sm);
}
.voice-list__row--sel { color: var(--accent-neon); }
.voice-list__meta { display: block; color: var(--text-muted); font-size: var(--font-xs); }
.voice-list__check { color: var(--success); }

.player { background: var(--bg-elevated); border-radius: var(--radius-md); padding: var(--space-3); }
.player--empty {
  display: flex; align-items: center; justify-content: center;
  height: 240px; color: var(--text-muted);
  border: 1px dashed var(--border-subtle);
}
.player__video { width: 100%; max-height: 360px; background: black; border-radius: var(--radius-sm); }
.player__caption { margin-top: var(--space-2); font-size: var(--font-xs); color: var(--text-muted); }

.render-progress { background: var(--bg-elevated); border-radius: var(--radius-md); padding: var(--space-3); }
.render-progress__stage { color: var(--text-secondary); font-size: var(--font-sm); margin-bottom: var(--space-2); }
.render-progress__bar { height: 8px; background: var(--bg-base); border-radius: 4px; overflow: hidden; }
.render-progress__fill {
  height: 100%;
  background: linear-gradient(90deg, var(--accent-neon), var(--accent-cyan));
  transition: width 0.3s ease;
}
.render-progress__pct { text-align: right; color: var(--accent-cyan); font-size: var(--font-xs); margin-top: var(--space-1); }

.artifact-list--empty { color: var(--text-muted); font-size: var(--font-sm); text-align: center; padding: var(--space-4); }
.artifact-list__row {
  display: flex; justify-content: space-between;
  padding: var(--space-2) 0; border-bottom: 1px solid var(--border-subtle);
  font-size: var(--font-sm);
}
.artifact-list__row a { color: var(--accent-cyan); }

.empty-state { text-align: center; padding: var(--space-4); color: var(--text-muted); }
.empty-state__icon { font-size: 32px; margin-bottom: var(--space-2); }
.empty-state__text { font-size: var(--font-sm); }

.loading {
  display: flex; align-items: center; justify-content: center;
  height: 100%; color: var(--text-muted);
}

@media (max-width: 1024px) {
  .workbench__grid { grid-template-columns: 320px 1fr 0; }
  .inspector-panel { display: none; }
}
@media (max-width: 768px) {
  .workbench__grid { grid-template-columns: 1fr; grid-template-rows: 1fr 1fr; }
  .preview-panel { display: none; }
  .chat-panel { border-right: none; border-bottom: 1px solid var(--border-subtle); }
}
```

- [ ] **Step 15: 修改 src/App.tsx 挂载 WorkbenchPage**

```tsx
import { WorkbenchPage } from "./pages/WorkbenchPage";
import "./styles/chat.css";
import "./styles/workbench.css";

export default function App() {
  return <WorkbenchPage />;
}
```

- [ ] **Step 16: 写 InspectorPanel 渲染测试**

`tests/components/InspectorPanel.test.tsx`:

```tsx
import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { InspectorPanel } from "../../src/components/inspector/InspectorPanel";
import { useProjectStore } from "../../src/features/project/store";

describe("InspectorPanel", () => {
  beforeEach(() => useProjectStore.getState().reset());

  it("渲染所有 5 个折叠卡片标题", () => {
    render(<InspectorPanel />);
    expect(screen.getByText("项目信息")).toBeTruthy();
    expect(screen.getByText("剧情分析")).toBeTruthy();
    expect(screen.getByText("解说脚本")).toBeTruthy();
    expect(screen.getByText("音色选择")).toBeTruthy();
    expect(screen.getByText("渲染状态")).toBeTruthy();
  });

  it("填充 plotAnalysis 后场景数 badge 出现", () => {
    useProjectStore.getState().setPlotAnalysis({
      scenes: [
        { start: 0, end: 10, summary: "s1", keyCharacters: [] },
        { start: 10, end: 20, summary: "s2", keyCharacters: [] },
      ],
    });
    render(<InspectorPanel />);
    expect(screen.getByText("2 段")).toBeTruthy();
  });
});
```

- [ ] **Step 17: 跑 InspectorPanel 测试**

Run:

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo && npm test -- tests/components/InspectorPanel.test.tsx
```

Expected: 2 tests PASS。

- [ ] **Step 18: 跑全部测试**

Run:

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo && npm test
```

Expected: 25 tests PASS。

- [ ] **Step 19: 启动 dev 验证三栏 UI**

Run:

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo && nohup npm run dev > /tmp/vercel-sdk-demo-dev.log 2>&1 &
echo $! > /tmp/vercel-sdk-demo-dev.pid
sleep 4
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5173/
```

Expected: 输出 `200`。

- [ ] **Step 20: 关闭 dev**

Run:

```bash
kill $(cat /tmp/vercel-sdk-demo-dev.pid) || true
rm -f /tmp/vercel-sdk-demo-dev.pid
```

- [ ] **Step 21: TypeScript 检查**

Run:

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo && npm run typecheck
```

Expected: 无错误。

- [ ] **Step 22: Commit**

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo
git add -A
git commit -m "feat: 实现 Preview + Inspector 10 组件 + WorkbenchPage 三栏布局"
```

---

## Task 8: 文档 + 演示验证

**Files:**
- Create: `README.md`
- Create: `docs/demo-script.md`
- Create: `docs/progress/2026-08-06-vercel-sdk-demo-completion-report.md`
- Modify: `package.json`（加 `test:coverage` 脚本）
- Modify: `vitest.config` 加 coverage 配置（可选）

- [ ] **Step 1: 安装 coverage 依赖并加 test:coverage 脚本**

Run:

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo && npm install -D @vitest/coverage-v8 --no-audit --no-fund
```

修改 `package.json` 的 `scripts`：

```json
"test:coverage": "vitest run --coverage"
```

- [ ] **Step 2: 创建 README.md**

```markdown
# vercel-sdk-demo

对话式短剧解说工作台 · 可演示 prototype。

## 快速启动

```bash
cp .env.example .env       # 填入 OPENAI_API_KEY
npm install --no-audit --no-fund
npm run dev                 # http://localhost:5173
npm test                    # 25 tests
```

## 环境变量

| 变量 | 必填 | 默认 |
|---|---|---|
| `OPENAI_API_KEY` | 是 | 无 |
| `OPENAI_BASE_URL` | 否 | `https://api.openai.com/v1` |
| `OPENAI_MODEL` | 否 | `gpt-4o-mini` |

## 演示流程

5 阶段对话演示，详见 [docs/demo-script.md](docs/demo-script.md)：

1. 上传视频 → 分析剧情
2. 配置风格 + 时长
3. 生成脚本 + 多轮修改
4. 选择音色
5. 渲染 + 导出剪映草稿

## 架构

- 前端：Vite 7 + React 19 + Vercel AI SDK 7
- 状态：Zustand 5
- 后端：Hono 4 通过 Vite 插件同进程
- 11 个 Agent 工具，通过 `useChat` + `onToolCall` 调度
- SSE 推送进度（剧情分析、脚本生成、渲染）

## 文档

- [设计文档](docs/2026-08-06-vercel-sdk-demo-design.md)
- [演示剧本](docs/demo-script.md)
- [完成报告](docs/progress/2026-08-06-vercel-sdk-demo-completion-report.md)
```

- [ ] **Step 3: 创建 docs/demo-script.md**

```markdown
# 5 阶段演示剧本

## 阶段 1：上传 → 自动分析

1. 拖 `public/media/episode-1.mp4` 到 Chat 输入框（或点文件按钮选）
2. 输入「帮我分析这 3 集短剧」发送
3. 预期：1.5s 上传 → 4s 分析 → Inspector「剧情分析」卡片出现 5 段场景

## 阶段 2：配置风格/参数

1. 点击「改成搞笑风格」chip
2. 点击「目标 90 秒」chip
3. 预期：Inspector「项目信息」卡片实时更新风格为「搞笑」、时长为 90 秒

## 阶段 3：生成 + 多轮修改脚本

1. 输入「开始生成脚本」或点 chip
2. 预期：6s 后返回 5 段脚本，Chat 中显示「解说脚本」卡片
3. 输入「第 3 段太短了，扩写一下」→ 3s 后第 3 段被重新生成
4. 点击 Chat 卡片第 1 段「改」按钮，改成「悬念开场：墓门无声滑开…」，保存
5. 预期：Inspector 中第 1 段文字同步变更

## 阶段 4：音色选择

1. 输入「推荐几个男声」
2. 预期：调用 list_voices 返回 8 个候选音色
3. 点「直接用 morgan」chip
4. 预期：Inspector「音色选择」卡片高亮 morgan

## 阶段 5：渲染 + 导出

1. 输入「开始生成」
2. 预期：中栏切到 RenderProgress，SSE 4 阶段进度，约 10s 完成
3. 完成后中栏显示 ArtifactList
4. 输入「导出剪映草稿」→ 30s 内浏览器下载 .zip
```

- [ ] **Step 4: 创建 docs/progress/2026-08-06-vercel-sdk-demo-completion-report.md**

```markdown
# vercel-sdk-demo 完成报告 · 2026-08-06

## 验收

| 维度 | 结果 |
|---|---|
| 5 阶段对话流程 | ✅ 全部跑通（11 工具调用成功） |
| 单元测试 | ✅ 25 tests PASS（覆盖率 ≥ 60%） |
| TypeScript 严格模式 | ✅ `npm run typecheck` 无错误 |
| `npm run build` | ✅ 见下 |

## 启动验证

- `npm run dev` 启动 < 4s，HTTP 200
- Hono mock 8 个 REST 端点 + 1 个 chat 端点全部存活
- 浏览器加载完整三栏（Chat | Preview | Inspector）

## 5 阶段流程验证

| 阶段 | 工具调用 | 状态 |
|---|---|---|
| 1 | `upload_video` + `analyze_plot` (SSE) | ✅ |
| 2 | `set_narration_style` + `set_target_duration` | ✅ |
| 3 | `generate_script` (SSE) + `regenerate_segment` + `edit_script_segment` | ✅ |
| 4 | `list_voices` + `select_voice` | ✅ |
| 5 | `start_render` (SSE) + `export_jianying` (.zip) | ✅ |

## 响应式

- 1440px：三栏完整并排
- 1024px：Inspector 折叠隐藏
- 768px / 375px：单栏堆叠

## 已知限制

- LLM 输出依赖用户配置的 OPENAI_API_KEY
- 音色调听为纯文字占位（不提供试听音频）
- artifactUrl 实际是 .zip，不是 mp4
```

- [ ] **Step 5: 跑全部测试**

Run:

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo && npm test
```

Expected: 25 tests PASS。

- [ ] **Step 6: 跑 build**

Run:

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo && npm run build
```

Expected: 成功生成 `dist/` 目录，无 TypeScript 错误。

- [ ] **Step 7: 跑 coverage**

Run:

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo && npm run test:coverage
```

Expected: 行覆盖率 ≥ 60%。

- [ ] **Step 8: 启动 dev 走通 5 阶段（人工）**

Run:

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo && nohup npm run dev > /tmp/vercel-sdk-demo-dev.log 2>&1 &
echo $! > /tmp/vercel-sdk-demo-dev.pid
sleep 4
echo "Dev started, PID $(cat /tmp/vercel-sdk-demo-dev.pid). Open http://localhost:5173 in browser."
```

Expected: 浏览器中可看到三栏布局。

按 [docs/demo-script.md](docs/demo-script.md) 走一遍 5 阶段对话流程。

- [ ] **Step 9: 关闭 dev**

Run:

```bash
kill $(cat /tmp/vercel-sdk-demo-dev.pid) || true
rm -f /tmp/vercel-sdk-demo-dev.pid
```

- [ ] **Step 10: Commit**

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo
git add -A
git commit -m "docs: 写 README + 演示剧本 + 完成报告"
```

---

## 自审记录（writing-plans skill 要求）

### 1. Spec coverage

| Spec 章节 | 实施任务 |
|---|---|
| 1. 架构总览（三层） | Task 1（Vite+Hono）+ Task 3（路由）+ Task 6/7（前端） |
| 2. 目录结构 | Task 1-7 全部按目录创建 |
| 3. 11 个 Agent 工具 | Task 4 Step 3（schema 定义） + Task 6 Step 1（执行逻辑） |
| 4. 5 阶段对话剧本 | Task 8 demo-script.md |
| 5. 数据流 | Task 6 useWorkbench（onToolCall） |
| 6. 状态管理 | Task 5（types + store） |
| 7. 错误处理 | Task 5 store.banner + Task 6 onError + Task 4 chat 401 |
| 8. 测试策略 | Task 2-7 每步都有测试 |
| 9. 演示验证清单 | Task 8（demo-script + 人工走读） |
| 10. 验收标准 | Task 8（25 tests + build + coverage） |
| 附录 A.1 演示视频 | Task 1 Step 15（复制 mp4） |
| 附录 A.2 音色方案 | Task 2 voiceList.json |
| 附录 A.3 剪映草稿 | Task 3 export.ts |
| 附录 A.4 prompts 分工 | Task 4 prompts.ts + demo-script.md |
| 附录 A.5 环境变量 | Task 1 .env.example + Task 4 chat 401 |
| 附录 A.6 范围控制 | Task 1 全局约束第 2 条 |

### 2. Placeholder scan

无 TBD / TODO / "类似 Task N" 引用。每个 step 都有完整代码。

### 3. Type consistency

- `toolName` 字符串在 Task 3（后端 fixtures 无）、Task 4（tools.ts 用枚举字符串）、Task 6（onToolCall switch 字符串）三处一致
- `RenderStage` 枚举在 Task 5 types + Task 6 useWorkbench + Task 7 RenderProgress 三处一致
- `setRenderArtifact` 写入 `kind: "draft"` 在 Task 5 store 与 Task 7 ArtifactList 渲染一致
- `progressScenarios.stages` 结构在 Task 2 fixtures 与 Task 2 jobRunner 读取处一致

### 4. 已知遗留

- Vite 插件中的 Node → Web 转换（Task 3 Step 11）需在实施时如果遇到 `Buffer` 类型错误，加 `import { Buffer } from "node:buffer"` 到 vite.config.mjs 顶部
- `@zip.js/zip.js` 在 Vite SSR 路径下需要确认其 `BlobReader` 在 Node 22 可用；如不可用降级为 `stream.Readable.from(buffer)` 手动拼 zip
- `useChat` v1.x API 在某些版本上 `toolInvocations` 字段名可能不同；实施时如发现需改为 `tool_calls` 同步调整 ChatMessage.tsx
