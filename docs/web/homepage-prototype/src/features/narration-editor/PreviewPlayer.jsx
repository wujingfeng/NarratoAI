import { ArrowsOutSimple, CaretLeft, CaretRight, Pause, Play, SkipBack, SkipForward, SpeakerHigh } from "@phosphor-icons/react";
import { useEffect, useRef } from "react";
import { useI18n } from "../../i18n/useI18n.js";
import { EDITOR_MEDIA, findCue } from "./editor-data.js";
import { formatTime } from "./timeline-geometry.js";

export function PreviewPlayer({ state, dispatch, cues }) {
  const { t } = useI18n();
  const videoRef = useRef(null);
  const videoClip = state.clips.find((clip) => clip.trackId === "video" && state.playhead >= clip.start && state.playhead < clip.start + clip.duration) ?? state.clips.find((clip) => clip.trackId === "video");
  const sourceTime = videoClip ? videoClip.sourceStart + Math.max(0, state.playhead - videoClip.start) : 0;
  const cue = findCue(cues, state.playhead);
  const timelineDuration = Math.max(...state.clips.map((clip) => clip.start + clip.duration));
  useEffect(() => { if (videoRef.current && Math.abs(videoRef.current.currentTime - sourceTime) > .45) videoRef.current.currentTime = sourceTime; }, [sourceTime]);
  useEffect(() => { const video = videoRef.current; if (!video) return; if (state.isPlaying) video.play().catch(() => dispatch({ type: "playing", value: false })); else video.pause(); }, [state.isPlaying, dispatch]);
  const posterIndex = Math.max(0, Number(videoClip?.id?.split("-")[1] || 1) - 1);
  return <section className="editor-preview" aria-label={t("editor.preview.ariaLabel")}>
    <div className="editor-preview__stage">
      <video data-testid="preview-video" ref={videoRef} src={videoClip?.assetId || EDITOR_MEDIA.videos[0]} poster={EDITOR_MEDIA.posters[posterIndex]} preload="metadata" playsInline onPlay={() => dispatch({ type: "playing", value: true })} onPause={() => dispatch({ type: "playing", value: false })} onTimeUpdate={(event) => state.isPlaying && dispatch({ type: "seek", seconds: videoClip.start + event.currentTarget.currentTime - videoClip.sourceStart })} onEnded={() => dispatch({ type: "playing", value: false })} />
      <span className="preview-ratio">9:16</span><span className="preview-safe">{t("editor.preview.safeArea")}</span>
      <p data-testid="subtitle" className="preview-caption">{cue?.text || t("editor.content.defaultCaption")}</p>
    </div>
    <div className="editor-preview__scrub"><input aria-label={t("editor.preview.progress")} type="range" min="0" max={timelineDuration} step="0.1" value={Math.min(timelineDuration, state.playhead)} onChange={(event) => dispatch({ type: "seek", seconds: Number(event.target.value) })} /><span>{formatTime(state.playhead)} / {formatTime(timelineDuration)}</span></div>
    <div className="editor-preview__controls"><button type="button" aria-label={t("editor.preview.start")} onClick={() => dispatch({ type: "seek", seconds: 0 })}><SkipBack /></button><button type="button" aria-label={t("editor.preview.backOne")} onClick={() => dispatch({ type: "seek", seconds: Math.max(0, state.playhead - 1) })}><CaretLeft /></button><button className="preview-play" type="button" aria-label={state.isPlaying ? t("editor.preview.pause") : t("editor.preview.play")} onClick={() => dispatch({ type: "playing", value: !state.isPlaying })}>{state.isPlaying ? <Pause weight="fill" /> : <Play weight="fill" />}</button><button type="button" aria-label={t("editor.preview.forwardOne")} onClick={() => dispatch({ type: "seek", seconds: Math.min(timelineDuration, state.playhead + 1) })}><CaretRight /></button><button type="button" aria-label={t("editor.preview.end")} onClick={() => dispatch({ type: "seek", seconds: timelineDuration })}><SkipForward /></button><i /><button type="button" aria-label={t("editor.preview.volume")}><SpeakerHigh /></button><label><select aria-label={t("editor.preview.speed")} defaultValue="1"><option value=".75">0.75×</option><option value="1">1.0×</option><option value="1.25">1.25×</option></select></label><button type="button" aria-label={t("editor.preview.fullscreen")} onClick={() => videoRef.current?.requestFullscreen?.()}><ArrowsOutSimple /></button></div>
  </section>;
}
