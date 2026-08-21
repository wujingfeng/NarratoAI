import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const root = new URL("../", import.meta.url);
const sources = new Map();
for (const relativePath of [
  "src/pages/ProjectResultPage.jsx",
  "src/pages/NarrationStagePage.jsx",
  "src/features/projects/projectApi.js",
  "src/styles/narration.css",
]) {
  sources.set(relativePath, await readFile(new URL(relativePath, root), "utf8"));
}

const combined = [...sources.values()].join("\n");
const forbidden = [
  ["已删除的原型结果数据", /projectResultData|ProjectResultDetails|ProjectResultPlayer/],
  ["固定完成状态", /status\s*:\s*["']completed["']/],
  ["固定示例项目", /霸总短剧解说\s*01|overlord/],
  ["固定示例时长", /08:42|01:25|85\s*seconds/i],
  ["固定消耗或日志", /project-result-(?:cost|log|steps)/],
  ["data image", /data:image/i],
  ["base64", /base64/i],
  ["canvas", /<canvas\b|CanvasRenderingContext2D|drawImage\s*\(/i],
  ["CSS url background", /background-image\s*:\s*url\s*\(/i],
  ["SVG bitmap", /<image\b|xlink:href\s*=|href\s*=\s*["']data:image/i],
];

for (const [label, pattern] of forbidden) {
  assert.doesNotMatch(combined, pattern, `result page must not contain ${label}`);
}

const wrapper = sources.get("src/pages/ProjectResultPage.jsx");
const page = sources.get("src/pages/NarrationStagePage.jsx");
const api = sources.get("src/features/projects/projectApi.js");

assert.match(wrapper, /<NarrationStagePage\s+stage="export"\s*\/>/, "history result route must reuse the real Artifact page");
assert.match(page, /getProjectStage\(projectId\)/, "result page must verify the current server stage");
assert.match(page, /getProjectResult\(projectId\)/, "result page must read the completion-gated result endpoint");
assert.match(page, /completed\.artifacts\?\.length/, "empty Artifact sets must be rejected");
assert.match(page, /find\(\(artifact\)\s*=>\s*artifact\.kind\s*===\s*"video"\)/, "video preview must come from a registered video Artifact");
assert.match(page, /<video[^>]+src=\{videoArtifact\.cdn_url\}/s, "preview must use the registered Artifact URL");
assert.match(page, /artifacts\.map\(\(artifact\)/, "download rows must be driven by registered Artifacts");
assert.match(page, /href=\{artifact\.cdn_url\}/, "downloads must use registered Artifact URLs");
assert.match(page, /exportJianyingZip\(manifest\)/, "Jianying export must use the server manifest");
assert.match(api, /request\(`\/projects\/\$\{projectId\}\/result`\)/, "result API must call the completion-gated endpoint");
assert.doesNotMatch(api, /status\s*:\s*["']completed["']/, "client must not invent completion");

console.log("verify-project-result: passed");
