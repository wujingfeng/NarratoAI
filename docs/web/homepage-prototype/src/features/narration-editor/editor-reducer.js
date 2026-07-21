const MIN_DURATION = 0.5;

function sortedTrackClips(clips, trackId, excludedId) {
  return clips.filter((clip) => clip.trackId === trackId && clip.id !== excludedId).sort((a, b) => a.start - b.start);
}

function safeStart(clips, clip, intendedStart) {
  const neighbours = sortedTrackClips(clips, clip.trackId, clip.id);
  const snapped = Math.round(Math.max(0, intendedStart) * 10) / 10;
  const previous = neighbours.filter((item) => item.start + item.duration <= snapped + 0.01).at(-1);
  const next = neighbours.find((item) => item.start >= snapped);
  const minimum = previous ? previous.start + previous.duration : 0;
  const maximum = next ? next.start - clip.duration : Number.POSITIVE_INFINITY;
  return Math.max(minimum, Math.min(snapped, maximum));
}

function replaceClip(state, id, transform) {
  return state.map((clip) => clip.id === id ? transform(clip) : clip);
}

export function createEditorState(clips) {
  const timelineDuration = Math.max(...clips.map((clip) => clip.start + clip.duration));
  const usableWidth = Math.max(320, (typeof window === "undefined" ? 1440 : window.innerWidth) * .85 - 125);
  const minimumZoom = Math.max(1, Math.floor((usableWidth / timelineDuration) * 10) / 10);
  return { clips, activeClipIds: ["video-1"], playhead: 0, isPlaying: false, pixelsPerSecond: minimumZoom, rulerZoom: minimumZoom, minimumZoom, voiceRole: "沉稳男声·顾言", volume: 90, rate: 1.05, toast: "" };
}

export function editorReducer(state, action) {
  switch (action.type) {
    case "seek": return { ...state, playhead: Math.max(0, action.seconds) };
    case "playing": return { ...state, isPlaying: action.value };
    case "select": return { ...state, activeClipIds: action.append ? [...new Set([...state.activeClipIds, ...action.ids])] : action.ids };
    case "setZoom": {
      const rulerZoom = Math.max(state.minimumZoom, Math.min(100, action.value));
      return { ...state, rulerZoom, pixelsPerSecond: rulerZoom };
    }
    case "toast": return { ...state, toast: action.message };
    case "setSetting": return { ...state, [action.key]: action.value };
    case "moveClip": {
      const clip = state.clips.find((item) => item.id === action.id);
      if (!clip) return state;
      return { ...state, clips: replaceClip(state.clips, action.id, (item) => ({ ...item, start: safeStart(state.clips, item, action.start) })) };
    }
    case "trimClip": {
      const clip = state.clips.find((item) => item.id === action.id);
      if (!clip) return state;
      const end = clip.start + clip.duration;
      const nextStart = action.edge === "start" ? Math.min(end - MIN_DURATION, Math.max(0, action.seconds)) : clip.start;
      const nextDuration = action.edge === "start" ? end - nextStart : Math.max(MIN_DURATION, action.seconds - clip.start);
      return { ...state, clips: replaceClip(state.clips, action.id, (item) => ({ ...item, start: nextStart, duration: nextDuration })) };
    }
    case "setText": return { ...state, clips: replaceClip(state.clips, action.id, (clip) => ({ ...clip, text: action.text })) };
    default: return state;
  }
}
