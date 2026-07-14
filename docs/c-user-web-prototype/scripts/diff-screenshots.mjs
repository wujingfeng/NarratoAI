import { createReadStream, createWriteStream, existsSync } from "node:fs";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import { PNG } from "pngjs";
import pixelmatch from "pixelmatch";
import { screens } from "./screens.mjs";

const baselineDir = resolve("public/baseline");
const actualDir = resolve("visual-qa/actual");
const diffDir = resolve("visual-qa/diff");
const threshold = Number(process.env.PIXEL_THRESHOLD ?? 0.12);
const only = process.env.SCREEN ? new Set(process.env.SCREEN.split(",").map((item) => item.trim())) : null;

await mkdir(diffDir, { recursive: true });

function readPng(path) {
  return new Promise((resolvePng, reject) => {
    createReadStream(path)
      .pipe(new PNG())
      .on("parsed", function parsed() {
        resolvePng(this);
      })
      .on("error", reject);
  });
}

function writePng(path, png) {
  return new Promise((resolveWrite, reject) => {
    png.pack().pipe(createWriteStream(path)).on("finish", resolveWrite).on("error", reject);
  });
}

const rows = [];
for (const screen of screens) {
  if (only && !only.has(screen.id)) continue;
  const baselinePath = resolve(baselineDir, `${screen.id}.png`);
  const actualPath = resolve(actualDir, `${screen.id}.png`);
  if (!existsSync(baselinePath) || !existsSync(actualPath)) {
    rows.push({ id: screen.id, status: "missing", diffPixels: null, ratio: null });
    continue;
  }
  const baseline = await readPng(baselinePath);
  const actual = await readPng(actualPath);
  if (baseline.width !== actual.width || baseline.height !== actual.height) {
    rows.push({
      id: screen.id,
      status: "size-mismatch",
      baseline: `${baseline.width}x${baseline.height}`,
      actual: `${actual.width}x${actual.height}`,
      diffPixels: null,
      ratio: null,
    });
    continue;
  }
  const diff = new PNG({ width: baseline.width, height: baseline.height });
  const diffPixels = pixelmatch(
    baseline.data,
    actual.data,
    diff.data,
    baseline.width,
    baseline.height,
    { threshold },
  );
  await writePng(resolve(diffDir, `${screen.id}.png`), diff);
  rows.push({
    id: screen.id,
    status: "ok",
    diffPixels,
    ratio: Number((diffPixels / (baseline.width * baseline.height)).toFixed(6)),
  });
}

console.table(rows);
const failed = rows.filter((row) => row.status !== "ok");
if (failed.length) process.exitCode = 1;
