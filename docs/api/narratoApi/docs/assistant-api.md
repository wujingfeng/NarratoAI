# AI 助手会话 API

所有接口位于 `/api/v1`，需要 `Authorization: Bearer <token>`。会话由当前
用户独占，跨用户读取或提交统一返回 `ASSISTANT_THREAD_NOT_FOUND` / `404`。

## 线程与预任务上传

```http
POST /assistant/threads
{ "mode": "video_generation", "title": "可选标题" }
```

模式枚举：`chat`、`short_drama_narration`、`video_translation`、
`video_generation`。线程的 `mode` 只是新输入框的默认展示；每条消息和每个
草稿均可显式指定模式，message/run 会冻结发起时模式，绝不由 Agent 自动改写。

线程标题默认为空；首次成功提交用户内容时，服务端会将首条内容压缩为列表标题。
调用方提供了非空自定义 `title` 时不会被自动改写。

任务模式、或需要图片参考的普通聊天，先创建草稿：

```http
POST /assistant/threads/{thread_id}/drafts
{ "mode": "video_generation" }
```

响应 `data` 为 `{ "project_id", "mode" }`。上传仍复用既有受控 OSS 流程：

1. `POST /projects/{project_id}/uploads/policy`
2. 使用返回的表单字段直传 OSS
3. `POST /projects/{project_id}/uploads/complete`
4. 轮询 `GET /assets/{asset_id}` 至 `status=ready`

这样不会绕过现有文件约束、媒体探测和项目资产归属。提交消息时引用
`attachments: [{"asset_id":"ast_x"}]`。

## 提交消息

```http
POST /assistant/threads/{thread_id}/messages
X-Idempotency-Key: <client-unique-key>
{
  "mode": "video_generation",
  "content": "雨夜霓虹街头，镜头缓慢推进",
  "attachments": [{"asset_id":"ast_first_frame"}],
  "input": {
    "project_id": "prj_x",
    "generation_mode": "first_frame",
    "model": "model_x",
    "ratio": "9:16",
    "duration": 5,
    "resolution": "720p",
    "audio": false,
    "model_params": {}
  }
}
```

`options` 是 `input` 的兼容别名；两者不能同时发送。短剧解说、视频翻译和视频生成
在事务提交后由后台提交 Provider，接口不等待模型或视频服务的响应；因此即使 Provider
延迟或无响应，`202` 仍会立即返回已创建的 message/run。成功 `202` 的 `data`：

```json
{
  "message": {"id":"...","role":"user","mode":"...","content":"...","attachments":[],"created_at":"..."},
  "assistant_message": {"id":"...","role":"assistant","mode":"...","content":"...","attachments":[],"created_at":"..."},
  "run": {"id":"...","message_id":"...","assistant_message_id":"...","mode":"...","status":"queued","project_id":"...","display_config":{},"steps":[],"video_url":null,"created_at":"...","updated_at":"..."}
}
```

短剧解说 Run 会额外返回可直接渲染进聊天时间线的 `steps`。步骤来自真实
`WorkflowNode` 与最新 `WorkflowNodeAttempt`，刷新接口不会重复创建会话消息：

```json
{
  "id": "subtitle_recognition",
  "title": "字幕识别",
  "status": "completed",
  "outputs": [
    {
      "type": "file",
      "artifact_id": "...",
      "kind": "subtitle",
      "filename": "episode-01.srt",
      "content_type": "application/x-subrip; charset=utf-8",
      "url": "https://cdn.example.com/episode-01.srt",
      "preview_text": "1\n00:00:00,000 --> 00:00:02,000\n...",
      "preview_truncated": false
    }
  ],
  "error_code": null,
  "updated_at": "..."
}
```

`outputs.type` 当前只允许 `markdown | file | video`。剧情理解、冲突/爽点、高光
分析和解说文案使用 `markdown`；ASR、字幕与时间线使用 `file`；最终成片使用
`video`。SRT 预览由 Core 在完成校验后生成有界文本，完整文件仍通过 Artifact URL
下载。已完成的剧情理解、冲突/爽点与高光步骤必须返回对应的具体 Markdown 内容；
兼容升级前只保存分析 Artifact 的任务时，Business API 仅从当前部署配置的 CDN
回读 `short-drama-analysis.v1` 白名单字段，不返回 Provider 原始结果。没有真实节点
结果时仅返回步骤状态，不生成替代内容。

`GET /assistant/threads/{thread_id}/runs` 与 `GET /assistant/runs/{run_id}` 只返回
上述前端展示投影及步骤的白名单结果。推导提示词、用户原始需求、附件清单、模型/玩法/供应商任务 ID、
完整工作流状态、Provider 原始响应、内部错误和完整解析配置均不会通过会话接口返回。

普通聊天可先读取可流式调用模型：

```http
GET /assistant/chat-models
```

返回的 `id` 可在普通聊天的 `input.model_id` 中显式提交。服务端只接受已启用、
具有启用供应商、启用 Token 价格且支持聊天 SSE 的模型；指定后不会改用默认模型。

读取接口：`GET /assistant/threads`、`GET /assistant/threads/{thread_id}`、
`GET /assistant/threads/{thread_id}/runs`、`GET /assistant/runs/{run_id}`。

