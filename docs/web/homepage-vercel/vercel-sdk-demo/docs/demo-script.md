# Demo 走查脚本：5 阶段对话式短剧解说

> 本脚本用于在 `npm run dev` 启动后，于浏览器端到端走通对话式工作流。
> 假设演示者已按 README 配置好 LLM（`.env.local` 中 `OPENAI_API_KEY` 至少填了一个非占位值）。
> 演示视频：分辨率 ≥ 1024px（Inspector 在 1024px 以下自动隐藏）。

## 0. 启动（30 秒）

```bash
cd docs/web/homepage-vercel/vercel-sdk-demo
npm run dev
# 浏览器打开 http://localhost:5173
```

打开后页面表现：

- 顶部：品牌 `vercel-sdk-demo` + 项目名 `演示项目`（自动从 `/api/projects` 创建）
- 左栏：Chat 面板，底部输入框，初始状态为欢迎语
- 中栏：Preview 面板，显示一个 video player 占位 + 空 artifact 区
- 右栏：Inspector，5 张折叠卡片（项目信息、剧情分析、脚本段、选音、渲染状态），默认全部展开
- 视觉：深色霓虹色（青/品红/紫渐变高亮），与 homepage-prototype 一致

## 1. 阶段 1：上传视频

**目标**：触发 `upload_video` 工具，Preview 出现可播放的视频

| 步骤 | 用户输入 | 期望表现 | 验证点 |
| --- | --- | --- | --- |
| 1.1 | 点击 Chat 输入框左侧 📎 按钮 | 弹出文件选择器 | —— |
| 1.2 | 选择 `public/media/episode-1.mp4` | 文件名出现在输入框右侧 | 演示用任意文件即可，本 demo 不真正上传文件流 |
| 1.3 | 在输入框中输入："上传这一集" | 点击发送 | 触发 `upload_video` 工具 |
| 1.4 | —— | 1–2 秒后 Assistant 回复 + Chat 出现 ToolCallCard | ToolCallCard 显示 `upload_video` ✅ |
| 1.5 | —— | Preview Panel 的 VideoPlayer 显示 `episode-1.mp4` 元信息（duration、thumbnail） | 验证 Preview 切换 |
| 1.6 | 点击 Preview 中的 ▶ 播放按钮 | 视频正常播放 | 验证媒体资源路径 |

**期望 Inspector 变化**：

- `ProjectInfoCard` 出现「视频」徽标 + 1 条视频元数据（name / durationSec / thumbnailUrl）

## 2. 阶段 2：剧情分析

**目标**：触发 `analyze_plot` 工具，Inspector 出现 5–8 个场景

| 步骤 | 用户输入 | 期望表现 | 验证点 |
| --- | --- | --- | --- |
| 2.1 | 输入："分析一下剧情" | 触发 `analyze_plot` | ToolCallCard 显示 |
| 2.2 | —— | Chat 出现 SSE 进度提示（"正在分析场景 1/6..."） | 验证 SSE 推送 |
| 2.3 | —— | Inspector `PlotAnalysisCard` 折叠展开后显示 5–8 个场景 | 每条场景：`start / end / summary / keyCharacters` |
| 2.4 | 点击 Inspector 右上角「折叠」按钮 | 卡片折叠为标题 + 徽标 | 验证 CollapsibleCard 折叠态 |

**期望 Preview 变化**：

- 不直接变化（剧情分析是离线数据，不影响视频流）；但若 Inspector 触发 `PreviewPanel` 联动更新，会切到 "分析进度" 状态。

## 3. 阶段 3：风格 + 时长配置

**目标**：触发 `set_narration_style` + `set_target_duration`，ProjectInfoCard 实时更新

| 步骤 | 用户输入 | 期望表现 | 验证点 |
| --- | --- | --- | --- |
| 3.1 | 输入："用悬疑风格，目标 90 秒" | 触发 2 个工具调用 | ToolCallCard × 2 |
| 3.2 | —— | Assistant 回复 "已设置风格：悬疑；目标时长：90 秒" | 文字反馈 |
| 3.3 | —— | Inspector `ProjectInfoCard` 实时显示 `悬疑 / 90s` | 验证 store 同步 |
| 3.4 | 输入："改成搞笑风格" | `set_narration_style` 再次触发 | 验证 store update |
| 3.5 | —— | Inspector `ProjectInfoCard` 风格更新为 `搞笑` | 验证动作幂等 |

**期望 Preview 变化**：

- 无

## 4. 阶段 4：脚本生成 + 编辑

**目标**：触发 `generate_script` / `edit_script_segment` / `regenerate_segment`，ScriptSegmentsCard 显示 5 段文案

