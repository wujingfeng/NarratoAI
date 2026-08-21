import SubtitleRegionWorker from "./subtitleRegionDetector.worker.js?worker";
import { selectMostReliableSubtitleDetection } from "./subtitleRegionConsensus.js";

export const SUBTITLE_REGION_DETECTION_DEFAULTS = Object.freeze({
  // 五个时段各抽两帧，最多检测十帧：覆盖片头、中段、片尾，并降低单帧
  // 画面文字被误判为原字幕的概率。
  maxFrames: 10,
  framesPerWindow: 2,
  windowRatios: [0.5, 0.25, 0.75, 0.1, 0.9],
  textDetThresh: 0.35,
  textDetBoxThresh: 0.5,
  textDetLimitSideLen: 960,
  postFilterMinArea: 250,
});

// 临时诊断开关：排查完毕后改为 false 或删除相关日志即可。
const DEBUG_SUBTITLE_DETECTOR = true;
const debug = (...args) => { if (DEBUG_SUBTITLE_DETECTOR) console.info("[subtitle-detector]", ...args); };
const debugError = (...args) => { if (DEBUG_SUBTITLE_DETECTOR) console.error("[subtitle-detector]", ...args); };

export class SubtitleDetectionAbortedError extends Error {
  constructor() {
    super("字幕位置探测已取消");
    this.name = "SubtitleDetectionAbortedError";
  }
}

const isAbort = (error) => error?.name === "AbortError" || error instanceof SubtitleDetectionAbortedError;
const clamp = (value, minimum, maximum) => Math.min(maximum, Math.max(minimum, value));

/**
 * 将少量抽帧分配到五个时段，而不是只看开头五秒。
 * 对于很短的视频，重复时间点会自动去重。
 */
export function planSubtitleDetectionSamples(durationSeconds, options = {}) {
  const { maxFrames, framesPerWindow, windowRatios } = { ...SUBTITLE_REGION_DETECTION_DEFAULTS, ...options };
  const duration = Number(durationSeconds);
  if (!Number.isFinite(duration) || duration <= 0) return [];
  const safeDuration = Math.max(duration, 0.12);
  const points = [];
  for (const ratio of windowRatios) {
    const center = clamp(safeDuration * ratio, 0.05, Math.max(0.05, safeDuration - 0.05));
    const spread = Math.min(0.72, safeDuration * 0.035);
    for (let index = 0; index < framesPerWindow; index += 1) {
      const offset = framesPerWindow === 1 ? 0 : ((index / (framesPerWindow - 1)) - 0.5) * spread * 2;
      points.push(clamp(center + offset, 0.05, Math.max(0.05, safeDuration - 0.05)));
    }
  }
  const unique = [];
  for (const point of points) {
    if (!unique.some((item) => Math.abs(item - point) < 0.08)) unique.push(point);
    if (unique.length >= maxFrames) break;
  }
  return unique;
}

function nextAnimationFrame() {
  return new Promise((resolve) => window.requestAnimationFrame(resolve));
}

function waitFor(video, event, signal) {
  return new Promise((resolve, reject) => {
    const done = () => {
      video.removeEventListener(event, success);
      video.removeEventListener("error", failure);
      signal?.removeEventListener("abort", aborted);
    };
    const success = () => { done(); resolve(); };
    const failure = () => { done(); reject(new Error("无法读取视频帧")); };
    const aborted = () => { done(); reject(new SubtitleDetectionAbortedError()); };
    video.addEventListener(event, success, { once: true });
    video.addEventListener("error", failure, { once: true });
    signal?.addEventListener("abort", aborted, { once: true });
  });
}

async function openVideo(file, signal) {
  if (signal?.aborted) throw new SubtitleDetectionAbortedError();
  const url = URL.createObjectURL(file);
  const video = document.createElement("video");
  video.muted = true;
  video.playsInline = true;
  video.preload = "auto";
  video.src = url;
  try {
    await waitFor(video, "loadedmetadata", signal);
    return { video, url };
  } catch (error) {
    URL.revokeObjectURL(url);
    throw error;
  }
}

async function captureVideoFrame(video, time, signal) {
  if (signal?.aborted) throw new SubtitleDetectionAbortedError();
  if (Math.abs(video.currentTime - time) > 0.025) {
    video.currentTime = time;
    await waitFor(video, "seeked", signal);
  }
  await nextAnimationFrame();
  if (signal?.aborted) throw new SubtitleDetectionAbortedError();
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const context = canvas.getContext("2d", { willReadFrequently: false });
  context.drawImage(video, 0, 0, canvas.width, canvas.height);
  if (typeof createImageBitmap === "function") return createImageBitmap(canvas);
  return context.getImageData(0, 0, canvas.width, canvas.height);
}

class DetectionWorkerPool {
  constructor({ concurrency, options }) {
    this.options = options;
    this.workers = Array.from({ length: concurrency }, () => ({ worker: new SubtitleRegionWorker(), busy: false }));
    this.pending = [];
    this.sequence = 0;
  }

