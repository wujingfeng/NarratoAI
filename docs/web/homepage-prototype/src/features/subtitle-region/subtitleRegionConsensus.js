const median = (values) => {
  const sorted = [...values].sort((left, right) => left - right);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? (sorted[middle - 1] + sorted[middle]) / 2
    : sorted[middle];
};

function sameSubtitlePosition(left, right) {
  const leftCenter = left.y + (left.height / 2);
  const rightCenter = right.y + (right.height / 2);
  const centerDistance = Math.abs(leftCenter - rightCenter);
  const verticalOverlap = Math.max(
    0,
    Math.min(left.y + left.height, right.y + right.height) - Math.max(left.y, right.y),
  );
  const overlapRatio = verticalOverlap / Math.min(left.height, right.height);
  // 同一字幕带可能在单行/双行之间变化，允许小幅位置偏移；但不能把
  // 画面下半区中相距较远的横幅、台标并入同一组。
  return overlapRatio >= 0.4 || centerDistance <= Math.max(0.035, (left.height + right.height) * 0.7);
}

function representativeRegion(detections) {
  return {
    x: Number(median(detections.map(({ region }) => region.x)).toFixed(6)),
    y: Number(median(detections.map(({ region }) => region.y)).toFixed(6)),
    width: Number(median(detections.map(({ region }) => region.width)).toFixed(6)),
    height: Number(median(detections.map(({ region }) => region.height)).toFixed(6)),
  };
}

/**
 * 以字幕区域的位置稳定性为主、平均单帧置信度为辅选出最终结果。
 * 每个检测帧仅向一个位置簇计数，因此出现次数表示有多少帧观察到了该区域。
 */
export function selectMostReliableSubtitleDetection(detections) {
  const clusters = [];
  for (const detection of detections) {
    if (!detection?.region) continue;
    const cluster = clusters.find((item) => sameSubtitlePosition(detection.region, item.region));
    if (cluster) {
      cluster.detections.push(detection);
      cluster.region = representativeRegion(cluster.detections);
    } else {
      clusters.push({ region: detection.region, detections: [detection] });
    }
  }
  if (!clusters.length) return null;

  const ranked = clusters.map((cluster) => ({
    ...cluster,
    occurrenceCount: cluster.detections.length,
    averageConfidence: cluster.detections.reduce((total, item) => total + (Number(item.confidence) || 0), 0) / cluster.detections.length,
  })).sort((left, right) => (
    right.occurrenceCount - left.occurrenceCount
    || right.averageConfidence - left.averageConfidence
    || right.region.y - left.region.y
  ));
  const winner = ranked[0];
  const bestFrame = [...winner.detections].sort((left, right) => (Number(right.confidence) || 0) - (Number(left.confidence) || 0))[0];

  return {
    ...bestFrame,
    region: winner.region,
    confidence: Number(winner.averageConfidence.toFixed(6)),
    occurrenceCount: winner.occurrenceCount,
    candidateClusters: ranked.length,
  };
}
