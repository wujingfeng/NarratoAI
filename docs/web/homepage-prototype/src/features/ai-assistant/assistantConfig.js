export const CONVERSATION_MODES = {
  chat: {
    id: "chat",
    label: "普通聊天",
    shortLabel: "普通聊天",
    placeholder: "输入消息",
    attachmentHint: "可选图片",
    accepted: "image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp",
    requiredAttachment: false,
  },
  short_drama_narration: {
    id: "short_drama_narration",
    label: "短剧解说 Agent",
    shortLabel: "短剧解说",
    placeholder: "上传短剧视频后描述解说需求，例如：生成 60 秒悬疑风解说，节奏紧凑并突出反转。",
    attachmentHint: "上传视频素材",
    accepted: "video/mp4,video/quicktime,video/x-msvideo,.mp4,.mov,.avi",
    requiredAttachment: true,
  },
  video_translation: {
    id: "video_translation",
    label: "视频翻译 Agent",
    shortLabel: "视频翻译",
    placeholder: "上传视频后说明配音偏好，例如：保留人物情绪，使用自然女声配音，字幕简洁。",
    attachmentHint: "上传需要翻译的视频",
    accepted: "video/mp4,video/quicktime,video/x-msvideo,.mp4,.mov,.avi",
    requiredAttachment: true,
  },
  video_generation: {
    id: "video_generation",
    label: "视频生成 Agent",
    shortLabel: "视频生成",
    placeholder: "描述想生成的视频，例如：雨夜霓虹街头，镜头缓慢推进，电影感。",
    attachmentHint: "按所选生成模式添加参考素材",
    accepted: "image/*,video/mp4,video/quicktime,video/x-msvideo,audio/*,.mp4,.mov,.avi,.mp3,.wav,.m4a,.aac,.ogg",
    requiredAttachment: false,
  },
};

export const VIDEO_GENERATION_MODES = [
  { id: "text_to_video", label: "文生视频", hint: "只需输入文字提示词" },
  { id: "first_frame", label: "首帧", hint: "上传一张首帧图片" },
  { id: "first_last_frame", label: "首尾帧", hint: "上传首帧与尾帧图片" },
  { id: "multi_subject_reference_audio_visual", label: "全能参考", hint: "上传图片、音频或视频参考素材" },
];

export const TARGET_LANGUAGES = [
  { id: "en", label: "English" },
  { id: "ja", label: "日本語" },
  { id: "ko", label: "한국어" },
  { id: "es", label: "Español" },
  { id: "fr", label: "Français" },
  { id: "de", label: "Deutsch" },
  { id: "pt", label: "Português" },
];

export function isVideoGenerationMode(value) {
  return VIDEO_GENERATION_MODES.some((item) => item.id === value);
}

export function attachmentRequirement(mode, generationMode) {
  if (mode === "short_drama_narration" || mode === "video_translation") return { min: 1, type: "video" };
  if (mode !== "video_generation") return { min: 0, type: "any" };
  if (generationMode === "first_frame") return { min: 1, type: "image" };
  if (generationMode === "first_last_frame") return { min: 2, type: "image" };
  if (generationMode === "multi_subject_reference_audio_visual") return { min: 1, type: "any" };
  return { min: 0, type: "any" };
}

export function validateAssistantSubmission({ mode, prompt, attachments, targetLanguage, generation }) {
  const text = String(prompt || "").trim();
  const files = attachments || [];
  if (!text) return "请输入你的需求。";
  if (mode === "video_translation" && !targetLanguage) return "请选择目标翻译语种。";
  if (mode === "video_generation") {
    if (!generation?.modelId || !generation?.generationMode || !generation?.ratio || !generation?.duration || !generation?.resolution) {
      return "请完成视频生成模式、模型、比例、时长和分辨率的选择。";
    }
    if (!Number.isFinite(Number(generation.duration)) || Number(generation.duration) <= 0) return "请选择一个固定的视频时长。";
  }
  const requirement = attachmentRequirement(mode, generation?.generationMode);
  const ready = files.filter((file) => file.status === "ready");
  if (files.some((file) => file.status !== "ready")) return "附件仍在上传或校验中，请稍候。";
  if (ready.length < requirement.min) return mode === "video_generation" ? "请按当前生成模式添加所需参考素材。" : "请先上传一个视频素材。";
  if (requirement.type !== "any" && ready.filter((file) => file.kind === requirement.type).length < requirement.min) return "上传素材类型不符合当前模式要求。";
  return "";
}

export function assetTypeForFile(file) {
  const type = String(file?.type || "").toLowerCase();
  const ext = String(file?.name || "").split(".").pop()?.toLowerCase();
  if (type.startsWith("video/") || ["mp4", "mov", "avi"].includes(ext)) return "video";
  if (type.startsWith("audio/") || ["mp3", "wav", "m4a", "aac", "ogg"].includes(ext)) return "audio";
  if (type.startsWith("image/") || ["png", "jpg", "jpeg", "webp"].includes(ext)) return "image";
  return "file";
}

