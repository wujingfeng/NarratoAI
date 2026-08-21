import * as ort from "onnxruntime-web/wasm";
import wasmUrl from "onnxruntime-web/ort-wasm-simd-threaded.wasm?url";
import wasmModuleUrl from "onnxruntime-web/ort-wasm-simd-threaded.mjs?url";
import { mergeAdjacentSubtitleLines } from "./subtitleRegionBand.js";
import { subtitleLineRegion } from "./subtitleRegionGeometry.js";

const MODEL_URL = "/models/ppocr-v6-tiny-det/inference.onnx";
let sessionPromise;
const debug = (...args) => console.info("[subtitle-detector:worker]", ...args);

function sigmoid(value) {
  return value >= 0 && value <= 1 ? value : 1 / (1 + Math.exp(-value));
}

function resizeDimensions(width, height, limit) {
  const scale = Math.min(1, limit / Math.max(width, height));
  return {
    width: Math.max(32, Math.ceil((width * scale) / 32) * 32),
    height: Math.max(32, Math.ceil((height * scale) / 32) * 32),
  };
}

function toTensor(frame, options) {
  const { width, height } = resizeDimensions(frame.width, frame.height, options.textDetLimitSideLen);
  const canvas = new OffscreenCanvas(width, height);
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (typeof ImageData !== "undefined" && frame instanceof ImageData) {
    const source = new OffscreenCanvas(frame.width, frame.height);
    source.getContext("2d").putImageData(frame, 0, 0);
    context.drawImage(source, 0, 0, width, height);
  } else context.drawImage(frame, 0, 0, width, height);
  const pixels = context.getImageData(0, 0, width, height).data;
  const plane = width * height;
  const input = new Float32Array(plane * 3);
  const mean = [0.485, 0.456, 0.406];
  const std = [0.229, 0.224, 0.225];
  for (let index = 0; index < plane; index += 1) {
    const pixel = index * 4;
    // inference.yml 指定 BGR；浏览器 canvas 是 RGBA。
    const bgr = [pixels[pixel + 2], pixels[pixel + 1], pixels[pixel]];
    for (let channel = 0; channel < 3; channel += 1) input[channel * plane + index] = ((bgr[channel] / 255) - mean[channel]) / std[channel];
  }
  return { tensor: new ort.Tensor("float32", input, [1, 3, height, width]), width, height };
}

function dilate(binary, width, height) {
  const result = new Uint8Array(binary.length);
  for (let y = 0; y < height; y += 1) for (let x = 0; x < width; x += 1) {
    const index = y * width + x;
    if (!binary[index]) continue;
    for (let dy = -1; dy <= 1; dy += 1) for (let dx = -1; dx <= 1; dx += 1) {
      const nextX = x + dx;
      const nextY = y + dy;
      if (nextX >= 0 && nextY >= 0 && nextX < width && nextY < height) result[nextY * width + nextX] = 1;
    }
  }
  return result;
}

function components(binary, probability, width, height) {
  const seen = new Uint8Array(binary.length);
  const found = [];
  for (let start = 0; start < binary.length; start += 1) {
    if (!binary[start] || seen[start]) continue;
    const queue = [start];
    seen[start] = 1;
    let cursor = 0;
    let minX = width; let maxX = 0; let minY = height; let maxY = 0; let count = 0; let score = 0;
    while (cursor < queue.length) {
      const index = queue[cursor++];
      const x = index % width;
      const y = Math.floor(index / width);
      minX = Math.min(minX, x); maxX = Math.max(maxX, x);
      minY = Math.min(minY, y); maxY = Math.max(maxY, y);
      count += 1; score += probability[index];
      for (let dy = -1; dy <= 1; dy += 1) for (let dx = -1; dx <= 1; dx += 1) {
        const nextX = x + dx; const nextY = y + dy;
        if (nextX < 0 || nextY < 0 || nextX >= width || nextY >= height) continue;
        const next = nextY * width + nextX;
        if (binary[next] && !seen[next]) { seen[next] = 1; queue.push(next); }
      }
    }
    found.push({ minX, maxX, minY, maxY, count, average: score / count });
  }
  return found;
}

