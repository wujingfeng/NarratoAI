import { useEffect, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { NarrationEditor } from "../features/narration-editor/NarrationEditor.jsx";
import { getProjectStage, submitRender } from "../features/projects/projectApi.js";
import { normalizeStageSnapshot, stagePath } from "../features/projects/narrationStage.js";

export function NarrationEditorPage() {
  const { state } = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const projectId = searchParams.get("projectId") || state?.projectId;
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [generating, setGenerating] = useState(false);
  useEffect(() => {
    let active = true;
    if (!projectId) { setError("缺少项目标识，请从任务流程进入编辑片段。"); return undefined; }
    getProjectStage(projectId).then((payload) => {
      if (!active) return;
      const snapshot = normalizeStageSnapshot(payload);
      if (snapshot.currentStage !== "edit") navigate(stagePath(snapshot.currentStage, projectId), { replace: true });
      else setReady(true);
    }).catch((requestError) => active && setError(requestError.message || "任务阶段读取失败。"));
    return () => { active = false; };
  }, [navigate, projectId]);
  const generate = async () => {
    if (!projectId || generating) return;
    setGenerating(true);
    try {
      await submitRender(projectId);
      navigate(stagePath("render", projectId), { replace: true });
    } catch (requestError) { setError(requestError.message || "无法开始生成视频。"); setGenerating(false); }
  };
  if (error) return <main className="editor-shell"><p role="alert">{error}</p></main>;
  if (!ready) return <main className="editor-shell"><p>正在验证编辑权限…</p></main>;
  return <NarrationEditor projectId={projectId} onGenerate={generate} generating={generating} />;
}
