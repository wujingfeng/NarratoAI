const MAX_ADJACENT_LINE_GAP = 0.028;
const MAX_SUBTITLE_BAND_HEIGHT = 0.12;

const verticalGap = (top, bottom, candidate) => Math.max(
  0,
  Math.max(top, candidate.y) - Math.min(bottom, candidate.y + candidate.height),
);

/**
 * 检测模型可能把双行字幕拆成两个文字连通域。以最佳候选为锚点，只合并
 * 与它相邻的字幕行；远处的画面文字、角标不能拉高字幕遮罩。
 */
export function mergeAdjacentSubtitleLines(candidates, anchor) {
  if (!anchor) return null;
  let top = anchor.y;
  let bottom = anchor.y + anchor.height;
  let changed = true;
  while (changed) {
    changed = false;
    for (const candidate of candidates) {
      const nextTop = Math.min(top, candidate.y);
      const nextBottom = Math.max(bottom, candidate.y + candidate.height);
      if (verticalGap(top, bottom, candidate) > MAX_ADJACENT_LINE_GAP
        || nextBottom - nextTop > MAX_SUBTITLE_BAND_HEIGHT
        || (candidate.y >= top && candidate.y + candidate.height <= bottom)) continue;
      top = nextTop;
      bottom = nextBottom;
      changed = true;
    }
  }
  return {
    ...anchor,
    y: Number(top.toFixed(6)),
    height: Number((bottom - top).toFixed(6)),
  };
}
