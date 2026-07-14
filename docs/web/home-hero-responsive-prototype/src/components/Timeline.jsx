import {
  Eye,
  MusicNotes,
  SpeakerHigh,
  TextAa,
} from "@phosphor-icons/react";

const thumbnails = [
  "/assets/d03/clip-1.png",
  "/assets/d03/clip-2.png",
  "/assets/d03/clip-3.png",
  "/assets/d03/clip-1.png",
  "/assets/d03/clip-2.png",
  "/assets/d03/clip-3.png",
  "/assets/d03/clip-1.png",
];

const waveformSeed = [18, 40, 26, 52, 33, 62, 22, 46, 30, 57, 24, 48, 20, 42, 31, 58, 35, 49, 27, 61, 36, 54, 25, 43, 20, 50, 29, 56, 33, 44, 24, 38];
const waveformPhases = [0, 5, -3];
const waveformHeights = Array.from({ length: 96 }, (_, index) => {
  const phase = waveformPhases[Math.floor(index / waveformSeed.length)];
  return Math.max(12, Math.min(68, waveformSeed[index % waveformSeed.length] + phase));
});

function WaveformTrack({ tone }) {
  return (
    <span className={`waveform waveform--${tone}`} aria-hidden="true">
      {waveformHeights.map((height, index) => (
        <i style={{ height: `${height}%` }} key={`${tone}-${index}`} />
      ))}
    </span>
  );
}

export function Timeline() {
  return (
    <section className="timeline" aria-label="视频编辑时间线">
      <div className="timeline-ruler" aria-hidden="true">
        <span>00:00</span><span>00:05</span><span>00:10</span><span>00:15</span><span>00:20</span><span>00:25</span><span>00:30</span>
      </div>

      <div className="timeline-row timeline-row--video">
        <span className="track-label"><Eye weight="duotone" />视频片段</span>
        <span className="thumbnail-track">
          {thumbnails.map((source, index) => (
            <img src={source} alt="" key={`${source}-${index}`} />
          ))}
        </span>
      </div>

      <div className="timeline-row timeline-row--copy">
        <span className="track-label"><TextAa weight="duotone" />解说文案</span>
        <span className="copy-track" aria-hidden="true">
          <i>这场相遇...</i><i>他本想只是应付...</i><i>却在她的眼里...</i><i>身份反转！</i><i>真相揭开</i><i>命运的反转</i>
        </span>
      </div>

      <div className="timeline-row timeline-row--voice">
        <span className="track-label"><SpeakerHigh weight="duotone" />配音音频</span>
        <WaveformTrack tone="cyan" />
      </div>

      <div className="timeline-row timeline-row--music">
        <span className="track-label"><MusicNotes weight="duotone" />背景音乐</span>
        <WaveformTrack tone="orange" />
      </div>

      <span className="playhead" aria-hidden="true"><i /></span>
    </section>
  );
}
