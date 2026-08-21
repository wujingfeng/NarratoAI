import { useEffect, useRef } from "react";
import { CheckCircle, Clock, DownloadSimple, Eye, FileText, PlayCircle, WarningCircle } from "@phosphor-icons/react";
import { DashboardThumbnail } from "../dashboard/DashboardThumbnail.jsx";
import { Link } from "react-router-dom";
import { useI18n } from "../../i18n/useI18n.js";
import { stagePath } from "../../features/projects/narrationStage.js";

const typeIcon = { narration: FileText, translation: PlayCircle, remix: WarningCircle };

function SelectionCheckbox({ checked, indeterminate = false, disabled = false, label, onChange }) {
  const inputRef = useRef(null);
  useEffect(() => {
    if (inputRef.current) inputRef.current.indeterminate = indeterminate;
  }, [indeterminate]);
  return <input ref={inputRef} className="project-selection-checkbox" type="checkbox" checked={checked} disabled={disabled} aria-label={label} aria-checked={indeterminate ? "mixed" : checked} onChange={onChange} />;
}

function ProjectStatus({ project }) {
  const { t } = useI18n();
  if (project.status === "processing") return <div className="project-status project-status--processing"><Clock aria-hidden="true" /><span><strong>{t(project.statusKey)}</strong><small>{t(project.processingStageKey)}</small></span></div>;
  const Icon = project.status === "complete" ? CheckCircle : project.status === "failed" ? WarningCircle : Clock;
  return <span className={`project-status project-status--${project.status}`}><Icon aria-hidden="true" />{t(project.statusKey)}{project.status === "failed" && <small>{t("projects.actions.reason")} ›</small>}</span>;
}

function ProjectActions({ project, continuing, exporting, onAction }) {
  const { t } = useI18n();
  let statusActions;
  if (project.status === "complete") {
    statusActions = <>{project.resultPath ? <Link to={project.resultPath}><Eye aria-hidden="true" />{t("projects.actions.result")}</Link> : <button type="button" onClick={() => onAction("result", project)}><Eye aria-hidden="true" />{t("projects.actions.result")}</button>}<button className="project-actions__export" type="button" disabled={exporting} aria-busy={exporting} onClick={() => onAction("export", project)}><DownloadSimple aria-hidden="true" />{exporting ? t("projects.actions.exporting") : t("projects.actions.export")}</button></>;
  } else if (project.status === "processing") {
    statusActions = <Link to={project.progressPath || stagePath(project.current_stage, project.id)}>{t("projects.actions.progress")}</Link>;
  } else if (project.status === "draft") {
    statusActions = <button className="project-actions__continue" type="button" disabled={continuing} aria-busy={continuing} onClick={() => onAction("continue", project)}>{t("projects.actions.continue")}</button>;
  } else {
    statusActions = <button className="project-actions__reason" type="button" onClick={() => onAction("reason", project)}>{t("projects.actions.reason")}</button>;
  }
  return <div className="project-actions">{statusActions}<button className="project-actions__retry" type="button" onClick={() => onAction("retry", project)}>↻ {t("projects.actions.retry")}</button></div>;
}

export function ProjectTable({ projects, selectedProjectIds, deleting, continuingProjectId, exportingProjectId, onAction, onSelectionChange, onToggleAll }) {
  const { formatDate, formatNumber, t } = useI18n();
  if (projects.length === 0) return <div className="projects-empty"><FileText aria-hidden="true" /><strong>{t("projects.empty.title")}</strong><span>{t("projects.empty.description")}</span></div>;
  const deletableProjects = projects.filter((project) => project.canDelete);
  const selectedDeletableCount = deletableProjects.filter((project) => selectedProjectIds.has(project.id)).length;
  const allDeletableSelected = deletableProjects.length > 0 && selectedDeletableCount === deletableProjects.length;
  return (
    <div className="projects-table-wrap">
      <table className="projects-table">
        <thead><tr><th className="project-select-cell"><SelectionCheckbox checked={allDeletableSelected} indeterminate={selectedDeletableCount > 0 && !allDeletableSelected} disabled={deleting || deletableProjects.length === 0} label={t("projects.bulkDelete.selectAll")} onChange={(event) => onToggleAll(event.target.checked)} /></th><th>{t("projects.table.project")}</th><th>{t("projects.table.type")}</th><th>{t("projects.table.status")}</th><th>{t("projects.table.created")}</th><th>{t("projects.table.credits")}</th><th>{t("projects.table.actions")}</th></tr></thead>
        <tbody>{projects.map((project) => {
          const Icon = typeIcon[project.type];
          const selected = selectedProjectIds.has(project.id);
          return <tr key={project.id} className={selected ? "is-selected" : undefined}>
            <td className="project-select-cell"><SelectionCheckbox checked={selected} disabled={deleting || !project.canDelete} label={project.canDelete ? t("projects.bulkDelete.selectProject", { name: project.title }) : t("projects.bulkDelete.unavailable", { name: project.title })} onChange={(event) => onSelectionChange(project.id, event.target.checked)} /></td>
            <td><span className="project-mobile-field-label sr-only">{t("projects.table.project")}</span><div className="project-name"><DashboardThumbnail src={project.image} alt={t("dashboard.thumbnailAlt", { name: project.title })} fallbackLabel={project.title} mediaType="video" /><div><strong>{project.title}</strong><small>素材 × {project.videoCount}</small><small><Clock aria-hidden="true" />{project.duration}</small></div></div></td>
            <td><span className={`project-type project-type--${project.type}`}><Icon aria-hidden="true" />{t(project.typeKey)}</span></td>
            <td><span className="project-mobile-field-label sr-only">{t("projects.table.status")}</span><ProjectStatus project={project} /></td><td className="project-date">{formatDate(project.createdAt, { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Shanghai" })}</td><td className="project-credits">{formatNumber(project.credits)}</td><td><span className="project-mobile-field-label sr-only">{t("projects.table.actions")}</span><ProjectActions project={project} continuing={continuingProjectId === project.id} exporting={exportingProjectId === project.id} onAction={onAction} /></td>
          </tr>;
        })}</tbody>
      </table>
    </div>
  );
}
