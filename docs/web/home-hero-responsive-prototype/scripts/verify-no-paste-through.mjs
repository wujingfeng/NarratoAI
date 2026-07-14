import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(scriptDirectory, "..");
const sourceRoot = path.join(projectRoot, "src");
const publicRoot = path.join(projectRoot, "public");

const allowedPublicAssets = new Set([
  "assets/d01/sample-urban.png",
  "assets/d03/clip-1.png",
  "assets/d03/clip-2.png",
  "assets/d03/clip-3.png",
  "assets/d16/voice-avatar.png",
  "assets/documentary-thumb.png",
  "assets/hero-drama-vertical.png",
]);

const sourceExtensions = new Set([
  ".css",
  ".html",
  ".js",
  ".jsx",
  ".mjs",
  ".ts",
  ".tsx",
]);

const bannedPatterns = [
  { label: "reference artwork path", pattern: /b-style[\\/]01-home-hero/i },
  { label: "reference asset", pattern: /(?:^|[/'\"`_-])reference(?:[/'\"`_.-]|$)/im },
  { label: "baseline asset", pattern: /(?:^|[/'\"`_-])baseline(?:[/'\"`_.-]|$)/im },
  { label: "data image URI", pattern: /data\s*:\s*image/i },
  { label: "base64 payload", pattern: /base64/i },
  { label: "canvas element", pattern: /<\s*canvas\b/i },
  { label: "canvas API", pattern: /(?:getContext|toDataURL|drawImage)\s*\(/i },
  { label: "inline SVG", pattern: /<\s*svg\b/i },
  { label: "programmatic inline SVG", pattern: /createElement(?:NS)?\s*\([^)]*[\"']svg[\"']/i },
];

async function walk(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = [];

  for (const entry of entries) {
    const absolutePath = path.join(directory, entry.name);
    if (entry.isDirectory()) files.push(...await walk(absolutePath));
    if (entry.isFile()) files.push(absolutePath);
  }

  return files;
}

function lineNumberFor(content, index) {
  return content.slice(0, index).split("\n").length;
}

const failures = [];
const sourceFiles = (await walk(sourceRoot)).filter((file) => sourceExtensions.has(path.extname(file)));

for (const file of sourceFiles) {
  const content = await readFile(file, "utf8");
  const relativePath = path.relative(projectRoot, file);

  for (const { label, pattern } of bannedPatterns) {
    const match = content.match(pattern);
    if (match) failures.push(`${relativePath}:${lineNumberFor(content, match.index)} uses ${label}`);
  }

  if (path.extname(file) === ".css") {
    const urlMatch = content.match(/url\s*\(/i);
    if (urlMatch) {
      failures.push(`${relativePath}:${lineNumberFor(content, urlMatch.index)} uses a CSS url() image; content images must use real <img> elements`);
    }
  }

  const assetPattern = /["'`](\/assets\/[^"'`?#]+\.(?:avif|gif|jpe?g|png|webp))["'`]/gi;
  for (const match of content.matchAll(assetPattern)) {
    const assetPath = match[1].replace(/^\//, "");
    if (!allowedPublicAssets.has(assetPath)) {
      failures.push(`${relativePath}:${lineNumberFor(content, match.index)} references non-whitelisted image ${match[1]}`);
    }
  }
}

const publicFiles = (await walk(publicRoot))
  .map((file) => path.relative(publicRoot, file).split(path.sep).join("/"))
  .sort();

for (const file of publicFiles) {
  if (!allowedPublicAssets.has(file)) failures.push(`public/${file} is not in the seven-file content-image allowlist`);
}

for (const asset of allowedPublicAssets) {
  if (!publicFiles.includes(asset)) failures.push(`public/${asset} is missing from the seven-file content-image allowlist`);
}

if (failures.length > 0) {
  console.error("No-paste-through verification failed:\n");
  failures.forEach((failure) => console.error(`- ${failure}`));
  process.exitCode = 1;
} else {
  console.log(`No-paste-through verification passed: ${sourceFiles.length} source files scanned; seven public content images accounted for.`);
}
