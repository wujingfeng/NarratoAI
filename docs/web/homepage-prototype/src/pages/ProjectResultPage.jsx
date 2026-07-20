import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { ProjectResultDetails } from "../components/projects/ProjectResultDetails.jsx";
import { exportJianyingZip } from "../features/exports/jianyingZip.js";
import { getProjectResult } from "../features/projects/projectApi.js";
import { apiRequest } from "../services/httpClient.js";

/** 项目结果页只消费完成项目结果；失败状态不渲染下载入口。 */
export function ProjectResultPage() {
  const { projectId } = useParams();
  const [project, setProject] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setProject(null);
    setLoading(true);
    setError("");
    getProjectResult(projectId)
      .then((result) => { if (active) setProject(result); })
      .catch((reason) => { if (active) setError(reason.message || "无法加载项目结果"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [projectId]);

  const exportDraft = async () => {
    try {
      setError("");
      const manifest = await apiRequest(`/projects/${project.id}/exports/jianying-manifest`, { method: "POST" });
      await exportJianyingZip(manifest);
    } catch (reason) {
      setError(`${reason.message || "导出失败"}，请重试。`);
    }
  };
  if (loading) return <p aria-live="polite">正在加载项目结果…</p>;
  if (!project) return <p role="alert">{error || "项目结果不可用"}</p>;
  return <><ProjectResultDetails project={project} onExportJianying={exportDraft} />{error && <p role="alert">{error}</p>}</>;
}
