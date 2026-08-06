import progressScenarios from "../fixtures/progressScenarios.json" with { type: "json" };

export type ProgressEvent = {
  jobId: string;
  stage: string;
  progress: number;
  timestamp: number;
};

type Listener = (e: ProgressEvent) => void;

const subscribers = new Map<string, Set<Listener>>();

function emit(jobId: string, event: ProgressEvent): void {
  const set = subscribers.get(jobId);
  if (!set) return;
  for (const listener of set) listener(event);
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(new Error("aborted"));
    const t = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(t);
      reject(new Error("aborted"));
    };
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

type JobKind = keyof typeof progressScenarios;

export const jobRunner = {
  async run<T = Record<string, unknown>>(
    jobId: string,
    kind: JobKind,
    _payload: unknown,
    onProgress?: (e: ProgressEvent) => void,
    options: { signal?: AbortSignal } = {},
  ): Promise<{ jobId: string } & T> {
    const scenario = progressScenarios[kind];
    if (!scenario) throw new Error(`Unknown job kind: ${kind}`);

    const fire = (e: ProgressEvent) => {
      emit(jobId, e);
      onProgress?.(e);
    };

    fire({ jobId, stage: "queued", progress: 0, timestamp: Date.now() });

    for (const step of scenario.stages) {
      await sleep(step.durationMs, options.signal);
      fire({ jobId, stage: step.stage, progress: step.progress, timestamp: Date.now() });
    }

    return { jobId } as { jobId: string } & T;
  },

  subscribe(jobId: string, listener: Listener): () => void {
    let set = subscribers.get(jobId);
    if (!set) {
      set = new Set();
      subscribers.set(jobId, set);
    }
    set.add(listener);
    return () => {
      set?.delete(listener);
      if (set && set.size === 0) subscribers.delete(jobId);
    };
  },
};
