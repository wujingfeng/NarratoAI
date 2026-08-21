import { CaretLeft, CaretRight, X } from "@phosphor-icons/react";
import { useEffect } from "react";
import { useI18n } from "../../i18n/useI18n.js";

export function NarrationFullscreenPlayer({ videos, activeIndex, onChange, onClose }) {
  const { formatNumber, t } = useI18n();
  const video = videos[activeIndex];
  useEffect(() => {
    const closeOnEscape = (event) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);
  if (!video) return null;
  return <div className="analysis-player" role="dialog" aria-modal="true" aria-label={t("analysis.player.dialog", { episode: video.label })}>
    <button className="analysis-player__close" type="button" onClick={onClose} aria-label={t("analysis.player.close")}><X weight="bold" /></button>
    <button className="analysis-player__switch analysis-player__switch--prev" type="button" onClick={() => onChange((activeIndex - 1 + videos.length) % videos.length)} aria-label={t("analysis.player.previous")}><CaretLeft weight="bold" /></button>
    <div className="analysis-player__screen">
      <video key={video.id} src={video.url} controls autoPlay playsInline preload="metadata" aria-label={video.label} />
      <span className="analysis-player__episode">{video.label}</span>
    </div>
    <button className="analysis-player__switch analysis-player__switch--next" type="button" onClick={() => onChange((activeIndex + 1) % videos.length)} aria-label={t("analysis.player.next")}><CaretRight weight="bold" /></button>
    <p className="analysis-player__hint">{t("analysis.player.hint", { current: formatNumber(activeIndex + 1), total: formatNumber(videos.length) })}</p>
  </div>;
}
