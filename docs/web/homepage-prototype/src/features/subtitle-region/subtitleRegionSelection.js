const REGION_KEYS = ["x", "y", "width", "height"];

function validRegion(value) {
  if (!value || typeof value !== "object") return null;
  const region = Object.fromEntries(REGION_KEYS.map((key) => [key, Number(value[key])]));
  if (!REGION_KEYS.every((key) => Number.isFinite(region[key]))) return null;
  if (region.x < 0 || region.y < 0 || region.width <= 0 || region.height <= 0) return null;
  if (region.x + region.width > 1 || region.y + region.height > 1) return null;
  return region;
}

/**
 * 上传页的检测结果仅暂存在 sessionStorage；设置页必须优先读取同一视频的
 * 结果，不能回退到通用默认框。已有服务端保存值（即用户上次提交的设置）
 * 仍有最高优先级。
 */
export function resolveSourceSubtitleRegion(savedRegion, layouts, assetId, fallback) {
  const detectedLayout = layouts?.[assetId];
  const detectedRegion = ["detected", "confirmed"].includes(detectedLayout?.status)
    ? validRegion(detectedLayout.region)
    : null;
  return validRegion(savedRegion)
    || detectedRegion
    || fallback;
}