  run(frame, signal) {
    if (signal?.aborted) {
      frame.close?.();
      return Promise.reject(new SubtitleDetectionAbortedError());
    }
    return new Promise((resolve, reject) => {
      const task = { id: `subtitle-det-${++this.sequence}`, frame, resolve, reject, signal, aborted: false };
      const abort = () => {
        task.aborted = true;
        task.frame?.close?.();
        reject(new SubtitleDetectionAbortedError());
      };
      task.abort = abort;
      signal?.addEventListener("abort", abort, { once: true });
      this.pending.push(task);
      this.dispatch();
    });
  }

  dispatch() {
    for (const slot of this.workers) {
      if (slot.busy) continue;
      const task = this.pending.shift();
      if (!task) return;
      if (task.aborted) continue;
      slot.busy = true;
      slot.task = task;
      const complete = (event) => {
        if (event.data?.id !== task.id) return;
        slot.worker.removeEventListener("message", complete);
        slot.worker.removeEventListener("error", failed);
        slot.busy = false;
        slot.task = null;
        task.signal?.removeEventListener("abort", task.abort);
        if (!task.aborted) {
          if (event.data.error) task.reject(new Error(event.data.error));
          else task.resolve(event.data.result);
        }
        this.dispatch();
      };
      const failed = () => {
        slot.worker.removeEventListener("message", complete);
        slot.worker.removeEventListener("error", failed);
        slot.busy = false;
        slot.task = null;
        task.signal?.removeEventListener("abort", task.abort);
        if (!task.aborted) task.reject(new Error("字幕检测模型加载失败"));
        this.dispatch();
      };
      slot.worker.addEventListener("message", complete);
      slot.worker.addEventListener("error", failed, { once: true });
      const transfer = typeof ImageBitmap !== "undefined" && task.frame instanceof ImageBitmap ? [task.frame] : [];
      slot.worker.postMessage({ id: task.id, frame: task.frame, options: this.options }, transfer);
      task.frame = null;
    }
  }

  terminate() {
    this.pending.forEach((task) => {
      task.frame?.close?.();
      task.reject(new SubtitleDetectionAbortedError());
    });
    this.pending = [];
    this.workers.forEach(({ worker }) => worker.terminate());
  }
}

/**
 * 可复用的前端字幕位置定位器。仅输出归一化位置，不运行文字识别模型。
 */
export function createSubtitleRegionDetector(options = {}) {
  const config = { ...SUBTITLE_REGION_DETECTION_DEFAULTS, ...options };
  // WASM worker 固定两个并发槽，避免多视频同时检测时拖慢主线程或抢占浏览器资源。
  const concurrency = 2;
  const pool = new DetectionWorkerPool({ concurrency, options: config });

  return {
    async detect(file, { signal, onProgress } = {}) {
      const { video, url } = await openVideo(file, signal);
      try {
        const samples = planSubtitleDetectionSamples(video.duration, config);
        debug("开始", { file: file.name, size: file.size, duration: video.duration, sourceWidth: video.videoWidth, sourceHeight: video.videoHeight, samples, config });
        if (!samples.length || !video.videoWidth || !video.videoHeight) return { status: "not_found", samplesChecked: 0 };
        const detectedSamples = [];
        for (let index = 0; index < samples.length; index += 1) {
          if (signal?.aborted) throw new SubtitleDetectionAbortedError();
          debug("抽帧", { file: file.name, index: index + 1, total: samples.length, timeSeconds: samples[index] });
          onProgress?.({ current: index + 1, total: samples.length, timeSeconds: samples[index] });
          const frame = await captureVideoFrame(video, samples[index], signal);
          const result = await pool.run(frame, signal);
          if (result?.region) {
            const detected = {
              status: "detected",
              region: result.region,
              confidence: result.confidence,
              timeSeconds: samples[index],
              samplesChecked: index + 1,
              sourceWidth: video.videoWidth,
              sourceHeight: video.videoHeight,
            };
            detectedSamples.push(detected);
            // 单帧高置信文字也可能是台标、横幅或画面内标语。完成全部计划
            // 抽帧后再选最佳结果，确保常规视频实际完成最多十次检测。
            debug("定位到候选，继续后续抽帧比对", { file: file.name, ...detected });
          }
        }
        const mostReliable = selectMostReliableSubtitleDetection(detectedSamples);
        if (mostReliable) {
          debug("候选已全部比对，采用出现次数最多的位置", { file: file.name, ...mostReliable });
          return { ...mostReliable, samplesChecked: samples.length };
        }
        const notFound = { status: "not_found", samplesChecked: samples.length, sourceWidth: video.videoWidth, sourceHeight: video.videoHeight };
        debug("全部抽帧完成，未发现候选字幕", { file: file.name, ...notFound });
        return notFound;
      } catch (error) {
        if (isAbort(error)) throw new SubtitleDetectionAbortedError();
        debugError("运行失败", { file: file.name, error });
        throw error;
      } finally {
        video.removeAttribute("src");
        video.load();
        URL.revokeObjectURL(url);
      }
    },
    dispose: () => pool.terminate(),
  };
}

let sharedDetector;
export function getSubtitleRegionDetector() {
  sharedDetector ||= createSubtitleRegionDetector();
  return sharedDetector;
}