// UI copy lives beside the mode contract so mode constraints and visible wording change together.
export const ASSISTANT_UI = {
  narration: "短剧解说", translation: "视频翻译", generation: "视频生成", agentRun: "Agent 任务", me: "我", chat: "普通聊天",
  completed: "已完成", failed: "任务失败", cancelled: "任务已取消", creating: "正在创建任务", queued: "等待任务执行", waitingForEdit: "等待确认剪辑", renderQueued: "等待视频渲染", processing: "处理中", generatingVideo: "第三方正在生成视频", savingGeneratedVideo: "视频已生成，正在保存结果", finalizing: "正在整理任务结果", refreshRun: "刷新任务状态", openVideo: "打开生成视频", openProject: "打开项目结果",
  selectMode: "选择对话模式", generationMode: "生成模式", modelLoading: "加载模型中…", selectModel: "选择模型", model: "模型", ratio: "比例", selectRatio: "选择比例", duration: "时长", selectDuration: "选择时长", resolution: "分辨率", selectResolution: "选择分辨率", autoAudio: "自动生成音频",
  seconds: "秒", remove: "移除", selectedAttachments: "已选附件", uploading: "正在上传…", ready: "已就绪", uploadFailed: "上传失败", modelLoadFailed: "视频生成模型加载失败。", assetNotReady: "素材校验未完成，请稍后重试。", sendFailed: "消息发送失败，请重试。",
  messageAttachments: "消息附件", attachment: "附件", openAttachment: "预览附件", previewAttachment: "附件预览", closePreview: "关闭预览", downloadAttachment: "下载附件", videoFile: "视频文件", imageFile: "图片文件", file: "文件",
  agentStepRunning: "正在执行", streamingStepResult: "正在实时生成，可折叠", agentResultFile: "Agent 结果文件", subtitleFile: "SRT 字幕文件", previewFile: "预览", closeFilePreview: "收起预览", expandStepResult: "展开具体内容", collapseStepResult: "收起具体内容", previewTruncated: "内容较长，聊天框仅展示部分预览；可下载文件查看完整内容。",
  newThread: "新建对话", newThreadTitle: "新对话", conversations: "对话", renameThread: "修改名称", deleteThread: "删除对话", deleteThreadConfirm: "确定删除这条对话记录吗？此操作不可恢复。", threadTitlePlaceholder: "输入对话名称", threadTitleInvalid: "对话名称不能为空。", threadRenameFailed: "修改对话名称失败，请重试。", threadDeleteFailed: "删除对话失败，请重试。", chatModel: "聊天模型", selectChatModel: "选择模型", send: "发送消息", sending: "发送中…", expandInput: "放大输入框", shrinkInput: "缩小输入框", chatReplyPending: "正在生成回复…", chatReplyFailed: "对话回复生成失败，请重试。", copy: "复制", copyFailed: "复制失败", regenerate: "重新生成", copied: "已复制",
  translateTo: "翻译为", refreshFailed: "任务状态刷新失败。", threadsLoadFailed: "对话列表加载失败。", threadIdMissing: "创建对话失败，未返回对话编号。", draftIdMissing: "创建上传草稿失败，未返回项目编号。", threadReadFailed: "对话读取失败。", loading: "正在载入 AI 助手…",
};

const TERMINAL_ASSISTANT_RUN_STATES = new Set([
  "completed", "succeeded", "succeeded_with_partial_output", "failed", "cancelled",
]);

export function isAssistantRunActive(status) {
  const value = String(status || "queued").toLowerCase();
  // 只允许明确终态停止观察；新增的中间状态不能再次让 SSE/轮询静默失效。
  return !TERMINAL_ASSISTANT_RUN_STATES.has(value);
}

export function assistantRunAnchorMessageId(run) {
  return String(
    run?.assistant_message_id
      || run?.assistantMessageId
      || run?.message_id
      || run?.messageId
      || "",
  );
}

export function assistantRunStatusLabel(run, status) {
  const value = String(status || run?.status || run?.state || "queued").toLowerCase();
  if (value === "completed" || value === "succeeded") return ASSISTANT_UI.completed;
  if (value === "failed") return ASSISTANT_UI.failed;
  if (value === "cancelled") return ASSISTANT_UI.cancelled;
  if (run?.stage_label || run?.stage) return run.stage_label || run.stage;
  if (value === "waiting_for_edit") return ASSISTANT_UI.waitingForEdit;
  if (value === "render_queued") return ASSISTANT_UI.renderQueued;
  if (value === "finalizing") return run?.mode === "video_generation" ? ASSISTANT_UI.savingGeneratedVideo : ASSISTANT_UI.finalizing;
  if (["processing", "running", "rendering", "analyzing", "retrying"].includes(value)) return run?.mode === "video_generation" ? ASSISTANT_UI.generatingVideo : ASSISTANT_UI.processing;
  if (["queued", "pending", "submitted"].includes(value)) return ASSISTANT_UI.queued;
  return ASSISTANT_UI.creating;
}
