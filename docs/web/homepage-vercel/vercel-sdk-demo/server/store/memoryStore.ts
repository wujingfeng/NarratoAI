/**
 * 进程内数据存储。重启后清空。用于 demo 演示，演示完不留脏数据。
 */
export type ProjectData = {
  id: string;
  title: string;
  style?: "悬疑" | "搞笑" | "深情" | "冷静";
  targetDurationSec?: number;
  audience?: string;
  selectedVoiceId?: string;
  createdAt: number;
};

export type MessageData = {
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  timestamp: number;
  toolName?: string;
};

export type RenderData = {
  renderId: string;
  projectId: string;
  stage: string;
  progress: number;
  startedAt: number;
  finishedAt?: number;
  artifactUrl?: string;
};

const projects = new Map<string, ProjectData>();
const messages = new Map<string, MessageData[]>();
const renders = new Map<string, RenderData>();

export const memoryStore = {
  setProject(
    id: string,
    data: Partial<ProjectData> & { id?: string; title?: string },
  ): ProjectData {
    const existing = projects.get(id);
    const merged: ProjectData = {
      id,
      title: data.title ?? existing?.title ?? "未命名项目",
      ...(data.style !== undefined
        ? { style: data.style }
        : existing?.style !== undefined
          ? { style: existing.style }
          : {}),
      ...(data.targetDurationSec !== undefined
        ? { targetDurationSec: data.targetDurationSec }
        : existing?.targetDurationSec !== undefined
          ? { targetDurationSec: existing.targetDurationSec }
          : {}),
      ...(data.audience !== undefined
        ? { audience: data.audience }
        : existing?.audience !== undefined
          ? { audience: existing.audience }
          : {}),
      ...(data.selectedVoiceId !== undefined
        ? { selectedVoiceId: data.selectedVoiceId }
        : existing?.selectedVoiceId !== undefined
          ? { selectedVoiceId: existing.selectedVoiceId }
          : {}),
      createdAt: existing?.createdAt ?? Date.now(),
    };
    projects.set(id, merged);
    return merged;
  },

  getProject(id: string): ProjectData | undefined {
    return projects.get(id);
  },

  appendMessage(projectId: string, msg: Omit<MessageData, "timestamp">): void {
    const list = messages.get(projectId) ?? [];
    list.push({ ...msg, timestamp: Date.now() });
    messages.set(projectId, list);
  },

  getMessages(projectId: string): MessageData[] {
    return messages.get(projectId) ?? [];
  },

  setRender(
    renderId: string,
    data: Partial<RenderData> & { projectId: string },
  ): RenderData {
    const existing = renders.get(renderId);
    const merged: RenderData = {
      renderId,
      projectId: data.projectId,
      stage: data.stage ?? existing?.stage ?? "idle",
      progress: data.progress ?? existing?.progress ?? 0,
      startedAt: existing?.startedAt ?? Date.now(),
      ...(data.finishedAt !== undefined
        ? { finishedAt: data.finishedAt }
        : existing?.finishedAt !== undefined
          ? { finishedAt: existing.finishedAt }
          : {}),
      ...(data.artifactUrl !== undefined
        ? { artifactUrl: data.artifactUrl }
        : existing?.artifactUrl !== undefined
          ? { artifactUrl: existing.artifactUrl }
          : {}),
    };
    renders.set(renderId, merged);
    return merged;
  },

  getRender(renderId: string): RenderData | undefined {
    return renders.get(renderId);
  },

  clear(): void {
    projects.clear();
    messages.clear();
    renders.clear();
  },
};
