# 火山方舟短剧音频/视频理解实现

## 目标与边界

- 通用 ASR API、Adapter 和火山录音文件识别保持不变。
- 仅短剧解说的 `subtitle_recognition` 节点改用独立
  `audio_understanding` Core Task。
- 音频理解和视频理解均把业务 OSS 的 HTTPS 公网视频 URL 直接传给方舟；
  不下载视频、不本地提取音轨、不做本地镜头检测或关键帧分析。
- 一个素材执行一次音频理解、一次完整视频理解；冲突与高光节点只投影同一
  `analysis` Artifact，不重复请求模型。
- 单素材时长必须在 `(0, 600]` 秒内。

## 模型配置

Worker 复用 `coreApi/config.toml` 的私有字段：

```toml
volcengine_ark_base_url = "https://ark.cn-beijing.volces.com/api/v3"
volcengine_ark_api_key = "..."
volcengine_ark_model_id = "..."
```

密钥和实际 Endpoint/Model ID 不进入数据库 Artifact、日志或能力 seed。
能力目录使用稳定 ID `model_volcengine_ark`，包含：

- `audio_understanding`
- `video_analysis`
- `script_generation`

## 方舟请求

两类理解都调用 OpenAI-compatible Chat Completions，并使用相同的公网视频输入：

```json
{
  "type": "video_url",
  "video_url": {
    "url": "https://cdn.example/video.mp4",
    "fps": 1
  }
}
```

`min_frame_tokens=64` 是当前方舟的 provider 默认值，不是此 Chat API 已公开的
请求字段，因此不会发送给上游。Core 仅在任务和 Artifact 元数据记录：

```json
{
  "fps": 1,
  "min_frame_tokens": 64,
  "min_frame_tokens_mode": "provider_default"
}
```

音频和视频返回都使用 `response_format.type=json_schema`、`strict=true`，且多模态
结构化请求禁用 streaming。

## Artifact

音频理解输出：

- 每个来源一个 `subtitle` SRT Artifact；
- 一个 `short-drama-audio-understanding.v1` JSON Artifact；
- Core Task result 保留 Business 已使用的 `subtitles[]` 合同。

完整视频理解输出继续使用兼容的 `short-drama-analysis.v1` 顶层，并扩展：

- `characters`
- `events[]`
- 每个事件的 `source_asset_id`、时间范围、视觉锚点、裁剪建议、视觉/音频证据及
  置信度。

## 音画对齐

火山 TTS 请求启用 `with_timestamp=1`，解析 `addition.frontend.words`。渲染阶段
按以下公式计算片段内解说开始时间：

```text
narration_start_offset =
  visual_anchor - source_start + visual_lead - voice_anchor_offset
```

负值优先通过向前扩展 `source_start` 消化，剩余值截断为 `0`。配音轨使用 FFmpeg
`adelay` 前置静音；片段时长为
`max(source_duration, narration_start_offset + voice_duration)`，字幕 cue 同步延后。
旧草稿没有锚点或 offset 时保持 `0`。

## 上线限制

当前方舟 URL 视频输入文档规定单视频文件不超过 50 MB。Business 在短剧项目的上传
预留和完成阶段都将视频限制为 50 MiB，并返回
`VIDEO_TOO_LARGE_FOR_MULTIMODAL`；其它产品仍保留原 300 MiB 上限。浏览器短剧创建页
也同步做 50 MiB 前置校验。不得为绕过限制增加本地转码、抽帧或音频提取。
