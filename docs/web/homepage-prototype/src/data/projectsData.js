export const projectCategories = [
  { id: "all", labelKey: "projects.categories.all" },
  { id: "narration", labelKey: "projects.categories.narration" },
  { id: "translation", labelKey: "projects.categories.translation" },
  { id: "remix", labelKey: "projects.categories.remix" },
];

export const projects = [
  { id: "overlord", title: "霸总短剧解说 01", duration: "00:30:00", type: "narration", typeKey: "projects.categories.narration", status: "complete", statusKey: "projects.status.complete", createdAt: "2024-05-30T14:30:00+08:00", credits: 120, image: "/assets/short-drama-thumb.webp", resultPath: "/dashboard/projects/overlord/result" },
  { id: "fate", title: "命运的反转 · 英文翻译", duration: "00:18:36", type: "translation", typeKey: "projects.categories.translation", status: "processing", statusKey: "projects.status.processingPercent", progress: 66, createdAt: "2024-05-30T13:22:00+08:00", credits: 80, image: "/assets/documentary-thumb.webp" },
  { id: "city", title: "都市逆袭高光混剪", duration: "00:01:45", type: "remix", typeKey: "projects.categories.remix", status: "complete", statusKey: "projects.status.complete", createdAt: "2024-05-30T11:05:00+08:00", credits: 150, image: "/assets/film-action-thumb.webp" },
  { id: "suspense", title: "悬疑短剧解说", duration: "00:25:20", type: "narration", typeKey: "projects.categories.narration", status: "draft", statusKey: "projects.status.draft", createdAt: "2024-05-29T18:40:00+08:00", credits: 60, image: "/assets/documentary-thumb.webp" },
  { id: "sweet", title: "甜宠短剧翻译", duration: "00:22:10", type: "translation", typeKey: "projects.categories.translation", status: "draft", statusKey: "projects.status.draft", createdAt: "2024-05-29T16:15:00+08:00", credits: 70, image: "/assets/short-drama-thumb.webp" },
  { id: "grudge", title: "豪门恩怨混剪", duration: "00:02:05", type: "remix", typeKey: "projects.categories.remix", status: "failed", statusKey: "projects.status.failed", createdAt: "2024-05-29T09:50:00+08:00", credits: 90, image: "/assets/film-action-thumb.webp" },
];

export const projectStatusOptions = [
  { id: "all", labelKey: "projects.status.all" },
  { id: "complete", labelKey: "projects.status.complete" },
  { id: "processing", labelKey: "projects.status.processing" },
  { id: "draft", labelKey: "projects.status.draft" },
  { id: "failed", labelKey: "projects.status.failed" },
];
