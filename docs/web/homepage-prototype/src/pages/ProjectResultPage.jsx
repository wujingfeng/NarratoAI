import { NarrationStagePage } from "./NarrationStagePage.jsx";

/** 历史项目入口与自动模式完成页共用同一真实 Artifact 读取链路。 */
export function ProjectResultPage() {
  return <NarrationStagePage stage="export" />;
}
