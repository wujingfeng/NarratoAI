const DELETABLE_TERMINAL_STATUSES = new Set(["completed", "failed"]);
const NOT_STARTED_STAGES = new Set(["created", "settings"]);
const DELETION_STATUSES = new Set(["deleting", "deleted"]);

/**
 * 删除资格只取项目当前状态与阶段，不依赖后端额外投影字段。
 * 已完成/失败，或仍停留在创建/设置阶段的项目可删除；删除中/已删除始终排除。
 */
export function isProjectDeletable(project) {
  const status = String(project?.taskStatus ?? project?.status ?? "").toLowerCase();
  const stage = String(project?.current_stage ?? "").toLowerCase();
  if (DELETION_STATUSES.has(status)) return false;
  return DELETABLE_TERMINAL_STATUSES.has(status) || NOT_STARTED_STAGES.has(stage);
}

export function deletableProjectIds(projects) {
  return projects.filter((project) => project.canDelete ?? isProjectDeletable(project)).map((project) => project.id);
}

/** 当前页或项目状态变化后只保留仍在当前页且仍可删除的选择。 */
export function reconcileProjectSelection(selectedIds, projects) {
  const allowedIds = new Set(deletableProjectIds(projects));
  let changed = false;
  const next = new Set();
  for (const id of selectedIds) {
    if (allowedIds.has(id)) next.add(id);
    else changed = true;
  }
  return changed ? next : selectedIds;
}

export function toggleProjectSelection(selectedIds, projectId, checked) {
  const next = new Set(selectedIds);
  if (checked) next.add(projectId);
  else next.delete(projectId);
  return next;
}

export function toggleAllDeletableProjects(selectedIds, projects, checked) {
  const next = new Set(selectedIds);
  for (const id of deletableProjectIds(projects)) {
    if (checked) next.add(id);
    else next.delete(id);
  }
  return next;
}
