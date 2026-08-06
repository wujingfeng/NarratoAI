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
  parameters: z.object({
    projectId: z.string(),
    targetSec: z.number().int().min(10).max(300),
  }),
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
