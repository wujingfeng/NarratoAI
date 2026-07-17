import { useState } from "react";
import { ProjectResultDetails } from "../components/projects/ProjectResultDetails.jsx";
import { exportJianyingZip } from "../features/exports/jianyingZip.js";
import { apiRequest } from "../services/httpClient.js";

/** 项目结果页只消费完成项目结果；失败状态不渲染下载入口。 */
export function ProjectResultPage({ project }) {
  const [error, setError] = useState("");
  const exportDraft = async () => {
    try {
      setError("");
      const manifest = await apiRequest(`/projects/${project.id}/exports/jianying-manifest`, { method: "POST" });
      await exportJianyingZip(manifest);
    } catch (reason) {
      setError(`${reason.message || "导出失败"}，请重试。`);
    }
  };
  return <><ProjectResultDetails project={project} onExportJianying={exportDraft} />{error && <p role="alert">{error}</p>}</>;
}
