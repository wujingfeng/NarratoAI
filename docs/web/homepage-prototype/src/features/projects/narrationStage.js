export const NARRATION_STAGES = [
  { id: "create", label: "创建任务", path: "/create" },
  { id: "settings", label: "参数设置", path: "/dashboard/narration/settings" },
  { id: "analysis", label: "AI 分析", path: "/dashboard/narration/analysis" },
  // 进入编辑阶段时，先展示表格审核页；时间轴编辑器仅由审核页的显式操作进入。
  { id: "edit", label: "编辑片段", path: "/dashboard/narration/review" },
  { id: "render", label: "生成视频", path: "/dashboard/narration/generate" },
  { id: "export", label: "导出完成", path: "/dashboard/narration/export" },
];

const LEGACY_STAGE_ALIASES = {
  created: "create", create_task: "create", parameter_settings: "settings", parameters: "settings",
  ai_analysis: "analysis", editing: "edit", editor: "edit", generate_video: "render",
  generate: "render", generated: "export", completed: "export",
};

export function normalizeNarrationStage(value) {
  const stage = String(value || "create").toLowerCase();
  return NARRATION_STAGES.some((item) => item.id === stage) ? stage : (LEGACY_STAGE_ALIASES[stage] || "create");
}

export function stageIndex(stage) {
  return NARRATION_STAGES.findIndex((item) => item.id === normalizeNarrationStage(stage));
}

export function stagePath(stage, projectId) {
  const item = NARRATION_STAGES.find((candidate) => candidate.id === normalizeNarrationStage(stage)) || NARRATION_STAGES[0];
  return projectId ? `${item.path}?projectId=${encodeURIComponent(projectId)}` : item.path;
}

/** Accept both the concise and detailed forms returned by the Business API. */
export function normalizeStageSnapshot(payload = {}) {
  const source = payload.stage || payload;
  const currentStage = normalizeNarrationStage(source.current_stage || source.currentStage || source.stage);
  const rawAnalysisTasks = source.analysis_tasks || source.analysisTasks || [];
  const rawVideoAssets = source.video_assets || source.videoAssets || [];
  const analysisTasks = rawAnalysisTasks.map((task) => ({
    ...task,
    id: task.id || task.key || task.type || task.name,
    name: task.name || "",
    state: task.state || task.status || "not_started",
    updatedAt: task.updated_at || task.updatedAt || null,
    errorCode: task.error_code || task.errorCode || null,
  }));
  const videoAssets = rawVideoAssets.map((asset) => {
    const rawDuration = asset.duration_seconds ?? asset.durationSeconds;
    return {
      ...asset,
      id: asset.id,
      filename: asset.filename || asset.name || asset.id,
      cdnUrl: asset.cdn_url || asset.cdnUrl || "",
      durationSeconds: rawDuration !== null && rawDuration !== undefined && Number.isFinite(Number(rawDuration))
        ? Number(rawDuration)
        : null,
      subtitleAssetId: asset.subtitle_asset_id || asset.subtitleAssetId || null,
      subtitleFilename: asset.subtitle_filename || asset.subtitleFilename || null,
    };
  });
  return {
    currentStage,
    projectId: source.project_id || source.projectId || null,
    projectTitle: source.project_title || source.projectTitle || source.project_id || source.projectId || "",
    projectStatus: source.project_status || source.projectStatus || null,
    executionMode: source.execution_mode === "auto" || source.executionMode === "auto" ? "auto" : "manual",
    workflowState: source.workflow_state || source.workflowState || null,
    failureCode: source.failure_code || source.failureCode || null,
    updatedAt: source.updated_at || source.updatedAt || null,
    workflowId: source.workflow_id || source.workflowId || null,
    analysisTasks,
    videoAssets,
    stages: source.stages || [],
  };
}

export function isStageLocked(currentStage, viewedStage) {
  return stageIndex(currentStage) > stageIndex(viewedStage);
}
