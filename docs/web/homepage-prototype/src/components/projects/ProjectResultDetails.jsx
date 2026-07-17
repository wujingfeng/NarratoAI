import { DownloadSimple, Export } from "@phosphor-icons/react";

/** 终态失败项目没有任何下载或导出动作，完成项目固定保留两个出口。 */
export function ProjectResultDetails({ project, onExportJianying }) {
  if (project.status !== "completed") return null;
  const videoUrl = project.artifacts?.find((artifact) => artifact.kind === "video")?.cdn_url;
  return (
    <section aria-label="项目导出">
      <h2>项目已完成</h2>
      {videoUrl && <a href={videoUrl} download><DownloadSimple aria-hidden="true" />导出视频</a>}
      <button type="button" onClick={onExportJianying}><Export aria-hidden="true" />导出到剪映草稿</button>
    </section>
  );
}
