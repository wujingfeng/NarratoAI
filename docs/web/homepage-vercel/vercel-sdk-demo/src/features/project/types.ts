export type NarrationStyle = "悬疑" | "搞笑" | "深情" | "冷静";
export type RenderStage =
  | "idle"
  | "tts"
  | "subtitle"
  | "mixing"
  | "encoding"
  | "done"
  | "failed";

export type Project = {
  id: string;
  title: string;
  style: NarrationStyle;
  targetDurationSec: number;
  audience: string;
};

export type Video = {
  id: string;
  name: string;
  durationSec: number;
  thumbnailUrl: string;
};

export type Scene = {
  start: number;
  end: number;
  summary: string;
  keyCharacters: string[];
};

export type PlotAnalysis = { scenes: Scene[] };

export type ScriptSegment = {
  id: string;
  start: number;
  end: number;
  text: string;
  tone: string;
};

export type Script = { segments: ScriptSegment[] };

export type Voice = {
  id: string;
  name: string;
  gender: "male" | "female";
  age: string;
  tone: string;
};

export type Artifact = {
  kind: "video" | "audio" | "subtitle" | "draft";
  url: string;
  label: string;
};

export type Render = {
  renderId: string | null;
  stage: RenderStage;
  progress: number;
  artifactUrl: string | null;
  artifacts: Artifact[];
};

export type InitialState = {
  project: Project;
  videos: Video[];
  plotAnalysis: PlotAnalysis;
  script: Script;
  voice: { candidates: Voice[]; selected: string | null };
  render: Render;
  banner: { kind: "error" | "warning" | "info"; text: string } | null;
};
