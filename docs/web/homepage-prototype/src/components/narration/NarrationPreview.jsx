import { Check, EyeSlash, HandPalm, Pause, Play } from "@phosphor-icons/react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useI18n } from "../../i18n/useI18n.js";

function formatDuration(totalSeconds) {
  const seconds = Math.max(0, Math.round(Number(totalSeconds) || 0));
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
const DEFAULT_REGION = { x: 0, y: 0.78, width: 1, height: 0.12 };
const DEFAULT_NARRATION_FONT_SCALE = 0.9;
const MIN_SOURCE_REGION_HEIGHT = 0.01;

function normalizeRegion(region) {
  const height = clamp(Number(region?.height) || DEFAULT_REGION.height, MIN_SOURCE_REGION_HEIGHT, 1);
  const width = clamp(Number(region?.width) || DEFAULT_REGION.width, 0.04, 1);
  return {
    x: clamp(Number(region?.x) || 0, 0, 1 - width),
    y: clamp(Number(region?.y) || 0, 0, 1 - height),
    width,
    height,
  };
}

function isLetterboxed(contentRect, frameRef) {
  const frameWidth = frameRef.current?.getBoundingClientRect().width || 0;
  return Boolean(contentRect && frameWidth && contentRect.width < frameWidth - 1);
}

function useVideoContentRect(frameRef, videoRef, selectionKey) {
  const [rect, setRect] = useState(null);
  const update = useCallback(() => {
    const frame = frameRef.current;
    const video = videoRef.current;
    if (!frame || !video?.videoWidth || !video?.videoHeight) return setRect(null);
    const bounds = frame.getBoundingClientRect();
    const scale = Math.min(bounds.width / video.videoWidth, bounds.height / video.videoHeight);
    const width = video.videoWidth * scale;
    const height = video.videoHeight * scale;
    setRect({ left: (bounds.width - width) / 2, top: (bounds.height - height) / 2, width, height });
  }, [frameRef, videoRef]);

  useLayoutEffect(() => {
    const frame = frameRef.current;
    if (!frame) {
      setRect(null);
      return undefined;
    }
    const observer = new ResizeObserver(update);
    observer.observe(frame);
    update();
    return () => observer.disconnect();
  }, [frameRef, selectionKey, update]);
  return [rect, update];
}

function draggablePointer(event, contentRect, callback) {
  event.preventDefault();
  event.currentTarget.setPointerCapture?.(event.pointerId);
  const startY = event.clientY;
  const onMove = (moveEvent) => callback(clamp((moveEvent.clientY - startY) / contentRect.height, -1, 1));
  const finish = () => {
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", finish);
    window.removeEventListener("pointercancel", finish);
  };
  window.addEventListener("pointermove", onMove);
  window.addEventListener("pointerup", finish, { once: true });
  window.addEventListener("pointercancel", finish, { once: true });
}

function subtitleStyleClass(subtitleStyle, subtitleStyles) {
  const index = subtitleStyles?.findIndex((item) => item.id === subtitleStyle) ?? -1;
  return ["is-glow", "is-classic", "is-blue-outline"][index] || "is-glow";
}

function useHorizontalDragScroll() {
  const railRef = useRef(null);
  const dragRef = useRef({ active: false, moved: false, startX: 0, startScrollLeft: 0 });

  const onPointerDown = (event) => {
    const rail = railRef.current;
    if (!rail || event.button !== 0) return;
    dragRef.current = { active: true, moved: false, startX: event.clientX, startScrollLeft: rail.scrollLeft };
  };
  const onPointerMove = (event) => {
    const rail = railRef.current;
    const drag = dragRef.current;
    if (!rail || !drag.active) return;
    const distance = event.clientX - drag.startX;
    if (Math.abs(distance) > 4) {
      if (!drag.moved) rail.setPointerCapture?.(event.pointerId);
      drag.moved = true;
      rail.scrollLeft = drag.startScrollLeft - distance;
    }
  };
  const finishDrag = () => { dragRef.current.active = false; };
  const wasDragged = () => dragRef.current.moved;
  return { railRef, onPointerDown, onPointerMove, onPointerUp: finishDrag, onPointerCancel: finishDrag, wasDragged };
}

export function NarrationPreview({
  ratio,
  estimate,
  videos = [],
  selectedVideoId,
  onSelectedVideoChange,
  sourceSubtitleLayout,
  onSourceRegionChange,
  onConfirmSourceSubtitle,
  onNoSourceSubtitle,
  narrationSubtitlePosition,
  onNarrationSubtitlePositionChange,
  subtitleStyle,
  subtitleStyles,
  disabled = false,
}) {
  const { formatNumber, t } = useI18n();
  const frameRef = useRef(null);
  const videoRef = useRef(null);
  const video = videos.find((item) => item.id === selectedVideoId) || videos[0] || null;
  const selectedVideoIndex = video ? Math.max(0, videos.findIndex((item) => item.id === video.id)) : -1;
  const [contentRect, updateContentRect] = useVideoContentRect(frameRef, videoRef, video?.id);
  const [isPlaying, setIsPlaying] = useState(false);
  const videoRail = useHorizontalDragScroll();
  const previewAspectRatio = ratio?.replace(":", " / ");
  const region = normalizeRegion(sourceSubtitleLayout?.region || DEFAULT_REGION);
  const sourceIsConfirmed = sourceSubtitleLayout?.status === "confirmed";
  const sourceHasNoSubtitle = sourceSubtitleLayout?.status === "none";
  const narrationY = narrationSubtitlePosition?.y ?? 0.82;
  const narrationFontScale = narrationSubtitlePosition?.font_scale ?? DEFAULT_NARRATION_FONT_SCALE;
  // 与 Core 的 _caption_geometry 保持同一安全带：字幕以有效视频内容区为坐标系，
  // 拖拽不得把中心点移到服务端最终会因字幕带越界而二次钳制的位置。
  const captionBandRatio = contentRect?.height
    ? Math.max(0.35, 0.225 * (contentRect.width / contentRect.height) * narrationFontScale)
    : 0.35;
  const captionVerticalPadding = captionBandRatio / 2;
  const captionYBounds = {
    min: clamp(captionVerticalPadding, 0.04, 0.45),
    max: clamp(1 - captionVerticalPadding, 0.55, 0.96),
  };
  const safeNarrationY = clamp(narrationY, captionYBounds.min, captionYBounds.max);
  const moveSource = (delta) => onSourceRegionChange?.({ ...region, y: clamp(region.y + delta, 0, 1 - region.height) });
  const resizeSource = (edge, delta) => {
    const minimumHeight = MIN_SOURCE_REGION_HEIGHT;
    if (edge === "top") {
      const nextY = clamp(region.y + delta, 0, region.y + region.height - minimumHeight);
      onSourceRegionChange?.({ ...region, y: nextY, height: region.height + region.y - nextY });
    } else onSourceRegionChange?.({ ...region, height: clamp(region.height + delta, minimumHeight, 1 - region.y) });
  };
  const moveNarration = (delta) => onNarrationSubtitlePositionChange?.({
    ...narrationSubtitlePosition,
    y: clamp(safeNarrationY + delta, captionYBounds.min, captionYBounds.max),
  });
  const changeFontScale = (fontScale) => onNarrationSubtitlePositionChange?.({ ...narrationSubtitlePosition, font_scale: fontScale });
  const togglePlayback = () => {
    const player = videoRef.current;
    if (!player) return;
    if (player.paused) player.play().catch(() => {});
    else player.pause();
  };
  const selectVideo = (itemId) => {
    if (disabled || itemId === video?.id) return;
    videoRef.current?.pause();
    onSelectedVideoChange?.(itemId);
  };

  useEffect(() => {
    setIsPlaying(false);
    updateContentRect();
  }, [video?.id, updateContentRect]);

  return <aside className="narration-preview" aria-labelledby="preview-title">
    <div className="narration-preview__heading">
      <div><h2 id="preview-title">字幕与遮罩设置</h2><p>在上方调整当前视频，使用下方列表切换片段。</p></div>
    </div>
    <div className="narration-preview__selected-wrap">
      <div
        ref={frameRef}
        className={`narration-preview__selected-stage ${isLetterboxed(contentRect, frameRef) ? "is-letterboxed" : ""}`}
        style={previewAspectRatio ? { aspectRatio: previewAspectRatio } : undefined}
      >
        {video?.cdnUrl ? <video
          ref={videoRef}
          src={video.cdnUrl}
          playsInline
          preload="metadata"
          aria-label={`${video.filename} ${t("narration.preview.sceneLabel")}`}
          onLoadedMetadata={updateContentRect}
          onPlay={() => setIsPlaying(true)}
          onPause={() => setIsPlaying(false)}
          onEnded={() => setIsPlaying(false)}
        /> : <p>{t("narration.preview.sourceUnavailable")}</p>}
        {video && <span className="narration-preview__selected-label" aria-hidden="true">当前片段 · {selectedVideoIndex + 1} / {videos.length}</span>}
        {video && contentRect && <div
          className="narration-preview__content-layer"
          style={{ left: contentRect.left, top: contentRect.top, width: contentRect.width, height: contentRect.height }}
          aria-label={isLetterboxed(contentRect, frameRef) ? "源视频有效内容区，字幕仅在此区域内生成" : undefined}
        >
          {isLetterboxed(contentRect, frameRef) && <span className="narration-preview__content-boundary" aria-hidden="true">有效内容区</span>}
          {!sourceHasNoSubtitle && <button
            className={`narration-source-mask ${sourceIsConfirmed ? "is-confirmed" : ""}`}
            type="button"
            disabled={disabled}
            style={{ left: `${region.x * 100}%`, top: `${region.y * 100}%`, width: `${region.width * 100}%`, height: `${region.height * 100}%` }}
            onPointerDown={(event) => draggablePointer(event, contentRect, moveSource)}
            aria-label="拖动原字幕遮罩位置"
          ><span className="narration-source-mask__resize narration-source-mask__resize--top" onPointerDown={(event) => { event.stopPropagation(); draggablePointer(event, contentRect, (delta) => resizeSource("top", delta)); }} aria-hidden="true" /><HandPalm aria-hidden="true" /><span>{sourceIsConfirmed ? "原字幕区 · 已确认" : "原字幕遮罩"}</span><span className="narration-source-mask__resize narration-source-mask__resize--bottom" onPointerDown={(event) => { event.stopPropagation(); draggablePointer(event, contentRect, (delta) => resizeSource("bottom", delta)); }} aria-hidden="true" /></button>}
          <button
            className={`narration-preview__caption ${subtitleStyleClass(subtitleStyle, subtitleStyles)}`}
            type="button"
            disabled={disabled}
            style={{ top: `${safeNarrationY * 100}%`, "--narration-font-scale": narrationFontScale }}
            onPointerDown={(event) => draggablePointer(event, contentRect, moveNarration)}
            aria-label="拖动当前解说字幕位置"
          >这是一句解说字幕示例</button>
        </div>}
      </div>
    </div>
    <div className="narration-preview__video-rail-wrap">
      <div className="narration-preview__video-rail-head"><strong>视频片段</strong><span>{video ? `已选片段 ${selectedVideoIndex + 1}` : "暂无视频"}</span></div>
      {videos.length ? <div
        ref={videoRail.railRef}
        className="narration-preview__video-rail"
        role="list"
        aria-label="选择要设置字幕位置的视频"
        onPointerDown={videoRail.onPointerDown}
        onPointerMove={videoRail.onPointerMove}
        onPointerUp={videoRail.onPointerUp}
        onPointerCancel={videoRail.onPointerCancel}
      >
        {videos.map((item, index) => {
          const selected = item.id === video?.id;
          return <article
            key={item.id}
            className={`narration-preview__video-card ${selected ? "is-selected" : ""}`}
            role="listitem"
            aria-current={selected ? "true" : undefined}
            aria-disabled={disabled || undefined}
            onClick={(event) => {
              if (event.target.closest("button") || videoRail.wasDragged()) return;
              selectVideo(item.id);
            }}
          >
            <span className="narration-preview__video-thumbnail">
              {item.cdnUrl ? <video
                src={item.cdnUrl}
                muted
                playsInline
                preload="metadata"
                aria-hidden="true"
              /> : <i aria-hidden="true" />}
              {selected && <span className="narration-preview__video-selected-badge" aria-hidden="true"><Check weight="bold" />已选</span>}
            </span>
            <button
              className="narration-preview__video-card-meta"
              type="button"
              aria-pressed={selected}
              disabled={disabled}
              onClick={(event) => { if (event.detail === 0 || !videoRail.wasDragged()) selectVideo(item.id); }}
            ><b>片段 {index + 1}</b><small>{item.filename || "未命名视频"}</small></button>
          </article>;
        })}
      </div> : <p className="narration-preview__video-empty">{t("narration.preview.sourceUnavailable")}</p>}
      <p className="narration-preview__video-rail-hint">选择下方片段，上方画面会同步切换；视频较多时可左右拖动列表。</p>
    </div>
    <div className="narration-preview__subtitle-controls" id="narration-source-subtitle-controls">
      <div>
        <strong>原视频字幕</strong>
        <small>{sourceHasNoSubtitle ? "已标记为无字幕，不会添加原字幕模糊。" : sourceIsConfirmed ? "遮罩位置已确认。" : sourceSubtitleLayout?.status === "detected" ? "已自动定位，请检查后确认或调整。" : sourceSubtitleLayout?.status === "detecting" ? "正在进行本地字幕位置识别，请稍候。" : sourceSubtitleLayout?.status === "failed" ? "自动识别运行失败，请手动调整或选择无字幕。" : "尚未定位，请手动调整或选择无字幕。"}</small>
      </div>
      <button className={sourceIsConfirmed ? "is-active" : ""} type="button" aria-pressed={sourceIsConfirmed} onClick={onConfirmSourceSubtitle} disabled={disabled}><Check weight="bold" aria-hidden="true" />确认位置</button>
      <button className={`is-secondary ${sourceHasNoSubtitle ? "is-active" : ""}`} type="button" aria-pressed={sourceHasNoSubtitle} onClick={onNoSourceSubtitle} disabled={disabled}><EyeSlash aria-hidden="true" />无字幕</button>
    </div>
    <div className="narration-preview__caption-controls">
      <button type="button" onClick={togglePlayback} disabled={!video?.cdnUrl}>{isPlaying ? <Pause aria-hidden="true" /> : <Play aria-hidden="true" />}{isPlaying ? "暂停所选视频" : "播放所选视频"}</button>
      <label><span>解说字幕字体大小</span><input type="range" min="0.7" max="1.5" step="0.05" value={narrationFontScale} onChange={(event) => changeFontScale(Number(event.target.value))} disabled={disabled} /><output>{Math.round(narrationFontScale * 100)}%</output></label>
    </div>
    <div className="narration-preview__stats">
      <div><span>{t("narration.preview.source")}</span><strong>{estimate ? formatDuration(estimate.total_seconds) : "—"}</strong></div><div><span>{t("narration.preview.estimatedOutput")}</span><strong>{estimate ? formatDuration(estimate.estimated_output_seconds) : "—"}</strong></div><div><span>{t("narration.preview.estimatedCost")}</span><strong>{estimate ? t("narration.preview.credits", { count: formatNumber(estimate.credits) }) : "—"}</strong></div>
    </div>
  </aside>;
}