| 步骤 | 用户输入 | 期望表现 | 验证点 |
| --- | --- | --- | --- |
| 4.1 | 输入："生成 5 段脚本" | 触发 `generate_script` | ToolCallCard |
| 4.2 | —— | SSE 推送 "正在生成 1/5..." 进度 | 验证 SSE |
| 4.3 | —— | Inspector `ScriptSegmentsCard` 出现 5 段 | 每段：`id / start / end / text / tone` |
| 4.4 | 输入："把第 3 段改得更紧张一些" | 触发 `regenerate_segment`（带 hint） | ToolCallCard 显示 hint |
| 4.5 | —— | 第 3 段文案实时更新 | 验证 `updateSegmentText` 写入 store |
| 4.6 | 输入："第 1 段第 1 个字改成'夜'" | 触发 `edit_script_segment` | 文本精确替换 |
| 4.7 | —— | 第 1 段文案变化 | 验证 edit 行为 |

**期望 Preview 变化**：

- 无直接变化（脚本是文本，不驱动视频流）

## 5. 阶段 5：选音 + 渲染 + 导出

**目标**：触发 `list_voices` / `select_voice` / `start_render` / `track_render_status`，渲染进度实时推进

| 步骤 | 用户输入 | 期望表现 | 验证点 |
| --- | --- | --- | --- |
| 5.1 | 输入："看看有哪些音色" | 触发 `list_voices` | ToolCallCard |
| 5.2 | —— | Assistant 回复音色清单（3–6 个候选） | 验证 `/api/voices` 数据 |
| 5.3 | —— | Inspector `VoiceSelectionCard` 显示 3–6 个音色（name / gender / age / tone） | 验证 store 写入 |
| 5.4 | 输入："用女声 001"（或具体 voiceId） | 触发 `select_voice` | ToolCallCard |
| 5.5 | —— | `VoiceSelectionCard` 选中态（高亮 / 徽标） | 验证选中态 |
| 5.6 | 输入："开始渲染" | 触发 `start_render` | ToolCallCard |
| 5.7 | —— | Inspector `RenderStatusCard` 出现 `tts` 阶段 + 进度条 | 验证 SSE 实时 |
| 5.8 | —— | 依次推进 `tts → subtitle → mixing → encoding → done` | 每阶段 1–2 秒 |
| 5.9 | —— | Preview 切换为 `RenderProgress` 组件，显示最终 100% | 验证阶段切换 |
| 5.10 | 输入："导出剪映草稿" | 触发 `export`（或由 `start_render` 自动产出 artifact） | —— |
| 5.11 | —— | Preview `ArtifactList` 出现 1 条 artifact：「剪映草稿 zip」+ 下载链接 | 验证 artifact 写入 |

**期望 Preview 变化**：

- 阶段 5.7–5.9：显示 `RenderProgress` 实时进度
- 阶段 5.11：显示 `ArtifactList` 包含剪映草稿

## 6. 异常 / 边界演示

| 场景 | 操作 | 期望表现 |
| --- | --- | --- |
| LLM Key 缺失 | 启动前不配 `.env.local` | Chat 发送消息后 banner 出现红色错误 "OPENAI_API_KEY 未配置"；工具不执行 |
| LLM 400 / 5xx | 配错 `OPENAI_BASE_URL` 或 Key 失效 | banner 显示具体错误；store 状态不变 |
| 工具返回 5xx | mock 服务端故障（手动 kill dev） | ToolCallCard 显示 ❌ + banner 错误；可点击 banner × 关闭 |
| Inspector 折叠 | 点击任一卡片头部 | 卡片折叠为单行 + 徽标；再点击展开 |
| 响应式 | 缩浏览器宽度至 < 1024px | Inspector 自动隐藏；Chat + Preview 占满 |

## 7. 验收检查清单

- [ ] 5 阶段全部跑通，每个阶段至少 1 个工具调用
- [ ] Inspector 5 张卡片（项目/剧情/脚本/音色/渲染）状态正确
- [ ] Preview 状态随阶段切换：idle → 视频 → 渲染进度 → artifact
- [ ] SSE 实时推送：剧情分析 / 脚本生成 / 渲染进度均可见
- [ ] 折叠卡片在 5 张上行为一致
- [ ] 1024px 以下 Inspector 隐藏，Chat + Preview 不破版
- [ ] 异常场景（无 Key / Key 错 / 服务端断）banner 正常显示
- [ ] `npm run test` 25 个用例全部通过
- [ ] `npm run build` 无错
- [ ] `npm run test:coverage` 报告可生成（`coverage/index.html`）

## 8. 演示时长预估

- 完整 5 阶段：约 8–10 分钟（含打字输入时间）
- 异常演示：额外 3–5 分钟
- 验收过场：1 分钟

总计：建议预留 15–20 分钟演示窗口。
