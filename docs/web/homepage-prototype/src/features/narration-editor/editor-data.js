export const findCue = (cues, seconds) => cues.find(
  (cue) => cue.start <= seconds && seconds < cue.end,
) ?? null;

const EDITOR_DRAFT_VERSION = 1;
const TRACK_IDS = new Set(['video', 'script', 'voice', 'bgm']);

function finiteNumber(value, fallback) {
  if (value === null || value === undefined || value === '') return fallback;
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function validClip(clip) {
  return clip && typeof clip.id === 'string' && TRACK_IDS.has(clip.trackId)
    && Number.isFinite(clip.start) && clip.start >= 0
    && Number.isFinite(clip.duration) && clip.duration > 0
    && (clip.trackId === 'script' || (typeof clip.assetId === 'string' && typeof clip.assetUrl === 'string'));
}

/** 将交互态收敛为可由服务端完整覆盖保存的草稿，不保存播放头、选区等瞬时 UI 状态。 */
export function createEditorDraft({ clips, cues, voiceRole, volume, rate, subtitleStyle, videoRatio, backgroundMusic }) {
  const settings = {
    voice_role: voiceRole,
    volume: Number(volume),
    rate: Number(rate),
    subtitle_style: subtitleStyle,
    video_ratio: videoRatio,
  };
  if (backgroundMusic?.assetId && backgroundMusic?.cdnUrl) {
    settings.background_music = {
      asset_id: backgroundMusic.assetId,
      cdn_url: backgroundMusic.cdnUrl,
      volume: Number(backgroundMusic.volume),
      ...(backgroundMusic.filename ? { filename: backgroundMusic.filename } : {}),
    };
  }
  return {
    version: EDITOR_DRAFT_VERSION,
    clips: clips.map(({ id, trackId, start, duration, sourceStart, assetId, assetUrl, text, regionId, picture, originalSound, eventId, visualAnchor, narrationAnchorText, matchConfidence, visualLead, narrationStartOffset }) => ({
      id, track_id: trackId, start, duration, ...(Number.isFinite(sourceStart) ? { source_start: sourceStart } : {}),
      ...(typeof assetId === 'string' ? { asset_id: assetId } : {}), ...(typeof assetUrl === 'string' ? { asset_url: assetUrl } : {}), ...(typeof text === 'string' ? { text } : {}),
      ...(typeof regionId === 'string' ? { region_id: regionId } : {}),
      ...(trackId === 'script' ? {
        picture: typeof picture === 'string' ? picture : '',
        original_sound: originalSound === true,
        ...(typeof narrationAnchorText === 'string' && narrationAnchorText && typeof text === 'string' && text.includes(narrationAnchorText) ? {
          ...(typeof eventId === 'string' && eventId ? { event_id: eventId } : {}),
          ...(Number.isFinite(visualAnchor) ? { visual_anchor: visualAnchor } : {}),
          narration_anchor_text: narrationAnchorText,
          ...(Number.isFinite(matchConfidence) ? { match_confidence: matchConfidence } : {}),
          ...(Number.isFinite(visualLead) ? { visual_lead: visualLead } : {}),
          ...(Number.isFinite(narrationStartOffset) ? { narration_start_offset: narrationStartOffset } : {}),
        } : {}),
      } : {}),
    })),
    subtitles: cues.map(({ start, end, text, regionId }) => ({
      start,
      end,
      text,
      ...(typeof regionId === 'string' ? { region_id: regionId } : {}),
    })),
    settings,
  };
}

/** 仅接受当前编辑器能够安全渲染的真实 API 字段；不提供本地演示数据回退。 */
export function readEditorDraft(content) {
  if (!content || typeof content !== 'object') return null;
  const clips = Array.isArray(content.clips) ? content.clips.map((clip) => ({
    id: clip.id, trackId: clip.track_id, start: Number(clip.start), duration: Number(clip.duration),
    sourceStart: Number.isFinite(Number(clip.source_start)) ? Number(clip.source_start) : undefined,
    assetId: clip.asset_id, assetUrl: clip.asset_url, text: clip.text, regionId: clip.region_id,
    ...(clip.track_id === 'script' ? {
      picture: typeof clip.picture === 'string' ? clip.picture : '',
      originalSound: clip.original_sound === true,
      ...(typeof clip.event_id === 'string' ? { eventId: clip.event_id } : {}),
      ...(Number.isFinite(Number(clip.visual_anchor)) ? { visualAnchor: Number(clip.visual_anchor) } : {}),
      ...(typeof clip.narration_anchor_text === 'string' ? { narrationAnchorText: clip.narration_anchor_text } : {}),
      ...(Number.isFinite(Number(clip.match_confidence)) ? { matchConfidence: Number(clip.match_confidence) } : {}),
      ...(Number.isFinite(Number(clip.visual_lead)) ? { visualLead: Number(clip.visual_lead) } : {}),
      ...(Number.isFinite(Number(clip.narration_start_offset)) ? { narrationStartOffset: Number(clip.narration_start_offset) } : {}),
    } : {}),
  })).filter(validClip) : [];
  if (!clips.length) return null;
  const cues = Array.isArray(content.subtitles) ? content.subtitles
    .map((cue) => ({
      start: Number(cue.start),
      end: Number(cue.end),
      text: cue.text,
      ...(typeof cue.region_id === 'string' ? { regionId: cue.region_id } : {}),
    }))
    .filter((cue) => Number.isFinite(cue.start) && Number.isFinite(cue.end) && cue.end > cue.start && typeof cue.text === 'string') : [];
  const settings = content.settings && typeof content.settings === 'object' ? content.settings : {};
  const rawBackgroundMusic = settings.background_music && typeof settings.background_music === 'object'
    ? settings.background_music
    : null;
  const backgroundMusic = rawBackgroundMusic
    && typeof rawBackgroundMusic.asset_id === 'string'
    && typeof rawBackgroundMusic.cdn_url === 'string'
    ? {
      assetId: rawBackgroundMusic.asset_id,
      cdnUrl: rawBackgroundMusic.cdn_url,
      filename: typeof rawBackgroundMusic.filename === 'string' ? rawBackgroundMusic.filename : '',
      volume: finiteNumber(rawBackgroundMusic.volume, 50),
    }
    : null;
  return {
    clips,
    cues,
    settings: {
      voiceRole: typeof settings.voice_role === 'string' ? settings.voice_role : '',
      volume: finiteNumber(settings.volume, 100),
      rate: finiteNumber(settings.rate, 1),
      subtitleStyle: typeof settings.subtitle_style === 'string' ? settings.subtitle_style : '',
      videoRatio: typeof settings.video_ratio === 'string' ? settings.video_ratio : '',
      backgroundMusic,
    },
  };
}
