export const analysisVideos = [
  { id: "ep01", label: "EP01", duration: "03:21", scene: "violet" },
  { id: "ep02", label: "EP02", duration: "02:58", scene: "blue" },
  { id: "ep03", label: "EP03", duration: "02:23", scene: "orange" },
  { id: "ep04", label: "EP04", duration: "01:46", scene: "pink" },
];

export const analysisStages = [
  { id: "caption", titleKey: "analysis.stages.caption", statusKey: "analysis.status.done", state: "done", icon: "caption" },
  { id: "story", titleKey: "analysis.stages.story", statusKey: "analysis.status.done", state: "done", icon: "book" },
  { id: "conflict", titleKey: "analysis.stages.conflict", statusKey: "analysis.status.active", state: "active", icon: "target" },
  { id: "highlights", titleKey: "analysis.stages.highlights", statusKey: "analysis.status.waiting", state: "waiting", icon: "star" },
];

export const analysisLogs = [
  { time: "14:30:25", messageKey: "analysis.logs.read", state: "done" },
  { time: "14:30:31", messageKey: "analysis.logs.caption", state: "done" },
  { time: "14:30:38", messageKey: "analysis.logs.merge", state: "done" },
  { time: "14:30:52", messageKey: "analysis.logs.characters", state: "done" },
  { time: "14:31:04", messageKey: "analysis.logs.conflict", state: "active" },
];
