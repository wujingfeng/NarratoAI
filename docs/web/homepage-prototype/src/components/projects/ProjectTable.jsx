import { CheckCircle, Clock, DownloadSimple, Eye, FileText, PlayCircle, WarningCircle } from "@phosphor-icons/react";
import { DashboardThumbnail } from "../dashboard/DashboardThumbnail.jsx";
import { Link } from "react-router-dom";
import { useI18n } from "../../i18n/useI18n.js";

const typeIcon = { narration: FileText, translation: PlayCircle, remix: WarningCircle };

function ProjectStatus({ project }) {
  const { t } = useI18n();
  if (project.status === "processing") return <div className="project-status project-status--processing"><strong>{t(project.statusKey, { progress: project.progress })}</strong><progress value={project.progress} max="100" aria-label={t("projects.table.progress", { name: project.title, progress: project.progress })} /></div>;
  const Icon = project.status === "complete" ? CheckCircle : project.status === "failed" ? WarningCircle : Clock;
  return <span className={`project-status project-status--${project.status}`}><Icon aria-hidden="true" />{t(project.statusKey)}{project.status === "failed" && <small>{t("projects.actions.reason")} ›</small>}</span>;
}

function ProjectActions({ project, onAction }) {
  const { t } = useI18n();
  if (project.status === "complete") return <div className="project-actions">{project.resultPath ? <Link to={project.resultPath}><Eye aria-hidden="true" />{t("projects.actions.result")}</Link> : <button type="button" onClick={() => onAction("result", project)}><Eye aria-hidden="true" />{t("projects.actions.result")}</button>}<button className="project-actions__export" type="button" onClick={() => onAction("export", project)}><DownloadSimple aria-hidden="true" />{t("projects.actions.export")}</button></div>;
  if (project.status === "processing") return <div className="project-actions"><button type="button" onClick={() => onAction("progress", project)}>{t("projects.actions.progress")}</button></div>;
  if (project.status === "draft") return <div className="project-actions"><button className="project-actions__continue" type="button" onClick={() => onAction("continue", project)}>{t("projects.actions.continue")}</button></div>;
  return <div className="project-actions"><button className="project-actions__reason" type="button" onClick={() => onAction("reason", project)}>{t("projects.actions.reason")}</button><button className="project-actions__retry" type="button" onClick={() => onAction("retry", project)}>↻ {t("projects.actions.retry")}</button></div>;
}

export function ProjectTable({ projects, onAction }) {
  const { formatDate, formatNumber, t } = useI18n();
  if (projects.length === 0) return <div className="projects-empty"><FileText aria-hidden="true" /><strong>{t("projects.empty.title")}</strong><span>{t("projects.empty.description")}</span></div>;
  return (
    <div className="projects-table-wrap">
      <table className="projects-table">
        <thead><tr><th>{t("projects.table.project")}</th><th>{t("projects.table.type")}</th><th>{t("projects.table.status")}</th><th>{t("projects.table.created")}</th><th>{t("projects.table.credits")}</th><th>{t("projects.table.actions")}</th></tr></thead>
        <tbody>{projects.map((project) => {
          const Icon = typeIcon[project.type];
          return <tr key={project.id}>
            <td><div className="project-name"><DashboardThumbnail src={project.image} alt={t("dashboard.thumbnailAlt", { name: project.title })} fallbackLabel={project.title} /><div><strong>{project.title}</strong><small><Clock aria-hidden="true" />{project.duration}</small></div></div></td>
            <td><span className={`project-type project-type--${project.type}`}><Icon aria-hidden="true" />{t(project.typeKey)}</span></td>
            <td><ProjectStatus project={project} /></td><td className="project-date">{formatDate(project.createdAt, { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Shanghai" })}</td><td className="project-credits">{formatNumber(project.credits)}</td><td><ProjectActions project={project} onAction={onAction} /></td>
          </tr>;
        })}</tbody>
      </table>
    </div>
  );
}
