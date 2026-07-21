const MEDIA_ROOT = '/media/narration-editor';

export const EDITOR_MEDIA = {
  videos: [
    `${MEDIA_ROOT}/古墓迷宫震全球1.mp4`,
    `${MEDIA_ROOT}/古墓迷宫震全球2.mp4`,
    `${MEDIA_ROOT}/古墓迷宫震全球3.mp4`,
  ],
  posters: [
    `${MEDIA_ROOT}/episode-1-poster.jpg`,
    `${MEDIA_ROOT}/episode-2-poster.jpg`,
    `${MEDIA_ROOT}/episode-3-poster.jpg`,
  ],
  audio: `${MEDIA_ROOT}/0e5bf3db017e0e593c4eef4144d7c68a.mp3`,
  subtitles: `${MEDIA_ROOT}/古墓迷宫震全球3.srt`,
};

function toSeconds(timestamp) {
  const [hours, minutes, secondsAndMilliseconds] = timestamp.trim().split(':');
  const [seconds, milliseconds = '0'] = secondsAndMilliseconds.replace('.', ',').split(',');

  return (Number(hours) * 3600)
    + (Number(minutes) * 60)
    + Number(seconds)
    + (Number(milliseconds.padEnd(3, '0').slice(0, 3)) / 1000);
}

/**
 * Parses a standard SRT document into timeline-friendly cues.
 * Multi-line captions are normalized into a single readable line.
 */
export function parseSrt(text) {
  return [...text.matchAll(/(?:^|\n)\s*\d+\s*\n([\d:,.]+)\s*-->\s*([\d:,.]+)[^\n]*\n([\s\S]*?)(?=\n\s*\n|$)/g)]
    .map(([, start, end, body]) => ({
      start: toSeconds(start),
      end: toSeconds(end),
      text: body.trim().replace(/\n+/g, ' '),
    }))
    .filter((cue) => cue.text);
}

export const findCue = (cues, seconds) => cues.find(
  (cue) => cue.start <= seconds && seconds < cue.end,
) ?? null;

const SCRIPT_SEGMENTS = [
  '古墓入口的谜团，正从这片沙海中浮现。',
  '真实存在的精绝古城，藏着远超传说的秘密。',
  '这座地下王国的核心，正等待被重新发现。',
];

// Read from the approved local MP4 files with ffprobe: 180s, 180s, 90s.
export const VIDEO_DURATIONS = [180, 180, 90];

/** @type {Array<{id:string, trackId:'video'|'script'|'voice'|'bgm', start:number, duration:number, sourceStart?:number, assetId?:string, text?:string, regionId?:string}>} */
export const INITIAL_CLIPS = [
  ...EDITOR_MEDIA.videos.flatMap((assetId, index) => {
    const start = VIDEO_DURATIONS.slice(0, index).reduce((total, duration) => total + duration, 0);
    const duration = VIDEO_DURATIONS[index];
    const regionId = `segment-${index + 1}`;

    return [
      { id: `video-${index + 1}`, trackId: 'video', start, duration, sourceStart: 0, assetId, regionId },
      { id: `script-${index + 1}`, trackId: 'script', start, duration, text: SCRIPT_SEGMENTS[index], regionId },
      { id: `voice-${index + 1}`, trackId: 'voice', start, duration, sourceStart: start, assetId: EDITOR_MEDIA.audio, regionId },
    ];
  }),
  { id: 'bgm-1', trackId: 'bgm', start: 0, duration: 450, sourceStart: 0, assetId: EDITOR_MEDIA.audio, regionId: 'music-bed' },
];