function locateSubtitle(output, inputWidth, inputHeight, options) {
  const dims = output.dims;
  const mapHeight = dims[dims.length - 2];
  const mapWidth = dims[dims.length - 1];
  const probabilities = new Float32Array(mapWidth * mapHeight);
  for (let index = 0; index < probabilities.length; index += 1) probabilities[index] = sigmoid(output.data[index]);
  const binary = dilate(Uint8Array.from(probabilities, (value) => Number(value >= options.textDetThresh)), mapWidth, mapHeight);
  const candidates = components(binary, probabilities, mapWidth, mapHeight)
    .map((item) => {
      const x = item.minX / mapWidth;
      const y = item.minY / mapHeight;
      const width = (item.maxX - item.minX + 1) / mapWidth;
      const height = (item.maxY - item.minY + 1) / mapHeight;
      const area = width * inputWidth * height * inputHeight;
      const centerY = y + (height / 2);
      const score = item.average * (0.55 + (centerY * 0.45)) * Math.min(1, Math.sqrt(area) / 180);
      return { ...item, x, y, width, height, area, centerY, score };
    })
    // 原字幕统一限定在画面下半区；不依赖语言或文字内容，所有语种均按
    // 同一视觉文本检测规则处理，同时排除画面上半区的台标、横幅和场景文字。
    .filter((item) => item.area >= options.postFilterMinArea && item.average >= options.textDetBoxThresh && item.y >= 0.5);
  if (!candidates.length) return { candidateCount: 0, region: null, confidence: null };
  candidates.sort((left, right) => right.score - left.score);
  const best = candidates[0];
  const band = mergeAdjacentSubtitleLines(candidates, best);
  return {
    candidateCount: candidates.length,
    confidence: Math.min(0.99, best.score),
    region: subtitleLineRegion(band),
  };
}

async function getSession() {
  if (!sessionPromise) {
    ort.env.wasm.numThreads = 1;
    // Vite 会为 WASM 增加 hash；显式传入产物 URL，避免 runtime 退回请求
    // `/ort-wasm-simd-threaded.wasm`，从而拿到 SPA 的 index.html。
    // ORT 1.27 会先 dynamic import 对应的 .mjs，再由 .mjs 加载 .wasm。
    // 传字符串会被 ORT 当成「目录前缀」，把 `.wasm` 拼进 .mjs 路径而导致
    // `Failed to fetch dynamically imported module`；两个文件必须分别提供完整 URL。
    ort.env.wasm.wasmPaths = { wasm: wasmUrl, mjs: wasmModuleUrl };
    debug("加载 ONNX 模型", { modelUrl: MODEL_URL, wasmUrl, wasmModuleUrl });
    sessionPromise = ort.InferenceSession.create(MODEL_URL, { executionProviders: ["wasm"] })
      .then((session) => {
        debug("模型就绪", { inputNames: session.inputNames, outputNames: session.outputNames });
        return session;
      });
  }
  return sessionPromise;
}

self.onmessage = async ({ data }) => {
  const { id, frame, options } = data;
  try {
    const prepared = toTensor(frame, options);
    frame.close?.();
    const session = await getSession();
    const output = await session.run({ [session.inputNames[0]]: prepared.tensor });
    const outputTensor = output[session.outputNames[0]];
    const detected = locateSubtitle(outputTensor, prepared.width, prepared.height, options);
    debug("单帧推理完成", { id, input: [prepared.width, prepared.height], outputDims: outputTensor.dims, candidateCount: detected.candidateCount, confidence: detected.confidence, region: detected.region });
    self.postMessage({ id, result: detected.region ? { region: detected.region, confidence: detected.confidence } : null });
  } catch (error) {
    frame?.close?.();
    console.error("[subtitle-detector:worker] 单帧推理失败", { id, error });
    self.postMessage({ id, error: error instanceof Error ? error.message : "字幕检测失败" });
  }
};
