import {
  ArrowsOutSimple,
  Pause,
  Play,
} from "@phosphor-icons/react";

export function VideoPreview({ playing, onToggle }) {
  return (
    <figure className={`video-preview ${playing ? "video-preview--playing" : ""}`}>
      <div className="video-stage">
        <img
          src="/assets/hero-drama-vertical.png"
          alt="都市短剧男女主角对视画面"
        />
        <span className="aspect-badge">9:16</span>
        <div className="video-overlay-copy" aria-hidden="true">
          <strong>命运的<br />反转</strong>
          <span>这一刻，他终于<br />发现自己爱上了她</span>
        </div>
      </div>
      <figcaption className="video-controls">
        <button
          className="video-center-control"
          type="button"
          aria-label={playing ? "暂停预览" : "播放预览"}
          onClick={onToggle}
        >
          {playing ? <Pause weight="fill" /> : <Play weight="fill" />}
        </button>
        <span className="playback-status">{playing ? "正在预览" : "00:12 / 00:30"}</span>
        <span className="video-progress" aria-hidden="true"><span /></span>
        <ArrowsOutSimple weight="bold" aria-hidden="true" />
      </figcaption>
    </figure>
  );
}
