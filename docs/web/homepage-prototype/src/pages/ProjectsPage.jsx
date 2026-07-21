import { useCallback, useEffect, useMemo, useState } from "react";
import { Info, MagnifyingGlass, MagicWand } from "@phosphor-icons/react";
import { Link } from "react-router-dom";
import { DashboardHeader } from "../components/dashboard/DashboardHeader.jsx";
import { DashboardMobileNav } from "../components/dashboard/DashboardMobileNav.jsx";
import { DashboardSidebar } from "../components/dashboard/DashboardSidebar.jsx";
import { DashboardToast } from "../components/dashboard/DashboardToast.jsx";
import { ProjectFilters } from "../components/projects/ProjectFilters.jsx";
import { ProjectPagination } from "../components/projects/ProjectPagination.jsx";
import { ProjectTable } from "../components/projects/ProjectTable.jsx";
import { dashboardCredits, dashboardNavItems } from "../data/dashboardData.js";
import { projectCategories, projects, projectStatusOptions } from "../data/projectsData.js";
import { useI18n } from "../i18n/useI18n.js";

export function ProjectsPage() {
  const { formatNumber, t } = useI18n();
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const [status, setStatus] = useState("all");
  const [page, setPage] = useState(1);
  const [toast, setToast] = useState({ id: 0, message: "" });
  const showToast = useCallback((message) => setToast(({ id }) => ({ id: id + 1, message })), []);
  const updateFilter = (setter) => (value) => { setter(value); setPage(1); };
  const filteredProjects = useMemo(() => projects.filter((project) =>
    (category === "all" || project.type === category) &&
    (status === "all" || project.status === status) &&
    project.title.toLowerCase().includes(query.trim().toLowerCase()),
  ), [category, status, query]);

  useEffect(() => {
    if (!toast.message) return undefined;
    const timer = window.setTimeout(() => setToast(({ id }) => ({ id, message: "" })), 3200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  return <div className="dashboard-shell projects-shell" data-page="projects">
    <h1 className="sr-only" data-route-heading tabIndex="-1">{t("projects.routeHeading")}</h1>
    <DashboardSidebar items={dashboardNavItems} onUnavailable={showToast} />
    <div className="dashboard-workspace">
      <DashboardHeader credits={dashboardCredits} onUnavailable={showToast} />
      <main className="projects-main">
        <section className="projects-heading" aria-labelledby="projects-title">
          <div><h2 id="projects-title">{t("projects.heading")}</h2><p>{t("projects.description")}</p></div>
          <div className="projects-heading__actions"><label className="project-search"><MagnifyingGlass aria-hidden="true" /><span className="sr-only">{t("projects.search")}</span><input value={query} onChange={(event) => updateFilter(setQuery)(event.target.value)} placeholder={t("projects.search")} /></label><Link to="/dashboard/create" className="projects-create"><MagicWand aria-hidden="true" />{t("projects.create")}</Link></div>
        </section>
        <div className="projects-notice"><Info aria-hidden="true" /><span>{t("projects.notice")}</span></div>
        <ProjectFilters categories={projectCategories} activeCategory={category} onCategoryChange={updateFilter(setCategory)} status={status} statuses={projectStatusOptions} onStatusChange={updateFilter(setStatus)} />
        <ProjectTable projects={filteredProjects} onAction={(action, project) => showToast(t("projects.messages.unavailable", { name: project.title, action: t(`projects.actions.${action}`) }))} />
        <ProjectPagination page={page} pages={2} onPageChange={(nextPage) => { setPage(nextPage); showToast(t("projects.messages.pageChanged", { page: formatNumber(nextPage) })); }} />
      </main>
    </div>
    <DashboardMobileNav items={dashboardNavItems} onUnavailable={showToast} />
    {toast.message && <DashboardToast key={toast.id} message={toast.message} onClose={() => setToast(({ id }) => ({ id, message: "" }))} />}
  </div>;
}
