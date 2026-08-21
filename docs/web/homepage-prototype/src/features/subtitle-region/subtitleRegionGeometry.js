const clamp = (value, minimum, maximum) => Math.min(maximum, Math.max(minimum, value));
const MIN_SUBTITLE_REGION_HEIGHT = 0.01;
const VERTICAL_TOLERANCE_RATIO = 0.08;

/**
 * 把检测器的文字候选框转为用户可编辑的字幕行区域。
 *
 * 在原检测框的上下各保留 8% 行高容错，覆盖文字描边、阴影及模型框选偏差。
 */
export function subtitleLineRegion(candidate) {
  const height = Math.max(MIN_SUBTITLE_REGION_HEIGHT, Number(candidate?.height) || 0);
  const tolerance = height * VERTICAL_TOLERANCE_RATIO;
  const top = clamp((Number(candidate?.y) || 0) - tolerance, 0, 1 - MIN_SUBTITLE_REGION_HEIGHT);
  const bottom = clamp((Number(candidate?.y) || 0) + height + tolerance, top + MIN_SUBTITLE_REGION_HEIGHT, 1);
  return {
    x: 0,
    y: Number(top.toFixed(6)),
    width: 1,
    height: Number((bottom - top).toFixed(6)),
  };
}
