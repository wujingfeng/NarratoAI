export const creationTypes = [
  { id: "narration", title: "短剧解说", description: "自动梳理剧情并生成解说视频", maxVideos: 5 },
  { id: "translation", title: "视频翻译", description: "为视频生成多语言字幕与配音", maxVideos: 1 },
  { id: "remix", title: "短剧混剪", description: "组合多个素材片段，快速生成混剪", maxVideos: 10 },
];

export const initialCreateVideos = [
  { id: "demo-01", name: "第01集片段.mp4", durationSeconds: 184, durationLabel: "03:04", subtitleStatus: "待识别，将使用 AI 识别", statusTone: "warning", subtitleName: null, thumbnail: null },
  { id: "demo-02", name: "第02集片段.mp4", durationSeconds: 247, durationLabel: "04:07", subtitleStatus: "待识别，将使用 AI 识别", statusTone: "warning", subtitleName: null, thumbnail: null },
  { id: "demo-03", name: "第03集片段.mp4", durationSeconds: 91, durationLabel: "01:31", subtitleStatus: "待识别，将使用 AI 识别", statusTone: "warning", subtitleName: null, thumbnail: null },
];
