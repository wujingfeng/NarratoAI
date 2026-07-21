import { Brain, FileText, FilmStrip, Microphone } from "@phosphor-icons/react";

export const projectResult = {
  id: "overlord",
  title: "霸总短剧解说 01",
  format: "MP4",
  resolution: "1080 × 1920",
  duration: "01:25",
  video: "/media/project-result/overlord-narration-result-85s.mp4",
  poster: "/media/narration-editor/episode-1-poster.jpg",
  subtitle: "/media/project-result/overlord-narration-result-85s.vtt",
  statusKey: "projectResult.status.generated",
  steps: ["recognize", "highlights", "script", "synthesis", "export"].map((id) => ({ id, labelKey: `projectResult.steps.${id}` })),
  logs: [
    { time: "14:30:25", messageKey: "projectResult.logs.recognize" },
    { time: "14:31:12", messageKey: "projectResult.logs.highlights" },
    { time: "14:31:48", messageKey: "projectResult.logs.script" },
    { time: "14:32:20", messageKey: "projectResult.logs.synthesis" },
    { time: "14:33:05", messageKey: "projectResult.logs.export" },
  ],
  costs: [
    { id: "analysis", labelKey: "projectResult.costs.analysis", value: 22, icon: Brain, tone: "violet" },
    { id: "script", labelKey: "projectResult.costs.script", value: 15, icon: FileText, tone: "blue" },
    { id: "voice", labelKey: "projectResult.costs.voice", value: 20, icon: Microphone, tone: "cyan" },
    { id: "render", labelKey: "projectResult.costs.render", value: 30, icon: FilmStrip, tone: "orange" },
  ],
  totalCredits: 87,
  summary: {
    sourceKey: "projectResult.summary.source",
    outputKey: "projectResult.summary.output",
    createdAt: "2024-05-30T14:30:00+08:00",
    typeKey: "projectResult.summary.type",
  },
};
