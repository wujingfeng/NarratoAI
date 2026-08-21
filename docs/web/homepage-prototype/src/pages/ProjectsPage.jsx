import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CheckSquare, Info, MagnifyingGlass, MagicWand, Trash } from "@phosphor-icons/react";
import { Link, useNavigate } from "react-router-dom";
import { DashboardHeader } from "../components/dashboard/DashboardHeader.jsx";
import { DashboardMobileNav } from "../components/dashboard/DashboardMobileNav.jsx";
import { DashboardSidebar } from "../components/dashboard/DashboardSidebar.jsx";
import { DashboardToast } from "../components/dashboard/DashboardToast.jsx";
import { ProjectFilters } from "../components/projects/ProjectFilters.jsx";
import { ProjectDeletionDialog } from "../components/projects/ProjectDeletionDialog.jsx";
import { ProjectPagination } from "../components/projects/ProjectPagination.jsx";
import { ProjectTable } from "../components/projects/ProjectTable.jsx";
import { dashboardNavItems } from "../data/dashboardData.js";
import { projectCategories, projectStatusOptions } from "../data/projectsData.js";
import { useAuth } from "../features/auth/AuthProvider.jsx";
import { getProjectResult, getProjectStage, listProjects, requestProjectDeletion, retryUploadPath } from "../features/projects/projectApi.js";
import { downloadArtifact } from "../features/exports/artifactDownload.js";
import { deletableProjectIds, isProjectDeletable, reconcileProjectSelection, toggleAllDeletableProjects, toggleProjectSelection } from "../features/projects/projectDeletion.js";
import { normalizeNarrationStage, normalizeStageSnapshot, stagePath } from "../features/projects/narrationStage.js";
import { getTranslationStage } from "../features/video-translation/translationApi.js";
import { useI18n } from "../i18n/useI18n.js";

