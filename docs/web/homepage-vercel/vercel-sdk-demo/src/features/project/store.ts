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
  project: {
    id: "demo-project",
    title: "新项目",
    style: "悬疑",
    targetDurationSec: 60,
    audience: "通用",
  },
  videos: [],
  plotAnalysis: { scenes: [] },
  script: { segments: [] },
  voice: { candidates: [], selected: null },
  render: {
    renderId: null,
    stage: "idle",
    progress: 0,
    artifactUrl: null,
    artifacts: [],
  },
  banner: null,
};

export const useProjectStore = create<
  InitialState & {
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
  }
>((set) => ({
  ...initial,
  setStyle: (style) => set((s) => ({ project: { ...s.project, style } })),
  setTargetDuration: (sec) =>
    set((s) => ({ project: { ...s.project, targetDurationSec: sec } })),
  setAudience: (audience) =>
    set((s) => ({ project: { ...s.project, audience } })),
  setTitle: (title) => set((s) => ({ project: { ...s.project, title } })),
  addVideo: (v) => set((s) => ({ videos: [...s.videos, v] })),
  setPlotAnalysis: (a) => set({ plotAnalysis: a }),
  appendScene: (s) =>
    set((st) => ({
      plotAnalysis: { scenes: [...st.plotAnalysis.scenes, s] },
    })),
  setScriptSegments: (segs) => set({ script: { segments: segs } }),
  updateSegmentText: (id, text) =>
    set((s) => ({
      script: {
        segments: s.script.segments.map((seg) =>
          seg.id === id ? { ...seg, text } : seg,
        ),
      },
    })),
  setVoiceCandidates: (vs) =>
    set((s) => ({ voice: { ...s.voice, candidates: vs } })),
  selectVoice: (id) => set((s) => ({ voice: { ...s.voice, selected: id } })),
  setRenderStart: (renderId) =>
    set({
      render: {
        renderId,
        stage: "tts",
        progress: 0,
        artifactUrl: null,
        artifacts: [],
      },
    }),
  setRenderProgress: (stage, progress) =>
    set((s) => ({ render: { ...s.render, stage, progress } })),
  setRenderArtifact: (url) =>
    set((s) => ({
      render: {
        ...s.render,
        artifactUrl: url,
        artifacts: [
          ...s.render.artifacts,
          { kind: "draft", url, label: "剪映草稿 zip" },
        ],
      },
    })),
  setBanner: (kind, text) => set({ banner: { kind, text } }),
  clearBanner: () => set({ banner: null }),
  reset: () => set(initial),
}));
