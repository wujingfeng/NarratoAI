import { useChat } from "@ai-sdk/react";
import { useProjectStore } from "../project/store";
import { getJSON, postJSON, subscribeSSE } from "../../lib/api";
import type { ScriptSegment, Voice } from "../project/types";

export function useWorkbench(projectId: string) {
  const setStyle = useProjectStore((s) => s.setStyle);
  const setTargetDuration = useProjectStore((s) => s.setTargetDuration);
  const setPlotAnalysis = useProjectStore((s) => s.setPlotAnalysis);
  const setScriptSegments = useProjectStore((s) => s.setScriptSegments);
  const updateSegmentText = useProjectStore((s) => s.updateSegmentText);
  const setVoiceCandidates = useProjectStore((s) => s.setVoiceCandidates);
  const selectVoice = useProjectStore((s) => s.selectVoice);
  const setRenderStart = useProjectStore((s) => s.setRenderStart);
  const setRenderProgress = useProjectStore((s) => s.setRenderProgress);
  const setRenderArtifact = useProjectStore((s) => s.setRenderArtifact);
  const setBanner = useProjectStore((s) => s.setBanner);

  return useChat({
    api: "/api/chat",
    body: { projectId },
    onError: (err) => setBanner("error", `LLM 错误：${err.message}`),
    onToolCall: async ({ toolCall }) => {
      const { toolName, args } = toolCall;
      try {
        switch (toolName) {
          case "set_narration_style": {
            const a = args as { style: "悬疑" | "搞笑" | "深情" | "冷静" };
            setStyle(a.style);
            return { ok: true, style: a.style };
          }
          case "set_target_duration": {
            const a = args as { targetSec: number };
            setTargetDuration(a.targetSec);
            return { ok: true, targetSec: a.targetSec };
          }
          case "analyze_plot": {
            const a = args as { projectId: string };
            return new Promise<{ ok: boolean }>((resolve) => {
              subscribeSSE("/api/analyze", (event, data) => {
                if (event === "result") {
                  const d = data as { scenes: import("../project/types").Scene[] };
                  setPlotAnalysis({ scenes: d.scenes });
                  resolve({ ok: true });
                }
              });
              postJSON("/api/analyze", { projectId: a.projectId }).catch((err) => {
                setBanner("error", `分析失败：${err.message}`);
                resolve({ ok: false });
              });
            });
          }
          case "generate_script": {
            const a = args as {
              projectId: string;
              style: string;
              targetSec: number;
            };
            return new Promise<{ ok: boolean }>((resolve) => {
              subscribeSSE("/api/script/generate", (event, data) => {
                if (event === "result") {
                  setScriptSegments(data as ScriptSegment[]);
                  resolve({ ok: true });
                }
              });
              postJSON("/api/script/generate", a).catch((err) => {
                setBanner("error", `脚本生成失败：${err.message}`);
                resolve({ ok: false });
              });
            });
          }
          case "edit_script_segment": {
            const a = args as {
              projectId: string;
              segmentId: string;
              newText: string;
            };
            updateSegmentText(a.segmentId, a.newText);
            const r = await postJSON<{ segment: ScriptSegment }>(
              "/api/script/edit",
              a,
            );
            return { ok: true, segment: r.segment };
          }
          case "regenerate_segment": {
            const a = args as {
              projectId: string;
              segmentId: string;
              hint?: string;
            };
            const r = await postJSON<{ segment: ScriptSegment }>(
              "/api/script/regenerate",
              a,
            );
            updateSegmentText(a.segmentId, r.segment.text);
            return { ok: true, segment: r.segment };
          }
          case "list_voices": {
            const a = (args as { language?: "zh" | "en" }) ?? {};
            const url = a.language
              ? `/api/voices?language=${a.language}`
              : "/api/voices";
            const voices = await getJSON<Voice[]>(url);
            setVoiceCandidates(voices);
            return { ok: true, voices };
          }
          case "select_voice": {
            const a = args as { projectId: string; voiceId: string };
            selectVoice(a.voiceId);
            return { ok: true, voiceId: a.voiceId };
          }
          case "start_render": {
            const a = args as { projectId: string };
            const r = await postJSON<{ renderId: string }>(
              "/api/render/start",
              a,
            );
            setRenderStart(r.renderId);
            subscribeSSE(`/api/render/${r.renderId}/status`, (event, data) => {
              const d = data as { progress: number; artifactUrl?: string };
              if (event === "done") {
                setRenderProgress("done", 1);
                if (d.artifactUrl) setRenderArtifact(d.artifactUrl);
              } else {
                setRenderProgress(
                  event as "tts" | "subtitle" | "mixing" | "encoding",
                  d.progress,
                );
              }
            });
            return { ok: true, renderId: r.renderId };
          }
          case "track_render_status": {
            const a = args as { renderId: string };
            return new Promise<{ ok: boolean }>((resolve) => {
              subscribeSSE(`/api/render/${a.renderId}/status`, (event, data) => {
                const d = data as { progress: number };
                if (event === "done") {
                  setRenderProgress("done", 1);
                  resolve({ ok: true });
                } else {
                  setRenderProgress(
                    event as "tts" | "subtitle" | "mixing" | "encoding",
                    d.progress,
                  );
                }
              });
            });
          }
          default:
            return { ok: false, error: `Unknown tool: ${toolName}` };
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : "工具执行失败";
        setBanner("error", `${toolName} 失败：${msg}`);
        return { ok: false, error: msg };
      }
    },
  });
}
