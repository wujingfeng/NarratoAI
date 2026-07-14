import { ArrowRight } from "@phosphor-icons/react";
import { DashboardThumbnail } from "./DashboardThumbnail.jsx";

export function RecentProjects({ projects, onUnavailable }) {
  return (
    <section className="recent-projects" aria-labelledby="recent-projects-title">
      <div className="dashboard-section-heading">
        <div><p>最近动态</p><h2 id="recent-projects-title">最近项目</h2></div>
        <button type="button" onClick={() => onUnavailable("全部项目功能建设中")}>查看全部<ArrowRight aria-hidden="true" /></button>
      </div>
      <div className="recent-projects__list">
        {projects.map((project) => (
          <button
            className="recent-projects__item"
            type="button"
            data-project-status={project.status}
            onClick={() => onUnavailable(`${project.title}功能建设中`)}
            key={project.id}
          >
            <DashboardThumbnail src={project.image} alt={`${project.title}封面`} fallbackLabel={project.tool} />
            <span className="recent-projects__details">
              <strong>{project.title}</strong>
              <small>{project.tool} · 消耗 {project.credits} 创作点</small>
            </span>
            <span className={`recent-projects__status recent-projects__status--${project.status}`}>
              {project.progress !== null && <progress value={project.progress} max="100">{project.progress}%</progress>}
              <span>{project.statusLabel}</span>
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}