`GET /assistant/threads/{thread_id}` 默认只返回最近 10 条消息。向上翻页时传递
`?limit=10&before={next_before}`；响应的 `has_more` 和 `next_before` 表示是否还有更早
记录。每个页面内仍按创建时间正序返回，前端可直接插入当前列表顶部。

### 普通聊天 SSE

普通聊天可使用以下接口获得真实增量回复。该接口只接受 `mode: "chat"`，请求体、
附件规则和幂等键与普通消息接口一致：

```http
POST /assistant/threads/{thread_id}/messages/stream
Accept: text/event-stream
X-Idempotency-Key: <client-unique-key>
```

服务端以 SSE 返回以下事件：

- `message_created`：用户消息与占位 assistant 消息已持久化；
- `message_start`：已连接上游模型（仅内部执行流使用，订阅端可忽略）；
- `delta`：`content` 为当前完整回复，`delta` 为本次新增文本；
- `completed`：最终回复、Token 用量与结算结果已写入；
- `error`：上游流失败，assistant 消息会持久化为失败提示。

创建消息后，模型流由服务端后台执行，SSE 连接仅用于观察结果：切换线程、离开
页面、网络中断或关闭订阅都不会取消任务。每条普通聊天 assistant message 额外返回
`stream_status`（`running` / `completed` / `failed`），不暴露内部 ModelTask ID。
页面返回后，使用以下接口按持久化内容重放并继续接收增量；它不会创建新任务或重新
计费：

```http
GET /assistant/threads/{thread_id}/messages/{assistant_message_id}/stream
Accept: text/event-stream
```

进程意外重启时，已有 `ModelTask` 在流租约到期后会由既有轮询 Worker 以非流式调用
继续恢复并回填回复。多元 X 通过 OpenAI Chat Completions 兼容协议请求 `stream: true`
和 `stream_options.include_usage: true`。短剧解说与视频翻译的结构化参数推导仍等待完整
JSON 后再校验并创建工作流。

### Agent Run SSE

任务模式可订阅一个已持久化 Run 的执行快照：

```http
GET /assistant/runs/{run_id}/stream
Accept: text/event-stream
```

服务端校验 Run 所有权，并返回以下事件：

- `run_snapshot`：与 `GET /assistant/runs/{run_id}` 相同的白名单 Run 投影；
- `step_snapshot`：当前推理步骤的最新公开草稿，包含 `step_id`、`phase`、
  `status_label`、`content`、`sequence` 与 `event_id`；
- `completed`：Run 进入 `completed | succeeded | failed | cancelled` 后返回最终投影；
- `error`：Run 不存在或订阅无法继续。

SSE 只是观察通道，关闭页面或断线不会取消任务。Core 会把当前阶段的有界公开草稿
持久化到 Task，因此重连后可恢复到最新快照；正式步骤结果一旦生成，会替换草稿。
当前短剧剧情分析与解说文案生成返回文本增量；画面匹配和时间线校正只返回阶段状态，
不展示结构化 JSON 半成品。需求参数推导同样只流式返回“正在推导”的状态，必须等完整
JSON 通过白名单校验后才创建工作流。前端仍应保留 `GET /assistant/runs/{run_id}` 轮询
作为 SSE 不可用时的降级通道。

### 行为白名单

- `chat`：只走可用 LLM 的普通对话任务，不创建 `agent_run` 或创作工作流。
  初次提交返回“正在生成回复…”，LLM 完成后 `GET /assistant/threads/{thread_id}` 会将
  持久化 assistant message 回填为真实文本回复。
  纯文本聊天无需草稿；需要图片时先 `POST /assistant/threads/{thread_id}/drafts`
  `{ "mode": "chat" }`，使用返回的 `ai_video` 项目走现有 OSS 上传，并在 message
  `input.project_id` 与 `attachments:[{"asset_id":"..."}]` 中引用。当前普通聊天仅
  接受 ready `image`；`pdf`、`doc` 和其它普通文件不属于现有 Asset/LLM 合同，前端不应
  提供上传入口。
- `short_drama_narration`：必须有 ready 视频。服务端先创建受既有 `ModelTask`
  与 Provider 链路驱动的结构化 LLM 推导 Run；仅在 LLM JSON 输出通过白名单校验
  后调用现有 `save_settings_and_start_analysis`，并固定 `execution_mode=auto`。
- `video_translation`：必须恰好一个 ready 视频，`input.target_language` 必填且仅
  接受当前 `SUPPORTED_LANGUAGES`。服务端先创建结构化 LLM 推导 Run；目标语言不
  进入 LLM 可修改字段。推导完成后固定 `original_sound_mode=voice_replacement`，
  从 `SUPPORTED_SUBTITLE_STYLES` 随机一次并写入 project settings 与
  `run.resolved_config`；重试和读取不会再次随机。
- `video_generation`：不调用 LLM 推导参数。`generation_mode` 的精确枚举是
  `text_to_video`、`first_frame`、`first_last_frame`、
  `multi_subject_reference_audio_visual`。模型、比例、时长、分辨率、音频开关均
  必填且按模型玩法规则严格校验；首帧/首尾帧/多主体素材形态也严格校验。当前
  标准能力目录未定义模型专属参数规则时，非空 `model_params` 返回
  `MODEL_PARAMETERS_UNSUPPORTED`，不会静默丢弃。
