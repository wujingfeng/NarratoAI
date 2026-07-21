import { ArrowsOut, Pause, Play, SpeakerHigh, SpeakerSlash } from "@phosphor-icons/react";
import { forwardRef } from "react";
import { useI18n } from "../../i18n/useI18n.js";

function formatTime(value) {
  if (!Number.isFinite(value)) return "00:00";
  const minutes = Math.floor(value / 60);
  const seconds = Math.floor(value % 60);
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

export const ProjectResultPlayer = forwardRef(function ProjectResultPlayer({
  project,
  isPlaying,
  isMuted,
  currentTime,
  duration,
  onTogglePlay,
  onToggleMute,
  onSeek,
  onTimeUpdate,
  onLoadedMetadata,
  onPlayStateChange,
  onFullscreen,
}, ref) {
  const { t } = useI18n();
  const progress = duration > 0 ? Math.min(100, Math.max(0, (currentTime / duration) * 100)) : 0;
  return (
    <div className="project-result-player">
      <video
        ref={ref}
        src={project.video}
        poster={project.poster}
        preload="metadata"
        playsInline
        muted={isMuted}
        onTimeUpdate={onTimeUpdate}
        onLoadedMetadata={onLoadedMetadata}
        onPlay={() => onPlayStateChange(true)}
        onPause={() => onPlayStateChange(false)}
        onEnded={() => onPlayStateChange(false)}
        aria-label={t("projectResult.player.video", { title: project.title })}
      />
      <div className="project-result-player__controls">
        <button type="button" onClick={onTogglePlay} aria-label={t(isPlaying ? "projectResult.player.pause" : "projectResult.player.play")}>
          {isPlaying ? <Pause weight="fill" aria-hidden="true" /> : <Play weight="fill" aria-hidden="true" />}
        </button>
        <span className="project-result-player__time">{formatTime(currentTime)} <i>/</i> {duration ? formatTime(duration) : project.duration}</span>
        <label className="project-result-player__progress">
          <span className="sr-only">{t("projectResult.player.progress")}</span>
          <input type="range" min="0" max="100" step="0.1" value={progress} onChange={onSeek} style={{ "--progress": `${progress}%` }} />
        </label>
        <button type="button" onClick={onToggleMute} aria-label={t(isMuted ? "projectResult.player.unmute" : "projectResult.player.mute")}>
          {isMuted ? <SpeakerSlash aria-hidden="true" /> : <SpeakerHigh aria-hidden="true" />}
        </button>
        <button type="button" onClick={onFullscreen} aria-label={t("projectResult.player.fullscreen")}><ArrowsOut aria-hidden="true" /></button>
      </div>
    </div>
  );
});
