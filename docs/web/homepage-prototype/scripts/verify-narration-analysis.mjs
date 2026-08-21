import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const files = {
  page: "src/pages/NarrationAnalysisPage.jsx",
  board: "src/components/narration/NarrationAnalysisBoard.jsx",
  player: "src/components/narration/NarrationFullscreenPlayer.jsx",
  stage: "src/features/projects/narrationStage.js",
  styles: "src/styles/narration-analysis.css",
};
const sources = Object.fromEntries(await Promise.all(Object.entries(files).map(async ([key, file]) => [key, await readFile(path.join(root, file), "utf8")])));

const combined = Object.values(sources).join("\n");
const forbidden = [
  /narrationAnalysisData/,
  /08:42/,
  /formatNumber\((?:3|6|12|18)\)/,
  /data:image/i,
  /base64/i,
  /background-image\s*:\s*url\s*\(/i,
  /<canvas\b/i,
];
if (forbidden.some((pattern) => pattern.test(combined))) throw new Error("分析链路仍包含静态样例或贴图数据");
if (!sources.stage.includes("videoAssets") || !sources.page.includes("snapshot?.videoAssets")) throw new Error("分析页必须读取阶段 API 的真实视频素材");
if (!sources.page.includes('id: "script_generation"')) throw new Error("分析进度必须包含真实脚本生成节点");
if (!sources.board.includes('<video className="analysis-thumb"') || !sources.player.includes("controls autoPlay")) throw new Error("素材预览与全屏播放必须使用真实 video 元素");
if (!sources.board.includes('metric(insights.characters)')) throw new Error("未知分析指标必须显示空值，不能硬编码样例数字");

console.log("verify-narration-analysis: passed");
