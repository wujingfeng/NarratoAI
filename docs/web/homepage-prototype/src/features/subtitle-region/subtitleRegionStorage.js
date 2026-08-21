const keyFor = (projectId) => `narrato:subtitle-region-layouts:${projectId}`;

export function readCachedSubtitleLayouts(projectId) {
  if (!projectId) return {};
  try {
    const raw = window.sessionStorage.getItem(keyFor(projectId));
    const value = raw ? JSON.parse(raw) : {};
    return value && typeof value === "object" && !Array.isArray(value) ? value : {};
  } catch {
    return {};
  }
}

export function cacheSubtitleLayout(projectId, assetId, layout) {
  if (!projectId || !assetId || !layout) return;
  try {
    window.sessionStorage.setItem(keyFor(projectId), JSON.stringify({ ...readCachedSubtitleLayouts(projectId), [assetId]: layout }));
    window.dispatchEvent(new CustomEvent("subtitle-region-layout-updated", { detail: { projectId, assetId, layout } }));
  } catch {
    // 当前页面状态仍会在 start-analysis 时原子提交。
  }
}
