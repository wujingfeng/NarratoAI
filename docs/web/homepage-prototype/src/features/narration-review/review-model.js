const MIN_SOURCE_DURATION = 0.1;
const INSERT_DURATION = 3;

const TRACK_ORDER = new Map([
  ["video", 0],
  ["script", 1],
  ["voice", 2],
  ["bgm", 3],
]);

let fallbackId = 0;

function finiteNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function makeId(prefix, idFactory) {
  if (idFactory) return `${prefix}-${idFactory()}`;
  if (globalThis.crypto?.randomUUID) return `${prefix}-${globalThis.crypto.randomUUID()}`;
  fallbackId += 1;
  return `${prefix}-${Date.now().toString(36)}-${fallbackId.toString(36)}`;
}

function sourceDuration(row) {
  return row.sourceEnd - row.sourceStart;
}

function orderedTrackClips(clips) {
  return [...clips].sort((left, right) => (
    (TRACK_ORDER.get(left.trackId) ?? 99) - (TRACK_ORDER.get(right.trackId) ?? 99)
  ));
}

export function formatTimecode(value) {
  const milliseconds = Math.max(0, Math.round(finiteNumber(value) * 1000));
  const hours = Math.floor(milliseconds / 3_600_000);
  const minutes = Math.floor((milliseconds % 3_600_000) / 60_000);
  const seconds = Math.floor((milliseconds % 60_000) / 1000);
  const fraction = milliseconds % 1000;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}.${String(fraction).padStart(3, "0")}`;
}

export function parseTimecode(value) {
  if (typeof value !== "string") return Number.NaN;
  const source = value.trim();
  if (!source) return Number.NaN;
  const parts = source.split(":");
  if (parts.length > 3 || parts.some((part) => !/^\d+(?:\.\d{1,3})?$/.test(part))) return Number.NaN;
  const numbers = parts.map(Number);
  if (parts.length > 1 && numbers.at(-1) >= 60) return Number.NaN;
  if (parts.length === 3 && numbers[1] >= 60) return Number.NaN;
  if (parts.length === 1) return numbers[0];
  if (parts.length === 2) return numbers[0] * 60 + numbers[1];
  return numbers[0] * 3600 + numbers[1] * 60 + numbers[2];
}

function normalizeAsset(asset = {}) {
  const duration = asset.durationSeconds ?? asset.duration_seconds;
  return {
    id: asset.id || "",
    filename: asset.filename || asset.name || asset.id || "",
    cdnUrl: asset.cdnUrl || asset.cdn_url || "",
    durationSeconds: Number.isFinite(Number(duration)) ? Number(duration) : null,
  };
}

export function collectReviewAssets(assets = [], rows = []) {
  const byId = new Map(assets.map(normalizeAsset).filter((asset) => asset.id).map((asset) => [asset.id, asset]));
  rows.forEach((row) => {
    if (!row.assetId || byId.has(row.assetId)) return;
    byId.set(row.assetId, {
      id: row.assetId,
      filename: row.assetId,
      cdnUrl: row.assetUrl || "",
      durationSeconds: null,
    });
  });
  return [...byId.values()];
}

/**
 * Builds a row-oriented editing model while retaining every original clip.
 * The model itself is UI-only; materializeReviewModel converts it back to the
 * shared editor draft shape used by both editing modes.
 */
export function createReviewModel(saved, { idFactory } = {}) {
  const originalClips = Array.isArray(saved?.clips) ? saved.clips.map((clip) => ({ ...clip })) : [];
  const videos = originalClips.filter((clip) => clip.trackId === "video").sort((a, b) => a.start - b.start);
  const scripts = originalClips.filter((clip) => clip.trackId === "script").sort((a, b) => a.start - b.start);
  const cues = Array.isArray(saved?.cues) ? saved.cues.map((cue) => ({ ...cue })) : [];
  const claimedScripts = new Set();
  const claimedCues = new Set();
  const normalizedClips = [...originalClips];

  const rows = videos.map((video, index) => {
    let script = scripts.find((item) => item.regionId && item.regionId === video.regionId && !claimedScripts.has(item.id));
    if (!script) script = scripts.find((item) => !claimedScripts.has(item.id) && Math.abs(item.start - video.start) < 0.02);
    if (!script) script = scripts.find((item) => !claimedScripts.has(item.id));
    if (script) claimedScripts.add(script.id);

    const regionId = video.regionId || script?.regionId || makeId("region", idFactory);
    let cueIndex = cues.findIndex((cue, candidateIndex) => (
      !claimedCues.has(candidateIndex) && cue.regionId && cue.regionId === regionId
    ));
    if (cueIndex < 0) cueIndex = cues.findIndex((cue, candidateIndex) => (
      !claimedCues.has(candidateIndex)
      && (typeof cue.regionId !== "string" || !cue.regionId)
      && Math.abs(finiteNumber(cue.start, Number.NaN) - video.start) < 0.02
    ));
    if (cueIndex < 0) cueIndex = cues.findIndex((cue, candidateIndex) => (
      !claimedCues.has(candidateIndex)
      && (typeof cue.regionId !== "string" || !cue.regionId)
    ));
    const cue = cueIndex >= 0 ? cues[cueIndex] : null;
    if (cueIndex >= 0) claimedCues.add(cueIndex);

    const videoIndex = normalizedClips.findIndex((clip) => clip.id === video.id);
    normalizedClips[videoIndex] = { ...video, regionId };

    if (script) {
      const scriptIndex = normalizedClips.findIndex((clip) => clip.id === script.id);
      script = {
        ...script,
        regionId,
        picture: typeof script.picture === "string" ? script.picture : "",
        originalSound: script.originalSound === true,
      };
      normalizedClips[scriptIndex] = script;
    } else {
      script = {
        id: makeId("script", idFactory),
        trackId: "script",
        start: video.start,
        duration: video.duration,
        text: "",
        picture: "",
        originalSound: false,
        regionId,
      };
      normalizedClips.push(script);
    }

    const start = Number.isFinite(video.sourceStart) ? video.sourceStart : 0;
    return {
      id: regionId,
      regionId,
      videoClipId: video.id,
      scriptClipId: script.id,
      assetId: video.assetId || "",
      assetUrl: video.assetUrl || "",
      sourceStart: start,
      sourceEnd: start + finiteNumber(video.duration),
      picture: script.picture,
      text: typeof script.text === "string" ? script.text : "",
      subtitleText: typeof cue?.text === "string" ? cue.text : (typeof script.text === "string" ? script.text : ""),
      originalSound: script.originalSound,
    };
  });

  return {
    rows,
    clips: normalizedClips,
    managedRegionIds: rows.map((row) => row.regionId),
    settings: { ...(saved?.settings || {}) },
  };
}

export function updateReviewRow(model, rowId, patch, assets = []) {
  const availableAssets = collectReviewAssets(assets, model.rows);
  return {
    ...model,
    rows: model.rows.map((row) => {
      if (row.id !== rowId) return row;
      const synchronizedSubtitle = Object.hasOwn(patch, "text") && row.subtitleText === row.text
        ? { subtitleText: patch.text }
        : {};
      if (Object.hasOwn(patch, "assetId") && patch.assetId !== row.assetId) {
        const asset = availableAssets.find((item) => item.id === patch.assetId);
        const maximum = asset?.durationSeconds;
        const duration = Number.isFinite(maximum)
          ? Math.max(MIN_SOURCE_DURATION, Math.min(Math.max(MIN_SOURCE_DURATION, sourceDuration(row)), maximum))
          : Math.max(MIN_SOURCE_DURATION, sourceDuration(row));
        return {
          ...row,
          ...patch,
          ...synchronizedSubtitle,
          assetUrl: asset?.cdnUrl || "",
          sourceStart: 0,
          sourceEnd: duration,
        };
      }
      return { ...row, ...patch, ...synchronizedSubtitle };
    }),
  };
}

export function moveReviewRow(model, rowId, direction) {
  const index = model.rows.findIndex((row) => row.id === rowId);
  const target = index + direction;
  if (index < 0 || target < 0 || target >= model.rows.length) return model;
  const rows = [...model.rows];
  [rows[index], rows[target]] = [rows[target], rows[index]];
  return { ...model, rows };
}

export function deleteReviewRow(model, rowId) {
  if (model.rows.length <= 1 || !model.rows.some((row) => row.id === rowId)) return model;
  return { ...model, rows: model.rows.filter((row) => row.id !== rowId) };
}

export function insertReviewRow(model, rowId, assets = [], { idFactory } = {}) {
  const index = model.rows.findIndex((row) => row.id === rowId);
  if (index < 0) return model;
  const current = model.rows[index];
  const availableAssets = collectReviewAssets(assets, model.rows);
  const asset = availableAssets.find((item) => item.id === current.assetId) || availableAssets[0] || null;
  const maximum = asset?.durationSeconds;
  const currentEnd = Math.max(0, current.sourceEnd);
  const canContinue = Number.isFinite(maximum) && maximum - currentEnd >= MIN_SOURCE_DURATION;
  const start = canContinue ? currentEnd : 0;
  const remaining = Number.isFinite(maximum) ? Math.max(0, maximum - start) : INSERT_DURATION;
  const duration = Math.max(MIN_SOURCE_DURATION, Math.min(INSERT_DURATION, remaining || MIN_SOURCE_DURATION));
  const regionId = makeId("region", idFactory);
  const videoClipId = makeId("video", idFactory);
  const scriptClipId = makeId("script", idFactory);
  const row = {
    id: regionId,
    regionId,
    videoClipId,
    scriptClipId,
    assetId: asset?.id || "",
    assetUrl: asset?.cdnUrl || "",
    sourceStart: start,
    sourceEnd: start + duration,
    picture: "",
    text: "",
    subtitleText: "",
    originalSound: false,
  };
  const rows = [...model.rows];
  rows.splice(index + 1, 0, row);
  return {
    ...model,
    rows,
    managedRegionIds: [...model.managedRegionIds, regionId],
    clips: [
      ...model.clips,
      {
        id: videoClipId,
        trackId: "video",
        start: 0,
        duration,
        sourceStart: start,
        assetId: row.assetId,
        assetUrl: row.assetUrl,
        regionId,
      },
      {
        id: scriptClipId,
        trackId: "script",
        start: 0,
        duration,
        text: "",
        picture: "",
        originalSound: false,
        regionId,
      },
    ],
  };
}

export function validateReviewModel(model, assets = []) {
  const availableAssets = collectReviewAssets(assets, model.rows);
  const assetById = new Map(availableAssets.map((asset) => [asset.id, asset]));
  const rowErrors = {};
  const seenRegions = new Set();
  let safeToSave = model.rows.length > 0;

  model.rows.forEach((row) => {
    const errors = {};
    const asset = assetById.get(row.assetId);
    if (!row.assetId || !row.assetUrl || !asset) {
      errors.asset = "missingAsset";
      safeToSave = false;
    }
    if (!Number.isFinite(row.sourceStart) || row.sourceStart < 0) {
      errors.sourceStart = "invalidStart";
      safeToSave = false;
    }
    if (!Number.isFinite(row.sourceEnd) || row.sourceEnd <= row.sourceStart) {
      errors.sourceEnd = "invalidEnd";
      safeToSave = false;
    } else if (Number.isFinite(asset?.durationSeconds) && row.sourceEnd > asset.durationSeconds + 0.02) {
      errors.sourceEnd = "outOfRange";
      safeToSave = false;
    }
    if (!row.text.trim()) errors.text = "emptyScript";
    if (seenRegions.has(row.regionId)) {
      errors.row = "duplicateRegion";
      safeToSave = false;
    }
    seenRegions.add(row.regionId);
    if (Object.keys(errors).length) rowErrors[row.id] = errors;
  });

  const errorCount = Object.values(rowErrors).reduce((count, errors) => count + Object.keys(errors).length, 0)
    + (model.rows.length ? 0 : 1);
  return {
    isValid: errorCount === 0,
    safeToSave,
    errorCount,
    rowErrors,
    generalError: model.rows.length ? null : "emptyRows",
  };
}

/** Synchronize every track back into the editor's clip/cue contract. */
export function materializeReviewModel(model) {
  const activeRegions = new Set(model.rows.map((row) => row.regionId));
  const managedRegions = new Set(model.managedRegionIds);
  const rowByRegion = new Map();
  let cursor = 0;
  model.rows.forEach((row) => {
    const duration = Math.max(MIN_SOURCE_DURATION, sourceDuration(row));
    rowByRegion.set(row.regionId, { ...row, start: cursor, duration });
    cursor += duration;
  });

  const retained = model.clips.filter((clip) => (
    !managedRegions.has(clip.regionId) || activeRegions.has(clip.regionId)
  ));
  const synchronized = retained.map((clip) => {
    if (clip.trackId === "bgm") return { ...clip, start: 0, duration: Math.max(MIN_SOURCE_DURATION, cursor) };
    const row = rowByRegion.get(clip.regionId);
    if (!row) return { ...clip };
    const shared = { ...clip, start: row.start, duration: row.duration, regionId: row.regionId };
    if (clip.id === row.videoClipId || clip.trackId === "video") {
      return {
        ...shared,
        sourceStart: row.sourceStart,
        assetId: row.assetId,
        assetUrl: row.assetUrl,
      };
    }
    if (clip.id === row.scriptClipId || clip.trackId === "script") {
      return {
        ...shared,
        text: row.text,
        picture: row.picture,
        originalSound: row.originalSound,
      };
    }
    return shared;
  });

  const clips = model.rows.flatMap((row) => orderedTrackClips(
    synchronized.filter((clip) => clip.regionId === row.regionId),
  ));
  clips.push(...synchronized.filter((clip) => !activeRegions.has(clip.regionId)));

  cursor = 0;
  const cues = model.rows.map((row) => {
    const duration = Math.max(MIN_SOURCE_DURATION, sourceDuration(row));
    const cue = {
      start: cursor,
      end: cursor + duration,
      text: typeof row.subtitleText === "string" ? row.subtitleText : row.text,
      regionId: row.regionId,
    };
    cursor += duration;
    return cue;
  });
  return { clips, cues, settings: model.settings, duration: cursor };
}