export function ProjectsPage() {
  const { formatNumber, t } = useI18n();
  const { user } = useAuth();
  const navigate = useNavigate();
  const projectsTitleRef = useRef(null);
  const focusTitleAfterRefreshRef = useRef(false);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const [status, setStatus] = useState("all");
  const [page, setPage] = useState(1);
  const [projectPage, setProjectPage] = useState({ items: [], total: 0, page: 1, page_size: 10 });
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [selectedProjectIds, setSelectedProjectIds] = useState(() => new Set());
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [continuingProjectId, setContinuingProjectId] = useState("");
  const [exportingProjectId, setExportingProjectId] = useState("");
  const [toast, setToast] = useState({ id: 0, message: "" });
  const showToast = useCallback((message) => setToast(({ id }) => ({ id: id + 1, message })), []);
  const handleProjectAction = useCallback(async (action, project) => {
    if (action === "retry") {
      const path = retryUploadPath(project.product, project.id);
      if (!path) {
        showToast(t("projects.messages.retryUnsupported", { name: project.title }));
        return;
      }
      navigate(path);
      return;
    }
    if (action === "continue") {
      if (continuingProjectId) return;
      setContinuingProjectId(project.id);
      try {
        // 列表阶段可能已过期；继续编辑前必须重新读取服务端状态机，再进入真实当前阶段。
        if (project.product === "video_translation") {
          const stage = await getTranslationStage(project.id);
          navigate(translationPath(stage.current_stage || stage.stage, project.id));
        } else {
          const stage = normalizeStageSnapshot(await getProjectStage(project.id));
          navigate(stagePath(stage.currentStage, project.id));
        }
      } catch (error) {
        showToast(error?.message?.trim() || t("projects.messages.loadFailed"));
      } finally {
        setContinuingProjectId((current) => current === project.id ? "" : current);
      }
      return;
    }
    if (action === "export") {
      if (exportingProjectId) return;
      setExportingProjectId(project.id);
      try {
        const result = await getProjectResult(project.id);
        const video = result.artifacts?.find((artifact) => artifact.kind === "video");
        if (!video) throw new Error(t("projects.messages.exportVideoUnavailable", { name: project.title }));
        await downloadArtifact({
          ...video,
          content_type: "video/mp4",
          filename: `${project.title}.mp4`,
        });
        showToast(t("projects.messages.exportStarted", { name: project.title }));
      } catch (error) {
        showToast(error?.message?.trim() || t("projects.messages.exportFailed", { name: project.title }));
      } finally {
        setExportingProjectId((current) => current === project.id ? "" : current);
      }
      return;
    }
    if (action !== "reason") {
      showToast(t("projects.messages.unavailable", { name: project.title, action: t(`projects.actions.${action}`) }));
      return;
    }
    try {
      const stage = normalizeStageSnapshot(await getProjectStage(project.id));
      const reason = stage.failureCode || stage.analysisTasks.find((task) => task.errorCode)?.errorCode;
      showToast(reason
        ? t("projects.messages.failureReason", { name: project.title, reason })
        : t("projects.messages.failureReasonUnavailable", { name: project.title }));
    } catch {
      showToast(t("projects.messages.failureReasonReadFailed", { name: project.title }));
    }
  }, [continuingProjectId, exportingProjectId, navigate, showToast, t]);
  const updateFilter = (setter) => (value) => {
    setter(value);
    setPage(1);
    setSelectedProjectIds(new Set());
    setDeleteDialogOpen(false);
  };
  const pages = Math.max(1, Math.ceil(projectPage.total / projectPage.page_size));
  const filteredProjects = useMemo(() => projectPage.items.map((project) => toProjectRow(project)), [projectPage.items]);
  const currentPageDeletableIds = useMemo(() => deletableProjectIds(filteredProjects), [filteredProjects]);
  const allCurrentPageDeletableSelected = currentPageDeletableIds.length > 0 && currentPageDeletableIds.every((projectId) => selectedProjectIds.has(projectId));
  const loadErrorMessage = loadError === "projects.messages.loadFailed" ? t(loadError) : loadError;

  const handleSelectionChange = useCallback((projectId, checked) => {
    setSelectedProjectIds((current) => toggleProjectSelection(current, projectId, checked));
  }, []);
  const handleToggleAll = useCallback((checked) => {
    setSelectedProjectIds((current) => toggleAllDeletableProjects(current, filteredProjects, checked));
  }, [filteredProjects]);

  const handleBulkDelete = useCallback(async () => {
    const projectIds = [...selectedProjectIds];
    if (projectIds.length === 0 || deleting) return;
    setDeleting(true);
    const results = await Promise.allSettled(projectIds.map((projectId) => Promise.resolve().then(() => requestProjectDeletion(projectId))));
    const successfulIds = new Set(projectIds.filter((_, index) => results[index].status === "fulfilled"));
    const successCount = successfulIds.size;
    const failureCount = projectIds.length - successCount;

    if (successCount > 0) {
      setProjectPage((current) => ({
        ...current,
        items: current.items.filter((project) => !successfulIds.has(project.id)),
        total: Math.max(0, current.total - successCount),
      }));
      setSelectedProjectIds((current) => {
        const next = new Set(current);
        for (const projectId of successfulIds) next.delete(projectId);
        return next;
      });
    }

    // 无论成功与否都重新读取服务端状态，避免提交期间的阶段变化留下陈旧选择。
    focusTitleAfterRefreshRef.current = true;
    setRefreshVersion((current) => current + 1);
    setDeleteDialogOpen(false);
    setDeleting(false);
    if (failureCount === 0) {
      showToast(t("projects.messages.deleteSuccess", { count: formatNumber(successCount) }));
    } else if (successCount > 0) {
      showToast(t("projects.messages.deletePartial", { success: formatNumber(successCount), failed: formatNumber(failureCount) }));
    } else {
      showToast(t("projects.messages.deleteFailed", { count: formatNumber(failureCount) }));
    }
  }, [deleting, formatNumber, selectedProjectIds, showToast, t]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setLoadError("");
    listProjects({ page, query, status, product: productFilterForCategory(category), signal: controller.signal })
      .then((data) => {
        const lastPage = Math.max(1, Math.ceil(data.total / data.page_size));
        if (page > lastPage) {
          // 先保留失败项选择；回退页加载后由项目 ID 对账，兼容并发删除导致项目前移。
          setDeleteDialogOpen(false);
          setPage(lastPage);
          return;
        }
        setProjectPage(data);
      })
      .catch((error) => {
        if (error?.name !== "AbortError") setLoadError(error?.message?.trim() || "projects.messages.loadFailed");
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [category, page, query, refreshVersion, status]);

  useEffect(() => {
    setSelectedProjectIds((current) => reconcileProjectSelection(current, filteredProjects));
  }, [filteredProjects]);

  useEffect(() => {
    if (!loading && focusTitleAfterRefreshRef.current && (loadError || projectPage.page === page)) {
      focusTitleAfterRefreshRef.current = false;
      projectsTitleRef.current?.focus();
    }
  }, [loadError, loading, page, projectPage.page]);

  useEffect(() => {
    if (!toast.message) return undefined;
    const timer = window.setTimeout(() => setToast(({ id }) => ({ id, message: "" })), 3200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  return <div className="dashboard-shell projects-shell" data-page="projects">
    <h1 className="sr-only" data-route-heading tabIndex="-1">{t("projects.routeHeading")}</h1>
    <DashboardSidebar items={dashboardNavItems} onUnavailable={showToast} />
    <div className="dashboard-workspace">
      <DashboardHeader credits={{ balance: user?.credit_balance ?? null }} onUnavailable={showToast} />
      <main className="projects-main">
        <section className="projects-heading" aria-labelledby="projects-title">
          <div><h2 ref={projectsTitleRef} id="projects-title" tabIndex="-1">{t("projects.heading")}</h2><p>{t("projects.description")}</p></div>
          <div className="projects-heading__actions"><label className="project-search"><MagnifyingGlass aria-hidden="true" /><span className="sr-only">{t("projects.search")}</span><input value={query} onChange={(event) => updateFilter(setQuery)(event.target.value)} placeholder={t("projects.search")} /></label><Link to="/dashboard/create" className="projects-create"><MagicWand aria-hidden="true" />{t("projects.create")}</Link></div>
        </section>
        <div className="projects-notice"><Info aria-hidden="true" /><span>{t("projects.notice")}</span></div>
        <ProjectFilters categories={projectCategories} activeCategory={category} onCategoryChange={updateFilter(setCategory)} status={status} statuses={projectStatusOptions} onStatusChange={updateFilter(setStatus)} />
        {!loading && !loadError && <div className="projects-bulk-toolbar">
          <div className="projects-bulk-toolbar__copy"><strong aria-live="polite">{t("projects.bulkDelete.selected", { count: formatNumber(selectedProjectIds.size) })}</strong><span>{t("projects.bulkDelete.hint")}</span></div>
          <div className="projects-bulk-toolbar__actions">
            <button className="projects-mobile-select-all" type="button" aria-pressed={allCurrentPageDeletableSelected} aria-label={t(allCurrentPageDeletableSelected ? "projects.bulkDelete.clearAll" : "projects.bulkDelete.selectAll")} disabled={deleting || currentPageDeletableIds.length === 0} onClick={() => handleToggleAll(!allCurrentPageDeletableSelected)}><CheckSquare aria-hidden="true" />{t(allCurrentPageDeletableSelected ? "projects.bulkDelete.clearAll" : "projects.bulkDelete.selectAllShort")}</button>
            <button type="button" disabled={selectedProjectIds.size === 0 || deleting} onClick={() => setDeleteDialogOpen(true)}><Trash aria-hidden="true" />{t("projects.bulkDelete.button", { count: formatNumber(selectedProjectIds.size) })}</button>
          </div>
        </div>}
        {loadError && <p className="projects-load-error" role="alert">{loadErrorMessage}</p>}
        {loading ? <div className="projects-loading" role="status">{t("projects.messages.loading")}</div> : !loadError && <ProjectTable projects={filteredProjects} selectedProjectIds={selectedProjectIds} deleting={deleting} continuingProjectId={continuingProjectId} exportingProjectId={exportingProjectId} onAction={handleProjectAction} onSelectionChange={handleSelectionChange} onToggleAll={handleToggleAll} />}
        {!loading && !loadError && <ProjectPagination page={page} pages={pages} onPageChange={(nextPage) => { setSelectedProjectIds(new Set()); setDeleteDialogOpen(false); setPage(nextPage); showToast(t("projects.messages.pageChanged", { page: formatNumber(nextPage) })); }} />}
      </main>
    </div>
    <DashboardMobileNav items={dashboardNavItems} onUnavailable={showToast} />
    <ProjectDeletionDialog open={deleteDialogOpen} count={formatNumber(selectedProjectIds.size)} deleting={deleting} onCancel={() => setDeleteDialogOpen(false)} onConfirm={handleBulkDelete} />
    {toast.message && <DashboardToast key={toast.id} message={toast.message} onClose={() => setToast(({ id }) => ({ id, message: "" }))} />}
  </div>;
}

function productFilterForCategory(category) {
  return {
    narration: "short_drama_narration",
    translation: "video_translation",
  }[category] || category;
}

function toProjectRow(project) {
  const type = project.product === "video_translation" ? "translation" : "narration";
  const status = project.status === "completed" ? "complete" : project.status === "failed" ? "failed" : project.status === "draft" ? "draft" : "processing";
  const title = project.title.replace(/\.[^.]+$/, "");
  return {
    ...project,
    taskStatus: project.status,
    canDelete: isProjectDeletable(project),
    title,
    videoCount: Math.max(0, Number(project.video_count) || 0),
    type,
    typeKey: `projects.categories.${type}`,
    status,
    statusKey: `projects.status.${status}`,
    processingStageKey: type === "translation"
      ? `videoTranslation.steps.${translationStage(project.current_stage)}`
      : `narration.steps.${normalizeNarrationStage(project.current_stage)}`,
    duration: formatDuration(project.duration_seconds),
    image: project.thumbnail_url,
    createdAt: project.created_at,
    resultPath: status === "complete"
      ? (type === "translation" ? translationPath("export", project.id) : `/projects/${project.id}/result`)
      : undefined,
    progressPath: status === "processing"
      ? (type === "translation" ? translationPath(project.current_stage, project.id) : stagePath(project.current_stage, project.id))
      : undefined,
  };
}

function translationStage(stage) {
  return ({ created: "upload", settings: "settings", analysis: "translation", ai_translation: "translation", edit: "edit", generate: "render", render: "render", export: "export", completed: "export" }[stage] || "translation");
}

function translationPath(stage, projectId) {
  return `/dashboard/video-translation/${translationStage(stage)}?projectId=${encodeURIComponent(projectId)}`;
}

function formatDuration(totalSeconds) {
  const seconds = Math.max(0, Number(totalSeconds) || 0);
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainder = seconds % 60;
  return [hours, minutes, remainder].map((part) => String(part).padStart(2, "0")).join(":");
}
