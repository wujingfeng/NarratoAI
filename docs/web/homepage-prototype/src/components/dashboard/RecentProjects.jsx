import { ArrowRight } from "@phosphor-icons/react";
import { DashboardThumbnail } from "./DashboardThumbnail.jsx";
import { useI18n } from "../../i18n/useI18n.js";

export function RecentProjects({ projects, onUnavailable }) {
  const { formatNumber, t } = useI18n();
  return (
    <section className="recent-projects" aria-labelledby="recent-projects-title">
      <div className="dashboard-section-heading">
        <div><p>{t("dashboard.recent.eyebrow")}</p><h2 id="recent-projects-title">{t("dashboard.recent.title")}</h2></div>
        <button type="button" onClick={() => onUnavailable(t("dashboard.unavailable.allProjects"))}>{t("dashboard.recent.viewAll")}<ArrowRight aria-hidden="true" /></button>
      </div>
      <div className="recent-projects__list">
        {projects.map((project) => (
          <button
            className="recent-projects__item"
            type="button"
            data-project-status={project.status}
            onClick={() => onUnavailable(t("dashboard.unavailable.project", { name: project.title }))}
            key={project.id}
          >
            <DashboardThumbnail src={project.image} alt={t("dashboard.coverAlt", { name: project.title })} fallbackLabel={t(`dashboard.nav.${project.type}`)} />
            <span className="recent-projects__details">
              <strong>{project.title}</strong>
              <small>{t(`dashboard.nav.${project.type}`)}</small>
            </span>
            <span className={`recent-projects__status recent-projects__status--${project.status}`}>
              {project.progress !== null && <progress value={project.progress} max="100">{project.progress}%</progress>}
              <span>{t(project.statusKey, { progress: project.progress })}</span>
              <small className="recent-projects__credits">{t("dashboard.recent.creditsUsed", { count: formatNumber(project.credits) })}</small>
            </span>
            <ArrowRight className="recent-projects__arrow" aria-hidden="true" />
          </button>
        ))}
      </div>
    </section>
  );
}
